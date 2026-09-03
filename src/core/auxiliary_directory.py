"""
DIP按病种分值分组测算工具 - 辅助目录测算模块
基于《国家医疗保障按病种分值(DIP)付费3.0版技术规范》第四章

辅助目录包括：
1. 疾病严重程度辅助目录（CCI、疾病严重程度分型、肿瘤分型等）
2. 违规行为监管辅助目录（病案质量、二次入院、低标入院、超长住院、死亡风险）
"""
import pandas as pd
from typing import List, Dict, Tuple, Optional
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta
from collections import defaultdict
from dataclasses import dataclass, field

from ..models.models import MedicalRecord, DiseaseGroup


@dataclass
class AuxiliarySubgroup:
    """辅助分型子组（核心病种 × 维度 × 子型 的一行，子组级输出，而非逐病例）。

    仅当核心病种组内存在明显临床复杂程度或资源消耗差异时才生成。

    闸门与竞争口径严格贴合 DIP3.0 §5.2：
      - 组内费用变异系数偏大（cv_before >= 阈值，默认 0.7）；
      - 经某维度分型后组内费用 CV 下降明显（reduction >= 20%）；
      - 触发系数 = 该维度子型最大 mj/M，维度竞争取触发系数最高者胜出。
    """
    disease_code: str
    disease_name: str
    dimension: str          # CCI / 疾病严重程度 / 年龄特征 / 重症监护
    subtype: str           # 该维度下的子型标签（level，可含 sub_level）
    case_count: int        # 子组病例数
    avg_cost: Decimal     # 子组平均费用 mj
    coefficient: Decimal   # 辅助分型调节系数：CCI 查表，其余 = mj / M
    cv_before: float       # 分型前（整个核心病种组）费用变异系数 CV
    cv_after: float        # 分型后（沿该维度拆分）组内费用变异系数 CV（池化）
    cv_reduction: float    # (cv_before - cv_after) / cv_before，下降幅度
    trigger_coefficient: Decimal  # 该维度触发系数 = 子型最大 mj / M
    is_winning_dimension: bool = False  # 该维度是否经竞争胜出（实际应用的维度）
    is_other: bool = False # 是否低频合并组（其他）

    def to_dict(self) -> Dict:
        return {
            "核心病种编码": self.disease_code,
            "核心病种名称": self.disease_name,
            "分型维度": self.dimension,
            "亚型": self.subtype,
            "病例数": self.case_count,
            "子组均费": f"¥{float(self.avg_cost):,.2f}",
            "辅助分型系数": f"{float(self.coefficient):.4f}",
            "触发系数(mj/M)": f"{float(self.trigger_coefficient):.4f}",
            "组内CV(分型前)": f"{self.cv_before:.3f}",
            "组内CV(分型后)": f"{self.cv_after:.3f}",
            "CV下降幅度": f"{self.cv_reduction:.1%}",
            "竞争胜出维度": "是" if self.is_winning_dimension else "否",
            "低频合并": "是" if self.is_other else "否",
        }


class CCICalculator:
    """Charlson合并症指数(CCI)计算器"""
    
    # 仅当权威 CCI.xlsx 缺失时的兜底（标准 Charlson 17 项核心，3 位前缀权重）；
    # 正式测算应以 data/CCI.xlsx（按 ICD10 code → 得分）为准。
    _CCI_FALLBACK = {
        # 心肌梗死 (1分)
        "I21": 1, "I22": 1, "I23": 1, "I24": 1, "I25": 1,
        # 充血性心力衰竭 (1分)
        "I50": 1,
        # 周围血管疾病 (1分)
        "I73": 1, "I74": 1,
        # 脑血管疾病 (1分)
        "I60": 1, "I61": 1, "I62": 1, "I63": 1, "I64": 1, "I65": 1, "I66": 1, "I67": 1, "I68": 1, "I69": 1,
        # 痴呆 (1分)
        "F00": 1, "F01": 1, "F02": 1, "F03": 1,
        # 慢性肺部疾病 (1分)
        "J40": 1, "J41": 1, "J42": 1, "J43": 1, "J44": 1, "J47": 1,
        # 结缔组织病 (1分)
        "M05": 1, "M06": 1, "M32": 1, "M33": 1, "M34": 1,
        # 溃疡病 (1分)
        "K25": 1, "K26": 1, "K27": 1,
        # 轻度肝脏疾病 (1分)
        "K73": 1, "K74": 1,
        # 糖尿病 (1分)
        "E10": 1, "E11": 1, "E12": 1, "E13": 1,
        # 偏瘫 (2分)
        "G81": 2, "G82": 2,
        # 中度或重度肾脏疾病 (2分)
        "N18": 2, "N19": 2,
        # 糖尿病合并并发症 (2分)
        "E10.3": 2, "E10.4": 2, "E10.5": 2, "E10.6": 2, "E10.7": 2,
        "E11.3": 2, "E11.4": 2, "E11.5": 2, "E11.6": 2, "E11.7": 2,
        # 肿瘤 (2分)
        "C00": 2, "C01": 2, "C02": 2, "C03": 2, "C04": 2, "C05": 2,
        "C06": 2, "C07": 2, "C08": 2, "C09": 2, "C10": 2, "C11": 2,
        "C12": 2, "C13": 2, "C14": 2, "C15": 2, "C16": 2, "C17": 2,
        "C18": 2, "C19": 2, "C20": 2, "C21": 2, "C22": 2, "C23": 2,
        "C24": 2, "C25": 2, "C26": 2, "C30": 2, "C31": 2, "C32": 2,
        "C33": 2, "C34": 2, "C37": 2, "C38": 2, "C39": 2, "C40": 2,
        "C41": 2, "C43": 2, "C44": 2, "C45": 2, "C46": 2, "C47": 2,
        "C48": 2, "C49": 2, "C50": 2, "C51": 2, "C52": 2, "C53": 2,
        "C54": 2, "C55": 2, "C56": 2, "C57": 2, "C58": 2,
        "C60": 2, "C61": 2, "C62": 2, "C63": 2, "C64": 2, "C65": 2,
        "C66": 2, "C67": 2, "C68": 2, "C69": 2, "C70": 2, "C71": 2,
        "C72": 2, "C73": 2, "C74": 2, "C75": 2,
        # 白血病 (2分)
        "C91": 2, "C92": 2, "C93": 2, "C94": 2, "C95": 2,
        # 淋巴瘤 (2分)
        "C81": 2, "C82": 2, "C83": 2, "C84": 2, "C85": 2, "C88": 2, "C90": 2, "C96": 2,
        # 中度或重度肝脏疾病 (3分)
        "K70": 3, "K72": 3, "K76": 3,
        # 转移性实体瘤 (6分)
        "C77": 6, "C78": 6, "C79": 6,
        # AIDS (6分)
        "B20": 6, "B21": 6, "B22": 6, "B23": 6, "B24": 6,
    }
    
    def __init__(self, cci_file: Optional[str] = None):
        from pathlib import Path
        from ..utils.paths import get_data_dir
        path = Path(cci_file) if cci_file else (get_data_dir() / "CCI.xlsx")
        if path.exists():
            self._cci_3, self._cci_4 = self._load_cci(path)
        else:
            import warnings
            warnings.warn(
                f"CCI 权威字典缺失({path})，回退内置 Charlson 17 项核心；"
                f"正式测算应配置 data/CCI.xlsx"
            )
            self._cci_3 = dict(self._CCI_FALLBACK)
            self._cci_4 = {}

    @staticmethod
    def _load_cci(path) -> Tuple[Dict[str, float], Dict[str, float]]:
        """从权威 CCI.xlsx 加载权重字典。

        - 列：ICD10 code / Charlson component / 得分
        - 4 位码（如 E10.3）与 3 位前缀（如 E10）分别建索引，便于 calculate_cci 优先 4 位匹配
        - '得分'为空的码（无权重）按用户要求不纳入计算
        """
        df = pd.read_excel(path, sheet_name=0)
        s3: Dict[str, float] = {}
        s4: Dict[str, float] = {}
        for _, row in df.iterrows():
            raw = str(row.get("ICD10 code", "")).strip()
            if not raw or raw.lower() == "nan":
                continue
            w = row.get("得分")
            if w is None or pd.isna(w):
                continue
            try:
                w = float(w)
            except (TypeError, ValueError):
                continue
            norm = raw.upper().replace(".", "")
            p3 = norm[:3]
            s3[p3] = max(s3.get(p3, 0.0), w)
            if len(norm) >= 4:
                s4[norm[:4]] = max(s4.get(norm[:4], 0.0), w)
        return s3, s4

    @staticmethod
    def _split_codes(code_str) -> List[str]:
        """把 '|' / ';' / '、' / ',' / '+' / 空格 分隔的编码串拆成清大写的编码列表。

        规范多值分隔符为 '|'（与 4101A 解析器、数据库模型「多个用|分隔」约定一致）；
        其余分隔符为历史/人工录入兼容。空串返回空列表。
        """
        if not code_str:
            return []
        return [c.strip().upper() for c in str(code_str).replace("|", ";").replace("；", ";")
                .replace("、", ";").replace(",", ";").replace("+", ";").split(";")
                if c.strip()]

    def calculate_cci(self, diagnoses: List[str]) -> int:
        """计算 CCI 总分。

        匹配规则：4 位码优先、3 位前缀回退；同一 3 位前缀（同类疾病）仅取最高权重分。
        传入的每个诊断码若含多值分隔符（'|' 等），将兜底拆分为多个码后计分，
        确保 4101A 等多值其他诊断的合并症 CCI 被正确累计（单值/空串结果不变）。
        """
        if not diagnoses:
            return 0
        max_by_cat: Dict[str, float] = {}
        expanded: List[str] = []
        for diag in diagnoses:
            expanded.extend(self._split_codes(diag))
        for diag in expanded:
            c = diag.replace(".", "")
            c3, c4 = c[:3], (c[:4] if len(c) >= 4 else c[:3])
            w = self._cci_4.get(c4, self._cci_3.get(c3, 0.0))
            if w > 0:
                if c3 not in max_by_cat or w > max_by_cat[c3]:
                    max_by_cat[c3] = w
        return int(sum(max_by_cat.values()))
    
    def get_cci_level(self, cci_score: int) -> Tuple[str, Decimal]:
        """
        根据CCI分数确定疾病严重程度等级和调节系数（DIP3.0 规范 CCI 分型）
        等级：极严重(≥5分) / 严重(3-4分) / 一般(1-2分) / 无(0分)
        调节系数为本地测算拟合默认值，可由统筹地区校准。

        Args:
            cci_score: CCI分数

        Returns:
            (等级名称, 调节系数)
        """
        if cci_score <= 0:
            return "无", Decimal("1.0")
        elif cci_score <= 2:
            return "一般", Decimal("1.1")
        elif cci_score <= 4:
            return "严重", Decimal("1.2")
        else:
            return "极严重", Decimal("1.3")


class DiseaseSeverityClassifier:
    """疾病严重程度分型分类器"""
    
    def __init__(self, assi_file: Optional[str] = None):
        from pathlib import Path
        from ..utils.paths import get_data_dir
        path = Path(assi_file) if assi_file else (get_data_dir() / "中重度分型诊断.xlsx")
        if path.exists():
            self._severe_codes = self._load_assi_codes(path, "2")
            self._organ_damage_codes = self._load_assi_codes(path, "1")
            # 转移分型：DIP_ASSISTANT_CODE='3'（C77/C78/C79 继发性/远处转移部位，共288条）
            self._metastasis_codes = self._load_assi_codes(path, "3")
        else:
            import warnings
            warnings.warn(
                f"中重度分型字典缺失({path})，回退内置少量码；"
                f"正式测算应配置 data/中重度分型诊断.xlsx"
            )
            self._severe_codes = {"R57", "N17", "N19", "J96", "K72", "A40", "A41"}
            self._organ_damage_codes = {
                "I20", "I21", "I22", "I23", "I24", "I25", "I60", "I61", "I62",
                "I63", "I64", "I65", "I66", "I67", "I68", "I69", "J85", "J86",
                "K80", "K81", "K82", "K83", "K84", "K85", "K86", "K87", "N10",
                "N11", "N12", "N13", "N14", "N15", "N16", "N17",
            }
            self._metastasis_codes = {"C77", "C78", "C79"}

    @staticmethod
    def _death_level(record: MedicalRecord) -> str:
        """死亡病例 IV 级：住院天数<3天 为 IV-A，≥3天 为 IV-B（DIP3.0 规范）。"""
        return "死亡-IV-B" if record.los >= 3 else "死亡-IV-A"

    def classify_malignant_tumor(
        self,
        record: MedicalRecord,
        avg_cost: Decimal,
        cost_standard: Decimal
    ) -> Dict:
        """
        恶性肿瘤疾病严重程度分型（DIP3.0 规范 7 亚型）
        (1)死亡 (2)高费用类型一 (3)高费用类型二 (4)肿瘤转移并发
        (5)功能衰竭/休克/脓毒症 (6)重要器官病损/感染 (7)其他
        """
        # (1) 死亡病例（IV级，按住院天数再分 IV-A/IV-B）
        if record.discharge_status == "死亡":
            return {
                "type": "恶性肿瘤严重程度",
                "level": self._death_level(record),
                "coefficient": Decimal("1.5"),
                "condition": "出院状态=死亡"
            }

        # (2) 高费用病例类型一：费用≥3倍标准，治疗费占比≥50%
        if (cost_standard > 0 and
            record.total_cost >= cost_standard * 3 and
            record.treatment_cost > 0 and
            record.treatment_cost / record.total_cost >= Decimal("0.5")):
            return {
                "type": "恶性肿瘤严重程度",
                "level": "高费用类型一",
                "coefficient": Decimal("1.4"),
                "condition": "费用≥3倍标准，治疗费占比≥50%"
            }

        # (3) 高费用病例类型二：费用≥3倍标准，药品费占比≥50%
        if (cost_standard > 0 and
            record.total_cost >= cost_standard * 3 and
            record.drug_cost > 0 and
            record.drug_cost / record.total_cost >= Decimal("0.5")):
            return {
                "type": "恶性肿瘤严重程度",
                "level": "高费用类型二",
                "coefficient": Decimal("1.35"),
                "condition": "费用≥3倍标准，药品费占比≥50%"
            }

        # (4) 肿瘤转移/其他部位并发：次要诊断含恶性肿瘤（参考中重度字典转移分型 code=3，
        #     或类目与主诊断不同的其他部位原发恶性肿瘤），且住院天数≥3天
        if record.related_diag_code and record.los >= 3:
            if self._has_metastasis(record.related_diag_code, record.main_diag_code):
                return {
                    "type": "恶性肿瘤严重程度",
                    "level": "肿瘤转移并发",
                    "coefficient": Decimal("1.25"),
                    "condition": "次要诊断含恶性肿瘤(转移分型/其他部位)，住院天数≥3天"
                }

        # (5) 次要诊断属于"功能衰竭、休克、脓毒症"，住院天数≥3天
        if record.related_diag_code and record.los >= 3:
            if self._has_severe_complication(record.related_diag_code):
                return {
                    "type": "恶性肿瘤严重程度",
                    "level": "功能衰竭/休克/脓毒症",
                    "coefficient": Decimal("1.3"),
                    "condition": "次要诊断含功能衰竭/休克/脓毒症，住院天数≥3天"
                }

        # (6) 次要诊断属于"重要器官病损、重要脏器感染"，住院天数≥3天
        if record.related_diag_code and record.los >= 3:
            if self._has_organ_damage(record.related_diag_code):
                return {
                    "type": "恶性肿瘤严重程度",
                    "level": "重要器官病损/感染",
                    "coefficient": Decimal("1.2"),
                    "condition": "次要诊断含重要器官病损/感染，住院天数≥3天"
                }

        # (7) 其他情况
        return {
            "type": "恶性肿瘤严重程度",
            "level": "其他",
            "coefficient": Decimal("1.0"),
            "condition": "默认"
        }

    def classify_non_malignant(self, record: MedicalRecord) -> Dict:
        """
        非恶性肿瘤疾病严重程度分型（DIP3.0 规范 4 级）
        (1)死亡 (2)重度 (3)中度 (4)轻度
        """
        # (1) 死亡病例（IV级，按住院天数再分 IV-A/IV-B）
        if record.discharge_status == "死亡":
            return {
                "type": "非恶性肿瘤严重程度",
                "level": self._death_level(record),
                "coefficient": Decimal("1.5"),
                "condition": "出院状态=死亡"
            }

        # (2) 重度：次要诊断含功能衰竭、休克、脓毒症，且住院天数≥3天
        if record.related_diag_code and record.los >= 3:
            if self._has_severe_complication(record.related_diag_code):
                return {
                    "type": "非恶性肿瘤严重程度",
                    "level": "重度",
                    "coefficient": Decimal("1.3"),
                    "condition": "次要诊断含功能衰竭/休克/脓毒症，住院天数≥3天"
                }

        # (3) 中度：次要诊断含重要器官病损、重要脏器感染，且住院天数≥3天
        if record.related_diag_code and record.los >= 3:
            if self._has_organ_damage(record.related_diag_code):
                return {
                    "type": "非恶性肿瘤严重程度",
                    "level": "中度",
                    "coefficient": Decimal("1.15"),
                    "condition": "次要诊断含重要器官病损/感染，住院天数≥3天"
                }

        # (4) 轻度：其他病例
        return {
            "type": "非恶性肿瘤严重程度",
            "level": "轻度",
            "coefficient": Decimal("1.0"),
            "condition": "默认"
        }
    
    @staticmethod
    def _load_assi_codes(path, code_value: str) -> set:
        """从中重度分型诊断.xlsx 的 GX_ASSI 表，按 DIP_ASSISTANT_TYPE=QTZD 且
        DIP_ASSISTANT_CODE=code_value 收集诊断码前缀（code_value: '2' 重度 / '1' 中度）。

        字典 ASSI_ITEM_ID 为带明细的 ICD 码（如 A01.000x005+），取前 3 位作为匹配键。
        """
        df = pd.read_excel(path, sheet_name="GX_ASSI")
        sub = df[(df["DIP_ASSISTANT_TYPE"] == "QTZD") &
                 (df["DIP_ASSISTANT_CODE"].astype(str) == code_value)]
        codes = set()
        for v in sub["ASSI_ITEM_ID"].dropna().astype(str):
            v = v.strip().upper().replace(".", "")
            if v:
                codes.add(v[:3])
        return codes

    @staticmethod
    def _split_diag_codes(code_str) -> list:
        """把含多值分隔符（'|' / ';' / '、' / ',' / '+' / 空格）的次要诊断串拆成清大写的编码列表。

        与 CCICalculator._split_codes 同口径，确保一条记录含多个次要诊断时逐码判断，
        避免只取首码导致漏判（原实现直接取 related_diag_code[:3] 的缺陷）。
        """
        if not code_str:
            return []
        return [c.strip().upper() for c in str(code_str).replace("|", ";").replace("；", ";")
                .replace("、", ";").replace(",", ";").replace("+", ";").split(";")
                if c.strip()]

    def _has_severe_complication(self, diag_code: str) -> bool:
        """次要诊断（可含多码）是否任意一条属于重度范围（功能衰竭/休克/脓毒症等，code=2）。"""
        return any(str(c).upper()[:3] in self._severe_codes
                   for c in self._split_diag_codes(diag_code))

    def _has_organ_damage(self, diag_code: str) -> bool:
        """次要诊断（可含多码）是否任意一条属于中度范围（重要器官病损/感染，code=1）。"""
        return any(str(c).upper()[:3] in self._organ_damage_codes
                   for c in self._split_diag_codes(diag_code))

    def _has_metastasis(self, diag_code: str, main_diag_code: str) -> bool:
        """次要诊断（可含多码）是否含肿瘤转移/其他部位并发：

        - 命中中重度字典转移分型码集(code=3, C77/C78/C79 继发性/远处转移部位)，或
        - 属于恶性肿瘤(C00-C96)且所属类目(前3位)与主要诊断不同（其他部位原发恶性肿瘤）；
        且均与主要诊断类目不同。供恶性肿瘤严重程度『肿瘤转移并发』判定参考。
        """
        main_prefix = (main_diag_code or "")[:3].upper()
        for c in self._split_diag_codes(diag_code):
            cp = c[:3].upper()
            if cp == main_prefix:
                continue
            if cp in self._metastasis_codes:
                return True
            if "C00" <= cp <= "C96":
                return True
        return False


class AgeFeatureClassifier:
    """年龄特征分型分类器"""
    
    def classify(self, record: MedicalRecord) -> Optional[Dict]:
        """
        年龄特征分型

        Args:
            record: 住院病例记录

        Returns:
            分型结果（如不适用返回None）
        """
        age = record.age

        if age < 18:
            return self._classify_pediatric(age, getattr(record, 'day_age', 0))
        elif age >= 65:
            return self._classify_elderly(age)

        return None

    def _classify_pediatric(self, age: int, day_age: int = 0) -> Dict:
        """儿科年龄分型（DIP3.0：0-28天 / 29天-1周岁 / 1-6岁 / 7-17岁）"""
        if age < 1:
            # 不足1周岁：依天龄细分 0-28天 与 29天-1周岁
            if 0 < day_age < 29:
                sub, coeff = "0-28天", Decimal("1.25")
            else:
                sub, coeff = "29天-1周岁", Decimal("1.2")
            return {
                "type": "年龄特征",
                "level": "婴幼儿",
                "sub_level": sub,
                "coefficient": coeff,
                "condition": f"天龄={day_age}天" if day_age > 0 else "年龄<1岁"
            }
        elif age <= 6:
            return {
                "type": "年龄特征",
                "level": "学龄前",
                "sub_level": "1-6岁",
                "coefficient": Decimal("1.15"),
                "condition": f"年龄={age}岁"
            }
        else:
            return {
                "type": "年龄特征",
                "level": "学龄及青春期",
                "sub_level": "7-17岁",
                "coefficient": Decimal("1.1"),
                "condition": f"年龄={age}岁"
            }

    def _classify_elderly(self, age: int) -> Dict:
        """老年年龄分型（DIP3.0：65岁以上）"""
        if age < 70:
            sub, coeff = "65-69岁", Decimal("1.05")
        elif age < 80:
            sub, coeff = "70-79岁", Decimal("1.1")
        else:
            sub, coeff = "80岁以上", Decimal("1.2")
        return {
            "type": "年龄特征",
            "level": "老年",
            "sub_level": sub,
            "coefficient": coeff,
            "condition": f"年龄={age}岁"
        }


class ICUStayClassifier:
    """ICU住院天数分型分类器"""
    
    def classify(self, icu_days: int) -> Optional[Dict]:
        """
        ICU住院天数分型
        
        Args:
            icu_days: ICU住院天数
            
        Returns:
            分型结果（如不适用返回None）
        """
        if icu_days < 2:
            return None
        
        if icu_days <= 7:
            return {
                "type": "ICU天数",
                "level": "短期ICU",
                "sub_level": "2-7天",
                "coefficient": Decimal("1.15"),
                "condition": f"ICU天数={icu_days}天"
            }
        elif icu_days <= 14:
            return {
                "type": "ICU天数",
                "level": "中期ICU",
                "sub_level": "8-14天",
                "coefficient": Decimal("1.3"),
                "condition": f"ICU天数={icu_days}天"
            }
        elif icu_days <= 30:
            return {
                "type": "ICU天数",
                "level": "长期ICU",
                "sub_level": "15-30天",
                "coefficient": Decimal("1.5"),
                "condition": f"ICU天数={icu_days}天"
            }
        else:
            return {
                "type": "ICU天数",
                "level": "超长ICU",
                "sub_level": "31天以上",
                "coefficient": Decimal("1.7"),
                "condition": f"ICU天数={icu_days}天"
            }


class ViolationBehaviorClassifier:
    """违规行为监管辅助目录分类器"""
    
    def calculate_rsa_score(
        self,
        record: MedicalRecord,
        discharge_records: List[MedicalRecord]
    ) -> Dict:
        """
        二次入院评分(RSA - Rating of Secondary Admission)
        
        Args:
            record: 当前住院记录
            discharge_records: 该患者历史出院记录
            
        Returns:
            评分结果
        """
        # 检查31天内是否有相同诊断的再入院
        if not record.discharge_date or not record.admission_date:
            return {
                "type": "二次入院",
                "score": Decimal("0"),
                "risk_level": "无风险",
                "condition": "无出院日期信息"
            }
        
        try:
            discharge_date = datetime.strptime(record.discharge_date, "%Y-%m-%d")
            admission_date = datetime.strptime(record.admission_date, "%Y-%m-%d")
        except:
            return {
                "type": "二次入院",
                "score": Decimal("0"),
                "risk_level": "无风险",
                "condition": "日期格式错误"
            }
        
        # 检查31天内再入院
        readmission_window = timedelta(days=31)
        for hist_record in discharge_records:
            if hist_record.record_id == record.record_id:
                continue
            
            if hist_record.patient_id != record.patient_id:
                continue
            
            try:
                hist_discharge = datetime.strptime(hist_record.discharge_date, "%Y-%m-%d")
                if (admission_date - hist_discharge) <= readmission_window:
                    # 相同诊断再入院
                    if hist_record.main_diag_code == record.main_diag_code:
                        return {
                            "type": "二次入院",
                            "score": Decimal("1.0"),
                            "risk_level": "高风险",
                            "condition": f"31天内相同诊断再入院"
                        }
                    else:
                        return {
                            "type": "二次入院",
                            "score": Decimal("0.5"),
                            "risk_level": "中风险",
                            "condition": f"31天内不同诊断再入院"
                        }
            except:
                continue
        
        return {
            "type": "二次入院",
            "score": Decimal("0"),
            "risk_level": "低风险",
            "condition": "非31天内再入院"
        }
    
    def calculate_rla_score(
        self,
        record: MedicalRecord,
        disease_avg_cost: Decimal
    ) -> Dict:
        """
        低标入院评分(RLA - Rating of Low-RW Admission)
        
        Args:
            record: 住院记录
            disease_avg_cost: 该病种平均费用
            
        Returns:
            评分结果
        """
        if disease_avg_cost <= 0:
            return {
                "type": "低标入院",
                "score": Decimal("0"),
                "risk_level": "无风险",
                "condition": "无费用数据"
            }
        
        cost_ratio = record.total_cost / disease_avg_cost
        
        if cost_ratio < Decimal("0.3"):
            return {
                "type": "低标入院",
                "score": Decimal("1.0"),
                "risk_level": "高风险",
                "condition": f"费用低于病种平均的30%"
            }
        elif cost_ratio < Decimal("0.5"):
            return {
                "type": "低标入院",
                "score": Decimal("0.7"),
                "risk_level": "中风险",
                "condition": f"费用低于病种平均的50%"
            }
        elif cost_ratio < Decimal("0.7"):
            return {
                "type": "低标入院",
                "score": Decimal("0.3"),
                "risk_level": "低风险",
                "condition": f"费用低于病种平均的70%"
            }
        else:
            return {
                "type": "低标入院",
                "score": Decimal("0"),
                "risk_level": "无风险",
                "condition": "费用正常"
            }
    
    def calculate_extended_stay_score(
        self,
        record: MedicalRecord,
        disease_avg_los: Decimal
    ) -> Dict:
        """
        超长住院评分
        
        Args:
            record: 住院记录
            disease_avg_los: 该病种平均住院天数
            
        Returns:
            评分结果
        """
        if disease_avg_los <= 0:
            return {
                "type": "超长住院",
                "score": Decimal("0"),
                "risk_level": "无风险",
                "condition": "无住院天数数据"
            }
        
        los_ratio = Decimal(str(record.los)) / disease_avg_los
        
        if los_ratio > Decimal("3.0"):
            return {
                "type": "超长住院",
                "score": Decimal("1.0"),
                "risk_level": "高风险",
                "condition": f"住院天数超过病种平均的3倍"
            }
        elif los_ratio > Decimal("2.0"):
            return {
                "type": "超长住院",
                "score": Decimal("0.6"),
                "risk_level": "中风险",
                "condition": f"住院天数超过病种平均的2倍"
            }
        elif los_ratio > Decimal("1.5"):
            return {
                "type": "超长住院",
                "score": Decimal("0.3"),
                "risk_level": "低风险",
                "condition": f"住院天数超过病种平均的1.5倍"
            }
        else:
            return {
                "type": "超长住院",
                "score": Decimal("0"),
                "risk_level": "无风险",
                "condition": "住院天数正常"
            }
    
    def calculate_death_risk_score(
        self,
        record: MedicalRecord,
        disease_mortality_rate: Decimal
    ) -> Dict:
        """
        死亡风险评分
        
        Args:
            record: 住院记录
            disease_mortality_rate: 该病种死亡率
            
        Returns:
            评分结果
        """
        if record.discharge_status == "死亡":
            # 实际死亡
            if disease_mortality_rate < Decimal("0.05"):
                return {
                    "type": "死亡风险",
                    "score": Decimal("1.0"),
                    "risk_level": "异常死亡",
                    "condition": "低死亡率病种发生死亡"
                }
            else:
                return {
                    "type": "死亡风险",
                    "score": Decimal("0.5"),
                    "risk_level": "正常死亡",
                    "condition": "病种允许的死亡范围内"
                }
        else:
            return {
                "type": "死亡风险",
                "score": Decimal("0"),
                "risk_level": "存活",
                "condition": "患者存活出院"
            }


class AuxiliaryDirectoryCalculator:
    """辅助目录综合计算器"""
    
    def __init__(self):
        self.cci_calculator = CCICalculator()
        self.severity_classifier = DiseaseSeverityClassifier()
        self.age_classifier = AgeFeatureClassifier()
        self.icu_classifier = ICUStayClassifier()
        self.violation_classifier = ViolationBehaviorClassifier()
    
    def calculate_all_auxiliary_coefficients(
        self,
        record: MedicalRecord,
        all_records: List[MedicalRecord] = None,
        disease_avg_cost: Decimal = Decimal("0"),
        disease_avg_los: Decimal = Decimal("0"),
        disease_mortality_rate: Decimal = Decimal("0"),
        rw: Decimal = None,
        point_value: Decimal = None
    ) -> Dict:
        """
        计算所有辅助分型调节系数
        
        Args:
            record: 住院病例记录
            all_records: 所有病例记录（用于二次入院判断）
            disease_avg_cost: 该病种平均费用
            disease_avg_los: 该病种平均住院天数
            disease_mortality_rate: 该病种死亡率
            
        Returns:
            所有辅助分型结果
        """
        results = {
            "cci": None,
            "severity": None,
            "age": None,
            "icu": None,
            "violation": {},
            "max_coefficient": Decimal("1.0"),
            "max_type": "无"
        }
        
        # 1. CCI计算（B1 修正：仅使用其他诊断/相关诊断，不计入主诊断）
        # 多值其他诊断（'|' 分隔等）逐码拆分，确保合并症 CCI 算全
        diagnoses = self.cci_calculator._split_codes(record.related_diag_code)
        cci_score = self.cci_calculator.calculate_cci(diagnoses)
        cci_level, cci_coeff = self.cci_calculator.get_cci_level(cci_score)
        results["cci"] = {
            "score": cci_score,
            "level": cci_level,
            "coefficient": cci_coeff
        }
        
        # 2. 疾病严重程度分型
        # 分值费用标准（高费用判定基准）= 未测算辅助分型的核心病种的平均费用（mi）。
        # 本地目录测算不计算真实点值，故默认直接取 disease_avg_cost（即该核心病种
        # 成组后的平均费用）。若调用方显式传入真实预算点值(rw, point_value)，可改用
        # 支付标准 = RW × 点值 作为基准（覆盖默认 mi）——仅当接入真实点值时使用。
        if rw is not None and point_value is not None and point_value > 0:
            cost_standard = rw * point_value
        else:
            cost_standard = disease_avg_cost
        is_tumor = self._is_tumor_diagnosis(record.main_diag_code)
        if is_tumor:
            results["severity"] = self.severity_classifier.classify_malignant_tumor(
                record, disease_avg_cost, cost_standard
            )
        else:
            results["severity"] = self.severity_classifier.classify_non_malignant(record)
        
        # 3. 年龄特征分型
        results["age"] = self.age_classifier.classify(record)
        
        # 4. ICU天数分型（需要从其他数据获取ICU天数）
        icu_days = getattr(record, 'icu_days', 0)
        results["icu"] = self.icu_classifier.classify(icu_days)
        
        # 5. 违规行为评分
        if all_records:
            results["violation"]["rsa"] = self.violation_classifier.calculate_rsa_score(
                record, all_records
            )
            results["violation"]["rla"] = self.violation_classifier.calculate_rla_score(
                record, disease_avg_cost
            )
            results["violation"]["extended_stay"] = self.violation_classifier.calculate_extended_stay_score(
                record, disease_avg_los
            )
            results["violation"]["death_risk"] = self.violation_classifier.calculate_death_risk_score(
                record, disease_mortality_rate
            )
        
        # 找出最大调节系数
        all_coefficients = []
        
        if results["cci"]:
            all_coefficients.append(("CCI", results["cci"]["coefficient"]))
        
        if results["severity"]:
            all_coefficients.append(("疾病严重程度", results["severity"]["coefficient"]))
        
        if results["age"]:
            all_coefficients.append(("年龄特征", results["age"]["coefficient"]))
        
        if results["icu"]:
            all_coefficients.append(("ICU天数", results["icu"]["coefficient"]))
        
        if all_coefficients:
            max_type, max_coeff = max(all_coefficients, key=lambda x: x[1])
            results["max_coefficient"] = max_coeff
            results["max_type"] = max_type
        
        return results
    
    def _is_tumor_diagnosis(self, diag_code: str) -> bool:
        """检查是否为肿瘤诊断"""
        if not diag_code:
            return False
        prefix = diag_code[:3]
        return "C00" <= prefix <= "C96" or "D00" <= prefix <= "D48"
    
    def batch_calculate(
        self,
        records: List[MedicalRecord],
        disease_groups: Dict[str, DiseaseGroup]
    ) -> List[Dict]:
        """
        批量计算辅助分型
        
        Args:
            records: 住院病例记录列表
            disease_groups: 病种组合字典
            
        Returns:
            辅助分型结果列表
        """
        results = []
        
        for record in records:
            # 获取病种信息
            disease_code = record.dip_disease_code
            if disease_code in disease_groups:
                group = disease_groups[disease_code]
                disease_avg_cost = group.avg_cost
                disease_avg_los = Decimal("10")  # 简化处理
                disease_mortality_rate = Decimal("0.02")  # 简化处理
            else:
                disease_avg_cost = record.total_cost
                disease_avg_los = Decimal("10")
                disease_mortality_rate = Decimal("0.02")
            
            # 计算辅助分型
            aux_result = self.calculate_all_auxiliary_coefficients(
                record=record,
                all_records=records,
                disease_avg_cost=disease_avg_cost,
                disease_avg_los=disease_avg_los,
                disease_mortality_rate=disease_mortality_rate
            )
            
            results.append({
                "record_id": record.record_id,
                "patient_id": record.patient_id,
                "disease_code": disease_code,
                "cci": aux_result["cci"],
                "severity": aux_result["severity"],
                "age": aux_result["age"],
                "icu": aux_result["icu"],
                "violation": aux_result["violation"],
                "max_coefficient": aux_result["max_coefficient"],
                "max_type": aux_result["max_type"]
            })

        return results

    # ------------------------------------------------------------------
    # 统一辅助分型引擎（子组级聚类 + 差异前置闸门）
    #
    # 设计严格贴合 DIP3.0 规范 §5.2 与用户口径：
    #   1. 辅助分型发生在「核心病种聚类成组之后」，针对组内费用偏高的病例，
    #      结合 CCI / 疾病严重程度 / 年龄 / 监护病房 等多维度「再次聚类」成子型组，
    #      而非逐病例一条。
    #   2. 触发条件（§5.2 三条，全部量化）：
    #      (1) 病种病例数 > AUX_MIN_CORE_CASES（上年度病例数超一定例数）；
    #      (2) 某分型评估病例数 > AUX_MIN_SUBTYPE_CASES（参与分型评估病例数超一定例数）；
    #      (3) 组内费用变异系数偏大（cv_before >= AUX_CV_BEFORE_THRESHOLD，规范术语建议
    #          遴选 CV>0.7 的病种引入辅助分型），且经某维度分型后组内费用 CV 下降明显
    #          （reduction = (cv_before - cv_after)/cv_before >= AUX_CV_IMPROVEMENT_THRESHOLD，
    #          规范示例 20% 以上）→ 二者同时成立才算该维度「达标」。
    #      监护病房住院天数辅助分型的触发条件可适当放宽（AUX_ICU_RELAX_FACTOR）。
    #   3. 维度竞争（§(二)）：若干个维度均达标时，选「触发系数最高」的维度胜出——
    #      触发系数 = 该辅助分型平均住院费用 ÷ 病种平均住院费用 = mj / M（取该维度子型最大值）。
    #   4. 子型系数（§(三)）：辅助分型调节系数 = mj / M（mj=子型均费，M=病种均费）；
    #      CCI 分级按规范查表固定系数（不纳入 mj/M 重算）。
    # ------------------------------------------------------------------
    AUX_MIN_CORE_CASES = 10       # 触发条件(1)：病种上年度病例数超一定例数
    AUX_MIN_SUBTYPE_CASES = 5     # 触发条件(2)：参与某一分型评估的病例数超一定例数
    AUX_CV_BEFORE_THRESHOLD = 0.7  # 触发条件(3)-组内CV偏大门槛（规范术语：遴选CV>0.7引入辅助分型）
    AUX_CV_IMPROVEMENT_THRESHOLD = 0.2  # 触发条件(3)-分型后CV下降≥20%（规范示例）
    AUX_ICU_RELAX_FACTOR = 0.5    # 监护病房触发条件适当放宽因子（§5.2）
    _CCI_LEVEL_COEFF = {
        "无": Decimal("1.0"),
        "一般": Decimal("1.1"),
        "严重": Decimal("1.2"),
        "极严重": Decimal("1.3"),
    }

    def build_auxiliary_subgroups(
        self,
        records: List[MedicalRecord],
        core_disease_codes: Optional[set] = None,
        min_core_cases: int = None,
        min_subtype_cases: int = None,
        cv_before_threshold: float = None,
        cv_improvement_threshold: float = None,
        icu_relax_factor: float = None,
    ) -> List[AuxiliarySubgroup]:
        """对核心病种记录做子组级辅助分型聚类（严格贴合 DIP3.0 §5.2）。

        Args:
            records: 全部（或已筛选的）病例记录。
            core_disease_codes: 若提供，仅对该集合内的核心病种记录测算
                                （Web 传核心病种码，避免综合病种混入）。
            min_core_cases: 触发条件(1) 病种最小病例数（默认 AUX_MIN_CORE_CASES）。
            min_subtype_cases: 触发条件(2) 子型最小病例数（默认 AUX_MIN_SUBTYPE_CASES）。
            cv_before_threshold: 触发条件(3) 组内费用 CV 偏大门槛
                                 （默认 AUX_CV_BEFORE_THRESHOLD=0.7）。
            cv_improvement_threshold: 触发条件(3) 分型后 CV 下降幅度门槛
                                 （默认 AUX_CV_IMPROVEMENT_THRESHOLD=0.2）。
            icu_relax_factor: 监护病房维度门槛放宽因子（默认 AUX_ICU_RELAX_FACTOR=0.5）。

        Returns:
            AuxiliarySubgroup 列表（子组级；无任何维度达标的病种不产生子组）。
        """
        if min_core_cases is None:
            min_core_cases = self.AUX_MIN_CORE_CASES
        if min_subtype_cases is None:
            min_subtype_cases = self.AUX_MIN_SUBTYPE_CASES
        if cv_before_threshold is None:
            cv_before_threshold = self.AUX_CV_BEFORE_THRESHOLD
        if cv_improvement_threshold is None:
            cv_improvement_threshold = self.AUX_CV_IMPROVEMENT_THRESHOLD
        if icu_relax_factor is None:
            icu_relax_factor = self.AUX_ICU_RELAX_FACTOR

        if core_disease_codes is not None:
            recs = [r for r in records if r.dip_disease_code in core_disease_codes]
        else:
            recs = list(records)

        groups = defaultdict(list)
        for r in recs:
            groups[r.dip_disease_code].append(r)

        subgroups: List[AuxiliarySubgroup] = []
        for dcode, grecs in groups.items():
            subs = self._build_disease_aux_subgroups(
                dcode, grecs, min_core_cases, min_subtype_cases,
                cv_before_threshold, cv_improvement_threshold, icu_relax_factor,
            )
            subgroups.extend(subs)
        return subgroups

    def _build_disease_aux_subgroups(
        self, dcode, grecs, min_core, min_subtype,
        cv_before_threshold, cv_improvement_threshold, icu_relax_factor,
    ) -> List[AuxiliarySubgroup]:
        n = len(grecs)
        if n < min_core:
            return []
        costs = [float(r.total_cost) for r in grecs]
        M = sum(costs) / n if n else 0.0
        if M <= 0:
            return []

        dname = getattr(grecs[0], "dip_disease_name", None) or dcode
        disease_mean = Decimal(str(M))

        # 触发条件(3)-前：分型前（整个核心病种组）组内费用变异系数 CV（偏大才值得分型）
        cv_before = self._compute_cv(costs)

        dim_defs = {
            "CCI": self._label_cci,
            "疾病严重程度": lambda r: self._label_severity(r, disease_mean),
            "年龄特征": self._label_age,
            "重症监护": self._label_icu,
        }

        candidates = []  # 每个维度一个候选：{dimension, kept, cv_after, reduction, trigger}
        for dim_name, labeller in dim_defs.items():
            subtype_costs = defaultdict(list)
            for r in grecs:
                st = labeller(r)
                subtype_costs[st].append(float(r.total_cost))

            if dim_name == "CCI":
                # CCI 系数查表、临床意义固定，不做低频合并
                kept = dict(subtype_costs)
            else:
                kept = {st: c for st, c in subtype_costs.items() if len(c) >= min_subtype}
                merged = [c for st, c in subtype_costs.items() if len(c) < min_subtype]
                if merged:
                    kept["其他(低频合并)"] = [x for sub in merged for x in sub]

            if len(kept) < 2:
                continue  # 仅一个子型 → 无差异，跳过该维度

            # 触发条件(3)-后：沿该维度拆分后的组内费用变异系数（池化，资源消耗差异度）
            cv_after = self._compute_cv_after_split(kept, M, n)
            reduction = (cv_before - cv_after) / cv_before if cv_before > 0 else 0.0
            # 触发系数 = 该维度的子型最大 mj/M（mj=子型均费，M=病种均费；§(二)）
            trigger = max((sum(c) / len(c)) / M for c in kept.values()) if M else 1.0
            candidates.append({
                "dimension": dim_name,
                "kept": kept,
                "cv_before": cv_before,
                "cv_after": cv_after,
                "reduction": reduction,
                "trigger": trigger,
            })

        # 闸门 + 维度竞争（§5.2 (一)(二)）：组内CV偏大 且 分型后CV下降≥20% 才算达标；
        # 多个达标维度取「触发系数(mj/M)最高」者胜出（实际应用的维度）。
        winner = self._select_winning_dimension(
            candidates, cv_before_threshold, cv_improvement_threshold, icu_relax_factor
        )
        if winner is None:
            # 无任何维度达标（组内同质或分型未明显改善差异）→ 不测算辅助分型
            return []

        out: List[AuxiliarySubgroup] = []
        for cand in candidates:
            dim_name = cand["dimension"]
            is_winner = (dim_name == winner)
            for st, c in cand["kept"].items():
                mj = sum(c) / len(c)
                if dim_name == "CCI":
                    coeff = self._CCI_LEVEL_COEFF.get(st, Decimal("1.0"))
                else:
                    coeff = Decimal(str(mj / M)) if M else Decimal("1.0")
                out.append(AuxiliarySubgroup(
                    disease_code=dcode,
                    disease_name=dname,
                    dimension=dim_name,
                    subtype=st,
                    case_count=len(c),
                    avg_cost=Decimal(str(mj)),
                    coefficient=coeff,
                    cv_before=cand["cv_before"],
                    cv_after=cand["cv_after"],
                    cv_reduction=cand["reduction"],
                    trigger_coefficient=Decimal(str(cand["trigger"])),
                    is_winning_dimension=is_winner,
                    is_other=(st == "其他(低频合并)"),
                ))
        return out

    @staticmethod
    def _compute_cv(values) -> float:
        """变异系数 CV = 标准差 / 均值（费用波动程度）。空/均值为 0 时返回 0。"""
        n = len(values)
        if n == 0:
            return 0.0
        mean = sum(values) / n
        if mean == 0:
            return 0.0
        var = sum((v - mean) ** 2 for v in values) / n
        return (var ** 0.5) / mean

    @staticmethod
    def _compute_cv_after_split(kept: Dict[str, list], M: float, n: int) -> float:
        """沿某维度拆分后，组内（池化）费用变异系数 CV（资源消耗差异度）。

        池化组内方差 = Σ_k Σ_{x∈k} (x - m_k)² / N，再 σ_within / M。
        反映分型后各子型内部的费用离散程度（越小说明分型把钱花得接近的病例聚到一起）。
        """
        if M <= 0 or n == 0:
            return 0.0
        ss_within = 0.0
        for c in kept.values():
            if not c:
                continue
            mk = sum(c) / len(c)
            ss_within += sum((x - mk) ** 2 for x in c)
        var_within = ss_within / n
        return (var_within ** 0.5) / M

    @staticmethod
    def _select_winning_dimension(
        candidates: list,
        cv_before_threshold: float,
        cv_improvement_threshold: float,
        icu_relax_factor: float,
    ) -> Optional[str]:
        """§5.2 闸门 + 维度竞争。

        闸门：组内费用 CV 偏大（cv_before >= 门槛，ICU 放宽）且分型后 CV 下降
              幅度 >= 门槛（ICU 放宽）→ 该维度达标。
        竞争：多个达标维度中，取「触发系数(mj/M)最高」者胜出（§(二)）。
        无任何维度达标返回 None（该病种不测算辅助分型）。
        """
        passing = []
        for c in candidates:
            dim = c["dimension"]
            relax = icu_relax_factor if dim == "重症监护" else 1.0
            bt = cv_before_threshold * relax
            it = cv_improvement_threshold * relax
            if c["cv_before"] >= bt and c["reduction"] >= it:
                passing.append(c)
        if not passing:
            return None
        return max(passing, key=lambda c: c["trigger"])["dimension"]

    # ---- 各维度子型标签 ----
    def _label_cci(self, rec: MedicalRecord) -> str:
        diags = self.cci_calculator._split_codes(rec.related_diag_code)
        score = self.cci_calculator.calculate_cci(diags)
        level, _ = self.cci_calculator.get_cci_level(score)
        return level

    def _label_severity(self, rec: MedicalRecord, disease_mean: Decimal) -> str:
        if self._is_tumor_diagnosis(rec.main_diag_code):
            res = self.severity_classifier.classify_malignant_tumor(
                rec, disease_mean, disease_mean
            )
        else:
            res = self.severity_classifier.classify_non_malignant(rec)
        return res["level"]

    def _label_age(self, rec: MedicalRecord) -> str:
        res = self.age_classifier.classify(rec)
        if res is None:
            return "基准(无)"
        sub = res.get("sub_level")
        return f"{res['level']}({sub})" if sub else res["level"]

    def _label_icu(self, rec: MedicalRecord) -> str:
        icu_days = getattr(rec, "icu_days", 0)
        res = self.icu_classifier.classify(icu_days)
        if res is None:
            return "基准(无)"
        sub = res.get("sub_level")
        return f"{res['level']}({sub})" if sub else res["level"]
