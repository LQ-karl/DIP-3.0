"""
DIP按病种分值分组测算工具 - 本地目录库生成模块
核心功能：根据医院上传的医保清单数据 + 国家目录库 → 生成本地目录库
"""
import pandas as pd
from typing import List, Dict, Tuple, Optional
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from collections import defaultdict
from types import SimpleNamespace
import json
import re
import os

from ..models.models import DiseaseGroup, GroupType, MedicalRecord, CalculationMethod
from ..core.grouping_engine import DIPGroupingEngine
from ..core.value_calculator import ValueCalculator
from ..utils.data_loader import DataLoader
from ..core.auxiliary_directory import (
    CCICalculator, DiseaseSeverityClassifier, AgeFeatureClassifier, ICUStayClassifier
)
from ..utils.paths import get_data_dir, get_output_dir
from ..core.national_directory_v30 import (
    NationalDirectoryV30, NationalMatch, ZongheMatch, CaseOps, get_national_engine,
)


class LocalDirectoryGenerator:
    """本地目录库生成器"""

    # 核心病种四层成组顺序（DIP3.0 规范）：本地目录库测算严格按此顺序成组与输出
    #   先期分组(①) → 并项规则(②) → 诊断辅助细分(③) → 基本规则(④)
    # 综合病种为第二阶段，单列于最后。
    LAYER_ORDER = {
        "先期分组": 0,
        "并项规则": 1,
        "诊断辅助细分": 2,
        "基本规则": 3,
        "综合病种": 4,
    }

    # 基层病种：「基层医疗机构」默认范围（一级及以下）
    #   规范原文（第三章第四节）：设置基层病种是引导三级医疗机构功能归位，发挥二级
    #   医疗机构枢纽作用；遴选条件之一为「基层医疗机构病例占比较大」。
    #   此处「基层医疗机构」口径经用户 2026-09-04 确认 = 一级及以下。
    #   2026-09-05 用户裁决：等级写法不统一（如「一级甲等」），改为「前缀匹配+扩展」：
    #     - 前缀匹配：以 DEFAULT_GRASSROOT_PREFIXES 中任一项开头的等级均计入
    #       （一级 / 一级甲等 / 一级乙等 / 一级丙等 …）
    #     - 机构名精确匹配：社区卫生服务中心 / 社区卫生服务站 / 乡镇卫生院
    #   目的：避免数据把一级医院写成「一级甲等」时分子漏计、占比被系统性低估。
    DEFAULT_GRASSROOT_LEVELS = ("社区卫生服务中心", "社区卫生服务站", "乡镇卫生院")
    DEFAULT_GRASSROOT_PREFIXES = ("一级",)

    @staticmethod
    def _layer_sort_key(g) -> Tuple[int, int, str]:
        """本地目录库输出的四层排序键：先期→并项→诊断辅助细分→基本规则→综合病种；
        同层内按病例数降序、病种代码升序，保证结果稳定可读。"""
        layer = getattr(g, "grouping_layer", "")
        order = LocalDirectoryGenerator.LAYER_ORDER.get(layer, 9)
        return (order, -getattr(g, "case_count", 0), getattr(g, "disease_code", ""))

    # 监护病房住院天数（重症）判断补充规则
    # ─────────────────────────────────────────────────────────────────────
    # 国家 DIP3.0 规范未明确「监护病房住院天数」如何分型，故补充两种业务判定方式，
    # 由 self.icu_days_rule 切换（后期据需求再确定使用哪种）：
    #   判断1 'charge_item'：结算含 重症监护/层流洁净 床位费收费项目 → 监护病房住院天数 = 特级护理天数
    #   判断2 'ward_type'  ：重症监护病房类型 非空                       → 监护病房住院天数 = 特级护理天数
    # 两种判断均以「特级护理天数(spga_nurscare_days)」作为监护病房住院天数；与既有
    # icu_days(如 icu_dura/ICU天数) 取大值，不丢失任何显式提供的监护天数。
    ICU_BED_FEE_CODES = {
        "011105000060000",  # 床位费(重症监护)
        "011105000070000",  # 床位费(层流洁净)
    }
    ICU_DAYS_RULE_OPTIONS = ("charge_item", "ward_type")

    def __init__(
        self,
        threshold: int = 15,
        data_dir: str = None,
        lower_quantile: float = 0.025,
        upper_quantile: float = 0.975,
        min_trim_group_size: int = 25,
        max_overall_trim_rate: float = 0.08,
        exclude_below_threshold: bool = False,
        icu_days_rule: str = "charge_item",
        enable_grassroot: bool = True,
        grassroot_min_basic_ratio: float = 0.5,
        grassroot_max_cv: float = 0.7,
        grassroot_hospital_levels: Optional[List[str]] = None,
        grassroot_level_prefixes: Optional[List[str]] = None,
    ):
        """
        初始化本地目录库生成器

        Args:
            threshold: 核心病种临界值（病例数阈值）
            data_dir: 字典/目录库数据目录
            lower_quantile: 极端病例裁剪下分位数（默认 0.025，即 2.5%）
            upper_quantile: 极端病例裁剪上分位数（默认 0.975，即 97.5%）
            min_trim_group_size: 触发裁剪的最小组内病例数；小于该值的组不做裁剪，
                以避免小样本组内单条记录占比过大导致过度裁剪（保证整体裁剪率可控）
            max_overall_trim_rate: 整体裁剪率上限（默认 0.08，即最高 8%），超出则告警
            icu_days_rule: 监护病房住院天数(重症)判定方式，取值见 ICU_DAYS_RULE_OPTIONS；
                'charge_item'(默认，判断1)=凭重症监护/层流洁净床位费收费项目；
                'ward_type'(判断2)=凭重症监护病房类型非空。两者均以特级护理天数为天数。
            enable_grassroot: 是否启用基层病种本地遴选（《技术规范》第三章第四节）
            grassroot_min_basic_ratio: 基层医疗机构病例占比下限（规范"占比较大"，地方自定）
            grassroot_max_cv: 基层病种组内变异系数上限（规范示例：CV 值不超过 0.7）
            grassroot_hospital_levels: 「基层医疗机构」等级范围，默认一级及以下
            grassroot_level_prefixes: 等级前缀匹配规则（默认「一级」→ 一级/一级甲等/一级乙等…）
        """
        self.threshold = threshold
        self.data_dir = data_dir if data_dir else str(get_data_dir())
        self.lower_quantile = lower_quantile
        self.upper_quantile = upper_quantile
        self.min_trim_group_size = min_trim_group_size
        self.max_overall_trim_rate = max_overall_trim_rate
        # 综合病种质量控制：聚类后仍低于地方临界值的组是否剔除（规范为"可予以剔除"，
        # 默认关闭以保留对低频病例的覆盖；如需收紧可置 True）
        self.exclude_below_threshold = exclude_below_threshold
        # 监护病房住院天数(重症)判定方式（判断1/判断2 切换；国家未明确分型，业务补充）
        self.icu_days_rule = icu_days_rule if icu_days_rule in self.ICU_DAYS_RULE_OPTIONS else "charge_item"

        self.grouping_engine = DIPGroupingEngine(threshold=threshold)
        self.value_calculator = ValueCalculator()
        self.data_loader = DataLoader(data_dir)

        # CCI 与疾病严重程度（中重度分型）字典（权威数据源，规范逻辑测算）
        self.severity_entries: List[Dict] = []   # 中重度分型字典条目
        self._load_dictionaries()

        # ICD-10 医保2.0 版 类目名称映射（综合病种命名权威来源）
        self._icd10_category_map: Dict[str, str] = {}
        self._load_icd10_category_map()

        # 手术操作类别映射（综合病种四子组所需）
        # 国临版手术码 -> 类别（手术/治疗性操作/诊断性操作/介入治疗）
        self._clinical_op_category: Dict[str, str] = {}
        # 医保版手术码 -> 国临版手术码（桥接，用于把清单里的医保码查到类别）
        self._insurance_to_clinical: Dict[str, str] = {}
        self._load_op_category_maps()

        # 综合病种质量控制：组内变异系数(CV)上限，超过则标记剔除
        self.max_cv_threshold: float = 1.0

        # ---- 基层病种（《DIP3.0 技术规范（征求意见稿）》第三章第四节）----
        # 基层病种是「核心病种中的一个类别」，由地方在本地数据中遴选：
        #   候选池：《分组方案》基层病种 sheet 名录（诊断+手术对；手术空=仅内科诊疗组）
        #   校验项：① 属核心病种 ② 基层医疗机构病例占比 ≥ 阈值 ③ 组内 CV ≤ 阈值
        # 口径经用户 2026-09-04 确认：基层机构=一级及以下、占比≥50%、CV≤0.7。
        self.enable_grassroot = enable_grassroot
        self.grassroot_min_basic_ratio = float(grassroot_min_basic_ratio)
        self.grassroot_max_cv = float(grassroot_max_cv)
        self.grassroot_levels = set(
            grassroot_hospital_levels
            if grassroot_hospital_levels
            else self.DEFAULT_GRASSROOT_LEVELS
        )
        self.grassroot_level_prefixes = tuple(
            grassroot_level_prefixes
            if grassroot_level_prefixes
            else self.DEFAULT_GRASSROOT_PREFIXES
        )
        # 遴选过程留痕（导出《基层病种遴选依据表》）
        self.grassroot_report: List[Dict] = []

        # 综合病种被质控剔除的病例数（统计报告用）
        self.excluded_cases: int = 0

        # 存储结果
        self.raw_groups = {}  # 原始聚类结果
        self.core_groups = []  # 核心病种
        self.mixed_groups = []  # 综合病种
        self.national_directory = None  # 国家目录库

        # ---- DIP 3.0 版国家目录引擎（以《按病种分值（DIP）付费3.0版分组方案》为准） ----
        # 四层成组统一走 XQ/BX/FZ/JC 分段查表；加载失败则回退到内置种子规则（向后兼容）。
        self._nat_engine: Optional[NationalDirectoryV30] = None
        # seq(方案序号) -> NationalMatch：成组时登记，供 _build_group 回填国家目录元数据
        self._nat_seq_meta: Dict[str, NationalMatch] = {}
        # 综合病种编码 -> ZongheMatch：未入核心病种者按官方综合病种字典兜底成组（2026-09-14）
        self._zh_meta: Dict[str, "ZongheMatch"] = {}
        # 成组键 -> CaseOps：成组时登记的「生效术式」（按《不纳入分组的主要手术操作》
        # 清洗后的结果），供第二阶段综合病种子组判定复用（2026-09-14）
        self._case_ops_meta: Dict[str, "CaseOps"] = {}
        self._load_national_engine()

        # 不纳入分组：主要诊断剔除清单（命中即不参与分组测算）
        self.excluded_diag_records: List[Dict] = []
        self.excluded_diag_cases: int = 0

        self._nat_dip_codes: set = set()
        self._nat_rows_by_dip: Dict[str, dict] = {}

        # 极端病例裁剪统计
        self.total_original_cases = 0   # 裁剪前总病例数
        self.total_trimmed_cases = 0    # 裁剪剔除的病例数
        self.overall_trim_rate = 0.0    # 整体裁剪率

    def _load_national_engine(self) -> None:
        """加载《DIP3.0版分组方案》国家目录引擎（XQ/BX/FZ/JC 分段查表）。"""
        xlsx = os.path.join(self.data_dir, "DIP3.0国家目录库.xlsx")
        if not os.path.exists(xlsx):
            print(f"警告: 未找到国家目录库 {xlsx}，四层成组回退内置种子规则")
            return
        try:
            # 模块级缓存：只读实例可安全复用，避免每个生成器实例重读 5-sheet xlsx + 建索引
            self._nat_engine = get_national_engine(xlsx)
        except Exception as e:  # noqa: BLE001
            print(f"警告: 加载国家目录引擎失败，四层成组回退内置种子规则: {e}")
            self._nat_engine = None

    def set_threshold(self, threshold: int):
        """
        设置核心病种临界值（病例数阈值）

        聚类时以 self.threshold 为准（cluster_records_to_groups 读取它）。
        同时同步给内部 grouping_engine，保持一致性。

        Args:
            threshold: 核心病种临界值
        """
        self.threshold = int(threshold)
        if hasattr(self, "grouping_engine") and self.grouping_engine is not None:
            self.grouping_engine.set_threshold(threshold)

    # ------------------------------------------------------------------
    # 字典加载（CCI.xlsx + 中重度分型诊断.xlsx）
    # 字典为权威数据源；CCI 分数与严重度等级严格按 DIP3.0 技术规范逻辑测算
    # ------------------------------------------------------------------
    def _load_dictionaries(self) -> None:
        """加载 CCI 与疾病严重程度（中重度分型）字典，构建查表结构。

        CCI 统一使用 CCICalculator 单引擎（B4），字典为权威数据源
        （data/CCI.xlsx 的「得分」列，B3），不再维护第二套硬编码权重表。
        """
        # CCI 单引擎：由 CCICalculator 在构造时自行加载权威字典（含 得分 缺失回退）
        self.cci_calculator = CCICalculator()
        self._load_severity_dictionary()

    def _load_severity_dictionary(self) -> None:
        """加载 中重度分型诊断.xlsx：诊断码 -> (严重程度/辅助分型名称, 类型)。"""
        try:
            df = self.data_loader.load_severity_classification()
        except Exception as e:
            print(f"警告: 加载疾病严重程度字典失败，严重程度将为空: {e}")
            return

        for _, row in df.iterrows():
            # 注意：真实诊断码在 ASSI_ITEM_ID 列（如 A01.000x005+），
            # DIP_ASSISTANT_CODE 仅为行序号，不能作为诊断码匹配。
            code = str(row.get("ASSI_ITEM_ID", "")).strip() or str(row.get("DIP_ASSISTANT_CODE", "")).strip()
            name = str(row.get("DIP_ASSISTANT_NAME", "")).strip()
            atype = str(row.get("DIP_ASSISTANT_TYPE", "")).strip()
            if not code:
                continue
            self.severity_entries.append({
                "norm": self._normalize_code(code),
                "name": name,
                "type": atype,
            })
        print(f"已加载疾病严重程度字典: {len(self.severity_entries)} 条")

    @staticmethod
    def _normalize_code(code) -> str:
        """归一化诊断码：去 '+' / 'x' 扩展标记，仅保留字母数字。"""
        if not code:
            return ""
        s = str(code).lower().replace("+", "").replace("x", "")
        return "".join(ch for ch in s if ch.isalnum())

    @staticmethod
    def _severity_priority(name: str) -> int:
        """严重程度/辅助分型的优先级（数值越大越重）。

        字典（data/中重度分型诊断.xlsx）严格以官方附件为准，仅含「中度/重度」；
        「轻度」为规范中"不属于中重度"的兜底标签，保留以兼容既有口径。
        """
        order = {"重度": 6, "中度": 5, "轻度": 4}
        return order.get(name, 0)

    def _compute_group_cci(self, diag_codes: List[str], exclude_main: str = "") -> int:
        """病种组级 CCI 评分（B1：不计入主诊断，仅用其他/相关诊断）。

        统一使用 CCICalculator 单引擎（B4），字典为权威数据源
        （data/CCI.xlsx 的「得分」列；缺失得分的条目不参与评分，B3）。
        """
        exclude = self._clean_str(exclude_main).upper()
        diags = [d for d in diag_codes if self._clean_str(d).upper() != exclude]
        return self.cci_calculator.calculate_cci(diags)

    def _compute_group_severity(self, diag_codes: List[str]) -> Tuple[str, str]:
        """病种组级疾病严重程度：在字典中匹配诊断码，取最高优先级条目。

        Returns:
            (严重程度/辅助分型名称, 类型)
        """
        best = None  # (priority, name, type)
        for code in diag_codes:
            if not code:
                continue
            d = self._normalize_code(code)
            if not d:
                continue
            for entry in self.severity_entries:
                c = entry["norm"]
                if not c:
                    continue
                if c.startswith(d) or d.startswith(c):
                    prio = self._severity_priority(entry["name"])
                    if best is None or prio > best[0]:
                        best = (prio, entry["name"], entry["type"])
        if best:
            return best[1], best[2]
        return "", ""

    def load_national_directory(self, file_path: str) -> pd.DataFrame:
        """
        加载国家DIP目录库（3.0版）
        
        Args:
            file_path: 国家目录库文件路径
            
        Returns:
            国家目录库DataFrame
        """
        if file_path.endswith('.xlsx') or file_path.endswith('.xls'):
            # 医保/手术编码含尾随零(如 47.0100)，默认解析为浮点会丢失，故强制按字符串读
            df = pd.read_excel(file_path, dtype=str)
        elif file_path.endswith('.csv'):
            # 优先 utf-8；中文 Windows 常见 GBK 编码，解码失败自动回退（纯容错，
            # 不影响既有 utf-8 CSV 行为，也不改变任何测算逻辑）
            try:
                df = pd.read_csv(file_path, encoding='utf-8', dtype=str)
            except (UnicodeDecodeError, UnicodeError):
                df = pd.read_csv(file_path, encoding='gbk', dtype=str)
        else:
            raise ValueError(f"不支持的文件格式: {file_path}")
        
        self.national_directory = df
        self._build_national_lookups(df)
        print(f"已加载国家目录库: {len(df)} 条记录")
        return df

    def _build_national_lookups(self, df: pd.DataFrame):
        """从国家目录库（合并核心病种表）建立 DIP 编码索引。

        仅构建两个展示/回退用索引：
          - _nat_dip_codes / _nat_rows_by_dip：DIP编码 -> 目录行 dict，
            供 _build_group 旧路径回写与 Web 显示链路（按 诊断(4位)+手术 查目录）使用。
        四层成组本身一律走 NationalDirectoryV30 引擎（XQ/BX/FZ/JC 查表），
        旧《函》时代的 LBW/肿瘤/结核/烧伤行级解析器已随种子回落规则一并移除。
        """
        self._nat_dip_codes: set = set()
        self._nat_rows_by_dip: Dict[str, dict] = {}
        for _, r in df.iterrows():
            dip = str(r.get('DIP编码', '')).strip()
            if dip.lower() == 'nan' or not dip:
                continue
            self._nat_dip_codes.add(dip)
            self._nat_rows_by_dip[dip] = r.to_dict()

    def _load_icd10_category_map(self) -> None:
        """加载《ICD-10医保2.0版》抽取的「3 位类目码 -> 类目名称」映射。

        该映射由 scripts/extract_icd10_category.py 从《ICD-10医保2.0版.pdf》一次性抽取，
        存为 data/icd10_category_map.json。综合病种命名优先使用此权威类目名称；
        缺失时（如非常见码）回退到病例名推导。
        """
        import json
        fname = "icd10_category_map.json"
        path = os.path.join(self.data_dir, fname)
        if not os.path.exists(path):
            print(f"警告: 未找到 {fname}，综合病种类目名称将回退到病例名推导")
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                self._icd10_category_map = json.load(f)
            print(f"已加载 ICD-10 医保2.0 类目名称映射: {len(self._icd10_category_map)} 条")
        except Exception as e:
            print(f"警告: 加载 ICD-10 类目名称映射失败: {e}")

    def load_hospital_settlement_data(self, file_path: str) -> pd.DataFrame:
        """
        加载医院上传的医保清单数据
        
        Args:
            file_path: 医保清单数据文件路径（Excel/CSV）
            
        Returns:
            清单数据DataFrame
        """
        if file_path.endswith('.xlsx') or file_path.endswith('.xls'):
            # 医保/手术编码含尾随零(如 47.0100)，默认解析为浮点会丢失，故强制按字符串读
            df = pd.read_excel(file_path, dtype=str)
        elif file_path.endswith('.csv'):
            # 优先 utf-8；中文 Windows 常见 GBK 编码，解码失败自动回退（纯容错，
            # 不影响既有 utf-8 CSV 行为，也不改变任何测算逻辑）
            try:
                df = pd.read_csv(file_path, encoding='utf-8', dtype=str)
            except (UnicodeDecodeError, UnicodeError):
                df = pd.read_csv(file_path, encoding='gbk', dtype=str)
        else:
            raise ValueError(f"不支持的文件格式: {file_path}")
        
        print(f"已加载医保清单数据: {len(df)} 条记录")
        return df
    
    def _normalize_column_names(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        标准化列名，兼容不同格式的清单数据
        
        Args:
            df: 原始DataFrame
            
        Returns:
            标准化后的DataFrame
        """
        # 列名映射（兼容多种格式）
        column_mapping = {
            # 主要诊断
            '主要诊断代码': 'main_diag_code',
            'main_diag_code': 'main_diag_code',
            'diag_code': 'main_diag_code',
            '主诊断编码': 'main_diag_code',
            '主要诊断编码': 'main_diag_code',
            
            '主要诊断名称': 'main_diag_name',
            'main_diag_name': 'main_diag_name',
            'diag_name': 'main_diag_name',
            '主诊断名称': 'main_diag_name',
            
            # 相关诊断
            '相关诊断代码': 'related_diag_code',
            'related_diag_code': 'related_diag_code',
            '次要诊断编码': 'related_diag_code',
            '相关诊断编码': 'related_diag_code',  # 兼容常见导出表头「相关诊断编码」
            
            '相关诊断名称': 'related_diag_name',
            'related_diag_name': 'related_diag_name',
            
            # 主要手术操作
            '主要手术操作代码': 'main_oprn_code',
            'main_oprn_code': 'main_oprn_code',
            'oprn_code': 'main_oprn_code',
            '主要操作代码': 'main_oprn_code',
            '手术操作编码': 'main_oprn_code',
            
            '主要手术操作名称': 'main_oprn_name',
            'main_oprn_name': 'main_oprn_name',
            'oprn_name': 'main_oprn_name',
            '主要操作名称': 'main_oprn_name',
            '手术操作名称': 'main_oprn_name',
            
            # 相关手术操作
            '相关手术操作代码': 'related_oprn_code',
            'related_oprn_code': 'related_oprn_code',
            '相关操作代码': 'related_oprn_code',
            
            '相关手术操作名称': 'related_oprn_name',
            'related_oprn_name': 'related_oprn_name',
            
            # 费用信息
            '医疗总费用': 'total_cost',
            'total_cost': 'total_cost',
            '费用总额': 'total_cost',
            '住院总费用': 'total_cost',
            '次均费用': 'total_cost',
            
            # 费用拆分（辅助分型：高费用类型一/二判定）
            '药品费用': 'drug_cost',
            '药品费': 'drug_cost',
            'drug_cost': 'drug_cost',
            '治疗费用': 'treatment_cost',
            '治疗费': 'treatment_cost',
            'treatment_cost': 'treatment_cost',

            # 辅助分型所需字段（第三步：严重程度/年龄特征/ICU天数/CCI）
            '住院天数': 'los',
            '实际住院天数': 'los',
            'los': 'los',
            '年龄': 'age',
            'age': 'age',
            '日龄': 'day_age',
            '天龄': 'day_age',
            '年龄不足1周岁天龄': 'day_age',
            'day_age': 'day_age',
            'ICU天数': 'icu_days',
            '监护病房住院天数': 'icu_days',
            '重症监护天数': 'icu_days',
            'icu_days': 'icu_days',

            # 重症判断补充字段（收费项目 / 病房类型 + 特级护理天数）
            '特级护理天数': 'spga_nurscare_days',
            'spga_nurscare_days': 'spga_nurscare_days',
            '重症监护病房类型': 'scs_cutd_ward_type',
            'scs_cutd_ward_type': 'scs_cutd_ward_type',
            '收费项目编码': 'charge_item_codes',
            'charge_item_codes': 'charge_item_codes',

            '出院状态': 'discharge_status',
            '离院方式': 'discharge_status',
            'discharge_status': 'discharge_status',

            # 其他字段
            '病例数': 'case_count',
            'case_count': 'case_count',

            # 新生儿 / 人口学字段（先期分组·低出生体重、烧伤/肿瘤年龄推算）
            '出生体重': 'birth_weight',
            '新生儿出生体重': 'birth_weight',
            '出生体重(g)': 'birth_weight',
            'birth_weight': 'birth_weight',
            '出生日期': 'birth_date',
            'birth_date': 'birth_date',
            '入院时间': 'admission_date',
            '入院日期': 'admission_date',
            'admission_date': 'admission_date',

            # 医疗机构等级（基层病种遴选：统计基层机构病例占比）
            '医院等级': 'hospital_level',
            '医疗机构等级': 'hospital_level',
            '医保结算等级': 'hospital_level',
            '定点医疗机构等级': 'hospital_level',
            'hospital_level': 'hospital_level',
        }
        
        # 重命名列
        df_renamed = df.rename(columns=column_mapping)
        # 多值列折叠：其他诊断1~5 / 其他手术1~5 分列 → 单一 related_* 字段（| 分隔）
        df_renamed = self._fold_multi_value_columns(df_renamed)
        return df_renamed

    @staticmethod
    def _fold_multi_value_columns(df: pd.DataFrame) -> pd.DataFrame:
        """把「其他诊断1~5 / 其他手术1~5」等分列折叠进 related_diag_code / related_oprn_code。

        真实 4101A 医保清单为分列结构（其他诊断编码1~5、其他手术操作编码1~5），
        而引擎数据模型 related_diag_code / related_oprn_code 是「单字段多值」，
        内部规范用 '|' 分隔（见 database/models.py 注释「多个用|分隔」、
        parser_4101a.py 以 '|'.join 折叠）。宽表导入器此前只做 1:1 列名映射，
        分列既不会被 rename 命中、也无法并入同一字段，导致整列被忽略。

        本函数在规范化后显式折叠：扫描数字分列（兼容多种常见表头写法），
        按行把非空编码/名称以 '|' 拼接写入 related_diag_code / related_oprn_code
        （并与已存在的单值列合并、去重保序）。纯加法——输入若无分列则原样返回，
        不改变任何单列场景的测算行为与结果。
        """
        diag_code_re = re.compile(
            r'^(?:其他诊断编码|其他诊断代码|相关诊断编码|次要诊断编码|其他诊断)'
            r'(?:编码|代码)?[\s_]*(\d+)$')
        diag_name_re = re.compile(
            r'^(?:其他诊断编码|其他诊断代码|相关诊断编码|次要诊断编码|其他诊断)'
            r'(?:编码|代码)?[\s_]*(\d+)名称$')
        oprn_code_re = re.compile(
            r'^(?:其他手术操作编码|其他手术编码|相关手术操作编码|其他手术)'
            r'(?:编码|代码)?[\s_]*(\d+)$')
        oprn_name_re = re.compile(
            r'^(?:其他手术操作编码|其他手术编码|相关手术操作编码|其他手术)'
            r'(?:编码|代码)?[\s_]*(\d+)名称$')

        def _groups(pat):
            g, matched = {}, []
            for col in df.columns:
                m = pat.match(str(col).strip())
                if m:
                    g.setdefault(int(m.group(1)), []).append(col)
                    matched.append(col)
            return g, matched

        def _fold(target_code, target_name, code_groups, name_groups):
            code_cols = [c for i in sorted(code_groups) for c in code_groups[i]]
            name_cols = [c for i in sorted(name_groups) for c in name_groups[i]]
            base_code = df[target_code] if target_code in df.columns else None
            base_name = df[target_name] if target_name in df.columns else None
            folded_codes, folded_names = [], []
            for i in range(len(df)):
                cvals, nvals = [], []
                if base_code is not None:
                    bv = str(base_code.iat[i])
                    if bv not in ('', 'nan', 'None'):
                        cvals.append(bv)
                for c in code_cols:
                    v = str(df[c].iat[i])
                    if v not in ('', 'nan', 'None'):
                        cvals.append(v)
                for c in name_cols:
                    v = str(df[c].iat[i])
                    if v not in ('', 'nan', 'None'):
                        nvals.append(v)
                if base_name is not None:
                    bv = str(base_name.iat[i])
                    if bv not in ('', 'nan', 'None'):
                        nvals.append(bv)
                folded_codes.append('|'.join(dict.fromkeys(cvals)))
                folded_names.append('|'.join(dict.fromkeys(nvals)))
            df[target_code] = folded_codes
            df[target_name] = folded_names
            return [c for c in code_cols + name_cols if c in df.columns]

        df = df.copy()
        dcg, dnm = _groups(diag_code_re)
        dng, dnn = _groups(diag_name_re)
        ocg, onm = _groups(oprn_code_re)
        ong, onn = _groups(oprn_name_re)
        dropped = []
        if dcg or dng:
            dropped += _fold('related_diag_code', 'related_diag_name', dcg, dng)
        if ocg or ong:
            dropped += _fold('related_oprn_code', 'related_oprn_name', ocg, ong)
        if dropped:
            df = df.drop(columns=dropped)
        return df
    
    @staticmethod
    def _safe_int(value) -> int:
        """NaN/None/空串 安全的 int 转换（清单缺失字段回退 0）。"""
        try:
            if value is None:
                return 0
            f = float(value)
            if f != f:  # NaN
                return 0
            return int(f)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _safe_decimal(value) -> Decimal:
        """NaN/None/空串 安全的 Decimal 转换（清单缺失字段回退 0）。"""
        try:
            if value is None:
                return Decimal('0')
            f = float(value)
            if f != f:  # NaN
                return Decimal('0')
            return Decimal(str(value))
        except (TypeError, ValueError, ArithmeticError):
            return Decimal('0')

    @staticmethod
    def _effective_case_count(group: DiseaseGroup) -> int:
        """RW 测算使用的有效病例数（裁剪后；未裁剪时回退到原始病例数）。"""
        return group.trimmed_case_count if group.trimmed_case_count > 0 else group.case_count

    def _trim_group_costs(
        self, costs: List[Decimal]
    ) -> Tuple[List[Decimal], int, Decimal, Decimal]:
        """
        对单病种组内的住院总费用做极端病例裁剪。

        以组内所有病例住院总费用排序，取 lower_quantile（默认 2.5%）下分位数、
        upper_quantile（默认 97.5%）上分位数作为费用上下限；低于下限或高于上限的
        极端病例予以剔除。

        组内科室数小于 min_trim_group_size 时不做裁剪（避免小样本单条记录占比过大
        导致过度裁剪，从而把整体裁剪率控制在合理区间）。

        Args:
            costs: 该组逐条住院总费用列表

        Returns:
            (裁剪后保留的费用列表, 被裁剪病例数, 费用下限, 费用上限)
            未裁剪时返回 (原列表, 0, Decimal('0'), Decimal('0'))
        """
        import numpy as np

        n = len(costs)
        if n < self.min_trim_group_size:
            return costs, 0, Decimal("0"), Decimal("0")

        arr = np.array([float(c) for c in costs], dtype=float)
        lb = float(np.quantile(arr, self.lower_quantile))
        ub = float(np.quantile(arr, self.upper_quantile))

        kept = [c for c in costs if lb <= float(c) <= ub]
        trimmed = n - len(kept)
        # 费用上下限保留两位小数，便于展示与核对
        return (
            kept,
            trimmed,
            Decimal(str(round(lb, 2))),
            Decimal(str(round(ub, 2))),
        )

    # ------------------------------------------------------------------
    # 手术操作类别映射（综合病种四子组：内科 / 诊断性操作 / 治疗性操作 / 相关手术）
    # 数据来源：手术操作分类代码国家临床版3.0（国临版码 -> 类别）
    #           + ICD9 国临↔医保对照（医保版码 -> 国临版码 桥接）
    # ------------------------------------------------------------------
    def _load_op_category_maps(self) -> None:
        """加载手术操作类别映射，构建 医保版手术码 -> 类别 的查表。"""
        import os
        import pandas as pd

        # 1) 国临版手术码 -> 类别
        clinical_file = os.path.join(
            self.data_dir, "（2）手术操作分类代码国家临床版3.0（2022汇总版）.xlsx"
        )
        if os.path.exists(clinical_file):
            try:
                sdf = pd.read_excel(clinical_file, sheet_name="3.0（2022汇总版）", dtype=str)
                for _, row in sdf.iterrows():
                    code = str(row.get("手术操作编码", "")).strip()
                    cat = str(row.get("类别", "")).strip()
                    if code and cat:
                        self._clinical_op_category[code] = cat
            except Exception as e:
                print(f"警告: 加载手术操作类别失败: {e}")

        # 2) 医保版手术码 -> 国临版手术码（桥接）
        icd9_file = os.path.join(
            self.data_dir, "ICD9国临版3.0对照医保版2.0_0125.xlsx"
        )
        if os.path.exists(icd9_file):
            try:
                idf = pd.read_excel(icd9_file, dtype=str)
                for _, row in idf.iterrows():
                    ins = str(row.get("医保2.0手术代码", "")).strip()
                    cli = str(row.get("国临3.0手术代码", "")).strip()
                    if ins and cli:
                        self._insurance_to_clinical[ins] = cli
            except Exception as e:
                print(f"警告: 加载 ICD9 对照失败: {e}")

        # 3) 新增医保手术操作代码 -> 国临版（扩展桥接，使新增码也能查到类别）
        #    表内含「新增医保手术操作与国临版映射表」：医保版码 <-> 国临版码
        new_file = os.path.join(self.data_dir, "新增医保手术操作代码.xlsx")
        if os.path.exists(new_file):
            try:
                ndf = pd.read_excel(
                    new_file, sheet_name="新增医保手术操作与国临版映射表",
                    header=1, dtype=str,
                )
                ndf.columns = [str(c).replace("\n", "").strip() for c in ndf.columns]
                ins_col = next((c for c in ndf.columns if "医保版手术操作代码" in c), None)
                cli_col = next((c for c in ndf.columns if "国临版手术操作代码" in c), None)
                if ins_col and cli_col:
                    for _, row in ndf.iterrows():
                        ins = str(row.get(ins_col, "")).strip()
                        cli = str(row.get(cli_col, "")).strip()
                        if ins and cli:
                            # setdefault：主对照表优先，新增表作补充
                            self._insurance_to_clinical.setdefault(ins, cli)
            except Exception as e:
                print(f"警告: 加载新增医保手术操作代码失败: {e}")
    def _nat_dip_for_diag_oprn(self, diag_code: str, oprn_code: str) -> str:
        """按 主要诊断(4位) + 主要手术操作 查国家目录 DIP 码（基本规则/并项规则层）。

        匹配优先级（严格对齐国家目录，避免 x 扩展码被吞）：
          1) 精确（含 x 扩展码）：如 39.9500x007(CRRT) 优先命中 N18.5-03，而非被
             39.9500(血液透析) 的前4位碰撞误归 N18.5-01；
          2) 去 x 基础码兜底：本地码无扩展时回退（如 55.6100 → 55.6100x001）；
          3) 前4位前缀兜底：编码体系差异时的最后手段。
        """
        nd = getattr(self, 'national_directory', None)
        if nd is None:
            return ""
        diag4 = self._extract_icd4(diag_code)
        if not diag4:
            return ""
        op_full = LocalDirectoryGenerator._clean_str(oprn_code).lower()  # 保留 x 扩展
        if not op_full:
            return ""
        op_base = re.sub(r'x\d+$', '', op_full, flags=re.IGNORECASE)
        best_base = ""
        for _, r in nd.iterrows():
            nd_diag = self._extract_icd4(str(r.get('主要诊断编码', '')))
            nd_op = LocalDirectoryGenerator._clean_str(r.get('主要手术操作编码', '')).lower()
            if nd_diag != diag4 or not nd_op:
                continue
            if nd_op == op_full:
                return str(r.get('DIP编码', '')).strip()   # 精确(含 x)命中即返回
            if nd_op == op_base:
                best_base = str(r.get('DIP编码', '')).strip()
        if best_base:
            return best_base
        for _, r in nd.iterrows():
            nd_diag = self._extract_icd4(str(r.get('主要诊断编码', '')))
            nd_op = LocalDirectoryGenerator._clean_str(r.get('主要手术操作编码', '')).lower()
            if nd_diag == diag4 and nd_op[:4] == op_base[:4]:
                return str(r.get('DIP编码', '')).strip()
        return ""
    def _get_op_category(self, insurance_op_code: str) -> str:
        """医保版手术码 -> 手术类别（手术/治疗性操作/诊断性操作/介入治疗/''）。"""
        code = self._clean_str(insurance_op_code)
        if not code:
            return ""
        clinical = self._insurance_to_clinical.get(code, code)  # 找不到桥接则原样尝试
        return self._clinical_op_category.get(clinical, "")

    def _get_op_subtype(self, insurance_op_code: str) -> str:
        """医保版手术码 -> 综合病种子组类型（四子组，见 DIP3.0 技术规范）。

        组判定（规范「综合病种成组」）：
          - 未包含手术及操作或仅包含简单操作 -> 内科诊疗组
          - 主要操作属性 = 诊断性操作           -> 诊断性操作组
          - 主要操作属性 = 治疗性操作           -> 治疗性操作组
          - 主要操作属性 = 手术 / 介入操作       -> 相关手术组（介入并入相关手术组）

        用户裁决（2026-09-14）：医保结算清单未填写手术操作 = 保守治疗；操作码
        不属于手术操作分类表四类（手术/治疗性/诊断性/介入治疗）者视为「简单
        治疗」，一并纳入内科诊疗组——对齐规范「按上述规则均不能入组的病例
        归入内科诊疗组」。注意：此前的实现把该类误归相关手术组，已修正。
        """
        if not self._clean_str(insurance_op_code):
            return "内科诊疗组"
        cat = self._get_op_category(insurance_op_code)
        if cat == "诊断性操作":
            return "诊断性操作组"
        if cat == "治疗性操作":
            return "治疗性操作组"
        if cat in ("手术", "介入治疗"):
            return "相关手术组"
        # 查不到类别 -> 简单治疗，归内科诊疗组
        return "内科诊疗组"

    @staticmethod
    def _clean_str(value) -> str:
        """将单元格读到的 NaN / None / 空值统一规整为空字符串。

        Excel 空单元格经 pandas 读入后常为 float('nan')，直接 str() 会得到
        'nan' 字符串，导致手术码判空、类别查询、国家目录匹配等一系列逻辑误判。
        """
        if value is None:
            return ""
        try:
            if value != value:  # NaN 检测
                return ""
        except TypeError:
            pass
        s = str(value).strip()
        return "" if s.lower() in ("nan", "none", "null", "") else s

    @staticmethod
    def _norm_op_code(op_code: str) -> str:
        """手术操作码归一化：去 x 扩展码、去前后空白；空集返回空串。

        国家目录库手术码常见写法：带 x 扩展码(60.2900x004)、用 '|' 列举多个
        等价码。本地医保清单则多为医保版2.0 码(60.2900)。匹配时统一取 x 之前的
        基础码以便比对。
        """
        s = LocalDirectoryGenerator._clean_str(op_code)
        if not s:
            return ""
        return s.split("x")[0].strip()

    @staticmethod
    def _extract_icd4(icd_code: str) -> str:
        """提取 ICD-10 主诊断 4 位码（类目+亚目，去除点号后的扩展码）。

        例如 J18.9 -> J18、K35.9 -> K35、I21.0 -> I21、N40 -> N40。
        原实现用 code[:4] 会截出 "J18."（含点号）导致与国家目录库永远不匹配，
        且会把不同亚目（如 J18.0/J18.9）错误归并，这里改为去除点号及之后部分。
        """
        code = str(icd_code or "").strip().upper()
        if not code:
            return ""
        # 去除点号及之后扩展码（J18.9 -> J18）
        base = code.split(".")[0]
        # 仅保留字母与数字，并取「1 位字母 + 最多 3 位数字」作为 4 位码
        base = "".join(ch for ch in base if ch.isalnum())
        m = re.match(r"^([A-Z])(\d{0,3})", base)
        return (m.group(1) + m.group(2)) if m else base

    @staticmethod
    def _extract_icd3(icd_code: str) -> str:
        """提取 ICD-10 主诊断 3 位码（类目，综合病种聚类用）。"""
        code = str(icd_code or "").strip()
        code = code.split("x")[0] if "x" in code else code
        return code[:3] if len(code) >= 3 else code

    def _resolve_category_name(self, diag3: str, candidates: List[Tuple[str, str]]) -> str:
        """由 3 位类目码解析综合病种类目名称（优先 ICD-10 医保2.0 版权威类目名称）。

        优先级：
          1) ICD-10 医保2.0 版类目名称映射（data/icd10_category_map.json，权威来源）；
          2) 组内存在「编码恰好等于 3 位类目码」的候选 -> 取其名称；
          3) 否则取所有去重名称中最短者（类目级名称通常短于亚目级，如「肺炎」<「急性肺炎」）；
          4) 兜底返回 3 位码本身。
        candidates: List[(诊断码, 诊断名称)]，来自组内合并的各初级组首条记录（仅作回退）。
        """
        diag3 = LocalDirectoryGenerator._clean_str(diag3).upper()
        if not diag3:
            return ""
        # 1) 权威类目名称（ICD-10 医保2.0 版）
        if diag3 in self._icd10_category_map:
            return self._icd10_category_map[diag3]
        # 2-3) 回退：从组内病例推导（ICD 字典无 3 位类目行时的兜底）
        exact = None
        names = set()
        for code, name in candidates:
            code = LocalDirectoryGenerator._clean_str(code).upper()
            name = LocalDirectoryGenerator._clean_str(name)
            if not name:
                continue
            if code == diag3:
                exact = name
            names.add(name)
        if exact:
            return exact
        if names:
            # 最短名称优先；同名长度并列时按字母序稳定取首个
            return min(names, key=lambda n: (len(n), n))
        return diag3

    def _refine_core_group_key(
        self,
        main_diag_code: str,
        main_oprn_code: str,
        related_oprn_code: str,
        related_diag_code: str = "",
        day_age: int = 0,
        birth_weight: Decimal = Decimal("0"),
        age: int = 0,
        birth_date: str = "",
        admission_date: str = "",
    ) -> Tuple[str, str]:
        """核心病种成组键（DIP3.0 规范四层顺序）。

        返回 (成组键, 成组层次)。成组层次 ∈ 先期分组/并项规则/诊断辅助细分/基本规则，
        用于本地目录库严格按 ①→②→③→④ 顺序成组与输出排序。

        ⚠️ 引擎唯一权威（用户 2026-09-04 裁决）：四层成组一律调用 NationalDirectoryV30
        按 XQ/BX/FZ/JC 分段查表，命中者返回**方案序号**（全局唯一）作为成组键。

        ⚠️ 综合病种兜底（用户 2026-09-14 裁决「纳入并接入引擎兜底成组」）：
        未入核心病种的病例（国家目录四层均未命中）不再落 ④ 基本规则键，
        而是按《综合病种字典表》以「主诊断 ICD-10 类目 + 治疗方式组」入组综合病种
        （DIP 2.0 技术规范 第四章第四节；治疗方式组由主要手术操作属性判定：
         手术/介入→相关手术组，治疗性操作→治疗性操作组，诊断性操作→诊断性操作组，
         其余→内科诊疗组）。综合病种字典缺失时保留原基本规则键兜底。
        """
        # ①②③④ 全部走《3.0 版分组方案》国家目录引擎（XQ/BX/FZ/JC 分段查表）
        case_ops = None
        key = ""
        layer = ""
        if self._nat_engine is not None:
            # 先按《不纳入分组的主要手术操作》清洗术式（用户裁决 2026-09-14：
            # 「未填写手术操作=保守治疗；参考不纳入主要手术操作的为简单治疗，
            #   都纳入保守治疗」）：
            #   ·「按保守治疗入组」  → 无生效术式（整条按保守治疗）
            #   ·「不可作为主要手术操作」→ 顺延取下一个手术操作
            #   ·「限范围可作主要手术操作」→ 主诊断在限定范围内方可作主手术
            # 综合病种子组必须基于**生效术式**判定，否则被官方标注"按保守治疗
            # 入组"的简单操作（如 00.0100 治疗性超声）会被误归治疗性操作组。
            case_ops = self._nat_engine.clean_operations(
                main_oprn_code, related_oprn_code, main_diag_code
            )
            m = self._nat_engine.match(
                main_diag_code, main_oprn_code, related_oprn_code, related_diag_code,
                day_age=day_age, birth_weight=birth_weight, age=age,
                birth_date=birth_date, admission_date=admission_date,
            )
            if m is not None:
                self._nat_seq_meta[m.seq] = m
                key, layer = m.seq, m.layer
            else:
                # ---- 回落①：未入核心病种 → 综合病种（官方兜底层） ----
                eff_oprn = case_ops.main_oprn if case_ops is not None else main_oprn_code
                zm = self._nat_engine.match_zonghe(
                    main_diag_code,
                    self._get_op_category(eff_oprn),
                    bool(self._clean_str(eff_oprn)),
                )
                if zm is not None:
                    self._zh_meta[zm.code] = zm
                    key, layer = zm.code, NationalDirectoryV30.LAYER_ZH

        if not key:
            # ---- 回落②：引擎未加载 或 综合病种字典缺失 → ④ 基本规则键（末位兜底） ----
            diag_key = self._extract_icd4(main_diag_code)
            if main_oprn_code:
                if related_oprn_code:
                    key = f"{diag_key}|{main_oprn_code}|{related_oprn_code}"
                else:
                    key = f"{diag_key}|{main_oprn_code}|"
            else:
                key = f"{diag_key}||"
            layer = "基本规则"

        # 记录本组成组时的生效术式（供第二阶段综合病种子组判定复用；
        # 避免"按保守治疗入组"的简单操作在本地聚类路径被误判）。
        # setdefault：同一成组键可能由多条不同原始术式的记录命中（如 BX 名录的
        # 「|」多选一），与第一阶段 stats 取首条记录的口径保持一致、结果确定。
        if case_ops is not None:
            self._case_ops_meta.setdefault(key, case_ops)
        return key, layer

    # ======================================================================
    # ③ 诊断辅助细分（独立于第三步「触发式辅助分型」）
    # ======================================================================
    @staticmethod
    def _split_codes(code_str: str) -> List[str]:
        """把 '|' / ';' / '、' / ',' / '+' / 空格 分隔的编码串拆成清大写的编码列表。

        规范多值分隔符为 '|'（与 4101A 解析器、数据库模型「多个用|分隔」约定一致）；
        其余 ; 、 , + 空格 为历史/人工录入兼容。空串返回空列表。

        ⚠️ 国家 DIP3.0 目录库编码语义约定（务必遵守）：
          - '/' 表示 **或(OR)**：同一字段内 'A/B' = A 或 B（如 心脏移植 37.5100/37.5100x001）。
          - '+' 表示 **且(AND)**：同一字段内 'A+B' = A 与 B 同时满足
            （如 化疗+靶向 99.2503+99.2800x006，须记录同时有化疗与靶向）。
          - 当一条目录行的『主要手术操作编码/名称』与『相关手术操作编码/名称』
            两列**都不为空**时，含义同样是 **且(AND)**（如 4966 行：主要手术 96.7201
            + 相关手术 39.9500x007，须两码同时出现才归该组）。
        本函数仅做"切分"，不判定 OR/AND；调用方须据上述约定自行解释：
        切出的多码若是 '+' 连接的，应视为 AND（下游逻辑需全部命中），而非任选其一。
        """
        if not code_str:
            return []
        return [c.strip().upper() for c in str(code_str).replace("|", ";").replace("；", ";")
                .replace("、", ";").replace(",", ";").replace("+", ";").split(";")
                if c.strip()]

    @staticmethod
    def _compute_cv(costs: List[Decimal]) -> float:
        """组内变异系数 CV = 标准差 / 均值（综合病种合理性校验）。"""
        import numpy as np
        if not costs:
            return 0.0
        arr = np.array([float(c) for c in costs], dtype=float)
        mean = float(np.mean(arr))
        if mean <= 0:
            return 0.0
        return float(np.std(arr) / mean)

    def _build_group(
        self,
        key: str,
        stats: Dict,
        case_count: int,
        avg_cost: Decimal,
        kept_count: int,
        lb: Decimal,
        ub: Decimal,
        trimmed: int,
        group_type: GroupType,
        mixed_subtype: str,
        records: List[Dict] = None,
        layer: str = "",
        diag3: str = "",
    ) -> DiseaseGroup:
        """从聚合统计构造 DiseaseGroup（含 CCI / 严重度 / 裁剪 / 类别 / 成组层次 字段）。

        综合病种(MIXED)名称按 DIP3.0 规范格式化为「类目名称 + 子组类型」
        （如「肺炎内科诊疗组」「肺炎相关手术组」），便于目录库直观区分治疗方式。
        """
        zh = getattr(self, '_zh_meta', {}).get(key)
        if zh is not None:
            # 综合病种（官方兜底层）：名称/编码一律以《综合病种字典表》为准
            disease_name = zh.name
            main_diag_name = zh.name
            main_diag_code = stats.get('main_diag_code', '') or zh.icd_class
        elif group_type == GroupType.MIXED:
            cat_name = (
                stats.get('category_name')
                or LocalDirectoryGenerator._clean_str(stats.get('main_diag_name'))
                or (diag3 if diag3 else '未分类')
            )
            disease_name = f"{cat_name}{mixed_subtype}"
            main_diag_name = f"{cat_name}{mixed_subtype}"
            main_diag_code = diag3 or stats.get('main_diag_code', '')
        else:
            disease_name = self._generate_disease_name(stats)
            main_diag_name = stats.get('main_diag_name', '')
            main_diag_code = stats.get('main_diag_code', '')
        group = DiseaseGroup(
            disease_code=key.replace('|', '_'),
            disease_name=disease_name,
            main_diag_code=main_diag_code,
            main_diag_name=main_diag_name,
            main_oprn_code=stats.get('main_oprn_code', ''),
            main_oprn_name=stats.get('main_oprn_name', ''),
            related_oprn_code=stats.get('related_oprn_code', ''),
            related_oprn_name=stats.get('related_oprn_name', ''),
            group_type=group_type,
            case_count=case_count,
            avg_cost=avg_cost,
            # 极端病例裁剪相关字段
            original_case_count=case_count,
            trimmed_case_count=kept_count,
            trim_lower_bound=lb,
            trim_upper_bound=ub,
            trim_count=trimmed,
            # 成组逻辑字段
            op_category=self._get_op_category(stats.get('main_oprn_code', '')),
            mixed_subtype=mixed_subtype,
            grouping_layer=layer,
            member_records=records or [],
        )
        # 组级查字典：CCI 评分 + 疾病严重程度（规范逻辑，字典为权威数据源）
        diags = list(stats.get('diag_codes', set()))
        group.cci_score = Decimal(str(self._compute_group_cci(diags, stats.get('main_diag_code', ''))))
        sev_level, sev_type = self._compute_group_severity(diags)
        group.severity_level = sev_level
        group.severity_type = sev_type

        # ---- 国家目录元数据回填 ----
        # ① 命中《3.0 版分组方案》引擎（XQ/BX/FZ/JC 查表）→ 方案序号权威，回填 DIP 编码/基层标记
        meta = getattr(self, '_nat_seq_meta', {}).get(key)
        if meta is not None:
            group.national_seq = meta.seq
            group.national_dip_code = meta.dip_code
            group.national_matched = True
            group.is_grassroot = meta.is_grassroot
            # 国家目录分组名称优先（烧伤/肿瘤/结核等 FZ 组的权威命名）
            if meta.group_name:
                group.disease_name = meta.group_name
        # ② 旧路径兼容：若组键即「烧伤函条目号」权威 DIP 码，直接回填
        elif key in getattr(self, '_nat_dip_codes', set()):
            group.national_dip_code = key
            group.national_matched = True
        # ③ 综合病种兜底层：回填官方综合病种编码（综合病种无方案序号）
        if zh is not None:
            group.national_dip_code = zh.code
            group.national_matched = True
            group.is_grassroot = False   # 基层病种是核心病种中的类别，综合病种一律不标记
        return group

    # ------------------------------------------------------------------
    # 监护病房住院天数（重症）判断补充规则
    #   国家 DIP3.0 规范未明确监护病房住院天数如何分型，故补充两种业务判定方式
    #   （self.icu_days_rule 切换，见 ICU_BED_FEE_CODES / ICU_DAYS_RULE_OPTIONS）。
    #   两种判断均以「特级护理天数(spga_nurscare_days)」作为监护病房住院天数；
    #   与既有 icu_days(如 icu_dura/ICU天数) 取大值，不丢失任何显式提供的监护天数。
    # ------------------------------------------------------------------
    def _derive_icu_days(self, icu_days_base: int, nurscare_days: int,
                         ward_type: str, charge_codes) -> int:
        """由业务补充规则推导监护病房住院天数(icu_days)。

        Args:
            icu_days_base: 既有监护天数（来自 icu_dura / ICU天数 / 重症监护天数 等字段）
            nurscare_days: 特级护理天数（spga_nurscare_days）
            ward_type:     重症监护病房类型（scs_cutd_ward_type）
            charge_codes:  收费项目编码集合（可迭代 / 集合 / 列表；判断1 用）
        Returns:
            推导后的监护病房住院天数（int）
        """
        rule = self.icu_days_rule
        if rule == "ward_type":
            severe = bool(ward_type)
        else:  # 默认 'charge_item'（判断1）
            severe = bool(
                {str(c).strip().upper() for c in (charge_codes or [])}
                & self.ICU_BED_FEE_CODES
            )
        if severe and nurscare_days > 0:
            return max(icu_days_base, nurscare_days)
        return icu_days_base

    def cluster_records_to_groups(self, df: pd.DataFrame) -> Dict[str, DiseaseGroup]:
        """
        将清单数据聚类为病种组合（本地目录库成组逻辑）

        成组流程（DIP3.0 技术规范），严格按四层顺序测算：
          一、核心病种：每条记录依次经 ① 先期分组 → ② 并项规则 →
             ③ 诊断辅助细分 → ④ 基本规则（兜底）四层判定，仅命中最高优先级的一层，
             得到唯一核心成组键；组内病例数 >= 地方临界值(threshold) 的依次形成地方
             核心病种（与国家目录库对照、顺序一致）。
          二、综合病种：未达到核心病种临界值的病例，按手术操作属性分 4 子组
             （内科诊疗组 / 诊断性操作组 / 治疗性操作组 / 相关手术组），
             叠加主诊断 3 位码类目聚类，并做质量控制（剔除仍低于阈值者、
             标记组内变异系数过高的组）。
         三、各组住院总费用做极端病例裁剪（2.5% / 97.5% 分位数），
             裁剪后有效病例数用于后续次均费用与 RW 测算。
         四、最终本地目录库输出严格按 ①先期→②并项→③诊断辅助细分→④基本规则→综合病种
             顺序排列（见 _layer_sort_key）。

        Args:
            df: 医保清单数据DataFrame

        Returns:
            病种组合字典（key=成组键），含核心病种与综合病种（含 excluded 标记者）
        """
        df = self._normalize_column_names(df)

        # 整体裁剪率统计复位
        self.total_original_cases = 0
        self.total_trimmed_cases = 0
        self.excluded_cases = 0
        # 不纳入分组（主要诊断）剔除清单复位 + 国家目录元数据复位
        self.excluded_diag_records = []
        self.excluded_diag_cases = 0
        self._nat_seq_meta = {}
        # 综合病种兜底元数据复位
        self._zh_meta = {}
        # 生效术式登记复位
        self._case_ops_meta = {}

        # ---------- 第一阶段：核心病种初级聚类（四层顺序成组） ----------
        primary = defaultdict(lambda: {
            'case_count': 0,
            'costs': [],                       # 逐条住院总费用，用于组内极端病例裁剪
            'records': [],                     # 逐条成员记录（含分型所需字段），供辅助分型使用
            'layer': '',                       # 成组层次（先期分组/并项规则/诊断辅助细分/基本规则）
            'main_diag_code': '',
            'main_diag_name': '',
            'main_oprn_code': '',
            'main_oprn_name': '',
            'related_oprn_code': '',
            'related_oprn_name': '',
            'related_diag_code': '',
            'diag_codes': set(),
        })

        # ---- 行为保持优化：iterrows -> itertuples（仅改变遍历方式，逐字段一一对应，
        #      测算逻辑与结果完全不变；详见 scripts/perf_stability_check.py 指纹校验）----
        _total_rows = len(df)
        _ci = {name: i for i, name in enumerate(df.columns)}
        def _cell(row, name, default=''):
            i = _ci.get(name)
            return row[i] if i is not None else default
        # 仅对大数据量打印进度（小样本/测试保持静默，避免干扰输出）
        _progress_step = max(1, _total_rows // 20) if _total_rows > 0 else 1

        for _pos, _row in enumerate(df.itertuples(index=False, name=None), 1):
            main_diag = self._clean_str(_cell(_row, 'main_diag_code'))
            main_oprn = self._clean_str(_cell(_row, 'main_oprn_code'))
            related_oprn = self._clean_str(_cell(_row, 'related_oprn_code'))
            related_diag = self._clean_str(_cell(_row, 'related_diag_code'))
            day_age = self._safe_int(_cell(_row, 'day_age', 0))
            birth_weight = self._safe_decimal(_cell(_row, 'birth_weight', 0))
            age = self._safe_int(_cell(_row, 'age', 0))
            birth_date = self._clean_str(_cell(_row, 'birth_date'))
            admission_date = self._clean_str(_cell(_row, 'admission_date'))

            if not main_diag:
                continue

            # 不纳入分组·主要诊断：命中即剔除，不参与分组测算（另出剔除清单）
            if self._nat_engine is not None and self._nat_engine.is_excluded_diag(main_diag):
                self.excluded_diag_records.append({
                    '主要诊断编码': main_diag,
                    '主要诊断名称': self._clean_str(_cell(_row, 'main_diag_name')),
                    '主要手术操作编码': main_oprn,
                    '主要手术操作名称': self._clean_str(_cell(_row, 'main_oprn_name')),
                    '总费用': self._clean_str(_cell(_row, 'total_cost', 0)),
                })
                self.excluded_diag_cases += 1
                continue

            # 四层顺序成组：先期分组 → 并项规则 → 诊断辅助细分 → 基本规则
            # （每条记录仅命中最高优先级一层，得到唯一 core 成组键 + 成组层次）
            cluster_key, layer = self._refine_core_group_key(
                main_diag, main_oprn, related_oprn, related_diag,
                day_age=day_age, birth_weight=birth_weight, age=age,
                birth_date=birth_date, admission_date=admission_date,
            )

            cost = Decimal(str(_cell(_row, 'total_cost', 0)))
            stats = primary[cluster_key]
            stats['case_count'] += 1
            stats['layer'] = layer
            stats['costs'].append(cost)
            # 保留成员记录供辅助分型逐条判定（住院天数/年龄/费用拆分/次要诊断/ICU/出院状态）
            stats['records'].append({
                'main_diag_code': main_diag,
                'main_oprn_code': main_oprn,
                'related_diag_code': related_diag,
                'total_cost': cost,
                'drug_cost': self._safe_decimal(_cell(_row, 'drug_cost', 0)),
                'treatment_cost': self._safe_decimal(_cell(_row, 'treatment_cost', 0)),
                'los': self._safe_int(_cell(_row, 'los', 0)),
                'age': self._safe_int(_cell(_row, 'age', 0)),
                'day_age': self._safe_int(_cell(_row, 'day_age', 0)),
                # 监护病房住院天数(重症)：业务补充规则推导（收费项目/病房类型 + 特级护理天数）
                'icu_days': self._derive_icu_days(
                    self._safe_int(_cell(_row, 'icu_days', 0)),
                    self._safe_int(_cell(_row, 'spga_nurscare_days', 0)),
                    self._clean_str(_cell(_row, 'scs_cutd_ward_type')),
                    set(str(c).strip().upper() for c in
                        (str(_cell(_row, 'charge_item_codes', '')).split('|')
                         if isinstance(_cell(_row, 'charge_item_codes', ''), str)
                         else list(_cell(_row, 'charge_item_codes', [])))
                        if str(c).strip()),
                ),
                'discharge_status': self._clean_str(_cell(_row, 'discharge_status')),
                # 医疗机构等级（基层病种遴选：统计基层机构病例占比）
                'hospital_level': self._clean_str(_cell(_row, 'hospital_level', '')),
            })

            if not stats['main_diag_code']:
                stats['main_diag_code'] = main_diag
                stats['main_diag_name'] = self._clean_str(_cell(_row, 'main_diag_name'))
                stats['main_oprn_code'] = main_oprn
                stats['main_oprn_name'] = self._clean_str(_cell(_row, 'main_oprn_name'))
                stats['related_oprn_code'] = related_oprn
                stats['related_oprn_name'] = self._clean_str(_cell(_row, 'related_oprn_name'))
                stats['related_diag_code'] = related_diag

            # 采集诊断码集合（用于组级 CCI / 疾病严重程度查字典）
            # 多值其他诊断（'|' 分隔，兼容 ; , 、 + 空格）逐码纳入，确保合并症 CCI 算全（B1 修正延伸）
            stats['diag_codes'].add(main_diag)
            for d in self._split_codes(related_diag):
                stats['diag_codes'].add(d)

            if _total_rows >= 1000 and (_pos % _progress_step == 0 or _pos == _total_rows):
                print(f"  [聚类] {_pos}/{_total_rows} ({_pos * 100 // _total_rows}%)", flush=True)

        # 初级组 -> 核心病种（达阈值） / 未达阈值者进入综合病种池
        groups: Dict[str, DiseaseGroup] = {}
        subthreshold_records: List[Dict] = []

        for key, stats in primary.items():
            case_count = stats['case_count']

            if case_count >= self.threshold:
                # 核心病种：达地方临界值(threshold)者形成地方核心病种。
                # 四层（先期分组/并项规则/诊断辅助细分/基本规则）一律受阈值约束：
                # 未达阈值的病种折叠进入综合病种池（与国家目录口径一致，本地病例不足不强行独立成组）。
                kept_costs, trimmed, lb, ub = self._trim_group_costs(stats['costs'])
                kept_count = len(kept_costs)
                total_cost = sum(kept_costs, Decimal('0'))
                avg_cost = total_cost / kept_count if kept_count > 0 else Decimal('0')

                self.total_original_cases += case_count
                self.total_trimmed_cases += trimmed

                # 综合病种兜底层（未入核心病种）：分组类型标为综合病种，
                # 不参与辅助分型/基层病种遴选（规范：二者均以核心病种为对象）。
                _is_zh = stats['layer'] == NationalDirectoryV30.LAYER_ZH
                group = self._build_group(
                    key=key, stats=stats, case_count=case_count, avg_cost=avg_cost,
                    kept_count=kept_count, lb=lb, ub=ub, trimmed=trimmed,
                    group_type=(GroupType.MIXED if _is_zh else GroupType.CORE),
                    mixed_subtype=(self._zh_meta[key].group_name
                                   if _is_zh and key in self._zh_meta else ""),
                    records=stats['records'], layer=stats['layer'],
                )
                groups[key] = group
            else:
                # 未达核心病种临界值 -> 进入综合病种池，第二阶段按手术属性 + 3 位码重聚类
                # （此处不裁剪、不计入整体裁剪统计；裁剪在综合病种成型时统一进行）
                # 子组判定用「生效术式」：被《不纳入分组的主要手术操作》标为
                # 「按保守治疗入组」的简单操作，其生效术式为空 -> 内科诊疗组
                _ops = self._case_ops_meta.get(key)
                _eff_oprn = _ops.main_oprn if _ops is not None else stats['main_oprn_code']
                for cost in stats['costs']:
                    subthreshold_records.append({
                        'main_diag': stats['main_diag_code'],
                        'main_diag_name': stats['main_diag_name'],
                        'main_oprn': _eff_oprn,
                        'main_oprn_name': stats['main_oprn_name'] if _eff_oprn else '',
                        'cost': cost,
                        'diag_codes': stats['diag_codes'],
                    })

        # ---------- 第二阶段：综合病种（4 子组 + 3 位码聚类 + 质控） ----------
        secondary = defaultdict(lambda: {
            'case_count': 0,
            'costs': [],
            'main_diag_code': '',
            'main_diag_name': '',
            'main_oprn_code': '',
            'main_oprn_name': '',
            'related_oprn_code': '',
            'related_oprn_name': '',
            'diag_codes': set(),
            'cat_candidates': [],   # [(诊断码, 诊断名称)] 用于推导 3 位类目名称
        })

        for rec in subthreshold_records:
            subtype = self._get_op_subtype(rec['main_oprn'])   # 保守治疗/诊断性/治疗性/相关手术
            diag3 = self._extract_icd3(rec['main_diag'])        # 主诊断 3 位码（类目）
            sec_key = f"{subtype}|{diag3}"
            s = secondary[sec_key]
            s['case_count'] += 1
            s['costs'].append(rec['cost'])
            if not s['main_diag_code']:
                s['main_diag_code'] = rec['main_diag']
                s['main_diag_name'] = rec['main_diag_name']
                s['main_oprn_code'] = rec['main_oprn']
                s['main_oprn_name'] = rec['main_oprn_name']
            s['diag_codes'] |= rec['diag_codes']
            s['cat_candidates'].append((rec['main_diag'], rec['main_diag_name']))

        for key, stats in secondary.items():
            case_count = stats['case_count']
            kept_costs, trimmed, lb, ub = self._trim_group_costs(stats['costs'])
            kept_count = len(kept_costs)
            total_cost = sum(kept_costs, Decimal('0'))
            avg_cost = total_cost / kept_count if kept_count > 0 else Decimal('0')

            self.total_original_cases += case_count
            self.total_trimmed_cases += trimmed

            subtype = key.split('|')[0]
            diag3 = key.split('|')[1]
            category_name = self._resolve_category_name(diag3, stats['cat_candidates'])
            stats['category_name'] = category_name

            group = self._build_group(
                key=f"MIX_{subtype}_{diag3}", stats=stats, case_count=case_count,
                avg_cost=avg_cost, kept_count=kept_count, lb=lb, ub=ub, trimmed=trimmed,
                group_type=GroupType.MIXED, mixed_subtype=subtype,
                layer="综合病种", diag3=diag3,
            )

            # 综合病种质量控制：
            # (1) 聚类后仍低于地方临界值 -> 默认保留（覆盖低频病例）；
            #     仅当 exclude_below_threshold=True 时剔除（规范："可予以剔除"）
            if case_count < self.threshold and self.exclude_below_threshold:
                group.excluded = True
                self.excluded_cases += case_count
                groups[key] = group
                continue

            # (2) 组内变异系数过高 -> 标记剔除（避免组内资源消耗差异过大，分值失准）
            group.cv = self._compute_cv(kept_costs)
            if group.cv > self.max_cv_threshold:
                group.excluded = True
                self.excluded_cases += case_count

            groups[key] = group

        # 整体裁剪率核算与告警
        self.overall_trim_rate = (
            self.total_trimmed_cases / self.total_original_cases
            if self.total_original_cases > 0 else 0.0
        )
        if self.overall_trim_rate > self.max_overall_trim_rate:
            print(
                f"警告: 整体裁剪率 {self.overall_trim_rate*100:.2f}% 超过上限 "
                f"{self.max_overall_trim_rate*100:.0f}%，请检查 min_trim_group_size "
                f"与分位数参数设置。"
            )

        self.raw_groups = groups
        return groups

    # ------------------------------------------------------------------
    # 第三步：辅助分型（疾病严重程度 / 年龄特征 / ICU天数 / CCI）
    # ------------------------------------------------------------------
    @staticmethod
    def _is_tumor_diagnosis(diag_code: str) -> bool:
        """判断是否为肿瘤诊断（用于恶性肿瘤/非恶性肿瘤严重程度分流）。"""
        if not diag_code:
            return False
        prefix = diag_code[:3]
        return "C00" <= prefix <= "C96" or "D00" <= prefix <= "D48"

    def apply_auxiliary_typing(
        self,
        groups: Dict[str, DiseaseGroup],
        min_total_cases: int = 10,
        min_type_cases: int = 5,
        cv_improvement_pct: float = 0.20,
        cv_mode: str = "absolute",
        cv_threshold: float = 0.6,
        tcm_disease_codes: Optional[set] = None,
        bed_day_disease_codes: Optional[set] = None,
    ) -> Dict[str, DiseaseGroup]:
        """对核心病种应用辅助分型（DIP3.0 第三步）。

        对每个核心病种逐条分型，评估四个维度（严重程度/年龄特征/ICU天数/CCI）
        的触发条件：
          - 核心病种病例数 > min_total_cases
          - 某分型等级（子型）病例数 > min_type_cases
          - CV 条件（由 cv_mode 决定口径）：
            * ``"absolute"``（默认，测试阶段）：拆分后组内加权 CV < cv_threshold
            * ``"improvement"``（正式使用，数据量大时）：CV 改善率 >= cv_improvement_pct
        B7 多规则竞争：若多个维度触发，取「触发系数（mj/M）最高」的维度拆分
        （触发系数并列时取 CV 改善更大者）；将该核心病种拆分为该维度下的若干
        子组（各自独立病种行，保留父代码）。未触发则保持原组不变。

        B5 分值费用标准：高费用判定基准 = 未测算辅助分型的核心病种的平均费用
            （即该核心病种成组后的 group.avg_cost，记为 mi）。本地目录测算不
            计算真实点值，故分值费用标准直接取 mi，而非任意平均费用倍数。
        B6 范围控制：中医优势病种 / 床日病种不纳入辅助分型（标记或码集命中即跳过）。
        B11 严重程度校正：65 岁以上病例的年龄子组结合疾病严重程度字典进一步
            区分（子组标签形如「70-79岁·重度」），各组合子型分别统计触发系数。

        参数说明：
          - cv_mode="absolute"：当前测试阶段默认，与 Web 门控口径一致
            （子型费用绝对 CV < 0.6 才测算）。
          - cv_mode="improvement"：后期正式使用、数据量大时切换
            （拆分后 CV 相对改善 >= 20% 才测算）。
        """
        cci_calc = CCICalculator()
        sev_calc = DiseaseSeverityClassifier()
        age_calc = AgeFeatureClassifier()
        icu_calc = ICUStayClassifier()

        new_groups: Dict[str, DiseaseGroup] = {}
        self.auxiliary_trigger_report: List[Dict] = []

        # 顺序护栏：辅助分型（第三步）必须发生在四层成组之后。
        # 每个核心病种都应已带 grouping_layer（先期/并项/诊断辅助细分/基本规则），
        # 否则说明调用顺序错误（辅助分型被提前执行），立即报错以阻止回归。
        for _k, _g in groups.items():
            if _g.group_type == GroupType.CORE and not _g.excluded:
                if _g.grouping_layer not in LocalDirectoryGenerator.LAYER_ORDER:
                    raise RuntimeError(
                        f"辅助分型顺序错误：核心病种 {_g.disease_code} 缺少分组层次"
                        f"(grouping_layer={_g.grouping_layer!r})，辅助分型必须在四层成组之后执行"
                    )

        for key, group in groups.items():
            # 仅对核心病种、未剔除者做辅助分型（综合病种不拆分）
            if group.group_type != GroupType.CORE or group.excluded:
                new_groups[key] = group
                continue

            members = group.member_records
            if not members:
                new_groups[key] = group
                continue

            # B6：中医优势病种 / 床日病种不纳入辅助分型范围（标记或码集命中即跳过）
            if (group.is_tcm_advantage or group.is_bed_day
                    or (tcm_disease_codes and group.main_diag_code in tcm_disease_codes)
                    or (bed_day_disease_codes and group.main_diag_code in bed_day_disease_codes)):
                group.auxiliary_split = False
                new_groups[key] = group
                continue

            # B5：分值费用标准 = 未测算辅助分型的核心病种平均费用（mi = group.avg_cost）
            cost_standard = group.avg_cost

            # 逐条分型，得到各维度下按等级归集的成员
            dim_levels = self._classify_members(
                members, group, cci_calc, sev_calc, age_calc, icu_calc,
                cost_standard=cost_standard,
            )
            all_costs = [float(m['total_cost']) for m in members]
            cv_before = self._compute_cv(all_costs)
            # B2：M = 该病种全部病例平均住院费用（调节系数/触发系数分母）
            M = sum(all_costs) / len(all_costs) if all_costs else 0.0

            best_dim = None
            best_trigger = 0.0          # 触发系数（mj/M）最高者胜出（B2）
            best_improvement = 0.0
            best_levels = None
            for dim, levels in dim_levels.items():
                buckets = {lv: info['members'] for lv, info in levels.items()}
                cv_after, _ = self._cv_after_split(buckets)
                improvement = (cv_before - cv_after) / cv_before if cv_before > 0 else 0.0
                max_bucket_count = max(
                    (len(info['members']) for info in levels.values()), default=0
                )
                triggered = (
                    group.case_count > min_total_cases
                    and max_bucket_count > min_type_cases
                    and (
                        cv_after < cv_threshold
                        if cv_mode == "absolute"
                        else improvement >= cv_improvement_pct
                    )
                )
                # B2：触发系数 = 各子组 mj/M 的最大值（mj=子组平均住院费用）
                trig = 0.0
                if M > 0:
                    for info in levels.values():
                        trig = max(trig, self._mean_cost(info['members']) / M)
                self.auxiliary_trigger_report.append({
                    'disease_code': group.disease_code,
                    'main_diag_code': group.main_diag_code,
                    'disease_name': group.disease_name,
                    'dimension': dim,
                    'cv_before': round(cv_before, 4),
                    'cv_after': round(cv_after, 4),
                    'cv_improvement': round(improvement, 4),
                    'cv_mode': cv_mode,
                    'cv_threshold': cv_threshold if cv_mode == "absolute" else cv_improvement_pct,
                    'trigger_coefficient': round(trig, 4),
                    'max_bucket_case_count': max_bucket_count,
                    'triggered': '是' if triggered else '否',
                })
                if triggered and (trig > best_trigger or
                                 (trig == best_trigger and improvement > best_improvement)):
                    best_trigger = trig
                    best_improvement = improvement
                    best_dim = dim
                    best_levels = levels

            if best_dim is None:
                group.auxiliary_split = False
                new_groups[key] = group
                continue

            # 触发：按 best_dim 拆分；低频等级（<=min_type_cases）并入"其他(低频)"
            group.auxiliary_split = True
            main_levels = {
                lv: info for lv, info in best_levels.items()
                if len(info['members']) > min_type_cases
            }
            small = [info for lv, info in best_levels.items()
                     if len(info['members']) <= min_type_cases]
            if small:
                merged_members = []
                for info in small:
                    merged_members.extend(info['members'])
                mj = self._mean_cost(merged_members)
                main_levels['其他(低频)'] = {
                    'members': merged_members,
                    'coeff': Decimal(str(mj / M)) if M > 0 else Decimal('1.0'),
                }

            for level, info in main_levels.items():
                # B2：调节系数 = mj / M（mj=该子组平均住院费用，M=病种全样本平均）
                mj = self._mean_cost(info['members'])
                coeff = Decimal(str(mj / M)) if M > 0 else Decimal('1.0')
                sub = self._build_auxiliary_subgroup(
                    parent=group, dimension=best_dim, level=level,
                    members=info['members'], coeff=coeff,
                    trigger_coefficient=Decimal(str(best_trigger)),
                )
                new_groups[f"{group.disease_code}_{best_dim}_{level}"] = sub

        return new_groups

    def _classify_members(
        self, members, group, cci_calc, sev_calc, age_calc, icu_calc,
        cost_standard: Optional[object] = None,
    ) -> Dict[str, Dict]:
        """逐条成员分型，返回 {维度: {等级: {'members':[...], 'coeff':x}}}。"""
        avg_cost = group.avg_cost
        # B5：高费用判定基准 = 分值费用标准（RW×点值）；缺省回退病种平均费用
        if cost_standard is None:
            cost_standard = avg_cost
        is_tumor = self._is_tumor_diagnosis(group.main_diag_code)
        dims = {'严重程度': {}, '年龄特征': {}, 'ICU天数': {}, 'CCI': {}}

        for m in members:
            rec = SimpleNamespace(
                main_diag_code=m['main_diag_code'],
                related_diag_code=m['related_diag_code'],
                los=m['los'], age=m['age'], day_age=m['day_age'],
                discharge_status=m['discharge_status'],
                total_cost=m['total_cost'], drug_cost=m['drug_cost'],
                treatment_cost=m['treatment_cost'], icu_days=m['icu_days'],
            )
            # 严重程度（恶性/非恶性分流）
            if is_tumor:
                sev = sev_calc.classify_malignant_tumor(rec, avg_cost, cost_standard)
            else:
                sev = sev_calc.classify_non_malignant(rec)
            self._bucket(dims['严重程度'], sev['level'], sev['coefficient'], m)

            # 年龄特征
            # B11（2026-09-04 用户裁决）：规范「65岁以上利用疾病严重程度辅助分型
            # 进行校正」——65+ 年龄子组结合严重程度字典进一步区分（子组标签形如
            # 「70-79岁·重度」），重度/中度/轻度分别成桶、分别统计触发系数 mj/M。
            age_cls = age_calc.classify(rec, severity_level=sev['level'])
            if age_cls:
                self._bucket(dims['年龄特征'], age_cls['sub_level'],
                             age_cls['coefficient'], m)
            else:
                self._bucket(dims['年龄特征'], "成人(18-64岁)", Decimal('1.0'), m)

            # ICU天数
            icu_cls = icu_calc.classify(m['icu_days'])
            if icu_cls:
                self._bucket(dims['ICU天数'], icu_cls['sub_level'],
                             icu_cls['coefficient'], m)
            else:
                self._bucket(dims['ICU天数'], "无ICU", Decimal('1.0'), m)

            # CCI（B1 修正：仅使用其他诊断/相关诊断，不计入主诊断）
            # 多值其他诊断（'|' 分隔等）逐码拆分，确保合并症 CCI 算全
            related = m.get('related_diag_code') or ''
            diags = self._split_codes(related)
            cci_score = cci_calc.calculate_cci(diags)
            cci_level, cci_coeff = cci_calc.get_cci_level(cci_score)
            m['cci_score'] = cci_score
            self._bucket(dims['CCI'], cci_level, cci_coeff, m)

        return dims

    @staticmethod
    def _bucket(d: Dict, level: str, coeff, m: Dict) -> None:
        """将成员按等级归入维度字典。"""
        if level not in d:
            d[level] = {'members': [], 'coeff': coeff}
        d[level]['members'].append(m)

    @staticmethod
    def _mean_cost(members: List[Dict]) -> float:
        """子组平均住院费用 mj（B2：用于计算 mj/M 数据化系数）。"""
        costs = [float(m['total_cost']) for m in members]
        return sum(costs) / len(costs) if costs else 0.0

    def _cv_after_split(self, buckets: Dict[str, List[Dict]]) -> Tuple[float, None]:
        """拆分后组内（within-subgroup）变异系数：按 n×std / n×mean 加权。

        拆分后各子组按自身均值付费，残余变异即组内变异；该指标低于 CV_before
        即表示费用差异改善。
        """
        num = 0.0
        den = 0.0
        for costs in ([float(m['total_cost']) for m in v] for v in buckets.values()):
            if not costs:
                continue
            mean = sum(costs) / len(costs)
            if mean == 0:
                continue
            var = sum((x - mean) ** 2 for x in costs) / len(costs)
            std = var ** 0.5
            n = len(costs)
            num += n * std
            den += n * mean
        cv = num / den if den > 0 else 0.0
        return cv, None

    def _build_auxiliary_subgroup(
        self, parent: DiseaseGroup, dimension: str, level: str,
        members: List[Dict], coeff: Decimal,
        trigger_coefficient: Decimal = Decimal("1.0"),
    ) -> DiseaseGroup:
        """由父核心病种 + 某一辅助维度等级构造拆分出的子组。"""
        costs = [Decimal(str(m['total_cost'])) for m in members]
        kept, trimmed, lb, ub = self._trim_group_costs(costs)
        kept_count = len(kept)
        avg = sum(kept, Decimal('0')) / kept_count if kept_count else Decimal('0')

        sub = DiseaseGroup(
            disease_code=f"{parent.disease_code}_{dimension}_{level}",
            disease_name=f"{parent.disease_name}({level})",
            main_diag_code=parent.main_diag_code,
            main_diag_name=parent.main_diag_name,
            main_oprn_code=parent.main_oprn_code,
            main_oprn_name=parent.main_oprn_name,
            related_oprn_code=parent.related_oprn_code,
            related_oprn_name=parent.related_oprn_name,
            group_type=parent.group_type,
            case_count=len(members),
            avg_cost=avg,
            original_case_count=len(members),
            trimmed_case_count=kept_count,
            trim_lower_bound=lb, trim_upper_bound=ub, trim_count=trimmed,
            op_category=parent.op_category,
            mixed_subtype="",
            grouping_layer=parent.grouping_layer,
            member_records=members,
            auxiliary_type=dimension,
            auxiliary_level=level,
            auxiliary_coefficient=coeff,
            auxiliary_trigger_coefficient=trigger_coefficient,
            auxiliary_parent_code=parent.disease_code,
            auxiliary_split=False,
        )
        # 子组 CCI / 严重度：若当前维度即对应维度则取该等级，否则继承父组
        if dimension == 'CCI':
            sub.cci_score = Decimal(str(
                {'无': 0, '一般': 1, '严重': 3, '极严重': 5}.get(level, 0)
            ))
        else:
            sub.cci_score = parent.cci_score
        if dimension == '严重程度':
            sub.severity_level = level
            sub.severity_type = '辅助分型'
        else:
            sub.severity_level = parent.severity_level
            sub.severity_type = parent.severity_type
        # 基层病种：父核心病种被拆分后不再单独输出，子组需继承基层属性
        sub.is_grassroot = parent.is_grassroot
        return sub
    
    def _generate_disease_name(self, stats: Dict) -> str:
        """
        生成病种名称
        
        Args:
            stats: 病种统计数据
            
        Returns:
            病种名称
        """
        diag_name = stats.get('main_diag_name', '') or ''
        oprn_name = stats.get('main_oprn_name', '') or ''
        # 处理 NaN（float('nan')）与空值，避免拼出 "肺炎-nan"
        if isinstance(diag_name, float) and diag_name != diag_name:
            diag_name = ''
        if isinstance(oprn_name, float) and oprn_name != oprn_name:
            oprn_name = ''
        if not diag_name:
            diag_name = stats.get('main_diag_code', '') or '未命名'

        if oprn_name:
            return f"{diag_name}-{oprn_name}"
        else:
            return f"{diag_name}-内科"
    
    def separate_core_and_mixed(self, groups: Dict[str, DiseaseGroup]) -> Tuple[List[DiseaseGroup], List[DiseaseGroup]]:
        """
        分离核心病种和综合病种
        
        Args:
            groups: 病种组合字典
            
        Returns:
            (核心病种列表, 综合病种列表)
        """
        core_groups = []
        mixed_groups = []
        
        for key, group in groups.items():
            if group.group_type == GroupType.CORE:
                core_groups.append(group)
            else:
                mixed_groups.append(group)
        
        # 按病例数排序
        core_groups.sort(key=lambda x: x.case_count, reverse=True)
        mixed_groups.sort(key=lambda x: x.case_count, reverse=True)
        
        self.core_groups = core_groups
        self.mixed_groups = mixed_groups
        
        return core_groups, mixed_groups
    
    def merge_mixed_groups(self, mixed_groups: List[DiseaseGroup]) -> List[DiseaseGroup]:
        """
        综合病种终态处理（质量控制收口）

        综合病种已在 cluster_records_to_groups 第二阶段按「手术类别子组 + 主诊断
        3 位码」聚类成型，此处不再按 4 位诊断码回并（否则会破坏四子组结构）。
        本方法仅做质量控制收口：剔除被标记 excluded（聚类后仍低于阈值或组内
        变异系数过高）的综合病种，返回纳入最终目录的综合病种列表。

        Args:
            mixed_groups: 综合病种列表

        Returns:
            纳入最终目录的综合病种列表（已剔除质控不达标者）
        """
        return [g for g in mixed_groups if not g.excluded]
    
    # ------------------------------------------------------------------
    # 基层病种（《DIP3.0 技术规范（征求意见稿）》第三章第四节 / 第十九条）
    #   定义：基层病种是核心病种中的一个类别。地方在适宜基层医疗机构开展且基层
    #         具备诊治能力的病种中，选取诊断明确、治疗方案成熟、临床路径清晰、
    #         医疗风险可控的一定数量病种，设为基层病种。
    #   遴选原则：① 以常见病、多发病、慢性病为主；② 基层医疗机构病例占比较大；
    #             ③ 医疗费用相对稳定，变异系数较低（如 CV 值不超过 0.7）。
    #   分值设定：可不设医疗机构调节系数，即采用同一分值与医疗机构结算（同病同治同价）。
    # ------------------------------------------------------------------
    def is_grassroot_institution(self, level: str) -> bool:
        """判定某病例所属机构是否属「基层医疗机构」（基层病种占比的分子口径）。

        匹配规则（用户 2026-09-05 裁决：前缀匹配 + 扩展）：
          1. 前缀匹配：等级以 grassroot_level_prefixes 中任一项开头
             （如「一级」「一级甲等」「一级乙等」「一级丙等」→ 计入）；
          2. 机构名精确匹配：社区卫生服务中心 / 社区卫生服务站 / 乡镇卫生院；
          3. 其余（二级、三级甲等…）与空值均不计入。

        Args:
            level: 医院等级原始字符串（结算清单「医院等级/医疗机构等级」列）

        Returns:
            是否计入基层机构病例数
        """
        lv = str(level or '').strip()
        if not lv:
            return False
        if any(lv.startswith(p) for p in self.grassroot_level_prefixes):
            return True
        return lv in self.grassroot_levels

    def select_grassroot_groups(
        self,
        groups: Dict[str, DiseaseGroup],
    ) -> Dict[str, DiseaseGroup]:
        """在本地核心病种中遴选基层病种，并留痕遴选依据（self.grassroot_report）。

        口径（用户 2026-09-04 确认）：
          候选池 = 《分组方案》基层病种 sheet 名录（成组时已初判 group.is_grassroot）
          校验项 = ① 属核心病种 ② 基层机构病例占比 ≥ grassroot_min_basic_ratio
                   ③ 组内 CV（裁剪后，与综合病种同口径）≤ grassroot_max_cv
          三项全通过才最终设为基层病种；未通过者置 False 并记录原因。

        Args:
            groups: 聚类成组结果（含核心病种与综合病种）

        Returns:
            已回填 is_grassroot 的病种组字典
        """
        self.grassroot_report = []
        if not self.enable_grassroot:
            return groups

        for group in groups.values():
            # 基层病种是核心病种中的一个类别；综合病种不参与遴选
            if group.group_type != GroupType.CORE:
                group.is_grassroot = False
                continue

            # 非候选：未命中《分组方案》基层病种名录
            if not group.is_grassroot:
                continue

            members = group.member_records or []
            total = len(members)
            # 分子：基层机构病例数（2026-09-05 起用归一化判定，兼容「一级甲等」等写法）
            basic = sum(
                1 for m in members
                if self.is_grassroot_institution(m.get('hospital_level', ''))
            )
            ratio = (basic / total) if total else 0.0

            # 组内 CV：与综合病种同口径，取极端病例裁剪后的费用计算
            costs = [Decimal(str(m.get('total_cost', 0))) for m in members]
            kept, _trimmed, _lb, _ub = self._trim_group_costs(costs)
            cv = self._compute_cv(kept)

            reasons = []
            if total <= 0:
                reasons.append("无成员记录")
            if ratio < self.grassroot_min_basic_ratio:
                reasons.append(
                    f"基层机构病例占比 {ratio:.2%} < {self.grassroot_min_basic_ratio:.0%}"
                )
            if cv > self.grassroot_max_cv:
                reasons.append(f"组内CV {cv:.3f} > {self.grassroot_max_cv}")

            group.is_grassroot = not reasons
            self.grassroot_report.append({
                '病种代码': group.disease_code,
                '病种名称': group.disease_name,
                '主要诊断编码': group.main_diag_code,
                '主要诊断名称': group.main_diag_name,
                '主要手术操作编码': group.main_oprn_code,
                '主要手术操作名称': group.main_oprn_name,
                '分组层次': group.grouping_layer,
                '国家目录方案序号': group.national_seq,
                '病例数': total,
                '基层机构病例数': basic,
                '基层机构病例占比': round(ratio, 4),
                '组内CV(裁剪后)': round(cv, 4),
                '占比阈值': self.grassroot_min_basic_ratio,
                'CV阈值': self.grassroot_max_cv,
                '是否入选': '是' if group.is_grassroot else '否',
                '未入选原因': '；'.join(reasons),
            })
        return groups

    def calculate_all_disease_values(
        self,
        groups: List[DiseaseGroup],
        method: CalculationMethod = CalculationMethod.AVERAGE_COST
    ) -> List[DiseaseGroup]:
        """
        计算所有病种的分值
        
        Args:
            groups: 病种组合列表
            method: 计算方法
            
        Returns:
            更新分值后的病种组合列表
        """
        if not groups:
            return []
        
        # 计算全局平均费用（以裁剪后有效病例数为权重，与各组次均费用口径一致）
        total_cost = sum(g.avg_cost * self._effective_case_count(g) for g in groups)
        total_count = sum(self._effective_case_count(g) for g in groups)
        global_avg_cost = total_cost / total_count if total_count > 0 else Decimal('0')
        
        # 设置计算方法
        self.value_calculator.method = method
        
        # 计算每个病种的分值
        for group in groups:
            group.disease_value = self.value_calculator.calculate_disease_value(
                group.avg_cost, global_avg_cost
            )
        
        return groups
    
    def generate_local_directory(
        self,
        settlement_file: str,
        national_directory_file: str = None,
        output_dir: str = None
    ) -> str:
        """
        生成本地目录库（主入口）
        
        Args:
            settlement_file: 医保清单数据文件路径
            national_directory_file: 国家目录库文件路径（可选）
            output_dir: 输出目录
            
        Returns:
            本地目录库文件路径
        """
        print("=" * 60)
        print("开始生成本地DIP目录库")
        print("=" * 60)
        
        # 1. 加载医保清单数据
        print("\n[1/6] 加载医保清单数据...")
        df = self.load_hospital_settlement_data(settlement_file)
        
        # 2. 加载国家目录库（如果提供）
        if national_directory_file:
            print("\n[2/6] 加载国家目录库...")
            self.load_national_directory(national_directory_file)
        else:
            print("\n[2/6] 跳过国家目录库加载")
        
        # 3. 聚类形成病种组合
        print("\n[3/6] 聚类形成病种组合...")
        groups = self.cluster_records_to_groups(df)
        print(f"   聚类完成: {len(groups)} 个病种组合")
        print(f"   极端病例裁剪: 裁剪前 {self.total_original_cases} 例, "
              f"剔除 {self.total_trimmed_cases} 例, 整体裁剪率 {self.overall_trim_rate*100:.2f}%")

        # 3.2 基层病种遴选（《技术规范》第三章第四节：基层病种是核心病种中的一个类别）
        #     严格排在四层成组之后、辅助分型之前——遴选指标（病例数/基层占比/组内CV）
        #     以完整核心病种为口径测算，不受后续辅助分型拆分影响。
        print("\n[3.2/6] 基层病种遴选（候选=《分组方案》基层病种名录；校验=核心病种+基层占比+CV）...")
        groups = self.select_grassroot_groups(groups)
        _gr_picked = sum(1 for r in self.grassroot_report if r['是否入选'] == '是')
        print(f"   基层病种候选: {len(self.grassroot_report)} 个，入选: {_gr_picked} 个")

        # 3.5 核心病种辅助分型（第三步）：严格排在「①先期→②并项→③诊断辅助细分→
        #     ④基本规则」四层成组（步骤3）之后执行。辅助分型是对已成型核心病种的
        #     触发式细分，不得穿插或提前于四层成组；拆出的子组继承父层 grouping_layer，
        #     从而保持「四层 + 综合病种」的整体输出框架。
        print("\n[3.5/6] 核心病种辅助分型（触发条件评估，必须在四层成组之后）...")
        groups = self.apply_auxiliary_typing(groups)
        print(f"   辅助分型后病种组合数: {len(groups)}（含拆分出的辅助子组）")
        
        # 4. 分离核心病种和综合病种
        print("\n[4/6] 分离核心病种和综合病种...")
        core_groups, mixed_groups = self.separate_core_and_mixed(groups)
        print(f"   核心病种: {len(core_groups)} 个")
        print(f"   综合病种: {len(mixed_groups)} 个")
        
        # 5. 合并综合病种
        print("\n[5/6] 合并综合病种...")
        merged_mixed = self.merge_mixed_groups(mixed_groups)
        print(f"   合并后综合病种: {len(merged_mixed)} 个")
        
        # 6. 计算分值（本地目录库严格按 ①先期→②并项→③诊断辅助细分→④基本规则→综合病种 顺序排列）
        print("\n[6/6] 计算病种分值...")
        all_groups = core_groups + merged_mixed
        all_groups = sorted(all_groups, key=self._layer_sort_key)
        all_groups = self.calculate_all_disease_values(all_groups)

        # 国家目录匹配信息已在成组阶段由引擎逐组回填
        # （national_matched/national_seq/national_dip_code，随目录列导出），
        # 旧「与国家目录库匹配结果.xlsx」独立报表已随 match_with_national_directory 废弃。

        # 导出结果
        print("\n导出本地目录库...")
        output_dir = output_dir if output_dir else str(get_output_dir())
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # 导出完整目录库
        result_df = self._export_full_directory(all_groups)
        full_path = output_path / "本地DIP目录库_完整版.xlsx"
        result_df.to_excel(full_path, index=False, engine='openpyxl')
        print(f"   完整目录库: {full_path}")

        # 导出核心病种
        core_df = self._export_core_directory(core_groups)
        core_path = output_path / "本地DIP目录库_核心病种.xlsx"
        core_df.to_excel(core_path, index=False, engine='openpyxl')
        print(f"   核心病种: {core_path}")

        # 导出综合病种
        mixed_df = self._export_mixed_directory(merged_mixed)
        mixed_path = output_path / "本地DIP目录库_综合病种.xlsx"
        mixed_df.to_excel(mixed_path, index=False, engine='openpyxl')
        print(f"   综合病种: {mixed_path}")

        # 导出统计报告
        stats_df = self._export_statistics(all_groups)
        stats_path = output_path / "本地DIP目录库_统计报告.xlsx"
        stats_df.to_excel(stats_path, index=False, engine='openpyxl')
        print(f"   统计报告: {stats_path}")

        # 基层病种目录（规范：可不设医疗机构调节系数，同病同治同价）
        grassroot_df = self._export_grassroot_directory(all_groups)
        if not grassroot_df.empty:
            gr_path = output_path / "本地DIP目录库_基层病种.xlsx"
            grassroot_df.to_excel(gr_path, index=False, engine='openpyxl')
            print(f"   基层病种目录: {gr_path}（{len(grassroot_df)} 个）")
        else:
            print("   基层病种目录: 本次无入选的基层病种（详见遴选依据表）")

        # 基层病种遴选依据表（候选池逐条：病例数/基层机构占比/组内CV/是否入选/未入选原因）
        if self.grassroot_report:
            sel_df = self._export_grassroot_selection()
            sel_path = output_path / "基层病种遴选依据表.xlsx"
            sel_df.to_excel(sel_path, index=False, engine='openpyxl')
            print(f"   基层病种遴选依据表: {sel_path}")

        # 不纳入分组·主要诊断：导出剔除清单（命中病例不参与分组测算）
        if self.excluded_diag_records:
            excl_df = pd.DataFrame(self.excluded_diag_records)
            excl_path = output_path / "不纳入分组_主要诊断剔除清单.xlsx"
            excl_df.to_excel(excl_path, index=False, engine='openpyxl')
            print(f"   不纳入分组剔除清单: {excl_path}（{self.excluded_diag_cases} 例）")
        
        print("\n" + "=" * 60)
        print("本地DIP目录库生成完成！")
        print("=" * 60)
        
        return str(full_path)
    
    def _export_full_directory(self, groups: List[DiseaseGroup]) -> pd.DataFrame:
        """导出完整目录库（严格按 ①先期→②并项→③诊断辅助细分→④基本规则→综合病种 顺序排列）"""
        ordered = sorted(groups, key=self._layer_sort_key)
        data = []
        for i, group in enumerate(ordered, 1):
            data.append({
                '序号': i,
                'DIP病种代码': group.disease_code,
                'DIP病种名称': group.disease_name,
                '分组层次': group.grouping_layer,
                '主要诊断代码': group.main_diag_code,
                '主要诊断名称': group.main_diag_name,
                '主要手术操作代码': group.main_oprn_code,
                '主要手术操作名称': group.main_oprn_name,
                '相关手术操作代码': group.related_oprn_code,
                '相关手术操作名称': group.related_oprn_name,
                '分组类型': group.group_type.value,
                '病例数': group.case_count,
                '原始病例数': group.original_case_count,
                '裁剪病例数': group.trim_count,
                '费用下限': float(group.trim_lower_bound),
                '费用上限': float(group.trim_upper_bound),
                '次均费用': round(float(group.avg_cost), 2),
                '病种分值(RW)': round(float(group.disease_value), 4),
                'CCI评分': int(group.cci_score),
                '疾病严重程度': group.severity_level,
                '综合病种子组': group.mixed_subtype,
                '手术操作类别': group.op_category,
                '组内变异系数': round(group.cv, 4),
                '质控剔除': '是' if group.excluded else '否',
                '国家目录匹配': '是' if group.national_matched else '否',
                '国家目录方案序号': group.national_seq,
                '国家DIP编码': group.national_dip_code,
                '基层病种': '是' if group.is_grassroot else '否',
                '辅助分型维度': group.auxiliary_type,
                '辅助分型等级': group.auxiliary_level,
                '辅助调节系数': float(group.auxiliary_coefficient),
                '父病种代码': group.auxiliary_parent_code,
            })
        return pd.DataFrame(data)

    def _export_core_directory(self, groups: List[DiseaseGroup]) -> pd.DataFrame:
        """导出核心病种目录（严格按 ①先期→②并项→③诊断辅助细分→④基本规则 顺序排列）"""
        ordered = sorted(groups, key=self._layer_sort_key)
        data = []
        for i, group in enumerate(ordered, 1):
            data.append({
                '序号': i,
                'DIP病种代码': group.disease_code,
                'DIP病种名称': group.disease_name,
                '分组层次': group.grouping_layer,
                '主要诊断代码': group.main_diag_code,
                '主要诊断名称': group.main_diag_name,
                '主要手术操作代码': group.main_oprn_code,
                '主要手术操作名称': group.main_oprn_name,
                '相关手术操作代码': group.related_oprn_code,
                '相关手术操作名称': group.related_oprn_name,
                '病例数': group.case_count,
                '原始病例数': group.original_case_count,
                '裁剪病例数': group.trim_count,
                '费用下限': float(group.trim_lower_bound),
                '费用上限': float(group.trim_upper_bound),
                '次均费用': round(float(group.avg_cost), 2),
                '病种分值(RW)': round(float(group.disease_value), 4),
                'CCI评分': int(group.cci_score),
                '疾病严重程度': group.severity_level,
                '手术操作类别': group.op_category,
                '组内变异系数': round(group.cv, 4),
                '国家目录匹配': '是' if group.national_matched else '否',
                '国家目录方案序号': group.national_seq,
                '国家DIP编码': group.national_dip_code,
                '基层病种': '是' if group.is_grassroot else '否',
                '辅助分型维度': group.auxiliary_type,
                '辅助分型等级': group.auxiliary_level,
                '辅助调节系数': float(group.auxiliary_coefficient),
                '父病种代码': group.auxiliary_parent_code,
            })
        return pd.DataFrame(data)

    def _export_mixed_directory(self, groups: List[DiseaseGroup]) -> pd.DataFrame:
        """导出综合病种目录"""
        data = []
        for i, group in enumerate(groups, 1):
            data.append({
                '序号': i,
                'DIP病种代码': group.disease_code,
                'DIP病种名称': group.disease_name,
                '主要诊断代码': group.main_diag_code,
                '主要诊断名称': group.main_diag_name,
                '合并病种数': group.case_count,
                '总病例数': group.case_count,
                '原始病例数': group.original_case_count,
                '裁剪病例数': group.trim_count,
                '费用下限': float(group.trim_lower_bound),
                '费用上限': float(group.trim_upper_bound),
                '平均费用': round(float(group.avg_cost), 2),
                '病种分值(RW)': round(float(group.disease_value), 4),
                'CCI评分': int(group.cci_score),
                '疾病严重程度': group.severity_level,
                '综合病种子组': group.mixed_subtype,
                '手术操作类别': group.op_category,
                '组内变异系数': round(group.cv, 4),
                '质控剔除': '是' if group.excluded else '否',
            })
        return pd.DataFrame(data)
    
    def _export_grassroot_directory(self, groups: List[DiseaseGroup]) -> pd.DataFrame:
        """导出《本地DIP目录库_基层病种》：入选的基层病种及其分值。

        分值口径（用户 2026-09-04 确认）：全样本合并测算——不分机构等级，采用
        全市该病种全部病例（极端病例裁剪后）的次均费用参与统一分值计算，并按
        规范「可不设医疗机构调节系数」以同一分值与各级医疗机构结算（同病同治同价）。
        """
        data = []
        ordered = sorted([g for g in groups if g.is_grassroot], key=self._layer_sort_key)
        for i, group in enumerate(ordered, 1):
            members = group.member_records or []
            basic = sum(
                1 for m in members
                if self.is_grassroot_institution(m.get('hospital_level', ''))
            )
            ratio = (basic / len(members)) if members else 0.0
            costs = [Decimal(str(m.get('total_cost', 0))) for m in members]
            kept, _trimmed, _lb, _ub = self._trim_group_costs(costs)
            data.append({
                '序号': i,
                '病种代码': group.disease_code,
                '病种名称': group.disease_name,
                '主要诊断编码': group.main_diag_code,
                '主要诊断名称': group.main_diag_name,
                '主要手术操作编码': group.main_oprn_code,
                '主要手术操作名称': group.main_oprn_name,
                '分组层次': group.grouping_layer,
                '国家目录方案序号': group.national_seq,
                '国家DIP编码': group.national_dip_code,
                '病例数': group.case_count,
                '基层机构病例数': basic,
                '基层机构病例占比': round(ratio, 4),
                '组内CV(裁剪后)': round(self._compute_cv(kept), 4),
                '次均费用': round(float(group.avg_cost), 2),
                '病种分值': round(float(group.disease_value), 4),
                '医疗机构调节系数': '不设（同病同治同价）',
            })
        return pd.DataFrame(data)

    def _export_grassroot_selection(self) -> pd.DataFrame:
        """导出《基层病种遴选依据表》：候选池逐条的遴选过程与未入选原因。"""
        return pd.DataFrame(self.grassroot_report)

    def _export_statistics(self, groups: List[DiseaseGroup]) -> pd.DataFrame:
        """导出统计报告"""
        core_count = sum(1 for g in groups if g.group_type == GroupType.CORE)
        mixed_count = sum(1 for g in groups if g.group_type == GroupType.MIXED)
        total_cases = sum(g.case_count for g in groups)
        total_cost = sum(g.avg_cost * g.case_count for g in groups)
        avg_cost = total_cost / total_cases if total_cases > 0 else Decimal('0')
        
        # 基层病种（《技术规范》运行质量监测指标之一：基层病种数量）
        grassroot_count = sum(1 for g in groups if g.is_grassroot)
        grassroot_cases = sum(g.case_count for g in groups if g.is_grassroot)

        stats = [
            {'统计项目': '病种总数', '数值': len(groups)},
            {'统计项目': '核心病种数', '数值': core_count},
            {'统计项目': '综合病种数', '数值': mixed_count},
            {'统计项目': '基层病种数', '数值': grassroot_count},
            {'统计项目': '基层病种覆盖病例数', '数值': grassroot_cases},
            {'统计项目': '总病例数', '数值': total_cases},
            {'统计项目': '总费用', '数值': round(float(total_cost), 2)},
            {'统计项目': '平均次均费用', '数值': round(float(avg_cost), 2)},
            {'统计项目': '核心病种覆盖病例数', '数值': sum(g.case_count for g in groups if g.group_type == GroupType.CORE)},
            {'统计项目': '核心病种覆盖率', '数值': f"{sum(g.case_count for g in groups if g.group_type == GroupType.CORE) / total_cases * 100:.2f}%" if total_cases > 0 else "0%"},
            {'统计项目': '裁剪前总病例数', '数值': self.total_original_cases},
            {'统计项目': '裁剪剔除病例数', '数值': self.total_trimmed_cases},
            {'统计项目': '整体裁剪率', '数值': f"{self.overall_trim_rate * 100:.2f}%"},
            {'统计项目': '质控剔除病例数(综合病种)', '数值': self.excluded_cases},
            {'统计项目': '最终纳入目录病例数', '数值': self.total_original_cases - self.total_trimmed_cases - self.excluded_cases},
        ]
        
        return pd.DataFrame(stats)
    
    def generate_report_summary(self) -> str:
        """生成报告摘要"""
        total_groups = len(self.core_groups) + len(self.mixed_groups)
        total_cases = sum(g.case_count for g in self.core_groups + self.mixed_groups)
        core_cases = sum(g.case_count for g in self.core_groups)
        
        summary = f"""
本地DIP目录库生成报告
====================

1. 病种统计
   - 病种总数: {total_groups}
   - 核心病种: {len(self.core_groups)} 个
   - 综合病种: {len(self.mixed_groups)} 个

2. 病例统计
   - 总病例数: {total_cases}
   - 核心病种病例数: {core_cases}
   - 核心病种覆盖率: {(core_cases/total_cases*100) if total_cases > 0 else 0:.2f}%

3. 分值计算
   - 已完成所有病种分值计算
   
4. 输出文件
   - 本地DIP目录库_完整版.xlsx
   - 本地DIP目录库_核心病种.xlsx
   - 本地DIP目录库_综合病种.xlsx
   - 本地DIP目录库_统计报告.xlsx
"""
        return summary
