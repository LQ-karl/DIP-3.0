"""
DIP按病种分值分组测算工具 - 本地目录库分值测算模块（可配置版本）
基于《国家医疗保障按病种分值(DIP)付费3.0版技术规范》第五章
"""
import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Any
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from collections import defaultdict

from ..models.models import (
    DiseaseGroup, MedicalRecord, HospitalCoefficient,
    DIPSettlementResult, ValueCalculationResult
)
from .calculation_config import (
    DIPCalculationConfig, CostType, CalculationType,
    CostCalculationConfig, StatisticalConfig,
    create_default_config, create_full_config
)


class LocalDirectoryScoreCalculator:
    """本地目录库分值测算器（可配置版本）"""
    
    def __init__(self, config: DIPCalculationConfig = None):
        """
        初始化计算器
        
        Args:
            config: 测算配置，如果为None则使用默认配置
        """
        self.config = config or create_default_config()
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
    
    def _get_cost_field(self, record: MedicalRecord, cost_type: CostType) -> Decimal:
        """
        根据费用类型获取对应的费用字段
        
        Args:
            record: 病例记录
            cost_type: 费用类型
            
        Returns:
            费用值
        """
        cost_mapping = {
            CostType.TOTAL: record.total_cost,
            CostType.DRUG: record.drug_cost,
            CostType.MATERIAL: record.material_cost,
            CostType.CONSUMABLE: record.consumable_cost,
            CostType.EXAM: record.exam_cost,
            CostType.TREATMENT: record.treatment_cost,
            CostType.NURSING: record.nursing_cost
        }
        return cost_mapping.get(cost_type, Decimal("0"))
    
    def _calculate_weighted_average(
        self,
        records: List[MedicalRecord],
        cost_type: CostType
    ) -> Decimal:
        """
        计算加权平均费用
        
        Args:
            records: 病例记录列表
            cost_type: 费用类型
            
        Returns:
            加权平均费用
        """
        if not records:
            return Decimal("0")
        
        total_cost = sum(self._get_cost_field(r, cost_type) for r in records)
        total_count = len(records)
        
        return (total_cost / total_count).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    
    def _calculate_median(
        self,
        records: List[MedicalRecord],
        cost_type: CostType
    ) -> Decimal:
        """
        计算中位数费用
        
        Args:
            records: 病例记录列表
            cost_type: 费用类型
            
        Returns:
            中位数费用
        """
        if not records:
            return Decimal("0")
        
        costs = [float(self._get_cost_field(r, cost_type)) for r in records]
        median = np.median(costs)
        
        return Decimal(str(median)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    
    def _calculate_percentile(
        self,
        records: List[MedicalRecord],
        cost_type: CostType,
        percentile: int
    ) -> Decimal:
        """
        计算分位数费用
        
        Args:
            records: 病例记录列表
            cost_type: 费用类型
            percentile: 分位数（0-100）
            
        Returns:
            分位数费用
        """
        if not records:
            return Decimal("0")
        
        costs = [float(self._get_cost_field(r, cost_type)) for r in records]
        p = np.percentile(costs, percentile)
        
        return Decimal(str(p)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    
    def _calculate_std(
        self,
        records: List[MedicalRecord],
        cost_type: CostType
    ) -> Decimal:
        """
        计算标准差
        
        Args:
            records: 病例记录列表
            cost_type: 费用类型
            
        Returns:
            标准差
        """
        if not records:
            return Decimal("0")
        
        costs = [float(self._get_cost_field(r, cost_type)) for r in records]
        std = np.std(costs)
        
        return Decimal(str(std)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    
    def _calculate_cv(
        self,
        records: List[MedicalRecord],
        cost_type: CostType
    ) -> Decimal:
        """
        计算变异系数（CV = 标准差 / 平均值）
        
        Args:
            records: 病例记录列表
            cost_type: 费用类型
            
        Returns:
            变异系数
        """
        if not records:
            return Decimal("0")
        
        avg = self._calculate_weighted_average(records, cost_type)
        if avg <= 0:
            return Decimal("0")
        
        std = self._calculate_std(records, cost_type)
        cv = std / avg
        
        return cv.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    
    def _remove_outliers(
        self,
        records: List[MedicalRecord],
        cost_type: CostType
    ) -> List[MedicalRecord]:
        """
        剔除异常值（超过阈值个标准差）
        
        Args:
            records: 病例记录列表
            cost_type: 费用类型
            
        Returns:
            剔除异常值后的病例列表
        """
        if not records or not self.config.statistical_config.remove_outliers:
            return records
        
        avg = self._calculate_weighted_average(records, cost_type)
        std = self._calculate_std(records, cost_type)
        threshold = self.config.statistical_config.outlier_std_threshold
        
        lower_bound = avg - threshold * std
        upper_bound = avg + threshold * std
        
        filtered = []
        for r in records:
            cost = self._get_cost_field(r, cost_type)
            if lower_bound <= cost <= upper_bound:
                filtered.append(r)
        
        return filtered
    
    def calculate_cost_statistics(
        self,
        records: List[MedicalRecord],
        cost_type: CostType
    ) -> Dict[str, Decimal]:
        """
        计算费用统计信息
        
        Args:
            records: 病例记录列表
            cost_type: 费用类型
            
        Returns:
            统计信息字典
        """
        if not records:
            return {}
        
        stats = {}
        
        # 平均值
        if self.config.statistical_config.calculate_mean:
            stats['average'] = self._calculate_weighted_average(records, cost_type)
        
        # 中位数
        if self.config.statistical_config.calculate_median:
            stats['median'] = self._calculate_median(records, cost_type)
        
        # 标准差
        if self.config.statistical_config.calculate_std:
            stats['std'] = self._calculate_std(records, cost_type)
        
        # 变异系数
        if self.config.statistical_config.calculate_cv:
            stats['cv'] = self._calculate_cv(records, cost_type)
        
        # 分位数
        if self.config.statistical_config.calculate_percentiles:
            for p in self.config.statistical_config.percentiles:
                stats[f'p{p}'] = self._calculate_percentile(records, cost_type, p)
        
        return stats
    
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
        return self._calculate_weighted_average(records, CostType.TOTAL)
    
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
        return self._calculate_weighted_average(filtered, CostType.TOTAL)
    
    def calculate_hospital_disease_coefficient(
        self,
        hospital_records: List[MedicalRecord],
        city_records: List[MedicalRecord],
        dip_code: str
    ) -> Decimal:
        """
        计算同级别医疗机构某病种病例加权平均住院费用
        
        Args:
            hospital_records: 该医院病例记录
            city_records: 全市病例记录
            dip_code: DIP分组编码
            
        Returns:
            病种级别调节系数
        """
        # 医院该病种平均费用
        hospital_filtered = [r for r in hospital_records if r.dip_disease_code == dip_code]
        if not hospital_filtered:
            return Decimal("1.0")
        
        hospital_disease_cost = self._calculate_weighted_average(hospital_filtered, CostType.TOTAL)
        
        # 全市该病种平均费用
        city_filtered = [r for r in city_records if r.dip_disease_code == dip_code]
        if not city_filtered:
            return Decimal("1.0")
        
        city_disease_cost = self._calculate_weighted_average(city_filtered, CostType.TOTAL)
        
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
        
        city_avg_cost = self._calculate_weighted_average(city_filtered, CostType.TOTAL)
        city_overall_avg = self.calculate_city_average_cost(city_records)
        
        if city_overall_avg <= 0:
            return Decimal("1.0")
        
        coefficient = city_avg_cost / city_overall_avg
        return coefficient.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    
    def calculate_local_directory_score(
        self,
        city_records: List[MedicalRecord],
        dip_code: str,
        hospital_coefficient: HospitalCoefficient = None
    ) -> Dict[str, Any]:
        """
        计算本地目录库分值
        
        Args:
            city_records: 全市病例记录
            dip_code: DIP分组编码
            hospital_coefficient: 医院调节系数（可选）
            
        Returns:
            计算结果字典
        """
        filtered = [r for r in city_records if r.dip_disease_code == dip_code]
        if not filtered:
            return {
                'dip_code': dip_code,
                'total_cases': 0,
                'cost_statistics': {},
                'final_score': Decimal("0"),
                'hospital_coefficient': Decimal("1.0"),
                'notes': "无病例数据"
            }
        
        # 基本统计
        total_cases = len(filtered)
        
        # 医院调节系数
        hospital_coeff = Decimal("1.0")
        if hospital_coefficient:
            hospital_coeff = hospital_coefficient.total_coefficient
        
        # 按配置的费用类型计算统计信息
        cost_statistics = {}
        final_score = Decimal("0")
        
        for cost_config in self.config.get_enabled_cost_configs():
            cost_type = cost_config.cost_type
            
            # 剔除异常值
            filtered_records = self._remove_outliers(filtered, cost_type)
            
            # 计算统计信息
            stats = self.calculate_cost_statistics(filtered_records, cost_type)
            cost_statistics[cost_type.value] = stats
            
            # 计算最终分值（使用平均费用）
            if 'average' in stats:
                score = stats['average'] * hospital_coeff
                cost_statistics[cost_type.value]['score'] = score
                
                # 如果是总费用，作为最终分值
                if cost_type == CostType.TOTAL:
                    final_score = score
        
        # 如果没有配置总费用，使用第一个启用的费用类型
        if final_score == Decimal("0") and cost_statistics:
            first_cost_type = list(cost_statistics.keys())[0]
            if 'score' in cost_statistics[first_cost_type]:
                final_score = cost_statistics[first_cost_type]['score']
        
        return {
            'dip_code': dip_code,
            'total_cases': total_cases,
            'cost_statistics': cost_statistics,
            'final_score': final_score,
            'hospital_coefficient': hospital_coeff,
            'notes': f"计算了{len(cost_statistics)}种费用类型的统计信息"
        }
    
    def batch_calculate_local_directory(
        self,
        city_records: List[MedicalRecord],
        dip_codes: List[str] = None,
        hospital_coefficients: List[HospitalCoefficient] = None
    ) -> Dict[str, Dict[str, Any]]:
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
            hospital_codes = list(set(
                r.hospital_code for r in city_records 
                if r.dip_disease_code == dip_code
            ))
            
            hospital_coeff = None
            if hospital_codes and self.hospital_coefficients:
                coeffs = [
                    self.hospital_coefficients[h] 
                    for h in hospital_codes 
                    if h in self.hospital_coefficients
                ]
                if coeffs:
                    # 创建平均调节系数
                    avg_coeff = sum(c.total_coefficient for c in coeffs) / len(coeffs)
                    hospital_coeff = HospitalCoefficient(
                        hospital_code="AVG",
                        hospital_name="平均",
                        hospital_level="",
                        total_coefficient=avg_coeff
                    )
            
            results[dip_code] = self.calculate_local_directory_score(
                city_records, dip_code, hospital_coeff
            )
        
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
        results: Dict[str, Dict[str, Any]],
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
            row = {
                '序号': i,
                'DIP编码': dip_code,
                '病例数': result['total_cases'],
                '医院调节系数': float(result['hospital_coefficient']),
                '最终分值': float(result['final_score']),
                '备注': result.get('notes', '')
            }
            
            # 添加各费用类型的统计信息
            for cost_type, stats in result.get('cost_statistics', {}).items():
                if 'average' in stats:
                    row[f'{cost_type}_平均费用'] = float(stats['average'])
                if 'median' in stats:
                    row[f'{cost_type}_中位数'] = float(stats['median'])
                if 'std' in stats:
                    row[f'{cost_type}_标准差'] = float(stats['std'])
                if 'cv' in stats:
                    row[f'{cost_type}_变异系数'] = float(stats['cv'])
            
            data.append(row)
        
        df = pd.DataFrame(data)
        df.to_excel(output_path, index=False, engine='openpyxl')
        return output_path
    
    def export_detailed_report(
        self,
        city_records: List[MedicalRecord],
        results: Dict[str, Dict[str, Any]],
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
            row = {
                'DIP编码': dip_code,
                '病例数': result['total_cases'],
                '最终分值': float(result['final_score'])
            }
            
            # 添加各费用类型的统计信息
            for cost_type, stats in result.get('cost_statistics', {}).items():
                if 'average' in stats:
                    row[f'{cost_type}_平均费用'] = float(stats['average'])
            
            data.append(row)
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
