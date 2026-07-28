"""
DIP按病种分值分组测算工具 - 测算参数配置模块
支持可选参数配置，灵活适配各种测算场景
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from decimal import Decimal
from enum import Enum


class CostType(Enum):
    """费用类型"""
    TOTAL = "总费用"
    DRUG = "药品费用"
    MATERIAL = "材料费用"
    CONSUMABLE = "耗材费用"
    EXAM = "检查费用"
    TREATMENT = "治疗费用"
    NURSING = "护理费用"


class CalculationType(Enum):
    """测算类型"""
    AVERAGE = "平均费用"
    WEIGHTED_AVERAGE = "加权平均费用"
    MEDIAN = "中位数费用"
    PERCENTILE_25 = "25%分位数"
    PERCENTILE_75 = "75%分位数"


@dataclass
class CostCalculationConfig:
    """费用测算配置"""
    cost_type: CostType = CostType.TOTAL  # 费用类型
    calculation_type: CalculationType = CalculationType.WEIGHTED_AVERAGE  # 测算类型
    enabled: bool = True  # 是否启用
    weight_field: str = "case_count"  # 权重字段（用于加权平均）
    
    def to_dict(self) -> Dict:
        return {
            'cost_type': self.cost_type.value,
            'calculation_type': self.calculation_type.value,
            'enabled': self.enabled
        }


@dataclass
class StatisticalConfig:
    """统计配置"""
    calculate_mean: bool = True  # 计算平均值
    calculate_median: bool = True  # 计算中位数
    calculate_std: bool = True  # 计算标准差
    calculate_cv: bool = True  # 计算变异系数
    calculate_percentiles: bool = True  # 计算分位数
    percentiles: List[int] = field(default_factory=lambda: [25, 50, 75])  # 分位数列表
    remove_outliers: bool = True  # 是否剔除异常值
    outlier_std_threshold: Decimal = Decimal("2")  # 异常值标准差阈值


@dataclass
class HospitalCoefficientConfig:
    """医院调节系数配置"""
    enable_basic_coefficient: bool = True  # 启用基本系数
    enable_bonus_coefficient: bool = True  # 启用加成系数
    
    # 加成系数权重
    medical_level_weight: Decimal = Decimal("0.25")  # 医疗水平权重
    specialty_weight: Decimal = Decimal("0.20")  # 专科特色权重
    cmi_weight: Decimal = Decimal("0.25")  # CMI权重
    performance_weight: Decimal = Decimal("0.15")  # 绩效考核权重
    agreement_weight: Decimal = Decimal("0.15")  # 协议履行权重
    
    # 病种级别系数
    enable_disease_level_coefficient: bool = False  # 启用病种级别系数


@dataclass
class AuxiliaryConfig:
    """辅助分型配置"""
    enable_cci: bool = True  # 启用CCI分型
    enable_severity: bool = True  # 启用疾病严重程度分型
    enable_age: bool = True  # 启用年龄特征分型
    enable_icu: bool = True  # 启用ICU分型
    enable_violation: bool = True  # 启用违规行为监测


@dataclass
class ExportConfig:
    """导出配置"""
    export_to_excel: bool = True  # 导出到Excel
    export_summary: bool = True  # 导出汇总表
    export_detail: bool = True  # 导出明细表
    export_coefficients: bool = True  # 导出系数表
    export_auxiliary: bool = True  # 导出辅助分型表
    
    # 自定义导出字段
    custom_fields: List[str] = field(default_factory=list)  # 自定义导出字段


@dataclass
class DIPCalculationConfig:
    """DIP测算总配置"""
    
    # 费用测算配置
    cost_configs: List[CostCalculationConfig] = field(default_factory=list)
    
    # 统计配置
    statistical_config: StatisticalConfig = field(default_factory=StatisticalConfig)
    
    # 医院调节系数配置
    hospital_coefficient_config: HospitalCoefficientConfig = field(
        default_factory=HospitalCoefficientConfig
    )
    
    # 辅助分型配置
    auxiliary_config: AuxiliaryConfig = field(default_factory=AuxiliaryConfig)
    
    # 导出配置
    export_config: ExportConfig = field(default_factory=ExportConfig)
    
    # 通用配置
    decimal_places: int = 4  # 小数位数
    min_case_count: int = 15  # 最小病例数
    
    def __post_init__(self):
        """初始化后处理"""
        if not self.cost_configs:
            # 默认配置：只计算总费用
            self.cost_configs = [
                CostCalculationConfig(
                    cost_type=CostType.TOTAL,
                    calculation_type=CalculationType.WEIGHTED_AVERAGE,
                    enabled=True
                )
            ]
    
    def add_cost_config(
        self,
        cost_type: CostType,
        calculation_type: CalculationType = CalculationType.WEIGHTED_AVERAGE,
        enabled: bool = True
    ):
        """添加费用测算配置"""
        # 检查是否已存在相同类型的配置
        for config in self.cost_configs:
            if config.cost_type == cost_type:
                config.calculation_type = calculation_type
                config.enabled = enabled
                return
        
        self.cost_configs.append(CostCalculationConfig(
            cost_type=cost_type,
            calculation_type=calculation_type,
            enabled=enabled
        ))
    
    def remove_cost_config(self, cost_type: CostType):
        """移除费用测算配置"""
        self.cost_configs = [c for c in self.cost_configs if c.cost_type != cost_type]
    
    def enable_cost_config(self, cost_type: CostType):
        """启用费用测算配置"""
        for config in self.cost_configs:
            if config.cost_type == cost_type:
                config.enabled = True
                return
    
    def disable_cost_config(self, cost_type: CostType):
        """禁用费用测算配置"""
        for config in self.cost_configs:
            if config.cost_type == cost_type:
                config.enabled = False
                return
    
    def get_enabled_cost_configs(self) -> List[CostCalculationConfig]:
        """获取启用的费用测算配置"""
        return [c for c in self.cost_configs if c.enabled]
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'cost_configs': [c.to_dict() for c in self.cost_configs],
            'statistical_config': {
                'calculate_mean': self.statistical_config.calculate_mean,
                'calculate_median': self.statistical_config.calculate_median,
                'calculate_std': self.statistical_config.calculate_std,
                'calculate_cv': self.statistical_config.calculate_cv,
                'calculate_percentiles': self.statistical_config.calculate_percentiles,
                'percentiles': self.statistical_config.percentiles,
                'remove_outliers': self.statistical_config.remove_outliers,
                'outlier_std_threshold': float(self.statistical_config.outlier_std_threshold)
            },
            'hospital_coefficient_config': {
                'enable_basic_coefficient': self.hospital_coefficient_config.enable_basic_coefficient,
                'enable_bonus_coefficient': self.hospital_coefficient_config.enable_bonus_coefficient,
                'enable_disease_level_coefficient': self.hospital_coefficient_config.enable_disease_level_coefficient
            },
            'auxiliary_config': {
                'enable_cci': self.auxiliary_config.enable_cci,
                'enable_severity': self.auxiliary_config.enable_severity,
                'enable_age': self.auxiliary_config.enable_age,
                'enable_icu': self.auxiliary_config.enable_icu,
                'enable_violation': self.auxiliary_config.enable_violation
            },
            'export_config': {
                'export_to_excel': self.export_config.export_to_excel,
                'export_summary': self.export_config.export_summary,
                'export_detail': self.export_config.export_detail,
                'export_coefficients': self.export_config.export_coefficients,
                'export_auxiliary': self.export_config.export_auxiliary
            },
            'decimal_places': self.decimal_places,
            'min_case_count': self.min_case_count
        }


def create_default_config() -> DIPCalculationConfig:
    """创建默认配置"""
    return DIPCalculationConfig(
        cost_configs=[
            CostCalculationConfig(
                cost_type=CostType.TOTAL,
                calculation_type=CalculationType.WEIGHTED_AVERAGE,
                enabled=True
            )
        ]
    )


def create_full_config() -> DIPCalculationConfig:
    """创建完整配置（所有费用类型都启用）"""
    return DIPCalculationConfig(
        cost_configs=[
            CostCalculationConfig(cost_type=CostType.TOTAL, enabled=True),
            CostCalculationConfig(cost_type=CostType.DRUG, enabled=True),
            CostCalculationConfig(cost_type=CostType.MATERIAL, enabled=True),
            CostCalculationConfig(cost_type=CostType.CONSUMABLE, enabled=True),
            CostCalculationConfig(cost_type=CostType.EXAM, enabled=True),
            CostCalculationConfig(cost_type=CostType.TREATMENT, enabled=True),
            CostCalculationConfig(cost_type=CostType.NURSING, enabled=True)
        ]
    )


def create_drug_material_config() -> DIPCalculationConfig:
    """创建药品+材料费用测算配置"""
    return DIPCalculationConfig(
        cost_configs=[
            CostCalculationConfig(cost_type=CostType.TOTAL, enabled=True),
            CostCalculationConfig(cost_type=CostType.DRUG, enabled=True),
            CostCalculationConfig(cost_type=CostType.MATERIAL, enabled=True)
        ]
    )


def create_simple_config() -> DIPCalculationConfig:
    """创建简单配置（只计算总费用，不进行异常值剔除）"""
    return DIPCalculationConfig(
        cost_configs=[
            CostCalculationConfig(cost_type=CostType.TOTAL, enabled=True)
        ],
        statistical_config=StatisticalConfig(
            calculate_mean=True,
            calculate_median=False,
            calculate_std=False,
            calculate_cv=False,
            calculate_percentiles=False,
            remove_outliers=False
        )
    )
