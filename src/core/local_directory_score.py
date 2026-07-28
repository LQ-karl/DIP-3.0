"""
DIP按病种分值分组测算工具 - 本地目录库分值测算模块
基于《国家医疗保障按病种分值(DIP)付费3.0版技术规范》第五章
"""
import pandas as pd
import numpy as np
from typing import List, Dict, Optional
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from collections import defaultdict

from ..models.models import (
    DiseaseGroup, MedicalRecord, HospitalCoefficient,
    DIPSettlementResult, ValueCalculationResult
)


class LocalDirectoryScoreCalculator:
    """本地目录库分值测算器"""
    
    def __init__(self):
        self.group_data = {}
        self.hospital_coefficients = {}
        self.disease_group_coefficients = {}
    
    def load_group_data(self, disease_groups: List[DiseaseGroup]):
        """加载分组数据"""
        for group in disease_groups:
            self.group_data[group.dip_code] = group
    
    def load_hospital_coefficients(self, coefficients: List[HospitalCoefficient]):
        """加载医院调节系数"""
        for coeff in coefficients:
            self.hospital_coefficients[coeff.hospital_code] = coeff
    
    def calculate_weighted_average_cost(
        self,
        records: List[MedicalRecord],
        dip_code: str
    ) -> Decimal:
        """
        计算加权平均住院费用
        公式：加权平均住院费用 = Σ(费用 × 病例数) / Σ病例数
        
        Args:
            records: 病例记录列表
            dip_code: DIP分组编码
            
        Returns:
            加权平均住院费用
        """
        filtered = [r for r in records if r.dip_disease_code == dip_code]
        if not filtered:
            return Decimal("0")
        
        total_weighted = sum(r.total_cost for r in filtered)
        total_count = len(filtered)
        
        return (total_weighted / total_count).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    
    def calculate_weighted_average_los(
        self,
        records: List[MedicalRecord],
        dip_code: str
    ) -> Decimal:
        """
        计算加权平均住院天数
        公式：加权平均住院天数 = Σ(住院天数 × 病例数) / Σ病例数
        
        Args:
            records: 病例记录列表
            dip_code: DIP分组编码
            
        Returns:
            加权平均住院天数
        """
        filtered = [r for r in records if r.dip_disease_code == dip_code]
        if not filtered:
            return Decimal("0")
        
        total_los = sum(r.los for r in filtered)
        total_count = len(filtered)
        
        return (total_los / total_count).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    
    def calculate_weighted_average_drug_cost(
        self,
        records: List[MedicalRecord],
        dip_code: str
    ) -> Decimal:
        """
        计算加权平均药品费用
        公式：加权平均药品费用 = Σ(药品费用 × 病例数) / Σ病例数
        
        Args:
            records: 病例记录列表
            dip_code: DIP分组编码
            
        Returns:
            加权平均药品费用
        """
        filtered = [r for r in records if r.dip_disease_code == dip_code]
        if not filtered:
            return Decimal("0")
        
        total_drug_cost = sum(r.drug_cost for r in filtered)
        total_count = len(filtered)
        
        return (total_drug_cost / total_count).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    
    def calculate_weighted_average_material_cost(
        self,
        records: List[MedicalRecord],
        dip_code: str
    ) -> Decimal:
        """
        计算加权平均材料费用
        公式：加权平均材料费用 = Σ(材料费用 × 病例数) / Σ病例数
        
        Args:
            records: 病例记录列表
            dip_code: DIP分组编码
            
        Returns:
            加权平均材料费用
        """
        filtered = [r for r in records if r.dip_disease_code == dip_code]
        if not filtered:
            return Decimal("0")
        
        total_material_cost = sum(r.material_cost for r in filtered)
        total_count = len(filtered)
        
        return (total_material_cost / total_count).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    
    def calculate_city_average_cost(
        self,
        records: List[MedicalRecord]
    ) -> Decimal:
        """
        计算全市平均住院费用
        
        Args:
            records: 病例记录列表
            
        Returns:
            全市平均住院费用
        """
        if not records:
            return Decimal("0")
        
        total_cost = sum(r.total_cost for r in records)
        total_count = len(records)
        
        return (total_cost / total_count).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    
    def calculate_city_average_cost_by_level(
        self,
        records: List[MedicalRecord],
        hospital_level: str
    ) -> Decimal:
        """
        计算同级别医疗机构平均住院费用
        
        Args:
            records: 病例记录列表
            hospital_level: 医院等级
            
        Returns:
            同级别医疗机构平均住院费用
        """
        filtered = [r for r in records if r.hospital_level == hospital_level]
        if not filtered:
            return Decimal("0")
        
        total_cost = sum(r.total_cost for r in filtered)
        total_count = len(filtered)
        
        return (total_cost / total_count).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    
    def calculate_hospital_disease_coefficient(
        self,
        hospital_records: List[MedicalRecord],
        city_records: List[MedicalRecord],
        dip_code: str,
        hospital_level: str
    ) -> Decimal:
        """
        计算同级别医疗机构某病种病例加权平均住院费用
        
        Args:
            hospital_records: 该医院病例记录
            city_records: 全市病例记录
            dip_code: DIP分组编码
            hospital_level: 医院等级
            
        Returns:
            病种级别调节系数
        """
        # 医院该病种平均费用
        hospital_filtered = [r for r in hospital_records if r.dip_disease_code == dip_code]
        if not hospital_filtered:
            return Decimal("1.0")
        
        hospital_disease_cost = sum(r.total_cost for r in hospital_filtered) / len(hospital_filtered)
        
        # 全市该病种平均费用
        city_filtered = [r for r in city_records if r.dip_disease_code == dip_code]
        if not city_filtered:
            return Decimal("1.0")
        
        city_disease_cost = sum(r.total_cost for r in city_filtered) / len(city_filtered)
        
        if city_disease_cost <= 0:
            return Decimal("1.0")
        
        coefficient = hospital_disease_cost / city_disease_cost
        return coefficient.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    
    def calculate_disease_group_coefficient(
        self,
        city_records: List[MedicalRecord],
        dip_code: str
    ) -> Decimal:
        """
        计算病种调节系数
        
        Args:
            city_records: 全市病例记录
            dip_code: DIP分组编码
            
        Returns:
            病种调节系数
        """
        city_filtered = [r for r in city_records if r.dip_disease_code == dip_code]
        if not city_filtered:
            return Decimal("1.0")
        
        city_avg_cost = sum(r.total_cost for r in city_filtered) / len(city_filtered)
        city_overall_avg = self.calculate_city_average_cost(city_records)
        
        if city_overall_avg <= 0:
            return Decimal("1.0")
        
        coefficient = city_avg_cost / city_overall_avg
        return coefficient.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    
    def calculate_weighted_average_drug_proportion(
        self,
        records: List[MedicalRecord],
        dip_code: str
    ) -> Decimal:
        """
        计算加权平均药品费用占比
        
        Args:
            records: 病例记录列表
            dip_code: DIP分组编码
            
        Returns:
            加权平均药品费用占比
        """
        filtered = [r for r in records if r.dip_disease_code == dip_code]
        if not filtered:
            return Decimal("0")
        
        total_drug = sum(r.drug_cost for r in filtered)
        total_cost = sum(r.total_cost for r in filtered)
        
        if total_cost <= 0:
            return Decimal("0")
        
        proportion = total_drug / total_cost
        return proportion.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    
    def calculate_local_directory_score(
        self,
        city_records: List[MedicalRecord],
        dip_code: str,
        hospital_coefficient: HospitalCoefficient = None
    ) -> ValueCalculationResult:
        """
        计算本地目录库分值
        
        Args:
            city_records: 全市病例记录
            dip_code: DIP分组编码
            hospital_coefficient: 医院调节系数（可选）
            
        Returns:
            计算结果
        """
        filtered = [r for r in city_records if r.dip_disease_code == dip_code]
        if not filtered:
            return ValueCalculationResult(
                calculation_method="本地目录库分值",
                value_per_point=Decimal("0"),
                total_payment=Decimal("0"),
                total_cases=0,
                average_cost=Decimal("0"),
                notes="无病例数据"
            )
        
        # 基本统计
        total_cases = len(filtered)
        total_cost = sum(r.total_cost for r in filtered)
        average_cost = total_cost / total_cases
        
        # 费用分位数计算
        costs = [float(r.total_cost) for r in filtered]
        p25 = Decimal(str(np.percentile(costs, 25)))
        p50 = Decimal(str(np.percentile(costs, 50)))
        p75 = Decimal(str(np.percentile(costs, 75)))
        
        # 费用波动系数
        cost_std = Decimal(str(np.std(costs)))
        cv = (cost_std / average_cost).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP) if average_cost > 0 else Decimal("0")
        
        # 异常值剔除（超过2个标准差）
        lower_bound = average_cost - 2 * cost_std
        upper_bound = average_cost + 2 * cost_std
        filtered_costs = [r for r in filtered if lower_bound <= r.total_cost <= upper_bound]
        
        if filtered_costs:
            adjusted_total = sum(r.total_cost for r in filtered_costs)
            adjusted_avg = adjusted_total / len(filtered_costs)
        else:
            adjusted_avg = average_cost
        
        # 医院调节系数
        hospital_coeff = Decimal("1.0")
        if hospital_coefficient:
            hospital_coeff = hospital_coefficient.total_coefficient
        
        # 最终分值
        final_score = adjusted_avg * hospital_coeff
        
        notes = f"""
        本地目录库分值测算结果:
        - DIP编码: {dip_code}
        - 病例数: {total_cases}
        - 原始平均费用: {average_cost:.2f}元
        - 费用分位数: P25={p25:.2f}, P50={p50:.2f}, P75={p75:.2f}
        - 费用波动系数(CV): {cv}
        - 异常值剔除后平均费用: {adjusted_avg:.2f}元
        - 医院调节系数: {hospital_coeff}
        - 最终分值: {final_score:.2f}元
        """
        
        return ValueCalculationResult(
            calculation_method="本地目录库分值",
            value_per_point=final_score,
            total_payment=final_score * total_cases,
            total_cases=total_cases,
            average_cost=average_cost,
            notes=notes
        )
    
    def calculate_disease_group_score(
        self,
        city_records: List[MedicalRecord],
        disease_groups: List[DiseaseGroup],
        dip_code: str
    ) -> ValueCalculationResult:
        """
        计算病种分值
        
        Args:
            city_records: 全市病例记录
            disease_groups: 病种分组列表
            dip_code: DIP分组编码
            
        Returns:
            计算结果
        """
        filtered = [r for r in city_records if r.dip_disease_code == dip_code]
        if not filtered:
            return ValueCalculationResult(
                calculation_method="病种分值",
                value_per_point=Decimal("0"),
                total_payment=Decimal("0"),
                total_cases=0,
                average_cost=Decimal("0"),
                notes="无病例数据"
            )
        
        # 病种分值
        disease_group = next((g for g in disease_groups if g.dip_code == dip_code), None)
        if not disease_group:
            return ValueCalculationResult(
                calculation_method="病种分值",
                value_per_point=Decimal("0"),
                total_payment=Decimal("0"),
                total_cases=0,
                average_cost=Decimal("0"),
                notes="未找到病种分组"
            )
        
        disease_score = disease_group.dip_weight
        
        # 基本统计
        total_cases = len(filtered)
        total_cost = sum(r.total_cost for r in filtered)
        average_cost = total_cost / total_cases
        
        notes = f"""
        病种分值测算结果:
        - DIP编码: {dip_code}
        - DIP分组: {disease_group.group_name}
        - 病例数: {total_cases}
        - 平均费用: {average_cost:.2f}元
        - 病种分值: {disease_score}
        """
        
        return ValueCalculationResult(
            calculation_method="病种分值",
            value_per_point=disease_score,
            total_payment=disease_score * total_cases,
            total_cases=total_cases,
            average_cost=average_cost,
            notes=notes
        )
    
    def batch_calculate_local_directory(
        self,
        city_records: List[MedicalRecord],
        dip_codes: List[str] = None,
        hospital_coefficients: List[HospitalCoefficient] = None
    ) -> Dict[str, ValueCalculationResult]:
        """
        批量计算本地目录库分值
        
        Args:
            city_records: 全市病例记录
            dip_codes: DIP编码列表（可选）
            hospital_coefficients: 医院调节系数列表（可选）
            
        Returns:
            计算结果字典
        """
        # 加载医院调节系数
        if hospital_coefficients:
            self.load_hospital_coefficients(hospital_coefficients)
        
        # 获取所有DIP编码
        if not dip_codes:
            dip_codes = list(set(r.dip_disease_code for r in city_records if r.dip_disease_code))
        
        results = {}
        for dip_code in dip_codes:
            # 获取对应的医院调节系数（取平均值）
            hospital_codes = list(set(r.hospital_code for r in city_records if r.dip_disease_code == dip_code))
            if hospital_codes and self.hospital_coefficients:
                coeffs = [self.hospital_coefficients[h] for h in hospital_codes if h in self.hospital_coefficients]
                if coeffs:
                    avg_coeff = sum(c.total_coefficient for c in coeffs) / len(coeffs)
                    result = self.calculate_local_directory_score(city_records, dip_code)
                    # 应用调节系数
                    result.value_per_point = result.value_per_point * avg_coeff
                    result.total_payment = result.value_per_point * result.total_cases
                    results[dip_code] = result
                else:
                    results[dip_code] = self.calculate_local_directory_score(city_records, dip_code)
            else:
                results[dip_code] = self.calculate_local_directory_score(city_records, dip_code)
        
        return results
    
    def calculate_city_wide_statistics(
        self,
        city_records: List[MedicalRecord]
    ) -> Dict:
        """
        计算全市统计信息
        
        Args:
            city_records: 全市病例记录
            
        Returns:
            统计信息字典
        """
        if not city_records:
            return {
                'total_cases': 0,
                'total_cost': Decimal('0'),
                'average_cost': Decimal('0'),
                'average_los': Decimal('0'),
                'dip_codes': 0
            }
        
        total_cases = len(city_records)
        total_cost = sum(r.total_cost for r in city_records)
        average_cost = total_cost / total_cases
        average_los = Decimal(str(sum(r.los for r in city_records))) / total_cases
        
        dip_codes = len(set(r.dip_disease_code for r in city_records if r.dip_disease_code))
        
        return {
            'total_cases': total_cases,
            'total_cost': total_cost,
            'average_cost': average_cost.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            'average_los': average_los.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            'dip_codes': dip_codes
        }
    
    def export_local_directory(
        self,
        results: Dict[str, ValueCalculationResult],
        output_path: str
    ) -> str:
        """
        导出本地目录库到Excel
        
        Args:
            results: 计算结果字典
            output_path: 输出文件路径
            
        Returns:
            输出文件路径
        """
        data = []
        for i, (dip_code, result) in enumerate(sorted(results.items()), 1):
            data.append({
                '序号': i,
                'DIP编码': dip_code,
                '计算方法': result.calculation_method,
                '分值': float(result.value_per_point),
                '病例数': result.total_cases,
                '平均费用': float(result.average_cost),
                '总支付金额': float(result.total_payment),
                '备注': result.notes
            })
        
        df = pd.DataFrame(data)
        df.to_excel(output_path, index=False, engine='openpyxl')
        return output_path
    
    def export_detailed_report(
        self,
        city_records: List[MedicalRecord],
        results: Dict[str, ValueCalculationResult],
        output_path: str
    ) -> str:
        """
        导出详细报告
        
        Args:
            city_records: 全市病例记录
            results: 计算结果字典
            output_path: 输出文件路径
            
        Returns:
            输出文件路径
        """
        writer = pd.ExcelWriter(output_path, engine='openpyxl')
        
        # 1. 全市统计概览
        city_stats = self.calculate_city_wide_statistics(city_records)
        stats_df = pd.DataFrame([{
            '指标': '总病例数',
            '值': city_stats['total_cases']
        }, {
            '指标': '总费用',
            '值': float(city_stats['total_cost'])
        }, {
            '指标': '平均费用',
            '值': float(city_stats['average_cost'])
        }, {
            '指标': '平均住院天数',
            '值': float(city_stats['average_los'])
        }, {
            '指标': 'DIP分组数',
            '值': city_stats['dip_codes']
        }])
        stats_df.to_excel(writer, sheet_name='全市统计', index=False)
        
        # 2. 本地目录库分值
        data = []
        for dip_code, result in sorted(results.items()):
            data.append({
                'DIP编码': dip_code,
                '计算方法': result.calculation_method,
                '分值': float(result.value_per_point),
                '病例数': result.total_cases,
                '平均费用': float(result.average_cost)
            })
        df = pd.DataFrame(data)
        df.to_excel(writer, sheet_name='本地目录库分值', index=False)
        
        # 3. 病例明细
        record_data = []
        for r in city_records:
            record_data.append({
                '住院号': r.record_id,
                '医院代码': r.hospital_code,
                '医院名称': r.hospital_name,
                '主诊断': r.main_diag_code,
                'DIP编码': r.dip_disease_code,
                '总费用': float(r.total_cost),
                '药品费用': float(r.drug_cost),
                '材料费用': float(r.material_cost),
                '住院天数': r.los
            })
        record_df = pd.DataFrame(record_data)
        record_df.to_excel(writer, sheet_name='病例明细', index=False)
        
        writer.close()
        return output_path
