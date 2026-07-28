"""
DIP按病种分值分组测算工具 - 基层病种范围模块
基于《国家医疗保障按病种分值(DIP)付费3.0版技术规范》
功能：基层医疗机构病种范围配置和管理
"""
import pandas as pd
from typing import List, Dict, Optional, Set
from decimal import Decimal, ROUND_HALF_UP
from dataclasses import dataclass, field
from enum import Enum

from ..models.models import MedicalRecord, DiseaseGroup


class HospitalLevel(Enum):
    """医院等级"""
    LEVEL_3A = "三级甲等"
    LEVEL_3B = "三级乙等"
    LEVEL_3C = "三级丙等"
    LEVEL_2A = "二级甲等"
    LEVEL_2B = "二级乙等"
    LEVEL_2C = "二级丙等"
    LEVEL_1 = "一级"
    COMMUNITY = "社区卫生服务中心"
    TOWNSHIP = "乡镇卫生院"


@dataclass
class BasicDiseaseGroup:
    """基层病种"""
    dip_code: str  # DIP编码
    disease_name: str  # 病种名称
    applicable_levels: List[str] = field(default_factory=list)  # 适用医院等级
    max_cost: Decimal = Decimal("0")  # 最高费用限额
    min_cases: int = 15  # 最小病例数
    is_basic_group: bool = True  # 是否为基层病种组
    description: str = ""  # 说明


@dataclass
class BasicGroupConfig:
    """基层病种范围配置"""
    enable_basic_group: bool = True  # 启用基层病种范围
    hospital_levels: List[str] = field(default_factory=lambda: ["一级", "社区卫生服务中心", "乡镇卫生院"])
    max_cost_ratio: Decimal = Decimal("0.6")  # 基层病种最高费用比例（相对于全市平均）
    min_cases_threshold: int = 15  # 最小病例数阈值
    include_diagnosis: List[str] = field(default_factory=list)  # 包含的诊断类型
    exclude_diagnosis: List[str] = field(default_factory=list)  # 排除的诊断类型


@dataclass
class BasicGroupResult:
    """基层病种范围结果"""
    total_dip_codes: int
    basic_group_count: int
    basic_groups: List[BasicDiseaseGroup] = field(default_factory=list)
    excluded_groups: List[str] = field(default_factory=list)
    processing_log: List[str] = field(default_factory=list)


class BasicDiseaseGroupManager:
    """基层病种范围管理器"""
    
    def __init__(self, config: BasicGroupConfig = None):
        """
        初始化管理器
        
        Args:
            config: 基层病种范围配置
        """
        self.config = config or BasicGroupConfig()
        self.basic_groups = {}
    
    def load_basic_groups(self, groups: List[BasicDiseaseGroup]):
        """加载基层病种"""
        for group in groups:
            self.basic_groups[group.dip_code] = group
    
    def add_basic_group(self, group: BasicDiseaseGroup):
        """添加基层病种"""
        self.basic_groups[group.dip_code] = group
    
    def remove_basic_group(self, dip_code: str):
        """移除基层病种"""
        if dip_code in self.basic_groups:
            del self.basic_groups[dip_code]
    
    def determine_basic_groups(
        self,
        disease_groups: List[DiseaseGroup],
        city_records: List[MedicalRecord]
    ) -> BasicGroupResult:
        """
        确定基层病种范围
        
        Args:
            disease_groups: 病种分组列表
            city_records: 全市病例记录
            
        Returns:
            基层病种范围结果
        """
        if not self.config.enable_basic_group:
            return BasicGroupResult(
                total_dip_codes=len(disease_groups),
                basic_group_count=0,
                processing_log=["未启用基层病种范围"]
            )
        
        # 计算全市平均费用
        city_avg_cost = self._calculate_city_average_cost(city_records)
        
        # 确定基层病种
        basic_groups = []
        excluded_groups = []
        
        for group in disease_groups:
            # 检查是否满足基层病种条件
            if self._is_basic_group(group, city_records, city_avg_cost):
                basic_group = BasicDiseaseGroup(
                    dip_code=group.disease_code,
                    disease_name=group.disease_name,
                    applicable_levels=self.config.hospital_levels,
                    max_cost=city_avg_cost * self.config.max_cost_ratio,
                    min_cases=self.config.min_cases_threshold,
                    is_basic_group=True,
                    description=f"基层病种，费用限额: {city_avg_cost * self.config.max_cost_ratio}"
                )
                basic_groups.append(basic_group)
            else:
                excluded_groups.append(group.disease_code)
        
        return BasicGroupResult(
            total_dip_codes=len(disease_groups),
            basic_group_count=len(basic_groups),
            basic_groups=basic_groups,
            excluded_groups=excluded_groups,
            processing_log=[
                f"全市平均费用: {city_avg_cost}",
                f"基层病种费用限额: {city_avg_cost * self.config.max_cost_ratio}",
                f"确定{len(basic_groups)}个基层病种"
            ]
        )
    
    def _is_basic_group(
        self,
        group: DiseaseGroup,
        city_records: List[MedicalRecord],
        city_avg_cost: Decimal
    ) -> bool:
        """判断是否为基层病种"""
        # 获取该DIP的病例
        dip_records = [r for r in city_records if r.dip_disease_code == group.disease_code]
        
        # 检查病例数
        if len(dip_records) < self.config.min_cases_threshold:
            return False
        
        # 计算该DIP的平均费用
        if not dip_records:
            return False
        
        avg_cost = sum(r.total_cost for r in dip_records) / len(dip_records)
        
        # 检查费用是否在基层范围内
        max_cost = city_avg_cost * self.config.max_cost_ratio
        if avg_cost > max_cost:
            return False
        
        # 检查医院等级分布
        level_counts = {}
        for record in dip_records:
            level = record.hospital_level
            level_counts[level] = level_counts.get(level, 0) + 1
        
        # 如果大部分病例来自基层医院，则为基层病种
        total = len(dip_records)
        basic_count = sum(
            count for level, count in level_counts.items()
            if level in self.config.hospital_levels
        )
        
        # 如果基层医院病例占比超过50%，则为基层病种
        if basic_count / total >= 0.5:
            return True
        
        return False
    
    def _calculate_city_average_cost(self, records: List[MedicalRecord]) -> Decimal:
        """计算全市平均费用"""
        if not records:
            return Decimal("0")
        
        total_cost = sum(r.total_cost for r in records)
        return (total_cost / len(records)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    
    def filter_records_by_basic_group(
        self,
        records: List[MedicalRecord],
        hospital_level: str
    ) -> List[MedicalRecord]:
        """
        根据基层病种范围过滤病例
        
        Args:
            records: 病例记录列表
            hospital_level: 医院等级
            
        Returns:
            过滤后的病例列表
        """
        if not self.config.enable_basic_group:
            return records
        
        # 如果不是基层医院，不过滤
        if hospital_level not in self.config.hospital_levels:
            return records
        
        # 过滤基层病种
        filtered = []
        for record in records:
            dip_code = record.dip_disease_code
            if dip_code in self.basic_groups:
                filtered.append(record)
        
        return filtered
    
    def get_basic_group_list(self) -> List[Dict]:
        """获取基层病种列表"""
        result = []
        for dip_code, group in self.basic_groups.items():
            result.append({
                'dip_code': group.dip_code,
                'disease_name': group.disease_name,
                'applicable_levels': group.applicable_levels,
                'max_cost': float(group.max_cost),
                'min_cases': group.min_cases
            })
        return result
    
    def export_basic_groups(self, output_path: str) -> str:
        """导出基层病种到Excel"""
        data = []
        for i, (dip_code, group) in enumerate(sorted(self.basic_groups.items()), 1):
            data.append({
                '序号': i,
                'DIP编码': group.dip_code,
                '病种名称': group.disease_name,
                '适用医院等级': ','.join(group.applicable_levels),
                '最高费用限额': float(group.max_cost),
                '最小病例数': group.min_cases,
                '说明': group.description
            })
        
        df = pd.DataFrame(data)
        df.to_excel(output_path, index=False, engine='openpyxl')
        return output_path


def create_default_basic_group_config() -> BasicGroupConfig:
    """创建默认基层病种范围配置"""
    return BasicGroupConfig(
        enable_basic_group=True,
        hospital_levels=["一级", "社区卫生服务中心", "乡镇卫生院"],
        max_cost_ratio=Decimal("0.6"),
        min_cases_threshold=15
    )


def create_strict_basic_group_config() -> BasicGroupConfig:
    """创建严格基层病种范围配置"""
    return BasicGroupConfig(
        enable_basic_group=True,
        hospital_levels=["一级", "社区卫生服务中心", "乡镇卫生院"],
        max_cost_ratio=Decimal("0.5"),
        min_cases_threshold=20
    )


def create_loose_basic_group_config() -> BasicGroupConfig:
    """创建宽松基层病种范围配置"""
    return BasicGroupConfig(
        enable_basic_group=True,
        hospital_levels=["一级", "二级丙等", "社区卫生服务中心", "乡镇卫生院"],
        max_cost_ratio=Decimal("0.7"),
        min_cases_threshold=10
    )
