"""
DIP按病种分值分组测算工具 - 年度加权计算模块
基于《国家医疗保障按病种分值(DIP)付费3.0版技术规范》
功能：多年度数据加权计算
"""
import pandas as pd
from typing import List, Dict, Optional, Tuple
from decimal import Decimal, ROUND_HALF_UP
from dataclasses import dataclass, field

from ..models.models import MedicalRecord


@dataclass
class YearWeight:
    """年度权重"""
    year: int  # 年度
    weight: Decimal  # 权重
    description: str = ""  # 说明


@dataclass
class YearWeightConfig:
    """年度加权配置"""
    enable_year_weight: bool = True  # 启用年度加权
    year_weights: List[YearWeight] = field(default_factory=list)  # 年度权重列表
    normalize_weights: bool = True  # 是否归一化权重
    
    def __post_init__(self):
        """初始化后处理"""
        if not self.year_weights:
            # 默认配置：最近三年加权
            self.year_weights = [
                YearWeight(year=2022, weight=Decimal("0.1"), description="前年"),
                YearWeight(year=2023, weight=Decimal("0.2"), description="去年"),
                YearWeight(year=2024, weight=Decimal("0.7"), description="当年")
            ]


@dataclass
class YearWeightResult:
    """年度加权结果"""
    total_years: int
    total_weight: Decimal
    weighted_records: int
    year_statistics: Dict[int, Dict] = field(default_factory=dict)
    processing_log: List[str] = field(default_factory=list)


class YearWeightCalculator:
    """年度加权计算器"""
    
    def __init__(self, config: YearWeightConfig = None):
        """
        初始化计算器
        
        Args:
            config: 年度加权配置
        """
        self.config = config or YearWeightConfig()
    
    def calculate_weighted_statistics(
        self,
        records: List[MedicalRecord],
        year_field: str = "admission_year"
    ) -> Dict:
        """
        计算加权统计信息
        
        Args:
            records: 病例记录列表
            year_field: 年度字段名
            
        Returns:
            加权统计信息
        """
        if not self.config.enable_year_weight:
            return self._calculate_unweighted_statistics(records)
        
        # 按年度分组
        year_groups = self._group_by_year(records, year_field)
        
        # 归一化权重
        weights = self._normalize_weights()
        
        # 计算加权统计
        weighted_stats = {}
        
        # 收集所有DIP编码
        all_dip_codes = set()
        for year, year_records in year_groups.items():
            for record in year_records:
                all_dip_codes.add(record.dip_disease_code)
        
        # 计算每个DIP的加权统计
        for dip_code in all_dip_codes:
            weighted_cost = Decimal("0")
            weighted_count = 0
            
            for year, weight in weights.items():
                year_records = year_groups.get(year, [])
                dip_records = [r for r in year_records if r.dip_disease_code == dip_code]
                
                if dip_records:
                    year_avg_cost = sum(r.total_cost for r in dip_records) / len(dip_records)
                    weighted_cost += year_avg_cost * weight
                    weighted_count += len(dip_records)
            
            weighted_stats[dip_code] = {
                'weighted_avg_cost': weighted_cost.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                'total_cases': weighted_count
            }
        
        return weighted_stats
    
    def calculate_weighted_dip_value(
        self,
        records: List[MedicalRecord],
        dip_code: str,
        year_field: str = "admission_year"
    ) -> Decimal:
        """
        计算单个DIP的加权分值
        
        Args:
            records: 病例记录列表
            dip_code: DIP编码
            year_field: 年度字段名
            
        Returns:
            加权分值
        """
        if not self.config.enable_year_weight:
            return self._calculate_simple_average(records, dip_code)
        
        # 按年度分组
        year_groups = self._group_by_year(records, year_field)
        
        # 归一化权重
        weights = self._normalize_weights()
        
        weighted_cost = Decimal("0")
        
        for year, weight in weights.items():
            year_records = year_groups.get(year, [])
            dip_records = [r for r in year_records if r.dip_disease_code == dip_code]
            
            if dip_records:
                year_avg_cost = sum(r.total_cost for r in dip_records) / len(dip_records)
                weighted_cost += year_avg_cost * weight
        
        return weighted_cost.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    
    def calculate_weighted_all_dip_values(
        self,
        records: List[MedicalRecord],
        year_field: str = "admission_year"
    ) -> Dict[str, Decimal]:
        """
        计算所有DIP的加权分值
        
        Args:
            records: 病例记录列表
            year_field: 年度字段名
            
        Returns:
            DIP加权分值字典
        """
        # 收集所有DIP编码
        all_dip_codes = set(r.dip_disease_code for r in records if r.dip_disease_code)
        
        # 计算每个DIP的加权分值
        result = {}
        for dip_code in all_dip_codes:
            result[dip_code] = self.calculate_weighted_dip_value(records, dip_code, year_field)
        
        return result
    
    def _group_by_year(
        self,
        records: List[MedicalRecord],
        year_field: str
    ) -> Dict[int, List[MedicalRecord]]:
        """按年度分组"""
        year_groups = {}
        
        for record in records:
            # 从入院日期提取年度
            if hasattr(record, 'admission_date') and record.admission_date:
                try:
                    year = int(record.admission_date[:4])
                except (ValueError, IndexError):
                    year = 2024  # 默认年度
            else:
                year = 2024  # 默认年度
            
            if year not in year_groups:
                year_groups[year] = []
            year_groups[year].append(record)
        
        return year_groups
    
    def _normalize_weights(self) -> Dict[int, Decimal]:
        """归一化权重"""
        weights = {}
        total_weight = Decimal("0")
        
        for yw in self.config.year_weights:
            weights[yw.year] = yw.weight
            total_weight += yw.weight
        
        if self.config.normalize_weights and total_weight > 0:
            for year in weights:
                weights[year] = (weights[year] / total_weight).quantize(
                    Decimal("0.0001"), rounding=ROUND_HALF_UP
                )
        
        return weights
    
    def _calculate_unweighted_statistics(self, records: List[MedicalRecord]) -> Dict:
        """计算非加权统计信息"""
        stats = {}
        
        for record in records:
            dip_code = record.dip_disease_code
            if not dip_code:
                continue
            
            if dip_code not in stats:
                stats[dip_code] = {
                    'total_cost': Decimal("0"),
                    'count': 0
                }
            
            stats[dip_code]['total_cost'] += record.total_cost
            stats[dip_code]['count'] += 1
        
        # 计算平均值
        for dip_code in stats:
            s = stats[dip_code]
            if s['count'] > 0:
                s['avg_cost'] = s['total_cost'] / s['count']
            else:
                s['avg_cost'] = Decimal("0")
        
        return stats
    
    def _calculate_simple_average(
        self,
        records: List[MedicalRecord],
        dip_code: str
    ) -> Decimal:
        """计算简单平均值"""
        dip_records = [r for r in records if r.dip_disease_code == dip_code]
        
        if not dip_records:
            return Decimal("0")
        
        total_cost = sum(r.total_cost for r in dip_records)
        return (total_cost / len(dip_records)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    
    def get_year_statistics(self, records: List[MedicalRecord]) -> Dict[int, Dict]:
        """获取年度统计信息"""
        year_groups = self._group_by_year(records, "admission_year")
        
        stats = {}
        for year, year_records in year_groups.items():
            stats[year] = {
                'count': len(year_records),
                'avg_cost': self._calculate_simple_average(year_records, None) if year_records else Decimal("0"),
                'dip_codes': len(set(r.dip_disease_code for r in year_records if r.dip_disease_code))
            }
        
        return stats
    
    def generate_weight_report(self, records: List[MedicalRecord]) -> str:
        """生成加权报告"""
        report = []
        report.append("=" * 60)
        report.append("年度加权计算报告")
        report.append("=" * 60)
        
        # 年度权重配置
        report.append("\n【年度权重配置】")
        for yw in self.config.year_weights:
            report.append(f"  {yw.year}年: {yw.weight} ({yw.description})")
        
        # 归一化权重
        weights = self._normalize_weights()
        report.append("\n【归一化权重】")
        for year, weight in sorted(weights.items()):
            report.append(f"  {year}年: {weight}")
        
        # 年度统计
        year_stats = self.get_year_statistics(records)
        report.append("\n【年度统计】")
        for year, stats in sorted(year_stats.items()):
            report.append(f"  {year}年:")
            report.append(f"    病例数: {stats['count']}")
            report.append(f"    DIP分组数: {stats['dip_codes']}")
        
        return "\n".join(report)


def create_default_year_weight_config() -> YearWeightConfig:
    """创建默认年度加权配置"""
    return YearWeightConfig(
        enable_year_weight=True,
        year_weights=[
            YearWeight(year=2022, weight=Decimal("0.1"), description="前年"),
            YearWeight(year=2023, weight=Decimal("0.2"), description="去年"),
            YearWeight(year=2024, weight=Decimal("0.7"), description="当年")
        ],
        normalize_weights=True
    )


def create_two_year_weight_config() -> YearWeightConfig:
    """创建两年度加权配置"""
    return YearWeightConfig(
        enable_year_weight=True,
        year_weights=[
            YearWeight(year=2023, weight=Decimal("0.3"), description="去年"),
            YearWeight(year=2024, weight=Decimal("0.7"), description="当年")
        ],
        normalize_weights=True
    )


def create_equal_weight_config() -> YearWeightConfig:
    """创建等权重配置"""
    return YearWeightConfig(
        enable_year_weight=True,
        year_weights=[
            YearWeight(year=2022, weight=Decimal("1"), description="前年"),
            YearWeight(year=2023, weight=Decimal("1"), description="去年"),
            YearWeight(year=2024, weight=Decimal("1"), description="当年")
        ],
        normalize_weights=True
    )
