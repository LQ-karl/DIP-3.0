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

from ..models.models import MedicalRecord, DiseaseGroup


class CCICalculator:
    """Charlson合并症指数(CCI)计算器"""
    
    # CCI评分标准
    CCI_SCORES = {
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
    
    def __init__(self):
        pass
    
    def calculate_cci(self, diagnoses: List[str]) -> int:
        """
        计算CCI分数
        
        Args:
            diagnoses: 诊断代码列表（ICD-10）
            
        Returns:
            CCI总分
        """
        if not diagnoses:
            return 0
        
        total_score = 0
        max_scores = {}  # 同类疾病取最高分
        
        for diag_code in diagnoses:
            if not diag_code:
                continue
            
            # 提取诊断代码前3-4位进行匹配
            code_prefix = diag_code[:3]
            code_4 = diag_code[:4] if len(diag_code) >= 4 else diag_code
            
            # 查找分数
            score = 0
            
            # 先尝试4位码匹配（更精确）
            if code_4 in self.CCI_SCORES:
                score = self.CCI_SCORES[code_4]
            # 再尝试3位码匹配
            elif code_prefix in self.CCI_SCORES:
                score = self.CCI_SCORES[code_prefix]
            
            if score > 0:
                # 同类疾病只取最高分
                category = self._get_disease_category(code_prefix)
                if category not in max_scores or score > max_scores[category]:
                    max_scores[category] = score
        
        total_score = sum(max_scores.values())
        return total_score
    
    def _get_disease_category(self, code_prefix: str) -> str:
        """获取疾病大类"""
        if "I21" <= code_prefix <= "I25":
            return "心肌梗死"
        elif "I50" <= code_prefix <= "I50":
            return "心力衰竭"
        elif "I60" <= code_prefix <= "I69":
            return "脑血管病"
        elif "C00" <= code_prefix <= "C96":
            return "肿瘤"
        elif "E10" <= code_prefix <= "E13":
            return "糖尿病"
        else:
            return code_prefix
    
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
    
    def __init__(self):
        pass
    
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

        # (4) 肿瘤有转移或其他部位并发：次要诊断含其他部位恶性肿瘤，住院天数≥3天
        if record.related_diag_code:
            related_prefix = record.related_diag_code[:3]
            main_prefix = record.main_diag_code[:3]
            if ("C00" <= related_prefix <= "C96" and
                related_prefix != main_prefix and
                record.los >= 3):
                return {
                    "type": "恶性肿瘤严重程度",
                    "level": "肿瘤转移并发",
                    "coefficient": Decimal("1.25"),
                    "condition": "次要诊断含其他部位肿瘤，住院天数≥3天"
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
    
    def _has_severe_complication(self, diag_code: str) -> bool:
        """检查是否含严重并发症（功能衰竭、休克、脓毒症）"""
        if not diag_code:
            return False
        prefix = diag_code[:3]
        # 休克、功能衰竭、脓毒症
        severe_codes = [
            ("R57", "R57.9"),  # 休克
            ("N17", "N19"),    # 肾衰竭
            ("J96", "J96.9"),  # 呼吸衰竭
            ("K72", "K72.9"),  # 肝衰竭
            ("A40", "A41.9"),  # 脓毒症
        ]
        for start, end in severe_codes:
            if start <= prefix <= end:
                return True
        return False
    
    def _has_organ_damage(self, diag_code: str) -> bool:
        """检查是否含重要器官病损、重要脏器感染"""
        if not diag_code:
            return False
        prefix = diag_code[:3]
        organ_codes = [
            ("I20", "I25"),  # 缺血性心脏病
            ("I60", "I69"),  # 脑血管病
            ("J85", "J86"),  # 肺脓肿
            ("K80", "K87"),  # 胆囊炎
            ("N10", "N17"),  # 肾感染
        ]
        for start, end in organ_codes:
            if start <= prefix <= end:
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
        disease_mortality_rate: Decimal = Decimal("0")
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
        
        # 1. CCI计算
        diagnoses = [record.main_diag_code]
        if record.related_diag_code:
            diagnoses.append(record.related_diag_code)
        cci_score = self.cci_calculator.calculate_cci(diagnoses)
        cci_level, cci_coeff = self.cci_calculator.get_cci_level(cci_score)
        results["cci"] = {
            "score": cci_score,
            "level": cci_level,
            "coefficient": cci_coeff
        }
        
        # 2. 疾病严重程度分型
        is_tumor = self._is_tumor_diagnosis(record.main_diag_code)
        if is_tumor:
            results["severity"] = self.severity_classifier.classify_malignant_tumor(
                record, disease_avg_cost, disease_avg_cost * Decimal("2")
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
