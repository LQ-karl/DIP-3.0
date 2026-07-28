"""
DIP按病种分值分组测算工具 - 点值计算与支付标准模块
基于《国家医疗保障按病种分值(DIP)付费3.0版技术规范》第五章、第六章
"""
import pandas as pd
from typing import List, Dict, Optional, Tuple
from decimal import Decimal, ROUND_HALF_UP
import numpy as np

from ..models.models import (
    DiseaseGroup, MedicalRecord, HospitalCoefficient,
    DIPSettlementResult, SimulationParams
)


class PointValueCalculator:
    """点值计算器"""
    
    def __init__(self):
        pass
    
    def calculate_weighted_total_cost(
        self,
        yearly_costs: List[Decimal],
        weights: List[float] = [0.1, 0.2, 0.7]
    ) -> Decimal:
        """
        计算加权年度住院总费用
        
        Args:
            yearly_costs: 各年份住院总费用
            weights: 年份权重
            
        Returns:
            加权平均年度住院总费用
        """
        weighted_sum = sum(cost * Decimal(str(w)) 
                          for cost, w in zip(yearly_costs, weights))
        return weighted_sum.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    
    def calculate_weighted_total_value(
        self,
        yearly_values: List[Decimal],
        weights: List[float] = [0.1, 0.2, 0.7]
    ) -> Decimal:
        """
        计算加权年度总分值
        
        Args:
            yearly_values: 各年份总分值
            weights: 年份权重
            
        Returns:
            加权平均年度总分值
        """
        weighted_sum = sum(value * Decimal(str(w)) 
                          for value, w in zip(yearly_values, weights))
        return weighted_sum.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    
    def calculate_initial_point_value(
        self,
        weighted_total_cost: Decimal,
        weighted_total_value: Decimal
    ) -> Decimal:
        """
        计算年初点值
        公式：年初点值 = 加权平均年度住院总费用 / 加权年度总分值
        
        Args:
            weighted_total_cost: 加权平均年度住院总费用
            weighted_total_value: 加权年度总分值
            
        Returns:
            年初点值
        """
        if weighted_total_value == 0:
            return Decimal("0")
        
        point_value = weighted_total_cost / weighted_total_value
        return point_value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    
    def calculate_initial_point_value_by_quantile(
        self,
        costs: List[Decimal],
        values: List[Decimal],
        lower_percentile: float = 2.5,
        upper_percentile: float = 97.5
    ) -> Decimal:
        """
        使用分位数法计算年初点值
        
        Args:
            costs: 各病例住院费用
            values: 各病例分值
            lower_percentile: 下限百分位数
            upper_percentile: 上限百分位数
            
        Returns:
            年初点值
        """
        costs_array = np.array([float(c) for c in costs])
        values_array = np.array([float(v) for v in values])
        
        # 裁剪费用数据
        lower_bound = np.percentile(costs_array, lower_percentile)
        upper_bound = np.percentile(costs_array, upper_percentile)
        
        mask = (costs_array >= lower_bound) & (costs_array <= upper_bound)
        filtered_costs = costs_array[mask]
        filtered_values = values_array[mask]
        
        # 计算点值
        if filtered_values.sum() == 0:
            return Decimal("0")
        
        point_value = filtered_costs.sum() / filtered_values.sum()
        return Decimal(str(point_value)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    
    def calculate_initial_point_value_by_excellent_interval(
        self,
        costs: List[Decimal],
        values: List[Decimal]
    ) -> Decimal:
        """
        使用优值区间法计算年初点值（一维角度）
        
        规范要求：
        一维角度以低于每指数点值地区均值的区段作为优值区间，
        利用该区间的加权平均值作为年初点值。
        
        Args:
            costs: 各病例住院费用
            values: 各病例分值
            
        Returns:
            年初点值
        """
        if not costs or not values or len(costs) != len(values):
            return Decimal("0")
        
        costs_array = np.array([float(c) for c in costs])
        values_array = np.array([float(v) for v in values])
        
        # 计算每指数点值
        total_cost = costs_array.sum()
        total_value = values_array.sum()
        
        if total_value == 0:
            return Decimal("0")
        
        avg_point_value = total_cost / total_value
        
        # 计算每个病例的每指数点值
        case_point_values = np.where(values_array > 0, costs_array / values_array, 0)
        
        # 优值区间：低于每指数点值地区均值的区段
        mask = case_point_values < avg_point_value
        excellent_costs = costs_array[mask]
        excellent_values = values_array[mask]
        
        if excellent_values.sum() == 0:
            return Decimal("0")
        
        # 计算优值区间的加权平均值
        point_value = excellent_costs.sum() / excellent_values.sum()
        return Decimal(str(point_value)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    
    def calculate_initial_point_value_by_2d_excellent_interval(
        self,
        costs: List[Decimal],
        values: List[Decimal],
        total_costs: List[Decimal] = None
    ) -> Decimal:
        """
        使用优值区间法计算年初点值（二维角度）
        
        规范要求：
        二维角度根据各医疗机构标化后的收入与成本建立比较关系，
        以每指数点值和每指数成本的地区均值为坐标系，以每指数点值低、
        每指数成本低，即收入低、成本低，且收入能覆盖成本的医疗机构
        集中的区域作为优值区间，利用该区域的几何中心作为年初点值。
        
        Args:
            costs: 各病例住院费用（收入）
            values: 各病例分值
            total_costs: 各病例总成本（如果为空，则使用费用作为成本近似）
            
        Returns:
            年初点值
        """
        if not costs or not values or len(costs) != len(values):
            return Decimal("0")
        
        costs_array = np.array([float(c) for c in costs])
        values_array = np.array([float(v) for v in values])
        
        # 如果没有提供成本数据，使用费用作为近似
        if total_costs is None:
            total_costs_array = costs_array * 1.1  # 假设成本比费用高10%
        else:
            total_costs_array = np.array([float(c) for c in total_costs])
        
        # 计算每指数点值和每指数成本
        total_value = values_array.sum()
        if total_value == 0:
            return Decimal("0")
        
        case_point_values = costs_array / total_value
        case_cost_values = total_costs_array / total_value
        
        # 计算地区均值
        avg_point_value = case_point_values.mean()
        avg_cost_value = case_cost_values.mean()
        
        # 二维优值区间：每指数点值低、每指数成本低，且收入能覆盖成本
        mask = (
            (case_point_values < avg_point_value) & 
            (case_cost_values < avg_cost_value) &
            (case_point_values >= case_cost_values)  # 收入能覆盖成本
        )
        
        excellent_point_values = case_point_values[mask]
        
        if len(excellent_point_values) == 0:
            return Decimal("0")
        
        # 计算几何中心（距离所有点距离之和最小的点）
        # 简化计算：使用中位数作为几何中心的近似
        point_value = np.median(excellent_point_values)
        
        return Decimal(str(point_value)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    
    def calculate_settlement_point_value(
        self,
        fund_amount: Decimal,
        payment_ratio: Decimal,
        total_dip_value: Decimal
    ) -> Decimal:
        """
        计算结算点值
        公式：结算点值 = (当年医保基金DIP付费总额 / 医保支付比例) / 当年度DIP总分值
        
        Args:
            fund_amount: 当年医保基金DIP付费总额
            payment_ratio: 医保支付比例
            total_dip_value: 当年度DIP总分值
            
        Returns:
            结算点值
        """
        if total_dip_value == 0 or payment_ratio == 0:
            return Decimal("0")
        
        total_cost = fund_amount / payment_ratio
        point_value = total_cost / total_dip_value
        return point_value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


class PaymentStandardCalculator:
    """支付标准计算器"""
    
    def __init__(self, point_value: Decimal = Decimal("0")):
        """
        初始化支付标准计算器
        
        Args:
            point_value: 点值
        """
        self.point_value = point_value
    
    def set_point_value(self, point_value: Decimal):
        """设置点值"""
        self.point_value = point_value
    
    def calculate_basic_payment_standard(
        self,
        disease_value: Decimal
    ) -> Decimal:
        """
        计算基础支付标准
        公式：支付标准 = 病种分值 × 点值
        
        Args:
            disease_value: 病种分值
            
        Returns:
            基础支付标准
        """
        return (disease_value * self.point_value).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    
    def calculate_adjusted_payment_standard(
        self,
        disease_value: Decimal,
        hospital_coefficient: Decimal = Decimal("1.0"),
        auxiliary_coefficient: Decimal = Decimal("1.0")
    ) -> Decimal:
        """
        计算调整后支付标准
        公式：支付标准 = 病种分值 × 医疗机构调节系数 × 辅助分型调节系数 × 点值
        
        Args:
            disease_value: 病种分值
            hospital_coefficient: 医疗机构调节系数
            auxiliary_coefficient: 辅助分型调节系数
            
        Returns:
            调整后支付标准
        """
        adjusted_value = disease_value * hospital_coefficient * auxiliary_coefficient
        return (adjusted_value * self.point_value).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    
    def is_abnormal_cost(
        self,
        actual_cost: Decimal,
        payment_standard: Decimal,
        low_threshold: float = 0.5,
        high_threshold: float = 2.0
    ) -> Tuple[bool, bool]:
        """
        判断是否为费用异常病例
        
        Args:
            actual_cost: 实际费用
            payment_standard: 支付标准
            low_threshold: 超低阈值（默认50%）
            high_threshold: 超高阈值（默认200%）
            
        Returns:
            (是否超低, 是否超高)
        """
        if payment_standard == 0:
            return False, False
        
        ratio = actual_cost / payment_standard
        is_low = ratio < Decimal(str(low_threshold))
        is_high = ratio >= Decimal(str(high_threshold))
        
        return is_low, is_high
    
    def calculate_abnormal_correction_coefficient(
        self,
        actual_cost: Decimal,
        payment_standard: Decimal,
        adjustment_coefficient: Decimal = Decimal("1.0")
    ) -> Decimal:
        """
        计算费用超低病例分值校正系数
        公式：校正系数 = 该病例医疗总费用 / (该病种支付标准 × 分值调节系数)
        
        Args:
            actual_cost: 实际费用
            payment_standard: 支付标准
            adjustment_coefficient: 分值调节系数
            
        Returns:
            校正系数
        """
        denominator = payment_standard * adjustment_coefficient
        if denominator == 0:
            return Decimal("1.0")
        
        return (actual_cost / denominator).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )


class SettlementCalculator:
    """结算计算器"""
    
    def __init__(self, params: SimulationParams):
        """
        初始化结算计算器
        
        Args:
            params: 模拟测算参数
        """
        self.params = params
        self.point_value_calculator = PointValueCalculator()
        self.payment_calculator = PaymentStandardCalculator()
    
    def calculate_case_settlement(
        self,
        record: MedicalRecord,
        disease_group: DiseaseGroup,
        hospital_coefficient: HospitalCoefficient,
        auxiliary_coefficient: Decimal = Decimal("1.0")
    ) -> DIPSettlementResult:
        """
        计算单个病例的结算结果
        
        Args:
            record: 住院病例记录
            disease_group: 病种组合
            hospital_coefficient: 医疗机构调节系数
            auxiliary_coefficient: 辅助分型调节系数
            
        Returns:
            结算结果
        """
        # 计算支付标准
        payment_standard = self.payment_calculator.calculate_adjusted_payment_standard(
            disease_value=disease_group.disease_value,
            hospital_coefficient=hospital_coefficient.total_coefficient,
            auxiliary_coefficient=auxiliary_coefficient
        )
        
        # 计算医保支付和个人支付
        insurance_payment = (payment_standard * self.params.payment_ratio).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        patient_payment = record.total_cost - insurance_payment
        if patient_payment < 0:
            patient_payment = Decimal("0")
        
        return DIPSettlementResult(
            record_id=record.record_id,
            patient_id=record.patient_id,
            hospital_code=record.hospital_code,
            disease_code=disease_group.disease_code,
            disease_name=disease_group.disease_name,
            disease_value=disease_group.disease_value,
            hospital_coefficient=hospital_coefficient.total_coefficient,
            auxiliary_coefficient=auxiliary_coefficient,
            point_value=self.payment_calculator.point_value,
            payment_standard=payment_standard,
            actual_cost=record.total_cost,
            insurance_payment=insurance_payment,
            patient_payment=patient_payment
        )
    
    def batch_settle(
        self,
        records: List[MedicalRecord],
        disease_groups: Dict[str, DiseaseGroup],
        hospital_coefficients: Dict[str, HospitalCoefficient],
        point_value: Decimal
    ) -> List[DIPSettlementResult]:
        """
        批量结算
        
        Args:
            records: 住院病例记录列表
            disease_groups: 病种组合字典
            hospital_coefficients: 医疗机构调节系数字典
            point_value: 点值
            
        Returns:
            结算结果列表
        """
        self.payment_calculator.set_point_value(point_value)
        results = []
        
        for record in records:
            # 获取病种组合
            disease_code = record.dip_disease_code
            if disease_code not in disease_groups:
                continue
            
            disease_group = disease_groups[disease_code]
            
            # 获取医疗机构调节系数
            hospital_coeff = hospital_coefficients.get(
                record.hospital_code,
                HospitalCoefficient(
                    hospital_code=record.hospital_code,
                    hospital_name="",
                    hospital_level="",
                    total_coefficient=Decimal("1.0")
                )
            )
            
            # 计算结算结果
            result = self.calculate_case_settlement(
                record=record,
                disease_group=disease_group,
                hospital_coefficient=hospital_coeff
            )
            results.append(result)
        
        return results
    
    def generate_simulation_report(
        self,
        results: List[DIPSettlementResult],
        original_costs: Dict[str, Decimal] = None
    ) -> Dict:
        """
        生成模拟测算报告
        
        Args:
            results: 结算结果列表
            original_costs: 原支付方式费用字典（可选）
            
        Returns:
            报告数据
        """
        total_cases = len(results)
        if total_cases == 0:
            return {"error": "无结算数据"}
        
        # 汇总统计
        total_dip_cost = sum(r.insurance_payment for r in results)
        total_actual_cost = sum(r.actual_cost for r in results)
        avg_payment_standard = sum(r.payment_standard for r in results) / total_cases
        
        # 费用异常分析
        abnormal_low = 0
        abnormal_high = 0
        for r in results:
            is_low, is_high = self.payment_calculator.is_abnormal_cost(
                r.actual_cost, r.payment_standard
            )
            if is_low:
                abnormal_low += 1
            if is_high:
                abnormal_high += 1
        
        report = {
            "summary": {
                "total_cases": total_cases,
                "total_dip_cost": float(total_dip_cost),
                "total_actual_cost": float(total_actual_cost),
                "avg_payment_standard": float(avg_payment_standard),
                "point_value": float(self.payment_calculator.point_value)
            },
            "abnormal_analysis": {
                "low_cost_cases": abnormal_low,
                "low_cost_ratio": abnormal_low / total_cases if total_cases > 0 else 0,
                "high_cost_cases": abnormal_high,
                "high_cost_ratio": abnormal_high / total_cases if total_cases > 0 else 0
            }
        }
        
        # 如果有原支付方式数据，计算对比
        if original_costs:
            original_total = sum(original_costs.values())
            report["comparison"] = {
                "original_total_cost": float(original_total),
                "dip_total_cost": float(total_dip_cost),
                "difference": float(total_dip_cost - original_total),
                "difference_ratio": float((total_dip_cost - original_total) / original_total) if original_total > 0 else 0
            }
        
        return report
