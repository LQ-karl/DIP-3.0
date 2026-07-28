"""
DIP按病种分值分组测算工具 - 分值测算模块（可选方法版本）
基于《国家医疗保障按病种分值(DIP)付费3.0版技术规范》第五章第一节
功能：支持多种分值计算方法，根据不同需求选择不同的测算公式
"""
import pandas as pd
from typing import List, Dict, Optional, Tuple
from decimal import Decimal, ROUND_HALF_UP
from dataclasses import dataclass, field
from enum import Enum

from ..models.models import MedicalRecord, DiseaseGroup


class ValueCalculationMethod(Enum):
    """分值计算方法"""
    AVERAGE_COST = "平均费用法"  # RWi = mi / M × 1000
    REFERENCE_DISEASE = "基准病种费用法"  # RWi = mi / M × 1000 (M为基准病种费用)
    STANDARD_QUOTA = "标准定额法"  # RWi = mi / M (M为固定参数)
    DRUG_VALUE = "药品分值法"  # dRWi = dmi / dM
    CONSUMABLE_VALUE = "耗材分值法"  # cRWi = cmi / cM


@dataclass
class ValueCalculationConfig:
    """分值计算配置"""
    calculation_method: ValueCalculationMethod = ValueCalculationMethod.AVERAGE_COST
    
    # 平均费用法配置
    base_value: Decimal = Decimal("1000")  # 基础分值（默认1000）
    
    # 基准病种费用法配置
    reference_disease_code: str = ""  # 基准病种DIP编码
    reference_disease_cost: Decimal = Decimal("0")  # 基准病种费用
    
    # 标准定额法配置
    standard_quota: Decimal = Decimal("1")  # 标准定额（M值）
    
    # 年度加权配置
    enable_year_weight: bool = True  # 启用年度加权
    year_weights: Dict[int, Decimal] = field(default_factory=lambda: {
        2022: Decimal("0.1"),
        2023: Decimal("0.2"),
        2024: Decimal("0.7")
    })
    
    # 药品分值配置
    enable_drug_value: bool = True  # 启用药品分值
    
    # 耗材分值配置
    enable_consumable_value: bool = True  # 启用耗材分值
    
    # 调节系数配置
    enable_adjustment: bool = True  # 启用调节系数
    adjustment_factors: Dict[str, Decimal] = field(default_factory=dict)


@dataclass
class ValueCalculationResult:
    """分值计算结果"""
    dip_code: str  # DIP编码
    disease_name: str  # 病种名称
    
    # 基本统计
    case_count: int = 0  # 病例数
    total_cost: Decimal = Decimal("0")  # 总费用
    avg_cost: Decimal = Decimal("0")  # 平均费用
    
    # 药品费用
    total_drug_cost: Decimal = Decimal("0")  # 药品总费用
    avg_drug_cost: Decimal = Decimal("0")  # 平均药品费用
    
    # 耗材费用
    total_consumable_cost: Decimal = Decimal("0")  # 耗材总费用
    avg_consumable_cost: Decimal = Decimal("0")  # 平均耗材费用
    
    # 分值结果
    disease_value: Decimal = Decimal("0")  # 病种分值
    drug_value: Decimal = Decimal("0")  # 药品分值
    consumable_value: Decimal = Decimal("0")  # 耗材分值
    
    # 计算信息
    calculation_method: str = ""  # 计算方法
    city_avg_cost: Decimal = Decimal("0")  # 全市平均费用
    calculation_formula: str = ""  # 计算公式
    calculation_details: Dict[str, Decimal] = field(default_factory=dict)


class DIPValueCalculator:
    """DIP分值计算器（可选方法版本）"""
    
    def __init__(self, config: ValueCalculationConfig = None):
        """
        初始化计算器
        
        Args:
            config: 分值计算配置
        """
        self.config = config or ValueCalculationConfig()
    
    def calculate_all_values(
        self,
        records: List[MedicalRecord],
        disease_groups: List[DiseaseGroup] = None
    ) -> List[ValueCalculationResult]:
        """
        计算所有DIP的分值
        
        Args:
            records: 病例记录列表
            disease_groups: 病种分组列表
            
        Returns:
            分值计算结果列表
        """
        # 计算全市平均费用
        city_avg_cost = self._calculate_city_average_cost(records)
        
        # 按DIP分组统计
        dip_statistics = self._calculate_dip_statistics(records)
        
        # 计算基准病种费用（如果使用基准病种费用法）
        reference_cost = self._get_reference_disease_cost(
            records, disease_groups
        )
        
        # 计算每个DIP的分值
        results = []
        
        for dip_code, stats in dip_statistics.items():
            # 获取病种名称
            disease_name = dip_code
            if disease_groups:
                group = next((g for g in disease_groups if g.disease_code == dip_code), None)
                if group:
                    disease_name = group.disease_name
            
            # 计算分值
            result = self._calculate_single_dip_value(
                dip_code=dip_code,
                disease_name=disease_name,
                stats=stats,
                city_avg_cost=city_avg_cost,
                reference_cost=reference_cost,
                records=records
            )
            
            results.append(result)
        
        return results
    
    def calculate_single_value(
        self,
        records: List[MedicalRecord],
        dip_code: str,
        disease_name: str = ""
    ) -> ValueCalculationResult:
        """
        计算单个DIP的分值
        
        Args:
            records: 病例记录列表
            dip_code: DIP编码
            disease_name: 病种名称
            
        Returns:
            分值计算结果
        """
        # 计算全市平均费用
        city_avg_cost = self._calculate_city_average_cost(records)
        
        # 获取该DIP的病例
        dip_records = [r for r in records if r.dip_disease_code == dip_code]
        
        if not dip_records:
            return ValueCalculationResult(
                dip_code=dip_code,
                disease_name=disease_name or dip_code,
                calculation_method=self.config.calculation_method.value
            )
        
        # 计算统计信息
        stats = self._calculate_record_statistics(dip_records)
        
        # 计算基准病种费用
        reference_cost = self._get_reference_disease_cost(records)
        
        # 计算分值
        return self._calculate_single_dip_value(
            dip_code=dip_code,
            disease_name=disease_name or dip_code,
            stats=stats,
            city_avg_cost=city_avg_cost,
            reference_cost=reference_cost,
            records=records
        )
    
    def _calculate_city_average_cost(self, records: List[MedicalRecord]) -> Decimal:
        """计算全市平均费用"""
        if not records:
            return Decimal("0")
        
        total_cost = sum(r.total_cost for r in records)
        return (total_cost / len(records)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    
    def _calculate_dip_statistics(self, records: List[MedicalRecord]) -> Dict:
        """计算各DIP的统计信息"""
        dip_stats = {}
        
        for record in records:
            dip_code = record.dip_disease_code
            if not dip_code:
                continue
            
            if dip_code not in dip_stats:
                dip_stats[dip_code] = {
                    'case_count': 0,
                    'total_cost': Decimal("0"),
                    'total_drug_cost': Decimal("0"),
                    'total_consumable_cost': Decimal("0")
                }
            
            stats = dip_stats[dip_code]
            stats['case_count'] += 1
            stats['total_cost'] += record.total_cost
            stats['total_drug_cost'] += record.drug_cost
            stats['total_consumable_cost'] += record.material_cost
        
        # 计算平均值
        for dip_code, stats in dip_stats.items():
            if stats['case_count'] > 0:
                stats['avg_cost'] = (stats['total_cost'] / stats['case_count']).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                stats['avg_drug_cost'] = (stats['total_drug_cost'] / stats['case_count']).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                stats['avg_consumable_cost'] = (stats['total_consumable_cost'] / stats['case_count']).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            else:
                stats['avg_cost'] = Decimal("0")
                stats['avg_drug_cost'] = Decimal("0")
                stats['avg_consumable_cost'] = Decimal("0")
        
        return dip_stats
    
    def _calculate_record_statistics(self, records: List[MedicalRecord]) -> Dict:
        """计算单个DIP的统计信息"""
        if not records:
            return {
                'case_count': 0,
                'total_cost': Decimal("0"),
                'avg_cost': Decimal("0"),
                'total_drug_cost': Decimal("0"),
                'avg_drug_cost': Decimal("0"),
                'total_consumable_cost': Decimal("0"),
                'avg_consumable_cost': Decimal("0")
            }
        
        case_count = len(records)
        total_cost = sum(r.total_cost for r in records)
        total_drug_cost = sum(r.drug_cost for r in records)
        total_consumable_cost = sum(r.material_cost for r in records)
        
        return {
            'case_count': case_count,
            'total_cost': total_cost,
            'avg_cost': (total_cost / case_count).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            'total_drug_cost': total_drug_cost,
            'avg_drug_cost': (total_drug_cost / case_count).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            'total_consumable_cost': total_consumable_cost,
            'avg_consumable_cost': (total_consumable_cost / case_count).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        }
    
    def _get_reference_disease_cost(
        self,
        records: List[MedicalRecord],
        disease_groups: List[DiseaseGroup] = None
    ) -> Decimal:
        """获取基准病种费用"""
        # 如果已配置基准病种费用，直接使用
        if self.config.reference_disease_cost > 0:
            return self.config.reference_disease_cost
        
        # 如果配置了基准病种编码，查找对应费用
        if self.config.reference_disease_code:
            ref_records = [
                r for r in records
                if r.dip_disease_code == self.config.reference_disease_code
            ]
            if ref_records:
                total_cost = sum(r.total_cost for r in ref_records)
                return (total_cost / len(ref_records)).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
        
        # 默认使用急性阑尾炎作为基准病种
        default_ref_code = "K35-1"
        ref_records = [
            r for r in records
            if r.dip_disease_code == default_ref_code
        ]
        
        if ref_records:
            total_cost = sum(r.total_cost for r in ref_records)
            return (total_cost / len(ref_records)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        
        return Decimal("10000")  # 默认基准费用
    
    def _calculate_single_dip_value(
        self,
        dip_code: str,
        disease_name: str,
        stats: Dict,
        city_avg_cost: Decimal,
        reference_cost: Decimal,
        records: List[MedicalRecord] = None
    ) -> ValueCalculationResult:
        """计算单个DIP的分值"""
        result = ValueCalculationResult(
            dip_code=dip_code,
            disease_name=disease_name,
            case_count=stats['case_count'],
            total_cost=stats['total_cost'],
            avg_cost=stats['avg_cost'],
            total_drug_cost=stats['total_drug_cost'],
            avg_drug_cost=stats['avg_drug_cost'],
            total_consumable_cost=stats['total_consumable_cost'],
            avg_consumable_cost=stats['avg_consumable_cost'],
            city_avg_cost=city_avg_cost,
            calculation_method=self.config.calculation_method.value
        )
        
        # 根据计算方法计算分值
        method = self.config.calculation_method
        
        if method == ValueCalculationMethod.AVERAGE_COST:
            # 平均费用法: RWi = mi / M × 1000
            if city_avg_cost > 0:
                result.disease_value = (stats['avg_cost'] / city_avg_cost * self.config.base_value).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            result.calculation_formula = f"RWi = {stats['avg_cost']} / {city_avg_cost} × {self.config.base_value}"
            
        elif method == ValueCalculationMethod.REFERENCE_DISEASE:
            # 基准病种费用法: RWi = mi / M × 1000
            if reference_cost > 0:
                result.disease_value = (stats['avg_cost'] / reference_cost * self.config.base_value).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            result.calculation_formula = f"RWi = {stats['avg_cost']} / {reference_cost} × {self.config.base_value}"
            
        elif method == ValueCalculationMethod.STANDARD_QUOTA:
            # 标准定额法: RWi = mi / M
            if self.config.standard_quota > 0:
                result.disease_value = (stats['avg_cost'] / self.config.standard_quota).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            result.calculation_formula = f"RWi = {stats['avg_cost']} / {self.config.standard_quota}"
            
        elif method == ValueCalculationMethod.DRUG_VALUE:
            # 药品分值法: dRWi = dmi / dM × 1000
            city_avg_drug_cost = self._calculate_city_avg_drug_cost(records)
            if city_avg_drug_cost > 0:
                result.drug_value = (stats['avg_drug_cost'] / city_avg_drug_cost * self.config.base_value).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                result.disease_value = result.drug_value
            result.calculation_formula = f"dRWi = {stats['avg_drug_cost']} / {city_avg_drug_cost} × {self.config.base_value}"
            
        elif method == ValueCalculationMethod.CONSUMABLE_VALUE:
            # 耗材分值法: cRWi = cmi / cM × 1000
            city_avg_consumable_cost = self._calculate_city_avg_consumable_cost(records)
            if city_avg_consumable_cost > 0:
                result.consumable_value = (stats['avg_consumable_cost'] / city_avg_consumable_cost * self.config.base_value).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                result.disease_value = result.consumable_value
            result.calculation_formula = f"cRWi = {stats['avg_consumable_cost']} / {city_avg_consumable_cost} × {self.config.base_value}"
        
        # 计算药品分值和耗材分值（如果启用）
        if self.config.enable_drug_value and method != ValueCalculationMethod.DRUG_VALUE:
            city_avg_drug_cost = self._calculate_city_avg_drug_cost(records)
            if city_avg_drug_cost > 0:
                result.drug_value = (stats['avg_drug_cost'] / city_avg_drug_cost * self.config.base_value).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
        
        if self.config.enable_consumable_value and method != ValueCalculationMethod.CONSUMABLE_VALUE:
            city_avg_consumable_cost = self._calculate_city_avg_consumable_cost(records)
            if city_avg_consumable_cost > 0:
                result.consumable_value = (stats['avg_consumable_cost'] / city_avg_consumable_cost * self.config.base_value).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
        
        # 保存计算详情
        result.calculation_details = {
            'city_avg_cost': city_avg_cost,
            'reference_cost': reference_cost,
            'base_value': self.config.base_value
        }
        
        return result
    
    def _calculate_city_avg_drug_cost(self, records: List[MedicalRecord]) -> Decimal:
        """计算全市平均药品费用"""
        if not records:
            return Decimal("0")
        total_drug_cost = sum(r.drug_cost for r in records)
        return (total_drug_cost / len(records)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    
    def _calculate_city_avg_consumable_cost(self, records: List[MedicalRecord]) -> Decimal:
        """计算全市平均耗材费用"""
        if not records:
            return Decimal("0")
        total_consumable_cost = sum(r.material_cost for r in records)
        return (total_consumable_cost / len(records)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    
    def batch_calculate(
        self,
        records: List[MedicalRecord],
        disease_groups: List[DiseaseGroup] = None
    ) -> List[ValueCalculationResult]:
        """批量计算分值"""
        return self.calculate_all_values(records, disease_groups)
    
    def export_results(
        self,
        results: List[ValueCalculationResult],
        output_path: str
    ) -> str:
        """导出计算结果"""
        data = []
        for i, result in enumerate(results, 1):
            data.append({
                '序号': i,
                'DIP编码': result.dip_code,
                '病种名称': result.disease_name,
                '病例数': result.case_count,
                '平均费用': float(result.avg_cost),
                '全市平均费用': float(result.city_avg_cost),
                '病种分值': float(result.disease_value),
                '药品分值': float(result.drug_value),
                '耗材分值': float(result.consumable_value),
                '计算方法': result.calculation_method,
                '计算公式': result.calculation_formula
            })
        
        df = pd.DataFrame(data)
        df.to_excel(output_path, index=False, engine='openpyxl')
        return output_path
    
    def generate_report(
        self,
        results: List[ValueCalculationResult]
    ) -> str:
        """生成计算报告"""
        report = []
        report.append("=" * 60)
        report.append("DIP分值计算报告")
        report.append("=" * 60)
        report.append(f"计算方法: {self.config.calculation_method.value}")
        report.append(f"基础分值: {self.config.base_value}")
        report.append(f"计算DIP数量: {len(results)}")
        report.append("")
        
        report.append("【计算公式】")
        if self.config.calculation_method == ValueCalculationMethod.AVERAGE_COST:
            report.append("  平均费用法: RWi = mi / M × 1000")
            report.append("  其中: mi = 病种平均费用, M = 全市平均费用")
        elif self.config.calculation_method == ValueCalculationMethod.REFERENCE_DISEASE:
            report.append("  基准病种费用法: RWi = mi / M × 1000")
            report.append("  其中: mi = 病种平均费用, M = 基准病种费用")
        elif self.config.calculation_method == ValueCalculationMethod.STANDARD_QUOTA:
            report.append("  标准定额法: RWi = mi / M")
            report.append("  其中: mi = 病种平均费用, M = 标准定额")
        
        report.append("")
        report.append("【计算结果】")
        for result in sorted(results, key=lambda r: r.disease_value, reverse=True)[:20]:
            report.append(f"  {result.dip_code} ({result.disease_name}): {result.disease_value}")
        
        return "\n".join(report)


# 预定义配置
def create_average_cost_config() -> ValueCalculationConfig:
    """创建平均费用法配置"""
    return ValueCalculationConfig(
        calculation_method=ValueCalculationMethod.AVERAGE_COST,
        base_value=Decimal("1000"),
        enable_drug_value=True,
        enable_consumable_value=True
    )


def create_reference_disease_config(
    reference_code: str = "K35-1",
    reference_cost: Decimal = Decimal("0")
) -> ValueCalculationConfig:
    """创建基准病种费用法配置"""
    return ValueCalculationConfig(
        calculation_method=ValueCalculationMethod.REFERENCE_DISEASE,
        base_value=Decimal("1000"),
        reference_disease_code=reference_code,
        reference_disease_cost=reference_cost,
        enable_drug_value=True,
        enable_consumable_value=True
    )


def create_standard_quota_config(
    standard_quota: Decimal = Decimal("100")
) -> ValueCalculationConfig:
    """创建标准定额法配置"""
    return ValueCalculationConfig(
        calculation_method=ValueCalculationMethod.STANDARD_QUOTA,
        standard_quota=standard_quota,
        enable_drug_value=True,
        enable_consumable_value=True
    )


def create_drug_value_config() -> ValueCalculationConfig:
    """创建药品分值法配置"""
    return ValueCalculationConfig(
        calculation_method=ValueCalculationMethod.DRUG_VALUE,
        base_value=Decimal("1000"),
        enable_drug_value=True,
        enable_consumable_value=False
    )


def create_consumable_value_config() -> ValueCalculationConfig:
    """创建耗材分值法配置"""
    return ValueCalculationConfig(
        calculation_method=ValueCalculationMethod.CONSUMABLE_VALUE,
        base_value=Decimal("1000"),
        enable_drug_value=False,
        enable_consumable_value=True
    )
