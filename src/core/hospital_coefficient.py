"""
DIP按病种分值分组测算工具 - 医疗机构等级系数测算模块
基于《国家医疗保障按病种分值(DIP)付费3.0版技术规范》第五章第二节
"""
import pandas as pd
from typing import List, Dict, Optional
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from collections import defaultdict

from ..models.models import MedicalRecord, HospitalCoefficient


class HospitalLevelClassifier:
    """医疗机构等级分类器"""
    
    # 医院等级映射
    HOSPITAL_LEVEL_MAP = {
        "三级甲等": {"level": 1, "type": "综合", "score": 1.2},
        "三级乙等": {"level": 2, "type": "综合", "score": 1.15},
        "三级丙等": {"level": 3, "type": "综合", "score": 1.1},
        "二级甲等": {"level": 4, "type": "综合", "score": 1.05},
        "二级乙等": {"level": 5, "type": "综合", "score": 1.0},
        "二级丙等": {"level": 6, "type": "综合", "score": 0.95},
        "一级": {"level": 7, "type": "基层", "score": 0.85},
        "未定级": {"level": 8, "type": "其他", "score": 1.0},
    }
    
    # 专科医院类型
    SPECIALTY_TYPES = {
        "儿童": {"coefficient": 1.15, "description": "儿童专科医院"},
        "妇产": {"coefficient": 1.10, "description": "妇产专科医院"},
        "肿瘤": {"coefficient": 1.12, "description": "肿瘤专科医院"},
        "心血管": {"coefficient": 1.08, "description": "心血管专科医院"},
        "骨科": {"coefficient": 1.06, "description": "骨科专科医院"},
        "精神": {"coefficient": 0.90, "description": "精神专科医院"},
        "中医": {"coefficient": 1.05, "description": "中医专科医院"},
        "康复": {"coefficient": 0.95, "description": "康复专科医院"},
    }
    
    def __init__(self):
        pass
    
    def classify_hospital(self, level: str, specialty: str = "") -> Dict:
        """
        医院分类
        
        Args:
            level: 医院等级
            specialty: 医院专科类型
            
        Returns:
            分类结果
        """
        # 基本等级
        level_info = self.HOSPITAL_LEVEL_MAP.get(level, self.HOSPITAL_LEVEL_MAP["未定级"])
        
        # 专科加成
        specialty_info = None
        if specialty:
            for key, value in self.SPECIALTY_TYPES.items():
                if key in specialty:
                    specialty_info = value
                    break
        
        return {
            "level": level_info["level"],
            "level_name": level,
            "type": level_info["type"],
            "base_score": Decimal(str(level_info["score"])),
            "specialty": specialty_info["description"] if specialty_info else None,
            "specialty_coefficient": Decimal(str(specialty_info["coefficient"])) if specialty_info else Decimal("1.0")
        }


class HospitalCoefficientCalculator:
    """医疗机构调节系数计算器"""
    
    def __init__(self):
        self.level_classifier = HospitalLevelClassifier()
    
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
        if city_avg_cost <= 0:
            return Decimal("1.0")
        
        coefficient = hospital_avg_cost / city_avg_cost
        return coefficient.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    
    def calculate_bonus_coefficient(
        self,
        medical_level_score: Decimal = Decimal("0"),
        specialty_score: Decimal = Decimal("0"),
        cmi_score: Decimal = Decimal("0"),
        performance_score: Decimal = Decimal("0"),
        agreement_score: Decimal = Decimal("0")
    ) -> Decimal:
        """
        计算加成系数
        公式：加成系数 = 医疗水平*0.25 + 专科特色*0.20 + CMI*0.25 + 绩效考核*0.15 + 协议履行*0.15
        
        Args:
            medical_level_score: 医疗水平得分
            specialty_score: 专科特色得分
            cmi_score: CMI得分
            performance_score: 绩效考核得分
            agreement_score: 协议履行得分
            
        Returns:
            加成系数
        """
        weights = {
            'medical': Decimal("0.25"),
            'specialty': Decimal("0.20"),
            'cmi': Decimal("0.25"),
            'performance': Decimal("0.15"),
            'agreement': Decimal("0.15")
        }
        
        bonus = (
            medical_level_score * weights['medical'] +
            specialty_score * weights['specialty'] +
            cmi_score * weights['cmi'] +
            performance_score * weights['performance'] +
            agreement_score * weights['agreement']
        )
        
        return bonus.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    
    def calculate_disease_specific_coefficient(
        self,
        hospital_disease_cost: Decimal,
        city_disease_cost: Decimal
    ) -> Decimal:
        """
        计算病种级别调节系数
        公式：病种系数 = 同级别类型医疗机构某病种病例加权平均住院费用 / 全市该病种病例加权平均住院费用
        
        Args:
            hospital_disease_cost: 医疗机构某病种平均费用
            city_disease_cost: 全市该病种平均费用
            
        Returns:
            病种级别调节系数
        """
        if city_disease_cost <= 0:
            return Decimal("1.0")
        
        coefficient = hospital_disease_cost / city_disease_cost
        return coefficient.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    
    def calculate_hospital_coefficient(
        self,
        hospital_data: Dict,
        city_avg_cost: Decimal,
        hospital_disease_costs: Dict[str, Decimal] = None,
        city_disease_costs: Dict[str, Decimal] = None
    ) -> HospitalCoefficient:
        """
        计算单个医院的调节系数
        
        Args:
            hospital_data: 医院数据
            city_avg_cost: 全市平均费用
            hospital_disease_costs: 医院各病种平均费用
            city_disease_costs: 全市各病种平均费用
            
        Returns:
            医院调节系数
        """
        # 基本系数
        hospital_avg_cost = Decimal(str(hospital_data.get('avg_cost', 0)))
        basic_coeff = self.calculate_basic_coefficient(hospital_avg_cost, city_avg_cost)
        
        # 加成系数
        bonus_coeff = self.calculate_bonus_coefficient(
            medical_level_score=Decimal(str(hospital_data.get('medical_level', 0))),
            specialty_score=Decimal(str(hospital_data.get('specialty_score', 0))),
            cmi_score=Decimal(str(hospital_data.get('cmi', 0))),
            performance_score=Decimal(str(hospital_data.get('performance_score', 0))),
            agreement_score=Decimal(str(hospital_data.get('agreement_score', 0)))
        )
        
        # 总系数
        total_coeff = basic_coeff + bonus_coeff
        
        # 医院分类信息
        level_info = self.level_classifier.classify_hospital(
            hospital_data.get('hospital_level', ''),
            hospital_data.get('specialty', '')
        )
        
        return HospitalCoefficient(
            hospital_code=hospital_data.get('hospital_code', ''),
            hospital_name=hospital_data.get('hospital_name', ''),
            hospital_level=hospital_data.get('hospital_level', ''),
            basic_coefficient=basic_coeff,
            bonus_coefficient=bonus_coeff,
            total_coefficient=total_coeff.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        )
    
    def batch_calculate(
        self,
        hospital_data_list: List[Dict],
        city_avg_cost: Decimal
    ) -> List[HospitalCoefficient]:
        """
        批量计算医院调节系数
        
        Args:
            hospital_data_list: 医院数据列表
            city_avg_cost: 全市平均费用
            
        Returns:
            医院调节系数列表
        """
        results = []
        for data in hospital_data_list:
            coeff = self.calculate_hospital_coefficient(data, city_avg_cost)
            results.append(coeff)
        return results
    
    def calculate_from_records(
        self,
        records: List[MedicalRecord]
    ) -> List[HospitalCoefficient]:
        """
        从病例记录计算医院调节系数
        
        Args:
            records: 病例记录列表
            
        Returns:
            医院调节系数列表
        """
        # 按医院分组统计
        hospital_stats = defaultdict(lambda: {
            'total_cost': Decimal('0'),
            'case_count': 0,
            'hospital_name': '',
            'hospital_level': ''
        })
        
        for record in records:
            code = record.hospital_code
            hospital_stats[code]['total_cost'] += record.total_cost
            hospital_stats[code]['case_count'] += 1
            hospital_stats[code]['hospital_name'] = record.hospital_name
        
        # 计算全市平均费用
        total_cost = sum(s['total_cost'] for s in hospital_stats.values())
        total_count = sum(s['case_count'] for s in hospital_stats.values())
        city_avg_cost = total_cost / total_count if total_count > 0 else Decimal('0')
        
        # 计算每个医院的系数
        hospital_data_list = []
        for code, stats in hospital_stats.items():
            avg_cost = stats['total_cost'] / stats['case_count'] if stats['case_count'] > 0 else Decimal('0')
            hospital_data_list.append({
                'hospital_code': code,
                'hospital_name': stats['hospital_name'],
                'hospital_level': stats['hospital_level'],
                'avg_cost': float(avg_cost),
                'case_count': stats['case_count']
            })
        
        return self.batch_calculate(hospital_data_list, city_avg_cost)
    
    def export_coefficients(
        self,
        coefficients: List[HospitalCoefficient],
        output_path: str
    ) -> str:
        """
        导出调节系数到Excel
        
        Args:
            coefficients: 调节系数列表
            output_path: 输出文件路径
            
        Returns:
            输出文件路径
        """
        data = []
        for i, coeff in enumerate(coefficients, 1):
            data.append({
                '序号': i,
                '医疗机构代码': coeff.hospital_code,
                '医疗机构名称': coeff.hospital_name,
                '医疗机构等级': coeff.hospital_level,
                '基本系数': float(coeff.basic_coefficient),
                '加成系数': float(coeff.bonus_coefficient),
                '总调节系数': float(coeff.total_coefficient)
            })
        
        df = pd.DataFrame(data)
        df.to_excel(output_path, index=False, engine='openpyxl')
        return output_path
