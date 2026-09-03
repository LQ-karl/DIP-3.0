"""
DIP按病种分值分组测算工具 - 医疗机构等级系数选择模块
基于《国家医疗保障按病种分值(DIP)付费3.0版技术规范》
功能：医疗机构等级系数支持多种测算方式选择
"""
import pandas as pd
from typing import List, Dict, Optional, Tuple
from decimal import Decimal, ROUND_HALF_UP
from dataclasses import dataclass, field
from enum import Enum

from ..models.models import MedicalRecord, HospitalCoefficient


class CoefficientCalculationMethod(Enum):
    """系数计算方法"""
    BASIC_ONLY = "基本系数法"  # 仅使用基本系数
    BONUS_ONLY = "加成系数法"  # 仅使用加成系数
    BASIC_AND_BONUS = "基本+加成系数法"  # 基本系数+加成系数
    DISEASE_SPECIFIC = "病种级别系数法"  # 病种级别调节系数
    COMPREHENSIVE = "综合系数法"  # 综合考虑多种因素


@dataclass
class CoefficientCalculationConfig:
    """系数计算配置"""
    calculation_method: CoefficientCalculationMethod = CoefficientCalculationMethod.BASIC_AND_BONUS
    
    # 基本系数配置
    enable_basic_coefficient: bool = True  # 启用基本系数
    basic_coefficient_weight: Decimal = Decimal("1.0")  # 基本系数权重
    
    # 加成系数配置
    enable_bonus_coefficient: bool = True  # 启用加成系数
    bonus_coefficient_weight: Decimal = Decimal("1.0")  # 加成系数权重
    
    # 加成系数子项配置
    medical_level_weight: Decimal = Decimal("0.25")  # 医疗水平权重
    specialty_weight: Decimal = Decimal("0.20")  # 专科特色权重
    cmi_weight: Decimal = Decimal("0.25")  # CMI权重
    performance_weight: Decimal = Decimal("0.15")  # 绩效考核权重
    agreement_weight: Decimal = Decimal("0.15")  # 协议履行权重
    
    # 病种级别系数配置
    enable_disease_level_coefficient: bool = False  # 启用病种级别系数
    disease_level_weight: Decimal = Decimal("1.0")  # 病种级别系数权重
    
    # 综合系数配置
    comprehensive_weights: Dict[str, Decimal] = field(default_factory=lambda: {
        "基本系数": Decimal("0.4"),
        "加成系数": Decimal("0.3"),
        "病种级别系数": Decimal("0.3")
    })


@dataclass
class CoefficientCalculationResult:
    """系数计算结果"""
    hospital_code: str = ""
    hospital_name: str = ""
    hospital_level: str = ""
    
    # 各项系数
    basic_coefficient: Decimal = Decimal("1.0")
    bonus_coefficient: Decimal = Decimal("0")
    disease_level_coefficient: Decimal = Decimal("1.0")
    
    # 加成系数子项
    medical_level_score: Decimal = Decimal("0")
    specialty_score: Decimal = Decimal("0")
    cmi_score: Decimal = Decimal("0")
    performance_score: Decimal = Decimal("0")
    agreement_score: Decimal = Decimal("0")
    
    # 最终系数
    final_coefficient: Decimal = Decimal("1.0")
    calculation_method: str = ""
    calculation_details: Dict[str, Decimal] = field(default_factory=dict)


class HospitalCoefficientSelector:
    """医疗机构等级系数选择器"""
    
    # 医院等级基础系数
    HOSPITAL_LEVEL_COEFFICIENTS = {
        "三级甲等": Decimal("1.2"),
        "三级乙等": Decimal("1.15"),
        "三级丙等": Decimal("1.1"),
        "二级甲等": Decimal("1.05"),
        "二级乙等": Decimal("1.0"),
        "二级丙等": Decimal("0.95"),
        "一级": Decimal("0.85"),
        "社区卫生服务中心": Decimal("0.8"),
        "乡镇卫生院": Decimal("0.8"),
        "未定级": Decimal("1.0")
    }
    
    # ⚠️ 旧基层病种前缀清单 BASIC_DISEASE_GROUPS 已停用（用户 2026-09-04 裁决）：
    # 基层病种判定一律以《分组方案》基层病种 sheet 名录（引擎）为唯一权威，
    # 旧式序号码（如 K35-1）不再判为基层病种。

    def __init__(self, config: CoefficientCalculationConfig = None):
        """
        初始化选择器

        Args:
            config: 系数计算配置
        """
        self.config = config or CoefficientCalculationConfig()
        self._nat_engine = None   # DIP3.0 国家目录引擎（延迟加载，基层病种权威判定）

    def _get_nat_engine(self):
        """延迟获取 DIP3.0 国家目录引擎（用于基层病种权威判定；缺失则返回 None）。"""
        if self._nat_engine is not None:
            return self._nat_engine
        try:
            import os
            from .national_directory_v30 import get_national_engine
            from ..utils.paths import get_data_dir
        except Exception:
            return None
        try:
            xlsx = os.path.join(str(get_data_dir()), "DIP3.0国家目录库.xlsx")
            if os.path.exists(xlsx):
                self._nat_engine = get_national_engine(xlsx)
        except Exception:
            self._nat_engine = None
        return self._nat_engine

    def is_basic_disease_group(self, dip_code: str) -> bool:
        """检查是否为基层病种（不区分医疗机构调节系数，同病同治同价）。

        DIP3.0 口径（用户 2026-09-04 裁决）：《分组方案》基层病种 sheet 名录为
        唯一权威（诊断+手术对；手术为空=仅保守治疗组）。命中方案序号（如 JC-3625）
        或 DIP 组合码（如 K35-47.0100- / I20-保守治疗-）时按引擎判定；
        旧式序号码（如 K35-1）与引擎不可用时一律不判为基层病种
        （旧前缀清单 BASIC_DISEASE_GROUPS 已停用）。
        """
        if not dip_code:
            return False
        import re as _re
        eng = self._get_nat_engine()
        if eng is None:
            return False
        # 仅当编码呈 DIP3.0 新方案形态（方案序号 / 含「保守治疗」段 / 含 ICD 手术码）
        # 才走引擎权威判定；旧式序号码（如 K35-1）不判为基层病种
        looks_new = bool(
            _re.fullmatch(r"[A-Z]{2}-\d+", dip_code.strip())
            or "保守治疗" in dip_code
            or _re.search(r"\d{2}\.\d{2}", dip_code)
        )
        if not looks_new:
            return False
        try:
            if _re.fullmatch(r"[A-Z]{2}-\d+", dip_code.strip()):
                # 方案序号（XQ/BX/FZ/JC-NN）
                row = eng.by_seq.get(dip_code.strip())
                if row is not None:
                    return eng.is_grassroot(row.get("主要诊断编码", ""),
                                            row.get("主要手术操作编码", ""))
            elif "-" in dip_code:
                # DIP 组合码：主诊断-主手术(-相关手术)；主手术段为「保守治疗」记空
                parts = dip_code.split("-")
                diag = parts[0]
                oprn = "" if len(parts) < 2 or parts[1] in ("保守治疗", "") else parts[1]
                return eng.is_grassroot(diag, oprn)
        except Exception:
            pass
        return False
    
    def calculate_coefficient(
        self,
        hospital_data: Dict,
        city_records: List[MedicalRecord] = None,
        hospital_records: List[MedicalRecord] = None,
        dip_code: str = ""
    ) -> CoefficientCalculationResult:
        """
        计算医院系数
        
        Args:
            hospital_data: 医院数据
            city_records: 全市病例记录
            hospital_records: 该医院病例记录
            
        Returns:
            系数计算结果
        """
        result = CoefficientCalculationResult(
            hospital_code=hospital_data.get('hospital_code', ''),
            hospital_name=hospital_data.get('hospital_name', ''),
            hospital_level=hospital_data.get('hospital_level', ''),
            calculation_method=self.config.calculation_method.value
        )
        
        # 基层病种不区分医疗机构调节系数，实施同病同治同价
        if self.is_basic_disease_group(dip_code):
            result.basic_coefficient = Decimal("1.0")
            result.bonus_coefficient = Decimal("0")
            result.disease_level_coefficient = Decimal("1.0")
            result.final_coefficient = Decimal("1.0")
            return result
        
        # 计算基本系数
        if self.config.enable_basic_coefficient:
            result.basic_coefficient = self._calculate_basic_coefficient(
                hospital_data, city_records
            )
        
        # 计算加成系数
        if self.config.enable_bonus_coefficient:
            result.bonus_coefficient, result.calculation_details = self._calculate_bonus_coefficient(
                hospital_data
            )
            result.medical_level_score = result.calculation_details.get('medical_level', Decimal("0"))
            result.specialty_score = result.calculation_details.get('specialty', Decimal("0"))
            result.cmi_score = result.calculation_details.get('cmi', Decimal("0"))
            result.performance_score = result.calculation_details.get('performance', Decimal("0"))
            result.agreement_score = result.calculation_details.get('agreement', Decimal("0"))
        
        # 计算病种级别系数
        if self.config.enable_disease_level_coefficient and city_records and hospital_records:
            result.disease_level_coefficient = self._calculate_disease_level_coefficient(
                hospital_records, city_records
            )
        
        # 计算最终系数
        result.final_coefficient = self._calculate_final_coefficient(result)
        
        return result
    
    def _calculate_basic_coefficient(
        self,
        hospital_data: Dict,
        city_records: List[MedicalRecord] = None
    ) -> Decimal:
        """
        计算基本系数
        规范公式：基本系数 = 同级别类型医疗机构近三年数据病例加权平均住院费用 / 全市近三年数据病例加权平均住院费用
        """
        hospital_level = hospital_data.get('hospital_level', '')
        
        # 如果有全市数据，使用费用比例法
        if city_records:
            # 计算全市平均费用
            city_avg_cost = self._calculate_city_average_cost(city_records)
            
            # 计算该医院平均费用
            hospital_avg_cost = Decimal(str(hospital_data.get('avg_cost', 0)))
            
            if city_avg_cost > 0 and hospital_avg_cost > 0:
                # 基本系数 = 同级别医院平均费用 / 全市平均费用
                base_coefficient = hospital_avg_cost / city_avg_cost
                # 限制调整范围在0.7-1.5之间
                base_coefficient = max(Decimal("0.7"), min(Decimal("1.5"), base_coefficient))
                return base_coefficient.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        
        # 如果没有数据，使用等级基础系数作为备选
        return self.HOSPITAL_LEVEL_COEFFICIENTS.get(
            hospital_level, Decimal("1.0")
        ).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    
    def _calculate_bonus_coefficient(self, hospital_data: Dict) -> Tuple[Decimal, Dict]:
        """计算加成系数"""
        details = {}
        
        # 医疗水平得分
        medical_level_score = Decimal(str(hospital_data.get('medical_level', 0)))
        details['medical_level'] = medical_level_score
        
        # 专科特色得分
        specialty_score = Decimal(str(hospital_data.get('specialty_score', 0)))
        details['specialty'] = specialty_score
        
        # CMI得分
        cmi_score = Decimal(str(hospital_data.get('cmi', 0)))
        details['cmi'] = cmi_score
        
        # 绩效考核得分
        performance_score = Decimal(str(hospital_data.get('performance_score', 0)))
        details['performance'] = performance_score
        
        # 协议履行得分
        agreement_score = Decimal(str(hospital_data.get('agreement_score', 0)))
        details['agreement'] = agreement_score
        
        # 计算加成系数
        bonus_coefficient = (
            medical_level_score * self.config.medical_level_weight +
            specialty_score * self.config.specialty_weight +
            cmi_score * self.config.cmi_weight +
            performance_score * self.config.performance_weight +
            agreement_score * self.config.agreement_weight
        )
        
        return bonus_coefficient.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP), details
    
    def _calculate_disease_level_coefficient(
        self,
        hospital_records: List[MedicalRecord],
        city_records: List[MedicalRecord]
    ) -> Decimal:
        """计算病种级别系数"""
        if not hospital_records or not city_records:
            return Decimal("1.0")
        
        # 计算医院平均费用
        hospital_total = sum(r.total_cost for r in hospital_records)
        hospital_avg = hospital_total / len(hospital_records) if hospital_records else Decimal("0")
        
        # 计算全市平均费用
        city_total = sum(r.total_cost for r in city_records)
        city_avg = city_total / len(city_records) if city_records else Decimal("0")
        
        if city_avg <= 0:
            return Decimal("1.0")
        
        # 计算系数
        coefficient = hospital_avg / city_avg
        
        # 限制范围在0.7-1.5之间
        coefficient = max(Decimal("0.7"), min(Decimal("1.5"), coefficient))
        
        return coefficient.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    
    def _calculate_final_coefficient(self, result: CoefficientCalculationResult) -> Decimal:
        """计算最终系数"""
        method = self.config.calculation_method
        
        if method == CoefficientCalculationMethod.BASIC_ONLY:
            return result.basic_coefficient * self.config.basic_coefficient_weight
        
        elif method == CoefficientCalculationMethod.BONUS_ONLY:
            return result.bonus_coefficient * self.config.bonus_coefficient_weight
        
        elif method == CoefficientCalculationMethod.BASIC_AND_BONUS:
            return (
                result.basic_coefficient * self.config.basic_coefficient_weight +
                result.bonus_coefficient * self.config.bonus_coefficient_weight
            )
        
        elif method == CoefficientCalculationMethod.DISEASE_SPECIFIC:
            return result.disease_level_coefficient * self.config.disease_level_weight
        
        elif method == CoefficientCalculationMethod.COMPREHENSIVE:
            weights = self.config.comprehensive_weights
            return (
                result.basic_coefficient * weights.get("基本系数", Decimal("0.4")) +
                result.bonus_coefficient * weights.get("加成系数", Decimal("0.3")) +
                result.disease_level_coefficient * weights.get("病种级别系数", Decimal("0.3"))
            )
        
        return result.basic_coefficient
    
    def _calculate_city_average_cost(self, records: List[MedicalRecord]) -> Decimal:
        """计算全市平均费用"""
        if not records:
            return Decimal("0")
        
        total_cost = sum(r.total_cost for r in records)
        return (total_cost / len(records)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    
    def batch_calculate(
        self,
        hospital_data_list: List[Dict],
        city_records: List[MedicalRecord] = None
    ) -> List[CoefficientCalculationResult]:
        """
        批量计算医院系数
        
        Args:
            hospital_data_list: 医院数据列表
            city_records: 全市病例记录
            
        Returns:
            系数计算结果列表
        """
        results = []
        
        for hospital_data in hospital_data_list:
            # 获取该医院的病例记录
            hospital_code = hospital_data.get('hospital_code', '')
            hospital_records = [
                r for r in (city_records or [])
                if r.hospital_code == hospital_code
            ]
            
            result = self.calculate_coefficient(
                hospital_data, city_records, hospital_records
            )
            results.append(result)
        
        return results
    
    def export_coefficients(
        self,
        results: List[CoefficientCalculationResult],
        output_path: str
    ) -> str:
        """
        导出系数计算结果
        
        Args:
            results: 系数计算结果列表
            output_path: 输出文件路径
            
        Returns:
            输出文件路径
        """
        data = []
        for i, result in enumerate(results, 1):
            data.append({
                '序号': i,
                '医院代码': result.hospital_code,
                '医院名称': result.hospital_name,
                '医院等级': result.hospital_level,
                '计算方法': result.calculation_method,
                '基本系数': float(result.basic_coefficient),
                '加成系数': float(result.bonus_coefficient),
                '病种级别系数': float(result.disease_level_coefficient),
                '医疗水平得分': float(result.medical_level_score),
                '专科特色得分': float(result.specialty_score),
                'CMI得分': float(result.cmi_score),
                '绩效考核得分': float(result.performance_score),
                '协议履行得分': float(result.agreement_score),
                '最终系数': float(result.final_coefficient)
            })
        
        df = pd.DataFrame(data)
        df.to_excel(output_path, index=False, engine='openpyxl')
        return output_path


# 预定义配置
def create_basic_only_config() -> CoefficientCalculationConfig:
    """创建仅基本系数配置"""
    return CoefficientCalculationConfig(
        calculation_method=CoefficientCalculationMethod.BASIC_ONLY,
        enable_basic_coefficient=True,
        enable_bonus_coefficient=False,
        enable_disease_level_coefficient=False
    )


def create_bonus_only_config() -> CoefficientCalculationConfig:
    """创建仅加成系数配置"""
    return CoefficientCalculationConfig(
        calculation_method=CoefficientCalculationMethod.BONUS_ONLY,
        enable_basic_coefficient=False,
        enable_bonus_coefficient=True,
        enable_disease_level_coefficient=False
    )


def create_basic_bonus_config() -> CoefficientCalculationConfig:
    """创建基本+加成系数配置"""
    return CoefficientCalculationConfig(
        calculation_method=CoefficientCalculationMethod.BASIC_AND_BONUS,
        enable_basic_coefficient=True,
        enable_bonus_coefficient=True,
        enable_disease_level_coefficient=False
    )


def create_disease_level_config() -> CoefficientCalculationConfig:
    """创建病种级别系数配置"""
    return CoefficientCalculationConfig(
        calculation_method=CoefficientCalculationMethod.DISEASE_SPECIFIC,
        enable_basic_coefficient=False,
        enable_bonus_coefficient=False,
        enable_disease_level_coefficient=True
    )


def create_comprehensive_config() -> CoefficientCalculationConfig:
    """创建综合系数配置"""
    return CoefficientCalculationConfig(
        calculation_method=CoefficientCalculationMethod.COMPREHENSIVE,
        enable_basic_coefficient=True,
        enable_bonus_coefficient=True,
        enable_disease_level_coefficient=True,
        comprehensive_weights={
            "基本系数": Decimal("0.4"),
            "加成系数": Decimal("0.3"),
            "病种级别系数": Decimal("0.3")
        }
    )
