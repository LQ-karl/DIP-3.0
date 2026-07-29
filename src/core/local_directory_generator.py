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

    @staticmethod
    def _layer_sort_key(g) -> Tuple[int, int, str]:
        """本地目录库输出的四层排序键：先期→并项→诊断辅助细分→基本规则→综合病种；
        同层内按病例数降序、病种代码升序，保证结果稳定可读。"""
        layer = getattr(g, "grouping_layer", "")
        order = LocalDirectoryGenerator.LAYER_ORDER.get(layer, 9)
        return (order, -getattr(g, "case_count", 0), getattr(g, "disease_code", ""))

    # ---- 核心病种成组·范围与字典常量（《DIP3.0版分组征求地方意见的函》） ----
    # ③ 诊断辅助细分·肿瘤其他诊断允许类目
    #    允许范围: C00-C75 / C76-C80 / C81-C86 / C88 / C90 / C91-C95（不含 D00-D48 / C87 / C89 / C97）
    NEOPLASM_ALLOWED_RANGES = [(0, 75), (76, 80), (81, 86), (88, 88), (90, 90), (91, 95)]

    # ③ 诊断辅助细分·结核耐药拓展码（《函》明确清单，默认启用；
    #    仍可由 data/dip30_grouping_rules.json 的 tb_drug_resistance_ext 追加）
    TB_DRUG_RESISTANT_CODES = (
        "A15.000x010", "A15.100x002", "A15.000x012", "A15.100x003",
        "A15.000x014", "A15.100x004", "A15.000x016", "A15.100x005",
        "A15.000x018", "A15.100x006", "A15.000x020", "A15.100x007",
        "A15.000x022", "A15.100x008", "A15.000x024", "A15.100x009",
        "A15.000x026", "A15.100x010", "A15.000x028", "A15.100x011",
        "A15.500x010", "A15.500x011", "A15.500x012", "A15.500x013",
        "A15.500x014", "A15.500x015", "A15.500x016", "A15.500x017",
        "A15.500x018", "A15.500x019", "A15.500x020", "A15.500x021",
        "A15.500x022", "A15.500x023", "A15.500x024", "A15.500x025",
        "A15.500x026", "A15.500x027", "A15.500x028", "A15.500x029",
        "A19.000x001", "A19.000x002", "A19.000x003", "A19.000x004",
        "A19.000x005", "A19.000x006", "A19.000x007", "A19.000x008",
        "A19.000x009", "A19.000x010", "A19.000x011", "A19.000x012",
        "A19.000x013", "A19.000x014", "A19.000x015", "A19.000x016",
        "A19.000x017", "A19.000x018", "A19.000x019", "A19.000x020",
    )

    # ③ 诊断辅助细分·烧伤（《函》序号 5016–5039，共 24 组，按 程度×面积×年龄 细分）
    # 《函》未给 DIP 编码列，此处按用户补充规则以《函》条目号作为权威编码。
    #   程度(degree_cat) ∈ {三度, 二度, 多部位三度, 多部位二度}
    #     - 主诊断 T29.*(多处/多部位) / T30.*(单部位)
    #     - 程度判定：依据 ICD 名称中含的「一度/二度/三度」（名称从
    #       《ICD10国临版2.0对照医保版2.0_0125》提取），**不使用编码第4位**；
    #       一度烧伤《函》无对应组 → 不进入诊断辅助细分（回落基本规则 ④）
    #   面积(area_cat)：依据 次要诊断 T31/T32 名称中含的「百分比区间」判定（同样不使用第4位）
    #     - <18岁：10%以下 / 10%以上
    #     - ≥18岁：10%以下 / 10%-20% / 20%-30% / 30%以上
    NAT_BURN_TABLE = [
        (5016, "三度", "<18岁", "10%以下"), (5017, "三度", "<18岁", "10%以上"),
        (5018, "三度", "≥18岁", "10%以下"), (5019, "三度", "≥18岁", "10%-20%"),
        (5020, "三度", "≥18岁", "20%-30%"), (5021, "三度", "≥18岁", "30%以上"),
        (5022, "二度", "<18岁", "10%以下"), (5023, "二度", "<18岁", "10%以上"),
        (5024, "二度", "≥18岁", "10%以下"), (5025, "二度", "≥18岁", "10%-20%"),
        (5026, "二度", "≥18岁", "20%-30%"), (5027, "二度", "≥18岁", "30%以上"),
        (5028, "多部位三度", "<18岁", "10%以下"), (5029, "多部位三度", "<18岁", "10%以上"),
        (5030, "多部位三度", "≥18岁", "10%以下"), (5031, "多部位三度", "≥18岁", "10%-20%"),
        (5032, "多部位三度", "≥18岁", "20%-30%"), (5033, "多部位三度", "≥18岁", "30%以上"),
        (5034, "多部位二度", "<18岁", "10%以下"), (5035, "多部位二度", "<18岁", "10%以上"),
        (5036, "多部位二度", "≥18岁", "10%以下"), (5037, "多部位二度", "≥18岁", "10%-20%"),
        (5038, "多部位二度", "≥18岁", "20%-30%"), (5039, "多部位二度", "≥18岁", "30%以上"),
    ]
    # 年龄分界（岁）：《函》烧伤 <18岁 / ≥18岁
    BURN_AGE_ADULT = 18
    # 先期分组·低出生体重判定阈值（g）：高于该值不属低出生体重，不进入先期分组
    LBW_BIRTH_WEIGHT_THRESHOLD = 2500

    def __init__(
        self,
        threshold: int = 15,
        data_dir: str = None,
        lower_quantile: float = 0.025,
        upper_quantile: float = 0.975,
        min_trim_group_size: int = 25,
        max_overall_trim_rate: float = 0.08,
        exclude_below_threshold: bool = False,
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

        self.grouping_engine = DIPGroupingEngine(threshold=threshold)
        self.value_calculator = ValueCalculator()
        self.data_loader = DataLoader(data_dir)

        # CCI 与疾病严重程度（中重度分型）字典（权威数据源，规范逻辑测算）
        self.cci_exact: Dict[str, int] = {}      # 精确诊断码 -> CCI 分数
        self.cci_prefix: Dict[str, int] = {}     # 3 位前缀 -> CCI 分数
        self.severity_entries: List[Dict] = []   # 中重度分型字典条目
        self._load_dictionaries()

        # 烧伤程度/面积名称查表：从《ICD10国临版2.0对照医保版2.0_0125》提取名称，
        # 用于按名称判定「一度/二度/三度」与「面积百分比」，而非编码第4位
        self._burn_name_map: Dict[str, str] = {}
        self._load_icd10_name_map()

        # 手术操作类别映射（综合病种四子组所需）
        # 国临版手术码 -> 类别（手术/治疗性操作/诊断性操作/介入治疗）
        self._clinical_op_category: Dict[str, str] = {}
        # 医保版手术码 -> 国临版手术码（桥接，用于把清单里的医保码查到类别）
        self._insurance_to_clinical: Dict[str, str] = {}
        self._load_op_category_maps()

        # 核心病种前三层成组规则（先期分组 / 并项规则 / 诊断辅助细分）
        # 数据驱动、可插拔：内置种子取自《DIP 3.0版分组征求地方意见的函》（概念+示例）；
        # 若 data/dip30_grouping_rules.json 存在，则覆盖/扩充，便于后续接入官方权威清单。
        # 诊断辅助细分（烧伤/肿瘤/结核）按用户约定留待「第三步」实现，此处仅占位。
        self._init_grouping_rules()

        # 综合病种质量控制：组内变异系数(CV)上限，超过则标记剔除
        self.max_cv_threshold: float = 1.0

        # 综合病种被质控剔除的病例数（统计报告用）
        self.excluded_cases: int = 0

        # 存储结果
        self.raw_groups = {}  # 原始聚类结果
        self.core_groups = []  # 核心病种
        self.mixed_groups = []  # 综合病种
        self.national_directory = None  # 国家目录库

        # 烧伤国家目录（函5016-5039）自包含：无论是否加载 xlsx 均可用
        # （xlsx 导出截断缺失该段，故烧伤查表直接来自《函》PDF 第95–96页）
        self._nat_dip_codes: set = set()
        self._nat_rows_by_dip: Dict[str, dict] = {}
        self._build_burn_national()

        # 极端病例裁剪统计
        self.total_original_cases = 0   # 裁剪前总病例数
        self.total_trimmed_cases = 0    # 裁剪剔除的病例数
        self.overall_trim_rate = 0.0    # 整体裁剪率

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
        """加载 CCI 与疾病严重程度（中重度分型）字典，构建查表结构。"""
        self._load_cci_dictionary()
        self._load_severity_dictionary()

    def _load_cci_dictionary(self) -> None:
        """加载 CCI.xlsx：ICD10 代码 -> Charlson 组成部分 -> CCI 分数。

        CCI 分数依据 Charlson 合并症指数权重（DIP3.0 技术规范逻辑）。
        """
        # Charlson 各组成部分权重（规范逻辑）
        charlson_weights = {
            "心肌梗死": 1, "充血性心力衰竭": 1, "周围血管疾病": 1, "脑血管疾病": 1,
            "痴呆": 1, "慢性肺部疾病": 1, "结缔组织病": 1, "溃疡病": 1,
            "轻度肝脏疾病": 1, "糖尿病": 1,
            "偏瘫": 2, "中度或重度肾脏疾病": 2, "糖尿病合并并发症": 2,
            "任何肿瘤": 2, "白血病": 2, "淋巴瘤": 2,
            "中度或重度肝脏疾病": 3, "转移性实体瘤": 6, "AIDS": 6,
        }
        try:
            df = self.data_loader.load_cci_index()
        except Exception as e:
            print(f"警告: 加载 CCI 字典失败，CCI 评分将为 0: {e}")
            return

        for _, row in df.iterrows():
            code = str(row.get("ICD10代码", "")).strip()
            component = str(row.get("Charlson组成部分", "")).strip()
            if not code:
                continue
            score = 0
            for key, val in charlson_weights.items():
                if key in component:
                    score = max(score, val)
            if score == 0:
                continue
            self.cci_exact[code] = max(self.cci_exact.get(code, 0), score)
            prefix3 = code[:3]
            self.cci_prefix[prefix3] = max(self.cci_prefix.get(prefix3, 0), score)
        print(f"已加载 CCI 字典: {len(self.cci_exact)} 条精确码")

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
        """严重程度/辅助分型的优先级（数值越大越重）。"""
        order = {"重度": 6, "中度": 5, "轻度": 4, "转移": 3, "放疗": 2, "化疗": 1}
        return order.get(name, 0)

    def _compute_group_cci(self, diag_codes: List[str]) -> int:
        """病种组级 CCI 评分：按 Charlson 分类取同类最高分，再求和。

        Args:
            diag_codes: 该病种组合涉及的诊断码列表（主诊断 + 相关诊断）
        """
        calc = CCICalculator()
        max_scores: Dict[str, int] = {}
        for code in diag_codes:
            if not code:
                continue
            code4 = code[:4]
            prefix3 = code[:3]
            score = (
                self.cci_exact.get(code)
                or self.cci_exact.get(code4)
                or self.cci_prefix.get(prefix3, 0)
            )
            if score > 0:
                category = calc._get_disease_category(prefix3)
                if category not in max_scores or score > max_scores[category]:
                    max_scores[category] = score
        return sum(max_scores.values())

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
            df = pd.read_csv(file_path, encoding='utf-8', dtype=str)
        else:
            raise ValueError(f"不支持的文件格式: {file_path}")
        
        self.national_directory = df
        self._build_national_lookups(df)
        print(f"已加载国家目录库: {len(df)} 条记录")
        return df

    def _build_national_lookups(self, df: pd.DataFrame):
        """从国家目录库解析 ①/③ 特殊组的权威 DIP 编码映射，供成组时严格对齐。

        仅解析《函》明确的三类先期/诊断辅助细分行：
          - 低出生体重先期(P07-01..05)：按 出生体重 分档
          - 肿瘤诊断辅助细分(Z51.1/Z51.8)：按 (主诊断, C范围, 治疗码) 唯一映射
          - 结核诊断辅助细分(A15-A16/A17/A18/A19)：按 (类目, 主手术集, 耐药) 唯一映射
        其余行（普通核心/综合病种）用于 match_with_national_directory 的通用回写。
        """
        self._nat_dip_codes: set = set()
        self._nat_rows_by_dip: Dict[str, dict] = {}
        for _, r in df.iterrows():
            dip = str(r.get('DIP编码', '')).strip()
            if dip.lower() == 'nan' or not dip:
                continue
            self._nat_dip_codes.add(dip)
            self._nat_rows_by_dip[dip] = r.to_dict()

        # ---- 低出生体重先期(P07-01..05) ----
        self._nat_lbw: List[dict] = []
        for _, r in df.iterrows():
            if str(r.get('主要诊断编码', '')).strip() != 'P07':
                continue
            if '出生体重' not in str(r.get('主要诊断名称', '')):
                continue
            wt = str(r.get('相关手术操作编码', '') or '')
            m_dash = re.search(r'(\d+)\s*-\s*(\d+)', wt)
            if m_dash:
                lo, hi = int(m_dash.group(1)), int(m_dash.group(2)) + 1
            else:
                m_lt = re.search(r'<\s*(\d+)', wt)
                if not m_lt:
                    continue
                lo, hi = 0, int(m_lt.group(1)) + 1
            self._nat_lbw.append({'dip': str(r['DIP编码']).strip(), 'lo': lo, 'hi': hi})

        # ---- 肿瘤诊断辅助细分(Z51.1/Z51.8，主要手术操作列放 C 范围、相关列放治疗组合) ----
        self._nat_tumor: Dict[Tuple[str, str, str], str] = {}
        for _, r in df.iterrows():
            md = str(r.get('主要诊断编码', '')).strip()
            if md not in ('Z51.1', 'Z51.8'):
                continue
            c = str(r.get('主要手术操作编码', '') or '').strip()
            if not c.startswith('C'):
                continue
            t = re.sub(r'^[^0-9]*', '', str(r.get('相关手术操作编码', '') or '').strip().replace(' ', ''))
            self._nat_tumor[(md, c, t)] = str(r['DIP编码']).strip()

        # ---- 结核诊断辅助细分(A15-A16/A17/A18/A19) ----
        self._nat_tb: Dict[Tuple[str, tuple, bool], str] = {}
        self._nat_tb_ops: Dict[str, List[tuple]] = {}
        for _, r in df.iterrows():
            md = str(r.get('主要诊断编码', '')).strip()
            if md not in ('A15-A16', 'A17', 'A18', 'A19'):
                continue
            raw_op = r.get('主要手术操作编码', '')
            op = '' if (raw_op is None or str(raw_op).strip().lower() == 'nan') else str(raw_op).strip()
            op_set = tuple(sorted(x.upper().replace(' ', '') for x in re.split(r'[| ]+', op) if x)) if op else ()
            # 结核耐药标志位于「相关手术操作编码」列（值为 否/是），而非名称列
            raw_relop = r.get('相关手术操作编码', '')
            rel_flag = '' if (raw_relop is None or str(raw_relop).strip().lower() == 'nan') else str(raw_relop).strip()
            resistant = (rel_flag == '是')
            dip = str(r['DIP编码']).strip()
            self._nat_tb[(md, op_set, resistant)] = dip
            if op_set not in self._nat_tb_ops.setdefault(md, []):
                self._nat_tb_ops[md].append(op_set)

        # 烧伤（函5016-5039）自包含：重新并入（_nat_dip_codes 已在上文清空重建）
        self._build_burn_national()

    def _build_burn_national(self):
        """构建烧伤国家目录（函5016-5039）查表：程度×年龄×面积 → 条目号。

        自包含（来自《函》PDF 第95–96页），不依赖 xlsx 导出（其截断缺失该段）。
        在 __init__ 与 load_national_directory 后均调用，保证烧伤查表始终可用。
        """
        self._nat_burn_by_key: Dict[Tuple[str, str, str], int] = {}
        for item, degree_cat, age_cat, area_cat in self.NAT_BURN_TABLE:
            self._nat_burn_by_key[(degree_cat, age_cat, area_cat)] = item
            code = str(item)
            if code not in self._nat_dip_codes:
                self._nat_dip_codes.add(code)
                self._nat_rows_by_dip[code] = {
                    'DIP编码': code,
                    '主要诊断编码': 'T29/T30',
                    '主要诊断名称': f'烧伤（{degree_cat}）',
                    '主要手术操作编码': '',
                    '主要手术操作名称': '',
                    '相关手术操作编码': '',
                    '相关手术操作名称': f'年龄{age_cat}，面积{area_cat}',
                }

    def _load_icd10_name_map(self) -> None:
        """从《ICD10国临版2.0对照医保版2.0_0125》抽取 T29/T30/T31/T32 名称映射。

        烧伤（③ 诊断辅助细分）程度/面积严格按 ICD *名称* 判定（用户明确要求：
        使用名称中的「一度/二度/三度」与「百分比区间」，不使用编码第4位）：
          - 程度：主诊断名称含 一度/二度/三度/四度；多处/多部位 → 多部位；
          - 面积：次要诊断 T31/T32 名称含百分比区间（如 体表10-19% / 累及体表20%~29%）。
        仅抽取烧伤相关(T29/T30/T31/T32)编码的 国临版名称与医保版2.0名称，
        构建 code→name 查表（同时收纳两列编码，兼容清单用国临版或医保版码）。
        """
        fname = "ICD10国临版2.0对照医保版2.0_0125.xlsx"
        path = os.path.join(self.data_dir, fname)
        if not os.path.exists(path):
            print(f"警告: 未找到 {fname}，烧伤程度/面积名称判定不可用(不进入诊断辅助细分)")
            return
        try:
            import openpyxl
            wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
            ws = wb.active
            rows = list(ws.iter_rows(values_only=True))
            hdr = rows[0]
            ci = {str(h): i for i, h in enumerate(hdr)}
            c_cl, n_cl = ci.get("国临版编码"), ci.get("国临版名称")
            c_im, n_im = ci.get("医保版2.0编码"), ci.get("医保版2.0名称")
            for r in rows[1:]:
                for col_c, col_n in ((c_cl, n_cl), (c_im, n_im)):
                    if col_c is None or col_n is None:
                        continue
                    code = str(r[col_c] or "").strip().upper()
                    name = str(r[col_n] or "").strip()
                    if not code or not name:
                        continue
                    if code[:3] in ("T29", "T30", "T31", "T32"):
                        # 国临版优先；同码两列同名时后者不覆盖；键统一大写以便不区分 x/X
                        self._burn_name_map.setdefault(code, name)
        except Exception as e:
            print(f"警告: 加载 ICD10 名称映射失败，烧伤名称判定不可用: {e}")
            return
        print(f"已加载烧伤 ICD 名称映射: {len(self._burn_name_map)} 条(T29/T30/T31/T32)")

    def _icd10_burn_name(self, code: str) -> str:
        """按编码查烧伤相关 ICD 名称（兼容国临版/医保版码，并做前缀匹配）。

        返回名称字符串；查不到返回空串。前缀匹配示例：T30.2 -> T30.200(二度烧伤)、
        T29.300x001 -> T29.300(多处三度烧伤)。
        """
        code = self._clean_str(code).upper()
        if not code:
            return ""
        if code in self._burn_name_map:
            return self._burn_name_map[code]
        prefix_hits = [k for k in self._burn_name_map if k.startswith(code)]
        if prefix_hits:
            return self._burn_name_map[min(prefix_hits, key=len)]
        rev_hits = [k for k in self._burn_name_map if code.startswith(k)]
        if rev_hits:
            return self._burn_name_map[max(rev_hits, key=len)]
        return ""

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
            df = pd.read_csv(file_path, encoding='utf-8', dtype=str)
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
        }
        
        # 重命名列
        df_renamed = df.rename(columns=column_mapping)
        return df_renamed
    
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

    # ------------------------------------------------------------------
    # 核心病种前三层成组规则（先期分组 / 并项规则 / 诊断辅助细分）
    # 数据驱动、可插拔：内置种子来自《DIP 3.0版分组征求地方意见的函》，
    # 权威清单可由 data/dip30_grouping_rules.json 覆盖/扩充（用户后续补充）。
    # ------------------------------------------------------------------
    def _init_grouping_rules(self) -> None:
        """初始化核心病种前三层成组规则（先期 / 并项 / 辅助细分占位）。"""
        # ---------- ① 先期分组 ----------
        # 低出生体重儿：诊断 P07.x（ICD-10 孕期短和低出生体重章）
        # 器官移植（实体器官/造血干细胞）：按手术码前缀精确判定。注意临床分类中
        # 「移植」一词极广（角膜/皮瓣/骨/腱/冠脉旁路等均含“移植”），故只用实体
        # 器官移植的稳定前缀，避免误伤组织移植。
        self._priority_transplant_ops = {
            "55.6", "55.69",          # 肾移植
            "50.51", "50.59",          # 肝移植
            "37.51",                  # 心脏移植
            "33.5",                   # 肺移植
            "52.8",                   # 胰腺移植
            "46.97",                  # 小肠/肠移植
            "41.0", "41.04", "41.05", "41.06", "41.07", "41.08", "41.09",  # 造血干细胞移植
        }
        # 呼吸循环支持：ECMO/体外循环 39.6x、CRRT 39.95x、呼吸机 96.7x、
        # 无创通气 93.9x（睡眠呼吸暂停 G47.3 不属先期）、IABP 主动脉内球囊反搏 37.6x
        self._priority_life_support_ops = {"39.6", "39.95", "96.7", "93.9", "37.6"}

        # ③ 诊断辅助细分·结核耐药拓展码（默认内置《函》明确清单；
        #   仍可由 data/dip30_grouping_rules.json 的 tb_drug_resistance_ext 追加）
        self._tb_drug_resistance_ext: set = set(self.TB_DRUG_RESISTANT_CODES)

        # ---------- ② 并项规则 ----------
        # 诊断并项：指定诊断族在 3 位码下归并（种子：心绞痛 I20.x -> I20）
        self._merge_diag_families = {"I20"}
        # 手操并项（诊断维度）：指定诊断下忽略具体术式、整体并项（种子：D18.0 血管瘤多术式）
        self._op_merge_diag_set = {"D18.0"}
        # 手操并项（术式维度）：个体手术码 -> 规范并项码（种子：肾动脉支架+球囊联合手术）
        self._op_merge_map = {
            "39.9016": "REN_STENT_BALLOON",   # 肾动脉支架置入术
            "39.5002": "REN_STENT_BALLOON",   # 肾动脉球囊血管成形术
        }

        # 尝试从外部 JSON 覆盖/扩充（用户后续补充权威清单，无需改代码）
        self._load_grouping_rules_from_json()

    def _load_grouping_rules_from_json(self) -> None:
        """若存在 data/dip30_grouping_rules.json，则覆盖/扩充内置种子规则。"""
        import os, json
        p = os.path.join(self.data_dir, "dip30_grouping_rules.json")
        if not os.path.exists(p):
            return
        try:
            with open(p, "r", encoding="utf-8") as f:
                rules = json.load(f)
            if isinstance(rules.get("merge_diag_families"), list):
                self._merge_diag_families |= set(rules["merge_diag_families"])
            if isinstance(rules.get("op_merge_diag_set"), list):
                self._op_merge_diag_set |= set(rules["op_merge_diag_set"])
            if isinstance(rules.get("op_merge_map"), dict):
                self._op_merge_map.update(rules["op_merge_map"])
            if isinstance(rules.get("priority_transplant_ops"), list):
                self._priority_transplant_ops |= set(rules["priority_transplant_ops"])
            if isinstance(rules.get("priority_life_support_ops"), list):
                self._priority_life_support_ops |= set(rules["priority_life_support_ops"])
            if isinstance(rules.get("tb_drug_resistance_ext"), list):
                self._tb_drug_resistance_ext |= set(rules["tb_drug_resistance_ext"])
            print(f"已加载外部成组规则: {p}")
        except Exception as e:
            print(f"警告: 加载成组规则 JSON 失败: {e}")

    def _detect_priority(
        self, main_diag_code: str, main_oprn_code: str, related_oprn_code: str,
        day_age: int = 0, birth_weight: Decimal = Decimal("0"),
        age: int = 0, birth_date: str = "", admission_date: str = "",
    ) -> str:
        """先期分组检测：返回先期成组键或 None。

        先期分组均不区分主要诊断，依据《函》4956–4973：
          - 器官移植：实体/造血干细胞移植手术码前缀（依靠主要/相关手术操作）
          - 呼吸循环支持：ECMO/CRRT/呼吸机/无创通气/IABP 手术码前缀（依靠手术操作）
          - 低出生体重儿：年龄不足1周岁（天龄/年龄/出生+入院日期推算）且出生体重
            属低出生体重(<2500g)，按 年龄分桶 + 出生体重分桶 分组
        """
        diag = self._clean_str(main_diag_code).upper()
        ops = [self._norm_op_code(main_oprn_code), self._norm_op_code(related_oprn_code)]
        ops = [o for o in ops if o]

        # 器官移植（实体器官/造血干细胞）：手术码前缀精确匹配，不区分主要诊断
        for op in ops:
            if any(op.startswith(p) for p in self._priority_transplant_ops):
                return f"PRI|TRANSPLANT|{op}"

        # 呼吸循环支持：ECMO/CRRT/呼吸机/无创通气/IABP，不区分主要诊断
        for op in ops:
            if any(op.startswith(p) for p in self._priority_life_support_ops):
                return f"PRI|LIFESUPPORT|{op}"

        # 低出生体重儿：不区分主要诊断，依靠 年龄(天) + 新生儿出生体重(g) 分组
        # 仅当 年龄不足1周岁 且 出生体重属低出生体重(<2500g) 时进入先期分组，
        # 避免与 ③ 烧伤等婴儿病种冲突（正常体重婴儿不占先期分组）。
        if self._is_under_one_year(age, day_age, birth_date, admission_date):
            if Decimal("0") < birth_weight < Decimal(str(self.LBW_BIRTH_WEIGHT_THRESHOLD)):
                # 对齐国家目录库先期 LBW：仅 <29天(≤28天) 进入，按出生体重档位取权威 DIP 码
                days = self._age_in_days(day_age, birth_date, admission_date)
                if days is not None and days <= 28:
                    if getattr(self, 'national_directory', None) is not None and getattr(self, '_nat_lbw', None):
                        dip = self._lbw_dip_for(birth_weight)
                        if dip:
                            return dip
                    weight_bucket = self._lbw_weight_bucket(birth_weight)
                    return f"PRI|LBW|新生儿期|{weight_bucket}"

        return None

    # ------------------------------------------------------------------
    # 先期分组辅助：年龄/出生体重判定（低出生体重儿，依据《函》4969–4973）
    # ------------------------------------------------------------------
    @staticmethod
    def _is_under_one_year(age, day_age, birth_date, admission_date) -> bool:
        """判断是否年龄不足1周岁（<365天）。

        优先用 出生日期 + 入院时间 推算；否则以 天龄(day_age) > 0 判定。
        注意：年龄(岁)字段缺失默认 0，不可单独作为判婴依据，以免成年患者被误判。
        """
        import datetime
        bd = LocalDirectoryGenerator._clean_str(birth_date)
        ad = LocalDirectoryGenerator._clean_str(admission_date)
        if bd and ad:
            try:
                b = datetime.datetime.strptime(bd[:10], "%Y-%m-%d")
                a = datetime.datetime.strptime(ad[:10], "%Y-%m-%d")
                days = (a - b).days
                if days >= 0:
                    return days < 365
            except Exception:
                pass
        try:
            if int(day_age or 0) > 0:
                return True
        except Exception:
            pass
        return False

    @staticmethod
    def _lbw_weight_bucket(weight_grams) -> str:
        """新生儿出生体重(g)分桶：超低<1000 / 极低1000-1499 / 低1500-2499。"""
        try:
            w = float(weight_grams)
        except Exception:
            return "未知"
        if w < 1000:
            return "超低出生体重"
        if w < 1500:
            return "极低出生体重"
        if w < 2500:
            return "低出生体重"
        return "正常体重"

    @staticmethod
    def _calc_age_years(age, day_age, birth_date, admission_date) -> int:
        """推算年龄(岁)：优先 出生日期+入院时间；否则 年龄(岁)；否则 天龄//365。"""
        import datetime
        bd = LocalDirectoryGenerator._clean_str(birth_date)
        ad = LocalDirectoryGenerator._clean_str(admission_date)
        if bd and ad:
            try:
                b = datetime.datetime.strptime(bd[:10], "%Y-%m-%d")
                a = datetime.datetime.strptime(ad[:10], "%Y-%m-%d")
                days = (a - b).days
                if days >= 0:
                    return days // 365
            except Exception:
                pass
        try:
            if int(age or 0) > 0:
                return int(age)
        except Exception:
            pass
        try:
            if int(day_age or 0) > 0:
                return int(day_age) // 365
        except Exception:
            pass
        return 0

    @staticmethod
    def _age_in_days(day_age, birth_date, admission_date):
        """推算年龄(天)；优先天龄，其次 出生日期+入院时间 之差；无法判定返回 None。"""
        try:
            if int(day_age or 0) > 0:
                return int(day_age)
        except Exception:
            pass
        import datetime
        bd = LocalDirectoryGenerator._clean_str(birth_date)
        ad = LocalDirectoryGenerator._clean_str(admission_date)
        if bd and ad:
            try:
                b = datetime.datetime.strptime(bd[:10], "%Y-%m-%d")
                a = datetime.datetime.strptime(ad[:10], "%Y-%m-%d")
                d = (a - b).days
                if d >= 0:
                    return d
            except Exception:
                pass
        return None

    @staticmethod
    def _c_code_to_range(c3: str) -> str:
        """3 位 C 码 → 国家目录肿瘤 C 范围标签（C00-C75/C76-C80/C81-C86/C88/C90/C91-C95）。"""
        if not (len(c3) >= 3 and c3[0] == 'C' and c3[1:3].isdigit()):
            return ""
        n = int(c3[1:3])
        if 0 <= n <= 75:
            return "C00-C75"
        if 76 <= n <= 80:
            return "C76-C80"
        if 81 <= n <= 86:
            return "C81-C86"
        if n == 88:
            return "C88"
        if n == 90:
            return "C90"
        if 91 <= n <= 95:
            return "C91-C95"
        return ""

    @staticmethod
    def _treatment_tag_to_code(tag: str) -> str:
        """治疗方式中文标签 → 国家目录手术操作码（化疗/靶向/免疫 组合）。"""
        return {
            "免疫": "99.2800x005",
            "化疗": "99.2503",
            "化疗+免疫": "99.2503+99.2800x005",
            "化疗+靶向": "99.2503+99.2800x006",
            "化疗+靶向+免疫": "99.2503+99.2800x006+99.2800x005",
            "靶向": "99.2800x006",
            "靶向+免疫": "99.2800x006+99.2800x005",
        }.get(tag, "")

    def _tumor_dip_for(self, main_diag, neo3, main_oprn, related_oprn) -> str:
        """反查肿瘤诊断辅助细分 DIP 码（(主诊断, C范围, 治疗码) → Z51.1/Z51.8-XX）。"""
        c_range = LocalDirectoryGenerator._c_code_to_range(neo3)
        if not c_range:
            return ""
        tag = self._tumor_treatment_tag(main_oprn, related_oprn)
        code = LocalDirectoryGenerator._treatment_tag_to_code(tag)
        if not code:
            return ""
        main_z = "Z51.1" if self._clean_str(main_diag).upper().startswith("Z51.1") else "Z51.8"
        return self._nat_tumor.get((main_z, c_range, code), "")

    def _lbw_dip_for(self, birth_weight) -> str:
        """按出生体重(g)反查国家目录低出生体重先期 DIP 码(P07-01..05)。"""
        if not getattr(self, '_nat_lbw', None):
            return ""
        try:
            w = float(birth_weight)
        except Exception:
            return ""
        for b in self._nat_lbw:
            if b['lo'] <= w < b['hi']:
                return b['dip']
        return ""

    def _tb_op_set_for(self, cat, main_oprn, related_oprn):
        """按病例手术码反查国家目录结核手术变体 op_set（A15-A16 7 种 / A17 含腰椎穿刺 / 其他无手术）。"""
        codes = set()
        for o in (self._split_codes(main_oprn) + self._split_codes(related_oprn)):
            codes.add(o.upper().replace(' ', ''))
        if not codes:
            return ()
        for op_set in self._nat_tb_ops.get(cat, []):
            if any(c in op_set for c in codes):
                return op_set
        return ()  # 未落在任何具体术式变体 → 归入“无特定手术”空 op_set 组

    def _tb_dip_for(self, cat, main_oprn, related_oprn, resistant) -> str:
        """反查结核诊断辅助细分 DIP 码（A15-A16-00..13 / A17-00..03 / A18-00..01 / A19-00..01）。"""
        op_set = self._tb_op_set_for(cat, main_oprn, related_oprn)
        dip = self._nat_tb.get((cat, op_set, resistant))
        if dip is None:
            # 容错：该术式组合无对应耐药/非耐药行时，退而取同术式另一耐药态
            dip = self._nat_tb.get((cat, op_set, not resistant), "")
        return dip or ""

    def _get_op_category(self, insurance_op_code: str) -> str:
        """医保版手术码 -> 手术类别（手术/治疗性操作/诊断性操作/介入治疗/''）。"""
        code = self._clean_str(insurance_op_code)
        if not code:
            return ""
        clinical = self._insurance_to_clinical.get(code, code)  # 找不到桥接则原样尝试
        return self._clinical_op_category.get(clinical, "")

    def _get_op_subtype(self, insurance_op_code: str) -> str:
        """医保版手术码 -> 综合病种子组类型。介入治疗并入相关手术组。"""
        if not self._clean_str(insurance_op_code):
            return "内科诊疗组"
        cat = self._get_op_category(insurance_op_code)
        if cat == "诊断性操作":
            return "诊断性操作组"
        if cat == "治疗性操作":
            return "治疗性操作组"
        # 手术 / 介入治疗 / 未匹配到类别 -> 相关手术组
        return "相关手术组"

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

    def _op_code_matches(self, local_op: str, nat_op_raw: str) -> bool:
        """判断本地手术码能否匹配国家目录库的某个手术码候选。

        - 国家目录库可能用 '|' 列举多个等价码，逐一比对；
        - 本地若使用医保版2.0 码，经 ICD9 国临↔医保对照桥接到国临版3.0 再比对。
        """
        local = self._clean_str(local_op)
        if local == "":
            return self._norm_op_code(nat_op_raw) == ""
        local_norm = self._norm_op_code(local)
        # 本地码可能本就是国临版，也可能需桥接
        local_bridge = self._insurance_to_clinical.get(local_norm, local_norm)
        nat_candidates = [self._norm_op_code(c) for c in str(nat_op_raw).split("|")] \
            if self._clean_str(nat_op_raw) else [""]
        return local_norm in nat_candidates or local_bridge in nat_candidates

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

        顺序：① 先期分组 → ② 并项规则 → ③ 诊断辅助细分 → ④ 基本规则（兜底）。
        每条记录仅命中最高优先级的一层，得到唯一成组键（与后续测算顺序一致）。

        ① 先期分组：器官移植 / 呼吸循环支持 / 低出生体重儿等，多不区分主要诊断，
           依靠主要手术操作（见 _detect_priority）。
        ② 并项规则：
           - 诊断并项：指定诊断族在 3 位码下归并（如心绞痛 I20.x -> I20）；
           - 手操并项（诊断维度）：指定诊断下忽略具体术式整体并项（如 D18.0 血管瘤）；
           - 手操并项（术式维度）：个体术式 -> 规范并项码（如肾动脉支架+球囊联合）。
        ③ 诊断辅助细分（肿瘤放化疗靶向免疫 / 结核耐药 / 烧伤）：
           与第三步「触发式辅助分型」(严重程度/年龄/ICU/CCI) 机制/阶段/字段/输出均不同，
           此处仅做核心病种成组层细分，产出独立核心病种组（各自 RW）。
        ④ 基本规则：主要诊断 4 位码 + 主要手术操作（+ 相关手术操作）。
        """
        diag4 = self._extract_icd4(main_diag_code)
        diag3 = self._extract_icd3(main_diag_code)

        # ① 先期分组（最高优先级，多不区分主要诊断）
        pri = self._detect_priority(
            main_diag_code, main_oprn_code, related_oprn_code,
            day_age, birth_weight, age, birth_date, admission_date,
        )
        if pri is not None:
            return pri, "先期分组"

        # ② 并项规则
        # 2a 诊断并项：指定诊断族用 3 位码归并（命中即属并项规则层）
        if diag3 in self._merge_diag_families:
            diag_key = diag3
            if main_oprn_code:
                return (f"{diag_key}|{main_oprn_code}|{related_oprn_code}"
                        if related_oprn_code else f"{diag_key}|{main_oprn_code}|"), "并项规则"
            return f"{diag_key}||", "并项规则"
        diag_key = diag4
        # 2b 手操并项（诊断维度）：指定诊断下整体并项，忽略具体术式
        if self._clean_str(main_diag_code).upper() in self._op_merge_diag_set:
            return f"{diag4}|OPMERGE", "并项规则"
        # 2c 手操并项（术式维度）：个体术式 -> 规范并项码（联合/相似并项，忽略相关手术）
        main_canon = self._op_merge_map.get(self._norm_op_code(main_oprn_code))
        rel_canon = self._op_merge_map.get(self._norm_op_code(related_oprn_code))
        if main_canon is not None or rel_canon is not None:
            canon = main_canon or rel_canon
            return f"{diag_key}|{canon}|", "并项规则"

        # ③ 诊断辅助细分（肿瘤放化疗靶向免疫 / 结核耐药 / 烧伤）
        #   与第三步「触发式辅助分型」(严重程度/年龄/ICU/CCI) 机制/阶段/字段/输出均不同，
        #   此处仅做核心病种成组层细分，产出独立核心病种组（各自 RW）。
        aux = self._refine_diagnostic_auxiliary(
            main_diag_code, main_oprn_code, related_oprn_code, related_diag_code,
            age=age, day_age=day_age, birth_date=birth_date, admission_date=admission_date,
        )
        if aux is not None:
            return aux, "诊断辅助细分"

        # ④ 基本规则（兜底）
        if main_oprn_code:
            if related_oprn_code:
                return f"{diag_key}|{main_oprn_code}|{related_oprn_code}", "基本规则"
            return f"{diag_key}|{main_oprn_code}|", "基本规则"
        return f"{diag_key}||", "基本规则"

    # ======================================================================
    # ③ 诊断辅助细分（独立于第三步「触发式辅助分型」）
    # ======================================================================
    @staticmethod
    def _split_codes(code_str: str) -> List[str]:
        """把 ';' / '、' / ',' / 空格 分隔的编码串拆成清大写的编码列表。"""
        if not code_str:
            return []
        return [c.strip().upper() for c in str(code_str).replace("；", ";")
                .replace("、", ";").replace(",", ";").replace("+", ";").split(";")
                if c.strip()]

    @staticmethod
    def _neoplasm_category(related_diag_code: str) -> str:
        """从其他/相关诊断取首个肿瘤类别(限定《函》4974–5015 范围)的 3 位码；无则返回 ''。

        允许范围: C00-C75 / C76-C80 / C81-C86 / C88 / C90 / C91-C95
        （不含 D00-D48 癌前病变/动态未定，亦不含 C87/C89/C97）。
        """
        for c in LocalDirectoryGenerator._split_codes(related_diag_code):
            if len(c) >= 3 and c[0] == "C" and c[1:3].isdigit():
                n = int(c[1:3])
                if any(lo <= n <= hi for lo, hi in LocalDirectoryGenerator.NEOPLASM_ALLOWED_RANGES):
                    return c[:3]
        return ""

    @staticmethod
    def _tumor_treatment_tag(main_oprn: str, related_oprn: str) -> str:
        """依据手术操作判定化疗/靶向/免疫组合标签（对齐国家目录 99.2503/99.2800x006/99.2800x005）。"""
        types: set = set()
        for o in (LocalDirectoryGenerator._split_codes(main_oprn)
                 + LocalDirectoryGenerator._split_codes(related_oprn)):
            o = o.upper().replace(" ", "")
            if o.startswith("99.25"):
                types.add("化疗")
            if "99.2800X006" in o:
                types.add("靶向")
            if "99.2800X005" in o:
                types.add("免疫")
        if not types:
            return "其他"
        return "+".join(t for t in ("化疗", "靶向", "免疫") if t in types)

    def _is_tb_drug_resistant(self, main_diag: str, related_diag_code: str) -> bool:
        """结核耐药判定：主诊断含耐药拓展码(可配置) 或 其他诊断含 U84.300。"""
        m = self._clean_str(main_diag).upper().replace(" ", "")
        for ext in self._tb_drug_resistance_ext:
            e = ext.upper().replace(" ", "")
            if e and m.startswith(e):
                return True
        for c in self._split_codes(related_diag_code):
            if c.startswith("U84.3") or c == "U84.300":
                return True
        return False

    def _burn_area_from_name(self, name: str, age_cat: str) -> str:
        """由 T31/T32 名称中的「百分比区间」+ 年龄分档，映射《函》烧伤面积分类。

        名称示例：'体表10-19%的烧伤'、'累及体表20%~29%的烧伤'、'体表小于10%的烧伤'、
        '累及体表90%及以上的烧伤'。解析其中的数字与『以下/小于/及以上/大于』判定：
          <18岁：10%以下 / 10%以上
          ≥18岁：10%以下 / 10%-20% / 20%-30% / 30%以上
        """
        if not name:
            return "10%以下"
        nums = re.findall(r"\d+", name)
        # "10%以下" / "小于10%"：最低档
        if ("以下" in name or "小于" in name) and nums:
            return "10%以下"
        if not nums:
            return "10%以下"
        lb = int(nums[0])
        if "及以上" in name or "大于" in name:
            lb = max(lb, 90)
        if lb < 10:
            return "10%以下"
        if age_cat == "<18岁":
            return "10%以上"
        if lb < 20:
            return "10%-20%"
        if lb < 30:
            return "20%-30%"
        return "30%以上"

    def _classify_burn(
        self, main_diag_code: str, related_diag_code: str,
        age: int, day_age: int, birth_date: str, admission_date: str,
    ) -> Optional[str]:
        """③ 诊断辅助细分·烧伤类（依据《函》5016–5039）：先区分年龄，再按
        烧伤程度(主诊断 T29/T30 名称中的 一度/二度/三度) + 面积(次要诊断 T31/T32
        名称中的百分比区间) 分组。程度与面积均取自 ICD *名称*，不使用编码第4位。

        严格对齐《函》24 组（程度×面积×年龄），返回条目号(DIP 编码，如 "5018")；
        非烧伤病种 / 一度·四度烧伤(《函》无对应组) 返回 None（回落基本规则）。
        """
        diag = self._clean_str(main_diag_code).upper()
        # 烧伤程度：主诊断命中 T29(多部位)/T30(单部位)，依据名称含 一度/二度/三度 判定
        site = None
        degree_level = None
        main_name = ""
        for c in self._split_codes(diag):
            if c.startswith("T29") or c.startswith("T30"):
                main_name = self._icd10_burn_name(c)
                if "多处" in main_name or "多部位" in main_name:
                    site = "多部位"
                else:
                    site = "单部位"
                if "四度" in main_name:
                    degree_level = "四度"
                elif "三度" in main_name:
                    degree_level = "三度"
                elif "二度" in main_name:
                    degree_level = "二度"
                elif "一度" in main_name:
                    degree_level = "一度"
                break
        if site is None or not main_name or degree_level is None:
            return None

        # 《函》5016-5039 仅定义 二度/三度 两档（含多部位）；一度·四度无对应组 → 不进入细分
        if degree_level in ("一度", "四度"):
            return None
        degree_cat = ("多部位" if site == "多部位" else "") + degree_level  # 多部位二度/三度, 二度/三度

        # 年龄：先区分年龄（岁）；<18岁 / ≥18岁
        age_years = self._calc_age_years(age, day_age, birth_date, admission_date)
        age_cat = "<18岁" if age_years < self.BURN_AGE_ADULT else "≥18岁"

        # 面积：次要诊断含 T31/T32，取名称中的百分比区间 → 年龄分档面积分类
        area_cat = "10%以下"  # 缺省（保守最小档）：次要诊断无 T31/T32 时归最小面积档
        for c in self._split_codes(related_diag_code):
            if c.startswith("T31") or c.startswith("T32"):
                rel_name = self._icd10_burn_name(c)
                if rel_name:
                    area_cat = self._burn_area_from_name(rel_name, age_cat)
                break

        # 严格对齐《函》5016–5039：查 (程度, 年龄, 面积) → 条目号
        item = self._nat_burn_by_key.get((degree_cat, age_cat, area_cat))
        if item is not None:
            return str(item)
        # 兜底（理论不可达：24 组已穷举所有 程度×年龄×面积 组合）
        return f"AUX|BURN|{age_cat}|{degree_cat}|{area_cat}"

    def _refine_diagnostic_auxiliary(
        self, main_diag_code: str, main_oprn_code: str,
        related_oprn_code: str, related_diag_code: str,
        age: int = 0, day_age: int = 0,
        birth_date: str = "", admission_date: str = "",
    ) -> Optional[str]:
        """③ 诊断辅助细分：核心病种第三层成组。

        与国家目录库 4974–5024 行对应，产出**独立核心病种组**（各自 RW）。
        与第三步「触发式辅助分型」(严重程度/年龄/ICU/CCI) 不同机制，严禁复用其代码。

        (A) 肿瘤放化疗靶向免疫：主诊断 Z51.1/Z51.8 + 其他诊断(C00-C95 肿瘤族)
            + 主要/相关手术操作(化疗99.2503/靶向99.2800x006/免疫99.2800x005 及组合)
            → 按 (肿瘤类别 × 治疗方式) 细分。
        (B) 结核耐药：主诊断 A15-A19，按「主诊断含耐药拓展码 或 其他诊断含 U84.300」
            → 耐药 / 非耐药 细分。
        不匹配返回 None，透传 ④ 基本规则。
        """
        diag = self._clean_str(main_diag_code).upper()
        if not diag:
            return None

        # ---- (A) 肿瘤放化疗靶向免疫 ----
        if diag.startswith("Z51.1") or diag.startswith("Z51.8"):
            neo3 = self._neoplasm_category(related_diag_code)
            if neo3:
                if getattr(self, 'national_directory', None) is not None and getattr(self, '_nat_tumor', None):
                    dip = self._tumor_dip_for(diag, neo3, main_oprn_code, related_oprn_code)
                    if dip:
                        return dip
                return f"AUX|TUMOR|{neo3}|{self._tumor_treatment_tag(main_oprn_code, related_oprn_code)}"

        # ---- (C) 烧伤类病种：先年龄，再 烧伤程度(T29/T30) + 面积(T31/T32) ----
        burn = self._classify_burn(
            main_diag_code, related_diag_code, age, day_age, birth_date, admission_date
        )
        if burn is not None:
            return burn

        # ---- (B) 结核耐药 ----
        if diag[:2] == "A1" and diag[:3] in ("A15", "A16", "A17", "A18", "A19"):
            cat = "A15-A16" if diag[:3] in ("A15", "A16") else diag[:3]
            resistant = self._is_tb_drug_resistant(diag, related_diag_code)
            if getattr(self, 'national_directory', None) is not None and getattr(self, '_nat_tb', None):
                dip = self._tb_dip_for(cat, main_oprn_code, related_oprn_code, resistant)
                if dip:
                    return dip
            return f"AUX|TB|{cat}|{'耐药' if resistant else '非耐药'}"

        return None

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
    ) -> DiseaseGroup:
        """从聚合统计构造 DiseaseGroup（含 CCI / 严重度 / 裁剪 / 类别 / 成组层次 字段）。"""
        group = DiseaseGroup(
            disease_code=key.replace('|', '_'),
            disease_name=self._generate_disease_name(stats),
            main_diag_code=stats.get('main_diag_code', ''),
            main_diag_name=stats.get('main_diag_name', ''),
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
        group.cci_score = Decimal(str(self._compute_group_cci(diags)))
        sev_level, sev_type = self._compute_group_severity(diags)
        group.severity_level = sev_level
        group.severity_type = sev_type
        # ①/③ 严格对齐：若组键即国家目录 DIP 编码，直接回填权威码
        if key in getattr(self, '_nat_dip_codes', set()):
            group.national_dip_code = key
            group.national_matched = True
        return group

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

        for _, row in df.iterrows():
            main_diag = self._clean_str(row.get('main_diag_code'))
            main_oprn = self._clean_str(row.get('main_oprn_code'))
            related_oprn = self._clean_str(row.get('related_oprn_code'))
            related_diag = self._clean_str(row.get('related_diag_code'))
            day_age = self._safe_int(row.get('day_age', 0))
            birth_weight = self._safe_decimal(row.get('birth_weight', 0))
            age = self._safe_int(row.get('age', 0))
            birth_date = self._clean_str(row.get('birth_date'))
            admission_date = self._clean_str(row.get('admission_date'))

            if not main_diag:
                continue

            # 四层顺序成组：先期分组 → 并项规则 → 诊断辅助细分 → 基本规则
            # （每条记录仅命中最高优先级一层，得到唯一 core 成组键 + 成组层次）
            cluster_key, layer = self._refine_core_group_key(
                main_diag, main_oprn, related_oprn, related_diag,
                day_age=day_age, birth_weight=birth_weight, age=age,
                birth_date=birth_date, admission_date=admission_date,
            )

            cost = Decimal(str(row.get('total_cost', 0)))
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
                'drug_cost': self._safe_decimal(row.get('drug_cost', 0)),
                'treatment_cost': self._safe_decimal(row.get('treatment_cost', 0)),
                'los': self._safe_int(row.get('los', 0)),
                'age': self._safe_int(row.get('age', 0)),
                'day_age': self._safe_int(row.get('day_age', 0)),
                'icu_days': self._safe_int(row.get('icu_days', 0)),
                'discharge_status': self._clean_str(row.get('discharge_status')),
            })

            if not stats['main_diag_code']:
                stats['main_diag_code'] = main_diag
                stats['main_diag_name'] = self._clean_str(row.get('main_diag_name'))
                stats['main_oprn_code'] = main_oprn
                stats['main_oprn_name'] = self._clean_str(row.get('main_oprn_name'))
                stats['related_oprn_code'] = related_oprn
                stats['related_oprn_name'] = self._clean_str(row.get('related_oprn_name'))
                stats['related_diag_code'] = related_diag

            # 采集诊断码集合（用于组级 CCI / 疾病严重程度查字典）
            stats['diag_codes'].add(main_diag)
            if related_diag:
                stats['diag_codes'].add(related_diag)

        # 初级组 -> 核心病种（达阈值） / 未达阈值者进入综合病种池
        groups: Dict[str, DiseaseGroup] = {}
        subthreshold_records: List[Dict] = []

        for key, stats in primary.items():
            case_count = stats['case_count']

            if case_count >= self.threshold:
                # 核心病种：与地方临界值(threshold)对照，达阈值者依次形成地方核心病种
                kept_costs, trimmed, lb, ub = self._trim_group_costs(stats['costs'])
                kept_count = len(kept_costs)
                total_cost = sum(kept_costs, Decimal('0'))
                avg_cost = total_cost / kept_count if kept_count > 0 else Decimal('0')

                self.total_original_cases += case_count
                self.total_trimmed_cases += trimmed

                group = self._build_group(
                    key=key, stats=stats, case_count=case_count, avg_cost=avg_cost,
                    kept_count=kept_count, lb=lb, ub=ub, trimmed=trimmed,
                    group_type=GroupType.CORE, mixed_subtype="",
                    records=stats['records'], layer=stats['layer'],
                )
                groups[key] = group
            else:
                # 未达核心病种临界值 -> 进入综合病种池，第二阶段按手术属性 + 3 位码重聚类
                # （此处不裁剪、不计入整体裁剪统计；裁剪在综合病种成型时统一进行）
                for cost in stats['costs']:
                    subthreshold_records.append({
                        'main_diag': stats['main_diag_code'],
                        'main_diag_name': stats['main_diag_name'],
                        'main_oprn': stats['main_oprn_code'],
                        'main_oprn_name': stats['main_oprn_name'],
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
        })

        for rec in subthreshold_records:
            subtype = self._get_op_subtype(rec['main_oprn'])   # 内科/诊断性/治疗性/相关手术
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

            group = self._build_group(
                key=f"MIX_{subtype}_{diag3}", stats=stats, case_count=case_count,
                avg_cost=avg_cost, kept_count=kept_count, lb=lb, ub=ub, trimmed=trimmed,
                group_type=GroupType.MIXED, mixed_subtype=subtype,
                layer="综合病种",
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
        min_total_cases: int = 15,
        min_type_cases: int = 5,
        cv_improvement_pct: float = 0.20,
    ) -> Dict[str, DiseaseGroup]:
        """对核心病种应用辅助分型（DIP3.0 第三步）。

        对每个核心病种逐条分型，评估四个维度（严重程度/年龄特征/ICU天数/CCI）
        的触发条件（规范：病例数阈值、分型病例数阈值、CV 改善≥20%）：
          - 上年度病例数（以当前组病例数代理）>= min_total_cases
          - 某分型等级病例数 >= min_type_cases
          - 分型后组内变异系数下降 >= cv_improvement_pct
        若多个维度触发，取 CV 改善最大者；将该核心病种拆分为该维度下的若干
        子组（各自独立病种行，保留父代码）。未触发则保持原组不变。
        """
        cci_calc = CCICalculator()
        sev_calc = DiseaseSeverityClassifier()
        age_calc = AgeFeatureClassifier()
        icu_calc = ICUStayClassifier()

        new_groups: Dict[str, DiseaseGroup] = {}
        self.auxiliary_trigger_report: List[Dict] = []

        for key, group in groups.items():
            # 仅对核心病种、未剔除者做辅助分型（综合病种不拆分）
            if group.group_type != GroupType.CORE or group.excluded:
                new_groups[key] = group
                continue

            members = group.member_records
            if not members:
                new_groups[key] = group
                continue

            # 逐条分型，得到各维度下按等级归集的成员
            dim_levels = self._classify_members(
                members, group, cci_calc, sev_calc, age_calc, icu_calc
            )
            all_costs = [float(m['total_cost']) for m in members]
            cv_before = self._compute_cv(all_costs)

            best_dim = None
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
                    group.case_count >= min_total_cases
                    and max_bucket_count >= min_type_cases
                    and improvement >= cv_improvement_pct
                )
                self.auxiliary_trigger_report.append({
                    'disease_code': group.disease_code,
                    'disease_name': group.disease_name,
                    'dimension': dim,
                    'cv_before': round(cv_before, 4),
                    'cv_after': round(cv_after, 4),
                    'cv_improvement': round(improvement, 4),
                    'max_bucket_case_count': max_bucket_count,
                    'triggered': '是' if triggered else '否',
                })
                if triggered and improvement > best_improvement:
                    best_improvement = improvement
                    best_dim = dim
                    best_levels = levels

            if best_dim is None:
                group.auxiliary_split = False
                new_groups[key] = group
                continue

            # 触发：按 best_dim 拆分；低频等级（<min_type_cases）并入“其他(低频)”
            group.auxiliary_split = True
            main_levels = {
                lv: info for lv, info in best_levels.items()
                if len(info['members']) >= min_type_cases
            }
            small = [info for lv, info in best_levels.items()
                     if len(info['members']) < min_type_cases]
            if small:
                merged_members = []
                for info in small:
                    merged_members.extend(info['members'])
                main_levels['其他(低频)'] = {
                    'members': merged_members, 'coeff': Decimal('1.0')
                }

            for level, info in main_levels.items():
                sub = self._build_auxiliary_subgroup(
                    parent=group, dimension=best_dim, level=level,
                    members=info['members'], coeff=info['coeff'],
                )
                new_groups[f"{group.disease_code}_{best_dim}_{level}"] = sub

        return new_groups

    def _classify_members(
        self, members, group, cci_calc, sev_calc, age_calc, icu_calc
    ) -> Dict[str, Dict]:
        """逐条成员分型，返回 {维度: {等级: {'members':[...], 'coeff':x}}}。"""
        avg_cost = group.avg_cost
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
                sev = sev_calc.classify_malignant_tumor(rec, avg_cost, avg_cost)
            else:
                sev = sev_calc.classify_non_malignant(rec)
            self._bucket(dims['严重程度'], sev['level'], sev['coefficient'], m)

            # 年龄特征
            age_cls = age_calc.classify(rec)
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

            # CCI
            diags = [d for d in (m['main_diag_code'], m['related_diag_code']) if d]
            cci_level, cci_coeff = cci_calc.get_cci_level(cci_calc.calculate_cci(diags))
            self._bucket(dims['CCI'], cci_level, cci_coeff, m)

        return dims

    @staticmethod
    def _bucket(d: Dict, level: str, coeff, m: Dict) -> None:
        """将成员按等级归入维度字典。"""
        if level not in d:
            d[level] = {'members': [], 'coeff': coeff}
        d[level]['members'].append(m)

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
    
    def match_with_national_directory(
        self,
        local_groups: List[DiseaseGroup]
    ) -> pd.DataFrame:
        """
        与国家目录库匹配
        
        Args:
            local_groups: 本地病种组合列表
            
        Returns:
            匹配结果DataFrame
        """
        if self.national_directory is None:
            print("警告: 未加载国家目录库")
            return pd.DataFrame()
        
        results = []

        for group in local_groups:
            # ①/③ 组键已是权威 DIP 码（严格对齐国家目录）：直接确认匹配并回填目录字段
            if group.disease_code in getattr(self, '_nat_dip_codes', set()):
                group.national_matched = True
                group.national_dip_code = group.disease_code
                row = self._nat_rows_by_dip.get(group.disease_code, {})
                results.append({
                    '本地病种代码': group.disease_code,
                    '本地病种名称': group.disease_name,
                    '主要诊断代码': row.get('主要诊断编码', group.main_diag_code),
                    '主要诊断名称': row.get('主要诊断名称', group.main_diag_name),
                    '主要手术操作代码': row.get('主要手术操作编码', group.main_oprn_code),
                    '主要手术操作名称': row.get('主要手术操作名称', group.main_oprn_name),
                    '相关手术操作代码': row.get('相关手术操作编码', group.related_oprn_code),
                    '相关手术操作名称': row.get('相关手术操作名称', group.related_oprn_name),
                    '病例数': group.case_count,
                    '次均费用': float(group.avg_cost),
                    '病种分值': float(group.disease_value),
                    'CCI评分': int(group.cci_score),
                    '疾病严重程度': group.severity_level,
                    '综合病种子组': group.mixed_subtype,
                    '手术操作类别': group.op_category,
                    '分组类型': group.group_type.value,
                    '是否匹配国家目录': '是',
                    '国家DIP编码': group.disease_code,
                })
                continue

            # 与国家目录库对照（按 主要诊断编码(4位) + 主要手术操作编码）
            # 本地核心病种主诊断已归并到 4 位码，与目录库口径一致
            group_diag4 = self._extract_icd4(group.main_diag_code)
            group_oprn = self._clean_str(group.main_oprn_code)

            matched = False
            national_info = {}

            for _, nat_row in self.national_directory.iterrows():
                nat_diag = str(nat_row.get('主要诊断编码', nat_row.get('main_diag_code', ''))).strip()
                nat_diag4 = self._extract_icd4(nat_diag)
                nat_oprn_raw = nat_row.get('主要手术操作编码', nat_row.get('main_oprn_code', ''))
                nat_oprn_raw = "" if (nat_oprn_raw != nat_oprn_raw or nat_oprn_raw is None) else str(nat_oprn_raw)

                if nat_diag4 == group_diag4 and self._op_code_matches(group_oprn, nat_oprn_raw):
                    matched = True
                    national_info = nat_row.to_dict()
                    break

            # 回写到病种对象（供目录库导出展示）
            group.national_matched = matched
            group.national_dip_code = str(national_info.get('DIP编码', '')).strip() if matched else ""

            results.append({
                '本地病种代码': group.disease_code,
                '本地病种名称': group.disease_name,
                '主要诊断代码': group.main_diag_code,
                '主要诊断名称': group.main_diag_name,
                '主要手术操作代码': group.main_oprn_code,
                '主要手术操作名称': group.main_oprn_name,
                '相关手术操作代码': group.related_oprn_code,
                '相关手术操作名称': group.related_oprn_name,
                '病例数': group.case_count,
                '次均费用': float(group.avg_cost),
                '病种分值': float(group.disease_value),
                'CCI评分': int(group.cci_score),
                '疾病严重程度': group.severity_level,
                '综合病种子组': group.mixed_subtype,
                '手术操作类别': group.op_category,
                '分组类型': group.group_type.value,
                '是否匹配国家目录': '是' if matched else '否',
                '国家DIP编码': group.national_dip_code,
            })

        return pd.DataFrame(results)
    
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

        # 3.5 核心病种辅助分型（第三步）：触发条件评估与拆分
        print("\n[3.5/6] 核心病种辅助分型（触发条件评估）...")
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
        
        # 与国家目录库匹配
        if self.national_directory is not None:
            print("\n与国家目录库匹配...")
            match_df = self.match_with_national_directory(all_groups)
        else:
            match_df = None
        
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
        
        # 如果有匹配结果，导出匹配报告
        if match_df is not None:
            match_path = output_path / "与国家目录库匹配结果.xlsx"
            match_df.to_excel(match_path, index=False, engine='openpyxl')
            print(f"   匹配结果: {match_path}")
        
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
                '国家DIP编码': group.national_dip_code,
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
                '国家DIP编码': group.national_dip_code,
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
    
    def _export_statistics(self, groups: List[DiseaseGroup]) -> pd.DataFrame:
        """导出统计报告"""
        core_count = sum(1 for g in groups if g.group_type == GroupType.CORE)
        mixed_count = sum(1 for g in groups if g.group_type == GroupType.MIXED)
        total_cases = sum(g.case_count for g in groups)
        total_cost = sum(g.avg_cost * g.case_count for g in groups)
        avg_cost = total_cost / total_cases if total_cases > 0 else Decimal('0')
        
        stats = [
            {'统计项目': '病种总数', '数值': len(groups)},
            {'统计项目': '核心病种数', '数值': core_count},
            {'统计项目': '综合病种数', '数值': mixed_count},
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
