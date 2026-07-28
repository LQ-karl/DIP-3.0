"""
DIP按病种分值分组测算工具 - 特例单议机制模块
基于《国家医疗保障按病种分值(DIP)付费3.0版技术规范》第六章第二节
功能：特例单议病例筛选、申报、评审
"""
import pandas as pd
from typing import List, Dict, Optional, Tuple
from decimal import Decimal, ROUND_HALF_UP
from dataclasses import dataclass, field
from datetime import datetime
from ..models.models import MedicalRecord


@dataclass
class SpecialNegotiationCase:
    """特例单议病例"""
    record_id: str  # 病例ID
    dip_code: str  # DIP编码
    hospital_code: str  # 医院代码
    hospital_name: str = ""  # 医院名称
    
    # 病例基本信息
    patient_name: str = ""  # 患者姓名
    admission_date: str = ""  # 入院日期
    discharge_date: str = ""  # 出院日期
    stay_days: int = 0  # 住院天数
    
    # 费用信息
    total_cost: Decimal = Decimal("0")  # 总费用
    payment_standard: Decimal = Decimal("0")  # 支付标准
    cost_ratio: Decimal = Decimal("0")  # 费用比例
    
    # 分值信息
    disease_value: Decimal = Decimal("0")  # 病种分值
    hospital_coefficient: Decimal = Decimal("1.0")  # 医院调节系数
    auxiliary_coefficient: Decimal = Decimal("1.0")  # 辅助分型系数
    case_value: Decimal = Decimal("0")  # 病例分值
    
    # 申报信息
    negotiation_type: str = ""  # 单议类型
    application_reason: str = ""  # 申报原因
    application_date: str = ""  # 申报日期
    application_materials: List[str] = field(default_factory=list)  # 申报材料
    
    # 评审信息
    review_status: str = "待评审"  # 评审状态
    review_result: str = ""  # 评审结果
    review_date: str = ""  # 评审日期
    reviewer: str = ""  # 评审人
    review_comments: str = ""  # 评审意见
    
    # 结算信息
    settlement_method: str = ""  # 结算方式
    adjusted_payment: Decimal = Decimal("0")  # 调整后支付


class SpecialNegotiationManager:
    """特例单议管理器"""
    
    # 特例单议类型
    NEGOTIATION_TYPES = {
        'long_stay': '住院时间长',
        'high_cost': '医疗费用高',
        'new_tech': '新药耗新技术使用',
        'complex_case': '复杂危重症',
        'multi_discipline': '多学科联合诊疗',
        'other': '其他'
    }
    
    # 评审结果
    REVIEW_RESULTS = {
        'approved': '通过',
        'rejected': '不通过',
        'pending': '待定'
    }
    
    # 结算方式
    SETTLEMENT_METHODS = {
        'item_based': '按项目付费',
        'adjusted_standard': '调整支付标准',
        'original': '按原病种规定付费'
    }
    
    # 默认配置
    DEFAULT_CONFIG = {
        'max_ratio': Decimal("0.005"),  # 特例单议病例数上限比例：5‰
        'min_hospital_ratio': Decimal("0.005"),  # 每家医院特例单议上限比例
        'review_cycle': '月',  # 评审周期
        'online_review': True,  # 是否支持线上评审
        'cross_hospital_review': False,  # 是否支持医疗机构交叉评审
    }
    
    def __init__(self, config: Dict = None):
        """
        初始化管理器
        
        Args:
            config: 配置信息
        """
        self.config = config or self.DEFAULT_CONFIG.copy()
        self.cases: List[SpecialNegotiationCase] = []
    
    def identify_eligible_cases(
        self,
        records: List[MedicalRecord],
        payment_standards: Dict[str, Decimal],
        hospital_coefficients: Dict[str, Decimal] = None
    ) -> List[SpecialNegotiationCase]:
        """
        识别符合特例单议条件的病例
        
        Args:
            records: 病例记录列表
            payment_standards: 各DIP支付标准
            hospital_coefficients: 医院调节系数
            
        Returns:
            符合条件的病例列表
        """
        eligible_cases = []
        
        for record in records:
            case = self._evaluate_case_eligibility(
                record=record,
                payment_standards=payment_standards,
                hospital_coefficients=hospital_coefficients
            )
            
            if case:
                eligible_cases.append(case)
        
        return eligible_cases
    
    def _evaluate_case_eligibility(
        self,
        record: MedicalRecord,
        payment_standards: Dict[str, Decimal],
        hospital_coefficients: Dict[str, Decimal] = None
    ) -> Optional[SpecialNegotiationCase]:
        """评估单个病例是否符合条件"""
        dip_code = record.dip_disease_code
        hospital_code = record.hospital_code
        
        # 获取支付标准
        base_payment_standard = payment_standards.get(dip_code, Decimal("0"))
        
        # 获取医院调节系数
        hospital_coeff = Decimal("1.0")
        if hospital_coefficients:
            hospital_coeff = hospital_coefficients.get(hospital_code, Decimal("1.0"))
        
        # 计算调整后支付标准
        adjusted_payment_standard = base_payment_standard * hospital_coeff
        
        # 计算费用比例
        total_cost = record.total_cost
        cost_ratio = Decimal("0")
        if adjusted_payment_standard > 0:
            cost_ratio = (total_cost / adjusted_payment_standard).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP
            )
        
        # 判断是否符合条件
        negotiation_types = []
        
        # 1. 住院时间长（超过平均住院日2倍）
        stay_days = getattr(record, 'stay_days', 0)
        if stay_days > 30:  # 简化判断
            negotiation_types.append('long_stay')
        
        # 2. 医疗费用高（超过支付标准2倍）
        if cost_ratio >= Decimal("2.0"):
            negotiation_types.append('high_cost')
        
        # 3. 复杂危重症
        severity_level = getattr(record, 'severity_level', '一般')
        if severity_level in ['危重', '重度']:
            negotiation_types.append('complex_case')
        
        # 4. 新药耗新技术使用（简化判断）
        # 实际需要根据具体用药和耗材判断
        
        # 如果符合条件，创建病例
        if negotiation_types:
            case = SpecialNegotiationCase(
                record_id=record.record_id,
                dip_code=dip_code,
                hospital_code=hospital_code,
                total_cost=total_cost,
                payment_standard=adjusted_payment_standard,
                cost_ratio=cost_ratio,
                stay_days=stay_days,
                negotiation_type='；'.join([self.NEGOTIATION_TYPES[t] for t in negotiation_types]),
                application_reason=f"符合特例单议条件：{self.NEGOTIATION_TYPES[negotiation_types[0]]}"
            )
            
            return case
        
        return None
    
    def submit_application(
        self,
        case: SpecialNegotiationCase,
        application_reason: str,
        materials: List[str] = None
    ) -> bool:
        """
        提交特例单议申报
        
        Args:
            case: 病例信息
            application_reason: 申报原因
            materials: 申报材料
            
        Returns:
            是否提交成功
        """
        case.application_reason = application_reason
        case.application_date = datetime.now().strftime("%Y-%m-%d")
        case.application_materials = materials or []
        case.review_status = "已申报"
        
        self.cases.append(case)
        return True
    
    def conduct_review(
        self,
        case: SpecialNegotiationCase,
        review_result: str,
        reviewer: str,
        comments: str = "",
        adjusted_payment: Decimal = None
    ) -> bool:
        """
        进行特例单议评审
        
        Args:
            case: 病例信息
            review_result: 评审结果
            reviewer: 评审人
            comments: 评审意见
            adjusted_payment: 调整后支付（如果通过）
            
        Returns:
            是否评审成功
        """
        case.review_result = review_result
        case.review_date = datetime.now().strftime("%Y-%m-%d")
        case.reviewer = reviewer
        case.review_comments = comments
        case.review_status = "已评审"
        
        if review_result == self.REVIEW_RESULTS['approved']:
            case.settlement_method = self.SETTLEMENT_METHODS['adjusted_standard']
            case.adjusted_payment = adjusted_payment or case.total_cost
        else:
            case.settlement_method = self.SETTLEMENT_METHODS['original']
            case.adjusted_payment = case.payment_standard
        
        return True
    
    def check_ratio_limit(
        self,
        total_cases: int,
        hospital_cases: Dict[str, int] = None
    ) -> Dict:
        """
        检查特例单议比例限制
        
        Args:
            total_cases: 总病例数
            hospital_cases: 各医院病例数
            
        Returns:
            检查结果
        """
        max_count = int(total_cases * self.config['max_ratio'])
        
        result = {
            'total_cases': total_cases,
            'max_allowed': max_count,
            'current_count': len(self.cases),
            'within_limit': len(self.cases) <= max_count
        }
        
        # 检查各医院限制
        if hospital_cases:
            hospital_limits = {}
            for hospital_code, cases_count in hospital_cases.items():
                hospital_max = int(cases_count * self.config['min_hospital_ratio'])
                hospital_current = sum(1 for c in self.cases if c.hospital_code == hospital_code)
                hospital_limits[hospital_code] = {
                    'max_allowed': hospital_max,
                    'current_count': hospital_current,
                    'within_limit': hospital_current <= hospital_max
                }
            result['hospital_limits'] = hospital_limits
        
        return result
    
    def export_cases(
        self,
        cases: List[SpecialNegotiationCase],
        output_path: str
    ) -> str:
        """导出特例单议病例"""
        data = []
        for i, case in enumerate(cases, 1):
            data.append({
                '序号': i,
                '病例ID': case.record_id,
                'DIP编码': case.dip_code,
                '医院代码': case.hospital_code,
                '住院天数': case.stay_days,
                '总费用': float(case.total_cost),
                '支付标准': float(case.payment_standard),
                '费用比例': float(case.cost_ratio),
                '单议类型': case.negotiation_type,
                '申报原因': case.application_reason,
                '申报日期': case.application_date,
                '评审状态': case.review_status,
                '评审结果': case.review_result,
                '评审日期': case.review_date,
                '评审人': case.reviewer,
                '评审意见': case.review_comments,
                '结算方式': case.settlement_method,
                '调整后支付': float(case.adjusted_payment)
            })
        
        df = pd.DataFrame(data)
        df.to_excel(output_path, index=False, engine='openpyxl')
        return output_path
    
    def generate_statistics(self) -> Dict:
        """生成统计信息"""
        total_count = len(self.cases)
        
        # 按评审状态统计
        status_counts = {}
        for case in self.cases:
            status = case.review_status
            if status not in status_counts:
                status_counts[status] = 0
            status_counts[status] += 1
        
        # 按评审结果统计
        result_counts = {}
        for case in self.cases:
            result = case.review_result or "待评审"
            if result not in result_counts:
                result_counts[result] = 0
            result_counts[result] += 1
        
        # 按单议类型统计
        type_counts = {}
        for case in self.cases:
            for nego_type in case.negotiation_type.split('；'):
                if nego_type not in type_counts:
                    type_counts[nego_type] = 0
                type_counts[nego_type] += 1
        
        # 费用统计
        total_cost = sum(case.total_cost for case in self.cases)
        total_adjusted = sum(case.adjusted_payment for case in self.cases)
        
        return {
            'total_count': total_count,
            'status_counts': status_counts,
            'result_counts': result_counts,
            'type_counts': type_counts,
            'total_cost': total_cost,
            'total_adjusted_payment': total_adjusted,
            'cost_difference': total_adjusted - total_cost
        }
