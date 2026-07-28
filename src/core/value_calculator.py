"""
DIP按病种分值分组测算工具 - 分值计算模块
基于《国家医疗保障按病种分值(DIP)付费3.0版技术规范》第五章
"""
import pandas as pd
from typing import List, Dict, Optional, Tuple
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime

from ..models.models import (
    DiseaseGroup, MedicalRecord, CalculationMethod,
    HospitalCoefficient, AuxiliaryClassification
)


class ValueCalculator:
    """分值计算器"""
    
    # 默认年份权重（1:2:7）
    DEFAULT_YEAR_WEIGHTS = [0.1, 0.2, 0.7]
    
    def __init__(self, method: CalculationMethod = CalculationMethod.AVERAGE_COST):
        """
        初始化分值计算器
        
        Args:
            method: 计算方法
        """
        self.method = method
        self.year_weights = self.DEFAULT_YEAR_WEIGHTS.copy()
    
    def set_year_weights(self, weights: List[float]):
        """
        设置年份权重
        
        Args:
            weights: 年份权重列表
        """
        if abs(sum(weights) - 1.0) > 0.001:
            raise ValueError("年份权重之和必须为1.0")
        self.year_weights = weights
    
    def calculate_weighted_average(self, yearly_data: List[Decimal]) -> Decimal:
        """
        计算加权平均值
        
        Args:
            yearly_data: 各年份数据列表（按时间顺序，如2020, 2021, 2022）
            
        Returns:
            加权平均值
        """
        if len(yearly_data) != len(self.year_weights):
            raise ValueError(f"数据年份数({len(yearly_data)})与权重数({len(self.year_weights)})不匹配")
        
        weighted_sum = sum(data * Decimal(str(weight)) 
                          for data, weight in zip(yearly_data, self.year_weights))
        return weighted_sum.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    
    def calculate_by_average_cost(
        self, 
        disease_cost: Decimal, 
        total_avg_cost: Decimal
    ) -> Decimal:
        """
        平均费用法计算分值
        公式：RWi = mi / M × 1000
        
        Args:
            disease_cost: 病种组合平均住院医疗费用(mi)
            total_avg_cost: 本地所有出院病例平均住院医疗费用(M)
            
        Returns:
            病种分值(RW)
        """
        if total_avg_cost == 0:
            return Decimal("0")
        
        value = (disease_cost / total_avg_cost) * Decimal("1000")
        return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    
    def calculate_by_benchmark_disease(
        self,
        disease_cost: Decimal,
        benchmark_cost: Decimal
    ) -> Decimal:
        """
        基准病种费用法计算分值
        公式：RWi = mi / M × 1000
        
        Args:
            disease_cost: 病种组合平均住院医疗费用(mi)
            benchmark_cost: 基准病种平均住院医疗费用(M)
            
        Returns:
            病种分值(RW)
        """
        if benchmark_cost == 0:
            return Decimal("0")
        
        value = (disease_cost / benchmark_cost) * Decimal("1000")
        return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    
    def calculate_by_standard_quota(
        self,
        disease_cost: Decimal,
        standard_quota: Decimal
    ) -> Decimal:
        """
        标准定额法计算分值
        公式：RWi = mi / M
        
        Args:
            disease_cost: 病种组合平均住院医疗费用(mi)
            standard_quota: 标准定额(M)
            
        Returns:
            病种分值(RW)
        """
        if standard_quota == 0:
            return Decimal("0")
        
        value = disease_cost / standard_quota
        return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    
    def calculate_disease_value(
        self,
        disease_cost: Decimal,
        reference_cost: Decimal,
        method: Optional[CalculationMethod] = None
    ) -> Decimal:
        """
        计算病种分值
        
        Args:
            disease_cost: 病种平均费用
            reference_cost: 参考费用（全局平均/基准病种/标准定额）
            method: 计算方法，为None时使用默认方法
            
        Returns:
            病种分值
        """
        calc_method = method or self.method
        
        if calc_method == CalculationMethod.AVERAGE_COST:
            return self.calculate_by_average_cost(disease_cost, reference_cost)
        elif calc_method == CalculationMethod.BENCHMARK_DISEASE:
            return self.calculate_by_benchmark_disease(disease_cost, reference_cost)
        elif calc_method == CalculationMethod.STANDARD_QUOTA:
            return self.calculate_by_standard_quota(disease_cost, reference_cost)
        else:
            raise ValueError(f"不支持的计算方法: {calc_method}")
    
    def calculate_drug_value(
        self,
        disease_drug_cost: Decimal,
        total_avg_drug_cost: Decimal
    ) -> Decimal:
        """
        计算药品分值(dRW)
        公式：dRWi = dmi / dM
        
        Args:
            disease_drug_cost: 病种平均药品费用(dmi)
            total_avg_drug_cost: 全部住院病例平均药品费用(dM)
            
        Returns:
            药品分值(dRW)
        """
        if total_avg_drug_cost == 0:
            return Decimal("0")
        
        value = disease_drug_cost / total_avg_drug_cost
        return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    
    def calculate_consumable_value(
        self,
        disease_consumable_cost: Decimal,
        total_avg_consumable_cost: Decimal
    ) -> Decimal:
        """
        计算耗材分值(cRW)
        公式：cRWi = cmi / cM
        
        Args:
            disease_consumable_cost: 病种平均耗材费用(cmi)
            total_avg_consumable_cost: 全部住院病例平均耗材费用(cM)
            
        Returns:
            耗材分值(cRW)
        """
        if total_avg_consumable_cost == 0:
            return Decimal("0")
        
        value = disease_consumable_cost / total_avg_consumable_cost
        return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    
    def batch_calculate_values(
        self,
        groups: List[DiseaseGroup],
        total_avg_cost: Decimal,
        total_avg_drug_cost: Decimal = Decimal("0"),
        total_avg_consumable_cost: Decimal = Decimal("0")
    ) -> List[DiseaseGroup]:
        """
        批量计算病种分值
        
        Args:
            groups: 病种组合列表
            total_avg_cost: 全局平均住院费用
            total_avg_drug_cost: 全局平均药品费用
            total_avg_consumable_cost: 全局平均耗材费用
            
        Returns:
            更新后的病种组合列表
        """
        for group in groups:
            # 计算病种分值
            group.disease_value = self.calculate_disease_value(
                group.avg_cost, total_avg_cost
            )
            
            # 计算药品分值（如果有数据）
            if total_avg_drug_cost > 0 and hasattr(group, 'avg_drug_cost'):
                group.drug_value = self.calculate_drug_value(
                    group.avg_drug_cost, total_avg_drug_cost
                )
            
            # 计算耗材分值（如果有数据）
            if total_avg_consumable_cost > 0 and hasattr(group, 'avg_consumable_cost'):
                group.consumable_value = self.calculate_consumable_value(
                    group.avg_consumable_cost, total_avg_consumable_cost
                )
        
        return groups


class HospitalCoefficientCalculator:
    """医疗机构调节系数计算器"""
    
    def __init__(self):
        self.coefficients = {}
    
    def calculate_basic_coefficient(
        self,
        hospital_avg_cost: Decimal,
        city_avg_cost: Decimal
    ) -> Decimal:
        """
        计算基本系数
        公式：基本系数 = 同级别类型医疗机构病例加权平均住院费用 / 全市病例加权平均住院费用
        
        Args:
            hospital_avg_cost: 医疗机构平均住院费用
            city_avg_cost: 全市平均住院费用
            
        Returns:
            基本系数
        """
        if city_avg_cost == 0:
            return Decimal("1.0")
        
        coefficient = hospital_avg_cost / city_avg_cost
        return coefficient.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    
    def calculate_bonus_coefficient(
        self,
        medical_level: float = 0,
        specialty_feature: float = 0,
        cmi: float = 0,
        performance_score: float = 0,
        agreement_compliance: float = 0
    ) -> Decimal:
        """
        计算加成系数
        
        Args:
            medical_level: 医疗水平得分
            specialty_feature: 专科特色得分
            cmi: CMI值
            performance_score: 绩效考核得分
            agreement_compliance: 协议履行得分
            
        Returns:
            加成系数
        """
        # 简化计算：各因素加权求和
        weights = {
            'medical_level': 0.25,
            'specialty_feature': 0.20,
            'cmi': 0.25,
            'performance_score': 0.15,
            'agreement_compliance': 0.15
        }
        
        bonus = (
            medical_level * weights['medical_level'] +
            specialty_feature * weights['specialty_feature'] +
            cmi * weights['cmi'] +
            performance_score * weights['performance_score'] +
            agreement_compliance * weights['agreement_compliance']
        )
        
        return Decimal(str(bonus)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    
    def calculate_total_coefficient(
        self,
        basic_coefficient: Decimal,
        bonus_coefficient: Decimal
    ) -> Decimal:
        """
        计算总调节系数
        
        Args:
            basic_coefficient: 基本系数
            bonus_coefficient: 加成系数
            
        Returns:
            总调节系数
        """
        total = basic_coefficient + bonus_coefficient
        return total.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    
    def calculate_hospital_coefficients(
        self,
        hospital_data: List[Dict],
        city_avg_cost: Decimal
    ) -> List[HospitalCoefficient]:
        """
        批量计算医疗机构调节系数
        
        Args:
            hospital_data: 医疗机构数据列表
            city_avg_cost: 全市平均住院费用
            
        Returns:
            调节系数列表
        """
        coefficients = []
        
        for data in hospital_data:
            hospital_avg_cost = Decimal(str(data.get('avg_cost', 0)))
            
            basic = self.calculate_basic_coefficient(hospital_avg_cost, city_avg_cost)
            bonus = self.calculate_bonus_coefficient(
                medical_level=data.get('medical_level', 0),
                specialty_feature=data.get('specialty_feature', 0),
                cmi=data.get('cmi', 0),
                performance_score=data.get('performance_score', 0),
                agreement_compliance=data.get('agreement_compliance', 0)
            )
            total = self.calculate_total_coefficient(basic, bonus)
            
            coefficient = HospitalCoefficient(
                hospital_code=data.get('hospital_code', ''),
                hospital_name=data.get('hospital_name', ''),
                hospital_level=data.get('hospital_level', ''),
                basic_coefficient=basic,
                bonus_coefficient=bonus,
                total_coefficient=total
            )
            coefficients.append(coefficient)
        
        return coefficients


class AuxiliaryClassifier:
    """辅助分型分类器"""
    
    # 功能衰竭、休克、脓毒症诊断代码范围
    FAILURE_DIAGNOSIS = [
        # 功能衰竭
        ("R57", "R57.9"),  # 休克
        ("N17", "N19"),    # 肾衰竭
        ("J96", "J96.9"),  # 呼吸衰竭
        ("K72", "K72.9"),  # 肝衰竭
        # 脓毒症
        ("A40", "A41.9"),  # 脓毒症
    ]
    
    # 重要器官病损、重要脏器感染诊断代码范围
    ORGAN_DAMAGE_DIAGNOSIS = [
        ("I20", "I25"),    # 缺血性心脏病
        ("I60", "I69"),    # 脑血管病
        ("J85", "J86"),    # 肺脓肿
        ("K80", "K87"),    # 胆囊炎
    ]
    
    def __init__(self):
        self.classifications = {}
    
    def classify_malignant_tumor_severity(
        self,
        record: MedicalRecord,
        avg_cost: Decimal,
        cost_standard: Decimal
    ) -> AuxiliaryClassification:
        """
        恶性肿瘤疾病严重程度分型
        
        Args:
            record: 住院病例记录
            avg_cost: 病种平均费用
            cost_standard: 费用标准
            
        Returns:
            辅助分型分类
        """
        # 死亡病例
        if record.discharge_status == "死亡":
            return AuxiliaryClassification(
                classification_type="恶性肿瘤严重程度",
                classification_name="死亡",
                trigger_condition="出院状态=死亡",
                coefficient=Decimal("1.5")
            )
        
        # 高费用病例类型一：费用≥3倍标准，治疗费占比≥50%
        if (cost_standard > 0 and 
            record.total_cost >= cost_standard * 3 and
            record.treatment_cost / record.total_cost >= Decimal("0.5")):
            return AuxiliaryClassification(
                classification_type="恶性肿瘤严重程度",
                classification_name="高费用类型一",
                trigger_condition="费用≥3倍标准，治疗费占比≥50%",
                coefficient=Decimal("1.4")
            )
        
        # 高费用病例类型二：费用≥3倍标准，药品费占比≥50%
        if (cost_standard > 0 and
            record.total_cost >= cost_standard * 3 and
            record.drug_cost / record.total_cost >= Decimal("0.5")):
            return AuxiliaryClassification(
                classification_type="恶性肿瘤严重程度",
                classification_name="高费用类型二",
                trigger_condition="费用≥3倍标准，药品费占比≥50%",
                coefficient=Decimal("1.35")
            )
        
        # 肿瘤有转移或其他部位并发
        if record.related_diag_code:
            related_diag_prefix = record.related_diag_code[:3]
            main_diag_prefix = record.main_diag_code[:3]
            if (related_diag_prefix != main_diag_prefix and
                record.los >= 3):
                return AuxiliaryClassification(
                    classification_type="恶性肿瘤严重程度",
                    classification_name="肿瘤转移",
                    trigger_condition="相关诊断与主诊断不同，住院天数≥3天",
                    coefficient=Decimal("1.25")
                )
        
        # 默认：其他情况
        return AuxiliaryClassification(
            classification_type="恶性肿瘤严重程度",
            classification_name="其他",
            trigger_condition="默认",
            coefficient=Decimal("1.0")
        )
    
    def classify_non_malignant_severity(
        self,
        record: MedicalRecord
    ) -> AuxiliaryClassification:
        """
        非恶性肿瘤疾病严重程度分型
        
        Args:
            record: 住院病例记录
            
        Returns:
            辅助分型分类
        """
        # 死亡病例
        if record.discharge_status == "死亡":
            return AuxiliaryClassification(
                classification_type="非恶性肿瘤严重程度",
                classification_name="死亡",
                trigger_condition="出院状态=死亡",
                coefficient=Decimal("1.5")
            )
        
        # 重度：次要诊断属于"功能衰竭、休克、脓毒症"，且住院天数≥3天
        if record.related_diag_code and record.los >= 3:
            related_prefix = record.related_diag_code[:3]
            for start, end in self.FAILURE_DIAGNOSIS:
                if start <= related_prefix <= end:
                    return AuxiliaryClassification(
                        classification_type="非恶性肿瘤严重程度",
                        classification_name="重度",
                        trigger_condition="次要诊断含功能衰竭/休克/脓毒症，住院天数≥3天",
                        coefficient=Decimal("1.3")
                    )
        
        # 中度：次要诊断属于"重要器官病损、重要脏器感染"，且住院天数≥3天
        if record.related_diag_code and record.los >= 3:
            related_prefix = record.related_diag_code[:3]
            for start, end in self.ORGAN_DAMAGE_DIAGNOSIS:
                if start <= related_prefix <= end:
                    return AuxiliaryClassification(
                        classification_type="非恶性肿瘤严重程度",
                        classification_name="中度",
                        trigger_condition="次要诊断含重要器官病损/感染，住院天数≥3天",
                        coefficient=Decimal("1.15")
                    )
        
        # 轻度：其他病例
        return AuxiliaryClassification(
            classification_type="非恶性肿瘤严重程度",
            classification_name="轻度",
            trigger_condition="默认",
            coefficient=Decimal("1.0")
        )
    
    def classify_age_feature(
        self,
        record: MedicalRecord
    ) -> Optional[AuxiliaryClassification]:
        """
        年龄特征分型
        
        Args:
            record: 住院病例记录
            
        Returns:
            辅助分型分类（如果不适用则返回None）
        """
        age = record.age
        
        # 18岁以下
        if age < 18:
            if age < 1:
                age_group = "新生儿期(0-28天)"
                coefficient = Decimal("1.2")
            elif age < 6:
                age_group = "婴幼儿期(1-5岁)"
                coefficient = Decimal("1.15")
            elif age < 12:
                age_group = "学龄期(6-11岁)"
                coefficient = Decimal("1.1")
            else:
                age_group = "青春期(12-17岁)"
                coefficient = Decimal("1.05")
            
            return AuxiliaryClassification(
                classification_type="年龄特征",
                classification_name=age_group,
                trigger_condition=f"年龄={age}岁",
                coefficient=coefficient
            )
        
        # 65岁以上
        if age >= 65:
            if age < 70:
                age_group = "年轻老年(65-69岁)"
                coefficient = Decimal("1.05")
            elif age < 80:
                age_group = "老年(70-79岁)"
                coefficient = Decimal("1.1")
            else:
                age_group = "高龄老年(80+岁)"
                coefficient = Decimal("1.2")
            
            return AuxiliaryClassification(
                classification_type="年龄特征",
                classification_name=age_group,
                trigger_condition=f"年龄={age}岁",
                coefficient=coefficient
            )
        
        return None
    
    def classify_icu_days(
        self,
        record: MedicalRecord,
        icu_days: int
    ) -> Optional[AuxiliaryClassification]:
        """
        监护病房住院天数分型
        
        Args:
            record: 住院病例记录
            icu_days: ICU住院天数
            
        Returns:
            辅助分型分类（如果不适用则返回None）
        """
        if icu_days < 2:
            return None
        
        if icu_days <= 7:
            days_group = "2-7天"
            coefficient = Decimal("1.1")
        elif icu_days <= 14:
            days_group = "8-14天"
            coefficient = Decimal("1.25")
        elif icu_days <= 30:
            days_group = "15-30天"
            coefficient = Decimal("1.4")
        else:
            days_group = "31天以上"
            coefficient = Decimal("1.6")
        
        return AuxiliaryClassification(
            classification_type="ICU天数",
            classification_name=days_group,
            trigger_condition=f"ICU天数={icu_days}天",
            coefficient=coefficient
        )
    
    def get_highest_coefficient(
        self,
        record: MedicalRecord,
        avg_cost: Decimal = Decimal("0"),
        cost_standard: Decimal = Decimal("0"),
        icu_days: int = 0
    ) -> AuxiliaryClassification:
        """
        获取最高的辅助分型调节系数
        
        Args:
            record: 住院病例记录
            avg_cost: 病种平均费用
            cost_standard: 费用标准
            icu_days: ICU住院天数
            
        Returns:
            最高系数的辅助分型分类
        """
        classifications = []
        
        # 恶性肿瘤严重程度
        if record.main_diag_code and DiagnosisClassifier.is_tumor_diagnosis(record.main_diag_code):
            classifications.append(
                self.classify_malignant_tumor_severity(record, avg_cost, cost_standard)
            )
        
        # 非恶性肿瘤严重程度
        classifications.append(
            self.classify_non_malignant_severity(record)
        )
        
        # 年龄特征
        age_class = self.classify_age_feature(record)
        if age_class:
            classifications.append(age_class)
        
        # ICU天数
        icu_class = self.classify_icu_days(record, icu_days)
        if icu_class:
            classifications.append(icu_class)
        
        # 返回最高系数的分类
        if classifications:
            return max(classifications, key=lambda x: x.coefficient)
        
        return AuxiliaryClassification(
            classification_type="默认",
            classification_name="无辅助分型",
            trigger_condition="默认",
            coefficient=Decimal("1.0")
        )


class DiagnosisClassifier:
    """疾病诊断分类器（辅助）"""
    
    @staticmethod
    def is_tumor_diagnosis(diag_code: str) -> bool:
        """检查是否为肿瘤诊断"""
        if not diag_code:
            return False
        prefix = diag_code[:3]
        return "C00" <= prefix <= "C97" or "D00" <= prefix <= "D48"
