"""
DIP3.0本地目录测算系统 - 高倍率/低倍率病例识别模块
实现高倍率、低倍率、偏差病例、特殊病例的识别
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from decimal import Decimal
import pandas as pd
import numpy as np


@dataclass
class RateThreshold:
    """倍率阈值配置"""
    high_rate_factor: float = 2.0  # 高倍率因子（费用超过平均费用的N倍）
    low_rate_factor: float = 0.5  # 低倍率因子（费用低于平均费用的N倍）
    high_rate_cv: float = 1.5  # 高倍率变异系数阈值
    extreme_high_factor: float = 3.0  # 极端高倍率因子
    extreme_low_factor: float = 0.3  # 极端低倍率因子


@dataclass
class RateClassification:
    """倍率分类结果"""
    record_id: str  # 病例ID
    disease_code: str  # 病种代码
    total_cost: float  # 总费用
    avg_cost: float  # 平均费用
    rate_ratio: float  # 倍率（费用/平均费用）
    rate_type: str  # 倍率类型（高倍率/低倍率/正常/极端高/极端低）
    risk_level: str  # 风险等级（高/中/低）
    detail_info: str  # 详细信息


class HighLowRateHandler:
    """高倍率/低倍率病例处理器"""
    
    def __init__(self, threshold: RateThreshold = None):
        """
        初始化处理器
        
        Args:
            threshold: 倍率阈值配置
        """
        self.threshold = threshold or RateThreshold()
    
    def calculate_rate_ratio(self, cost: float, avg_cost: float) -> float:
        """
        计算倍率
        
        Args:
            cost: 病例费用
            avg_cost: 平均费用
            
        Returns:
            倍率
        """
        if avg_cost <= 0:
            return 0
        return cost / avg_cost
    
    def classify_rate_type(self, rate_ratio: float) -> Tuple[str, str]:
        """
        分类倍率类型
        
        Args:
            rate_ratio: 倍率
            
        Returns:
            (倍率类型, 风险等级)
        """
        if rate_ratio >= self.threshold.extreme_high_factor:
            return "极端高倍率", "高"
        elif rate_ratio >= self.threshold.high_rate_factor:
            return "高倍率", "中"
        elif rate_ratio <= self.threshold.extreme_low_factor:
            return "极端低倍率", "高"
        elif rate_ratio <= self.threshold.low_rate_factor:
            return "低倍率", "中"
        else:
            return "正常", "低"
    
    def identify_high_low_rate(self, records: pd.DataFrame, disease_groups: pd.DataFrame) -> List[RateClassification]:
        """
        识别高倍率和低倍率病例
        
        Args:
            records: 病例数据
            disease_groups: 病种分组数据
            
        Returns:
            倍率分类结果列表
        """
        results = []
        
        # 构建病种平均费用查找表
        avg_cost_map = {}
        for _, group in disease_groups.iterrows():
            disease_code = group.get('disease_code', '')
            avg_cost = group.get('avg_cost', 0)
            avg_cost_map[disease_code] = avg_cost
        
        # 遍历每条病例
        for _, record in records.iterrows():
            record_id = record.get('record_id', '')
            disease_code = record.get('dip_disease_code', '')
            total_cost = record.get('total_cost', 0)
            
            # 获取该病种的平均费用
            avg_cost = avg_cost_map.get(disease_code, 0)
            
            if avg_cost <= 0:
                continue
            
            # 计算倍率
            rate_ratio = self.calculate_rate_ratio(total_cost, avg_cost)
            
            # 分类倍率类型
            rate_type, risk_level = self.classify_rate_type(rate_ratio)
            
            # 生成详细信息
            detail_info = f"费用{total_cost:.2f}/平均{avg_cost:.2f}={rate_ratio:.2f}倍"
            
            results.append(RateClassification(
                record_id=record_id,
                disease_code=disease_code,
                total_cost=total_cost,
                avg_cost=avg_cost,
                rate_ratio=rate_ratio,
                rate_type=rate_type,
                risk_level=risk_level,
                detail_info=detail_info
            ))
        
        return results
    
    def calculate_disease_rate_stats(self, records: pd.DataFrame, disease_groups: pd.DataFrame) -> pd.DataFrame:
        """
        计算每个病种的高低倍率统计
        
        Args:
            records: 病例数据
            disease_groups: 病种分组数据
            
        Returns:
            病种倍率统计DataFrame
        """
        stats_list = []
        
        # 构建病种平均费用查找表
        avg_cost_map = {}
        for _, group in disease_groups.iterrows():
            disease_code = group.get('disease_code', '')
            avg_cost = group.get('avg_cost', 0)
            avg_cost_map[disease_code] = avg_cost
        
        # 按病种分组统计
        for disease_code, avg_cost in avg_cost_map.items():
            if avg_cost <= 0:
                continue
            
            # 获取该病种的病例
            disease_records = records[records['dip_disease_code'] == disease_code]
            total_count = len(disease_records)
            
            if total_count == 0:
                continue
            
            # 计算高低倍率病例数
            high_rate_count = 0
            low_rate_count = 0
            extreme_high_count = 0
            extreme_low_count = 0
            
            for _, record in disease_records.iterrows():
                total_cost = record.get('total_cost', 0)
                rate_ratio = self.calculate_rate_ratio(total_cost, avg_cost)
                
                if rate_ratio >= self.threshold.extreme_high_factor:
                    extreme_high_count += 1
                elif rate_ratio >= self.threshold.high_rate_factor:
                    high_rate_count += 1
                elif rate_ratio <= self.threshold.extreme_low_factor:
                    extreme_low_count += 1
                elif rate_ratio <= self.threshold.low_rate_factor:
                    low_rate_count += 1
            
            stats_list.append({
                'disease_code': disease_code,
                'avg_cost': avg_cost,
                'total_count': total_count,
                'high_rate_count': high_rate_count,
                'low_rate_count': low_rate_count,
                'extreme_high_count': extreme_high_count,
                'extreme_low_count': extreme_low_count,
                'high_rate_pct': high_rate_count / total_count * 100,
                'low_rate_pct': low_rate_count / total_count * 100,
            })
        
        return pd.DataFrame(stats_list)
    
    def identify_special_cases(self, records: pd.DataFrame) -> pd.DataFrame:
        """
        识别特殊病例
        
        Args:
            records: 病例数据
            
        Returns:
            特殊病例DataFrame
        """
        special_cases = []
        
        for _, record in records.iterrows():
            record_id = record.get('record_id', '')
            total_cost = record.get('total_cost', 0)
            los = record.get('los', 0)
            main_diag_code = record.get('main_diag_code', '')
            
            is_special = False
            special_reasons = []
            
            # 检查1：住院天数异常长（超过30天）
            if los > 30:
                is_special = True
                special_reasons.append(f"住院天数异常: {los}天")
            
            # 检查2：费用为0或负数
            if total_cost <= 0:
                is_special = True
                special_reasons.append(f"费用异常: {total_cost}")
            
            # 检查3：诊断编码为空
            if not main_diag_code:
                is_special = True
                special_reasons.append("诊断编码为空")
            
            if is_special:
                special_cases.append({
                    'record_id': record_id,
                    'disease_code': record.get('dip_disease_code', ''),
                    'total_cost': total_cost,
                    'los': los,
                    'main_diag_code': main_diag_code,
                    'special_reasons': '; '.join(special_reasons)
                })
        
        return pd.DataFrame(special_cases)
    
    def generate_rate_report(self, records: pd.DataFrame, disease_groups: pd.DataFrame) -> str:
        """
        生成倍率分析报告
        
        Args:
            records: 病例数据
            disease_groups: 病种分组数据
            
        Returns:
            报告文本
        """
        # 识别高低倍率病例
        rate_results = self.identify_high_low_rate(records, disease_groups)
        
        # 统计各类型数量
        type_counts = {}
        for result in rate_results:
            rate_type = result.rate_type
            type_counts[rate_type] = type_counts.get(rate_type, 0) + 1
        
        # 计算病种统计
        disease_stats = self.calculate_disease_rate_stats(records, disease_groups)
        
        # 识别特殊病例
        special_cases = self.identify_special_cases(records)
        
        # 生成报告
        lines = []
        lines.append("=" * 60)
        lines.append("高倍率/低倍率病例分析报告")
        lines.append("=" * 60)
        lines.append(f"总病例数: {len(records)}")
        lines.append(f"总病种数: {len(disease_groups)}")
        lines.append("")
        
        lines.append("-" * 60)
        lines.append("倍率分布统计:")
        lines.append("-" * 60)
        for rate_type, count in sorted(type_counts.items()):
            pct = count / len(rate_results) * 100 if rate_results else 0
            lines.append(f"  {rate_type}: {count}例 ({pct:.2f}%)")
        
        lines.append("")
        lines.append("-" * 60)
        lines.append("高倍率病种统计(前10):")
        lines.append("-" * 60)
        if not disease_stats.empty:
            high_rate_diseases = disease_stats.sort_values('high_rate_pct', ascending=False).head(10)
            for _, row in high_rate_diseases.iterrows():
                lines.append(f"  {row['disease_code']}: {row['high_rate_count']}例 ({row['high_rate_pct']:.2f}%)")
        
        lines.append("")
        lines.append("-" * 60)
        lines.append("低倍率病种统计(前10):")
        lines.append("-" * 60)
        if not disease_stats.empty:
            low_rate_diseases = disease_stats.sort_values('low_rate_pct', ascending=False).head(10)
            for _, row in low_rate_diseases.iterrows():
                lines.append(f"  {row['disease_code']}: {row['low_rate_count']}例 ({row['low_rate_pct']:.2f}%)")
        
        lines.append("")
        lines.append("-" * 60)
        lines.append(f"特殊病例统计: {len(special_cases)}例")
        lines.append("-" * 60)
        if not special_cases.empty:
            for _, row in special_cases.head(10).iterrows():
                lines.append(f"  {row['record_id']}: {row['special_reasons']}")
        
        lines.append("")
        lines.append("=" * 60)
        
        return "\n".join(lines)
