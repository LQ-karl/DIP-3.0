"""
DIP按病种分值分组测算工具 - 辅助目录分型表格模块
基于《国家医疗保障按病种分值(DIP)付费3.0版技术规范》
功能：辅助目录分型单独形成表格输出
"""
import pandas as pd
from typing import List, Dict, Optional
from decimal import Decimal, ROUND_HALF_UP
from dataclasses import dataclass, field
from pathlib import Path

from ..models.models import MedicalRecord


@dataclass
class AuxiliaryClassification:
    """辅助分类记录"""
    record_id: str  # 病例ID
    dip_code: str  # DIP编码
    hospital_code: str  # 医院代码
    
    # CCI分类
    cci_score: Decimal = Decimal("0")  # CCI评分
    cci_type: str = ""  # CCI类型：无合并症/一般合并症/重要合并症/特别重要合并症
    cci_coefficient: Decimal = Decimal("1.0")  # CCI调节系数
    
    # 疾病严重程度分类
    severity_level: str = ""  # 严重程度：一般/中度/重度/危重
    severity_coefficient: Decimal = Decimal("1.0")  # 严重程度调节系数
    severity_type: str = ""  # 严重程度类型：恶性肿瘤/非恶性肿瘤
    
    # 年龄特征分类
    age_type: str = ""  # 年龄类型：新生儿/婴儿/幼儿/学龄期/青春期/中年/年轻老年/老年/高龄老年
    age_coefficient: Decimal = Decimal("1.0")  # 年龄调节系数
    
    # ICU天数分类
    icu_days: Decimal = Decimal("0")  # ICU天数
    icu_type: str = ""  # ICU类型：无ICU/短期ICU/中期ICU/长期ICU/超长ICU
    icu_coefficient: Decimal = Decimal("1.0")  # ICU调节系数
    
    # 违规行为监测
    violation_score: Decimal = Decimal("0")  # 违规评分
    violation_type: str = ""  # 违规类型：正常/二次入院/低标入院/超长住院/死亡风险
    violation_coefficient: Decimal = Decimal("1.0")  # 违规调节系数
    
    # 综合调节系数
    max_coefficient: Decimal = Decimal("1.0")  # 最高调节系数
    max_coefficient_type: str = ""  # 最高调节系数类型


class AuxiliaryDirectoryExporter:
    """辅助目录分型导出器"""
    
    # CCI分类标准
    CCI_TYPES = {
        0: {"type": "无合并症", "coefficient": Decimal("1.0")},
        1: {"type": "一般合并症", "coefficient": Decimal("1.1")},
        2: {"type": "重要合并症", "coefficient": Decimal("1.2")},
        3: {"type": "特别重要合并症", "coefficient": Decimal("1.3")},
        4: {"type": "特别重要合并症", "coefficient": Decimal("1.4")}
    }
    
    # 疾病严重程度分类标准
    SEVERITY_TYPES = {
        "恶性肿瘤": {
            "一般": {"coefficient": Decimal("1.0"), "type": "恶性肿瘤-一般"},
            "中度": {"coefficient": Decimal("1.2"), "type": "恶性肿瘤-中度"},
            "重度": {"coefficient": Decimal("1.5"), "type": "恶性肿瘤-重度"},
            "危重": {"coefficient": Decimal("1.8"), "type": "恶性肿瘤-危重"}
        },
        "非恶性肿瘤": {
            "一般": {"coefficient": Decimal("1.0"), "type": "非恶性肿瘤-一般"},
            "中度": {"coefficient": Decimal("1.1"), "type": "非恶性肿瘤-中度"},
            "重度": {"coefficient": Decimal("1.3"), "type": "非恶性肿瘤-重度"},
            "危重": {"coefficient": Decimal("1.5"), "type": "非恶性肿瘤-危重"}
        }
    }
    
    # 年龄特征分类标准
    AGE_TYPES = {
        "新生儿期(0-28天)": {"coefficient": Decimal("1.25"), "min_age": 0, "max_age": 0.077},
        "婴儿期(1月-1岁)": {"coefficient": Decimal("1.20"), "min_age": 0.077, "max_age": 1},
        "幼儿期(1-5岁)": {"coefficient": Decimal("1.15"), "min_age": 1, "max_age": 5},
        "学龄期(6-11岁)": {"coefficient": Decimal("1.10"), "min_age": 6, "max_age": 11},
        "青春期(12-17岁)": {"coefficient": Decimal("1.05"), "min_age": 12, "max_age": 17},
        "中年(18-64岁)": {"coefficient": Decimal("1.0"), "min_age": 18, "max_age": 64},
        "年轻老年(65-69岁)": {"coefficient": Decimal("1.05"), "min_age": 65, "max_age": 69},
        "老年(70-79岁)": {"coefficient": Decimal("1.10"), "min_age": 70, "max_age": 79},
        "高龄老年(80+岁)": {"coefficient": Decimal("1.20"), "min_age": 80, "max_age": 200}
    }
    
    # ICU天数分类标准
    ICU_TYPES = {
        "无ICU(0天)": {"coefficient": Decimal("1.0"), "min_days": 0, "max_days": 0},
        "短期ICU(2-7天)": {"coefficient": Decimal("1.15"), "min_days": 2, "max_days": 7},
        "中期ICU(8-14天)": {"coefficient": Decimal("1.30"), "min_days": 8, "max_days": 14},
        "长期ICU(15-30天)": {"coefficient": Decimal("1.50"), "min_days": 15, "max_days": 30},
        "超长ICU(31天以上)": {"coefficient": Decimal("1.70"), "min_days": 31, "max_days": 999}
    }
    
    def __init__(self):
        pass
    
    def classify_records(self, records: List[MedicalRecord]) -> List[AuxiliaryClassification]:
        """
        对病例记录进行辅助分类
        
        Args:
            records: 病例记录列表
            
        Returns:
            辅助分类记录列表
        """
        classifications = []
        
        for record in records:
            classification = AuxiliaryClassification(
                record_id=record.record_id,
                dip_code=record.dip_disease_code,
                hospital_code=record.hospital_code
            )
            
            # CCI分类
            classification.cci_score = getattr(record, 'cci_score', Decimal("0"))
            classification.cci_type, classification.cci_coefficient = self._classify_cci(
                classification.cci_score
            )
            
            # 疾病严重程度分类
            classification.severity_level = getattr(record, 'severity_level', '一般')
            classification.severity_type, classification.severity_coefficient = self._classify_severity(
                classification.severity_level,
                record.main_diag_code,
                record
            )
            
            # 年龄特征分类
            age = getattr(record, 'age', 0)
            classification.age_type, classification.age_coefficient = self._classify_age(age)
            
            # ICU天数分类
            classification.icu_days = getattr(record, 'icu_days', Decimal("0"))
            classification.icu_type, classification.icu_coefficient = self._classify_icu(
                classification.icu_days
            )
            
            # 违规行为监测
            classification.violation_score = getattr(record, 'violation_score', Decimal("0"))
            classification.violation_type, classification.violation_coefficient = self._classify_violation(
                classification.violation_score
            )
            
            # 计算综合调节系数
            classification.max_coefficient, classification.max_coefficient_type = \
                self._calculate_max_coefficient(classification)
            
            classifications.append(classification)
        
        return classifications
    
    def _classify_cci(self, cci_score: Decimal) -> tuple:
        """CCI分类"""
        score = int(cci_score)
        if score >= 4:
            return self.CCI_TYPES[4]["type"], self.CCI_TYPES[4]["coefficient"]
        return self.CCI_TYPES.get(score, self.CCI_TYPES[0])["type"], \
               self.CCI_TYPES.get(score, self.CCI_TYPES[0])["coefficient"]
    
    def _classify_severity(self, severity_level: str, diag_code: str, 
                           record: MedicalRecord = None) -> tuple:
        """
        疾病严重程度分类
        基于DIP3.0技术规范：
        恶性肿瘤疾病严重程度辅助分型：
        (1) 死亡病例
        (2) 高费用病例类型一：医疗费用≥该病种分值费用标准3倍，治疗费占比≥50%
        (3) 高费用病例类型二：医疗费用≥该病种分值费用标准3倍，药品费用占比≥50%
        (4) 肿瘤有转移或其他部位并发：次要诊断含恶性肿瘤且所属类目不同，住院天数≥3天
        (5) 次要诊断属于"功能衰竭、休克、脓毒症"范围，住院天数≥3天
        (6) 次要诊断属于"重要器官病损、重要脏器感染"范围，住院天数≥3天
        (7) 其他情况
        
        非恶性肿瘤疾病严重程度辅助分型：
        (1) 死亡病例
        (2) 重度：次要诊断属于"功能衰竭、休克、脓毒症"范围，住院天数≥3天
        (3) 中度：次要诊断属于"重要器官病损、重要脏器感染"范围，住院天数≥3天
        (4) 轻度：其他病例
        """
        # 判断是否为恶性肿瘤
        is_malignant = self._is_malignant_tumor(diag_code)
        category = "恶性肿瘤" if is_malignant else "非恶性肿瘤"
        
        # 如果有病例详细信息，进行详细分级
        if record:
            severity_level = self._determine_severity_level(record, is_malignant)
        
        severity_info = self.SEVERITY_TYPES[category].get(
            severity_level,
            self.SEVERITY_TYPES[category]["一般"]
        )
        
        return severity_info["type"], severity_info["coefficient"]
    
    def _determine_severity_level(self, record: MedicalRecord, is_malignant: bool) -> str:
        """根据病例信息确定疾病严重程度等级"""
        # 检查是否死亡
        if self._is_death_case(record):
            return "危重"
        
        # 检查住院天数
        stay_days = getattr(record, 'stay_days', 0)
        
        # 检查次要诊断
        secondary_diag = getattr(record, 'secondary_diag_code', '')
        
        # 功能衰竭、休克、脓毒症相关诊断编码
        failure_codes = ['I50', 'I62', 'I63', 'I64', 'R57', 'R65']
        # 重要器官病损、重要脏器感染相关诊断编码
        organ_codes = ['N10', 'N17', 'J18', 'K83', 'K85']
        
        has_failure = any(secondary_diag.startswith(code) for code in failure_codes) if secondary_diag else False
        has_organ_damage = any(secondary_diag.startswith(code) for code in organ_codes) if secondary_diag else False
        
        if is_malignant:
            # 恶性肿瘤分级
            if has_failure and stay_days >= 3:
                return "危重"
            elif has_organ_damage and stay_days >= 3:
                return "重度"
            elif self._is_high_cost_case(record):
                return "中度"
            else:
                return "一般"
        else:
            # 非恶性肿瘤分级
            if has_failure and stay_days >= 3:
                return "危重"
            elif has_organ_damage and stay_days >= 3:
                return "中度"
            else:
                return "一般"
    
    def _is_death_case(self, record: MedicalRecord) -> bool:
        """检查是否为死亡病例"""
        # 检查出院情况或死亡标记
        discharge_status = getattr(record, 'discharge_status', '')
        death_flag = getattr(record, 'death_flag', False)
        return death_flag or discharge_status in ['死亡', '死', 'D']
    
    def _is_high_cost_case(self, record: MedicalRecord, 
                           threshold_multiplier: Decimal = Decimal("3")) -> bool:
        """检查是否为高费用病例"""
        # 这里需要病种分值费用标准，暂时使用3倍作为判断
        total_cost = getattr(record, 'total_cost', Decimal("0"))
        # 简化判断：如果费用超过一定阈值则认为是高费用
        return total_cost > Decimal("50000")  # 临时阈值
    
    def _is_malignant_tumor(self, diag_code: str) -> bool:
        """判断是否为恶性肿瘤"""
        # 恶性肿瘤ICD-10代码范围：C00-C99
        if not diag_code:
            return False
        
        code = diag_code.upper().strip()
        if code.startswith('C') and len(code) >= 4:
            try:
                num = int(code[1:3])
                return 0 <= num <= 99
            except ValueError:
                return False
        return False
    
    def _classify_age(self, age: int) -> tuple:
        """年龄特征分类"""
        for age_type, info in self.AGE_TYPES.items():
            if info["min_age"] <= age <= info["max_age"]:
                return age_type, info["coefficient"]
        
        return "中年", Decimal("1.0")
    
    def _classify_icu(self, icu_days: Decimal) -> tuple:
        """ICU天数分类"""
        days = int(icu_days)
        
        for icu_type, info in self.ICU_TYPES.items():
            if info["min_days"] <= days <= info["max_days"]:
                return icu_type, info["coefficient"]
        
        return "无ICU(0天)", Decimal("1.0")
    
    def _classify_violation(self, violation_score: Decimal) -> tuple:
        """违规行为分类"""
        if violation_score >= 0.8:
            return "高风险", Decimal("1.0")
        elif violation_score >= 0.5:
            return "中风险", Decimal("1.0")
        elif violation_score > 0:
            return "低风险", Decimal("1.0")
        else:
            return "正常", Decimal("1.0")
    
    def _calculate_max_coefficient(self, classification: AuxiliaryClassification) -> tuple:
        """计算最高调节系数"""
        coefficients = {
            "CCI": classification.cci_coefficient,
            "疾病严重程度": classification.severity_coefficient,
            "年龄特征": classification.age_coefficient,
            "ICU天数": classification.icu_coefficient,
            "违规行为": classification.violation_coefficient
        }
        
        max_type = max(coefficients, key=coefficients.get)
        max_coeff = coefficients[max_type]
        
        return max_coeff, max_type
    
    def export_to_excel(
        self,
        classifications: List[AuxiliaryClassification],
        output_path: str
    ) -> str:
        """
        导出辅助分类到Excel
        
        Args:
            classifications: 辅助分类记录列表
            output_path: 输出文件路径
            
        Returns:
            输出文件路径
        """
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            # 1. CCI分类表
            cci_data = []
            for i, c in enumerate(classifications, 1):
                cci_data.append({
                    '序号': i,
                    '病例ID': c.record_id,
                    'DIP编码': c.dip_code,
                    '医院代码': c.hospital_code,
                    'CCI评分': float(c.cci_score),
                    'CCI类型': c.cci_type,
                    'CCI调节系数': float(c.cci_coefficient)
                })
            cci_df = pd.DataFrame(cci_data)
            cci_df.to_excel(writer, sheet_name='CCI分类', index=False)
            
            # 2. 疾病严重程度分类表
            severity_data = []
            for i, c in enumerate(classifications, 1):
                severity_data.append({
                    '序号': i,
                    '病例ID': c.record_id,
                    'DIP编码': c.dip_code,
                    '医院代码': c.hospital_code,
                    '疾病严重程度': c.severity_level,
                    '严重程度类型': c.severity_type,
                    '严重程度调节系数': float(c.severity_coefficient)
                })
            severity_df = pd.DataFrame(severity_data)
            severity_df.to_excel(writer, sheet_name='疾病严重程度', index=False)
            
            # 3. 年龄特征分类表
            age_data = []
            for i, c in enumerate(classifications, 1):
                age_data.append({
                    '序号': i,
                    '病例ID': c.record_id,
                    'DIP编码': c.dip_code,
                    '医院代码': c.hospital_code,
                    '年龄类型': c.age_type,
                    '年龄调节系数': float(c.age_coefficient)
                })
            age_df = pd.DataFrame(age_data)
            age_df.to_excel(writer, sheet_name='年龄特征', index=False)
            
            # 4. ICU天数分类表
            icu_data = []
            for i, c in enumerate(classifications, 1):
                icu_data.append({
                    '序号': i,
                    '病例ID': c.record_id,
                    'DIP编码': c.dip_code,
                    '医院代码': c.hospital_code,
                    'ICU天数': float(c.icu_days),
                    'ICU类型': c.icu_type,
                    'ICU调节系数': float(c.icu_coefficient)
                })
            icu_df = pd.DataFrame(icu_data)
            icu_df.to_excel(writer, sheet_name='ICU天数', index=False)
            
            # 5. 违规行为监测表
            violation_data = []
            for i, c in enumerate(classifications, 1):
                violation_data.append({
                    '序号': i,
                    '病例ID': c.record_id,
                    'DIP编码': c.dip_code,
                    '医院代码': c.hospital_code,
                    '违规评分': float(c.violation_score),
                    '违规类型': c.violation_type,
                    '违规调节系数': float(c.violation_coefficient)
                })
            violation_df = pd.DataFrame(violation_data)
            violation_df.to_excel(writer, sheet_name='违规行为', index=False)
            
            # 6. 综合调节系数表
            summary_data = []
            for i, c in enumerate(classifications, 1):
                summary_data.append({
                    '序号': i,
                    '病例ID': c.record_id,
                    'DIP编码': c.dip_code,
                    '医院代码': c.hospital_code,
                    'CCI调节系数': float(c.cci_coefficient),
                    '严重程度调节系数': float(c.severity_coefficient),
                    '年龄调节系数': float(c.age_coefficient),
                    'ICU调节系数': float(c.icu_coefficient),
                    '违规调节系数': float(c.violation_coefficient),
                    '最高调节系数': float(c.max_coefficient),
                    '最高调节系数类型': c.max_coefficient_type
                })
            summary_df = pd.DataFrame(summary_data)
            summary_df.to_excel(writer, sheet_name='综合调节系数', index=False)
            
            # 7. 统计汇总表
            stats = self._generate_statistics(classifications)
            stats_df = pd.DataFrame(stats)
            stats_df.to_excel(writer, sheet_name='统计汇总', index=False)
        
        return output_path
    
    def _generate_statistics(self, classifications: List[AuxiliaryClassification]) -> List[Dict]:
        """生成统计汇总"""
        if not classifications:
            return []
        
        stats = []
        
        # CCI统计
        cci_counts = {}
        for c in classifications:
            cci_type = c.cci_type
            cci_counts[cci_type] = cci_counts.get(cci_type, 0) + 1
        
        for cci_type, count in cci_counts.items():
            stats.append({
                '统计项': f'CCI-{cci_type}',
                '数量': count,
                '占比': f"{count/len(classifications)*100:.1f}%"
            })
        
        # 疾病严重程度统计
        severity_counts = {}
        for c in classifications:
            severity_type = c.severity_type
            severity_counts[severity_type] = severity_counts.get(severity_type, 0) + 1
        
        for severity_type, count in severity_counts.items():
            stats.append({
                '统计项': f'严重程度-{severity_type}',
                '数量': count,
                '占比': f"{count/len(classifications)*100:.1f}%"
            })
        
        # 年龄特征统计
        age_counts = {}
        for c in classifications:
            age_type = c.age_type
            age_counts[age_type] = age_counts.get(age_type, 0) + 1
        
        for age_type, count in age_counts.items():
            stats.append({
                '统计项': f'年龄-{age_type}',
                '数量': count,
                '占比': f"{count/len(classifications)*100:.1f}%"
            })
        
        # ICU统计
        icu_counts = {}
        for c in classifications:
            icu_type = c.icu_type
            icu_counts[icu_type] = icu_counts.get(icu_type, 0) + 1
        
        for icu_type, count in icu_counts.items():
            stats.append({
                '统计项': f'ICU-{icu_type}',
                '数量': count,
                '占比': f"{count/len(classifications)*100:.1f}%"
            })
        
        # 综合调节系数统计
        coeff_counts = {}
        for c in classifications:
            coeff_type = c.max_coefficient_type
            coeff_counts[coeff_type] = coeff_counts.get(coeff_type, 0) + 1
        
        for coeff_type, count in coeff_counts.items():
            stats.append({
                '统计项': f'最高系数-{coeff_type}',
                '数量': count,
                '占比': f"{count/len(classifications)*100:.1f}%"
            })
        
        return stats


def create_auxiliary_exporter() -> AuxiliaryDirectoryExporter:
    """创建辅助目录导出器"""
    return AuxiliaryDirectoryExporter()
