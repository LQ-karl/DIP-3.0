"""
DIP按病种分值分组测算工具 - 病种分组引擎

基于《国家医疗保障按病种分值(DIP)付费3.0版技术规范》第三章

核心原则:
1. 病种单元的适宜性：组内资源消耗差异小、组间资源消耗差异大
2. 核心病种成组：覆盖病例数达到95%或达到固定临界值（可人工调整）
3. 综合病种：依据治疗方式属性聚类成组，控制数量，CV低于阈值
4. 手术/介入操作自动入组手术组
"""
import pandas as pd
import numpy as np
from typing import List, Dict, Tuple, Optional
from decimal import Decimal
import re

from ..models.models import DiseaseGroup, GroupType, MedicalRecord
from .disease_group_suitability import (
    DiseaseGroupingOptimizer, GroupingConfig, GroupingStatistics,
    create_default_optimizer
)


class DIPGroupingEngine:
    """
    DIP病种分组引擎
    
    依据: DIP3.0版技术规范（征求意见稿）第三章
    - 病种分组原理
    - 成组规程
    - 病种单元的适宜性评估
    """
    
    def __init__(self, threshold: int = None, config: GroupingConfig = None):
        """
        初始化分组引擎
        
        Args:
            threshold: 核心病种临界值（可选，优先使用config）
            config: 分组配置（推荐使用）
        """
        # 分组配置
        if config:
            self.config = config
        else:
            self.config = GroupingConfig(
                target_coverage=0.95,  # 目标覆盖率95%
                min_core_threshold=10,  # 最小临界值
                max_core_threshold=50,  # 最大临界值
                default_threshold=threshold or 15,  # 默认临界值
                max_mixed_groups=100,  # 最大综合病种数量
                cv_threshold=1.0,  # CV阈值100%
                min_mixed_cases=5  # 综合病种最小病例数
            )
        
        # 使用病种适宜性评估优化器
        self.optimizer = DiseaseGroupingOptimizer(self.config)
        
        self.advanced_groups = []  # 先期分组
        self.core_groups = []  # 核心病种
        self.mixed_groups = []  # 综合病种
        self.exclusion_list = []  # 排除列表
        
        # 统计信息
        self.statistics = None

    def set_threshold(self, threshold: int):
        """
        设置核心病种临界值（核心病种/综合病种划分阈值）

        注意：引擎实际读取 self.config.default_threshold，必须在此统一设置，
        直接写 self.threshold 是无效属性（历史 Bug）。

        Args:
            threshold: 核心病种临界值（病例数阈值）
        """
        self.config.default_threshold = int(threshold)

    def load_disease_directory(self, file_path: str) -> pd.DataFrame:
        """
        加载DIP病种目录
        
        Args:
            file_path: 目录文件路径
            
        Returns:
            病种目录DataFrame
        """
        if file_path.endswith('.xlsx') or file_path.endswith('.xls'):
            return pd.read_excel(file_path)
        elif file_path.endswith('.csv'):
            return pd.read_csv(file_path, encoding='utf-8')
        else:
            raise ValueError(f"不支持的文件格式: {file_path}")
    
    def set_exclusion_list(self, exclusion_codes: List[str]):
        """
        设置排除列表
        
        Args:
            exclusion_codes: 不能作为主诊断的ICD-10编码列表
        """
        self.exclusion_list = exclusion_codes
    
    def classify_advanced_group(self, record: MedicalRecord) -> Optional[str]:
        """
        先期分组分类
        根据3.0规范表3-4：先期分组示例
        
        Args:
            record: 住院病例记录
            
        Returns:
            先期分组代码，如果不属于先期分组则返回None
        """
        # AA1: 心肺移植
        if record.main_oprn_code in ['33.6x00']:
            return "AA1"
        
        # AA2: 心脏移植
        if record.main_oprn_code in ['37.5100', '37.5100x001']:
            return "AA2"
        
        # AI1-AI5: 低出生体重儿系列
        if record.main_diag_code.startswith('P07'):
            # 根据出生体重和天龄判断
            if hasattr(record, 'birth_weight') and hasattr(record, 'day_age'):
                if record.day_age < 29:
                    if record.birth_weight < 750:
                        return "AI1"
                    elif 750 <= record.birth_weight < 1000:
                        return "AI2"
                    elif 1000 <= record.birth_weight < 1500:
                        return "AI3"
                    elif 1500 <= record.birth_weight < 2000:
                        return "AI4"
                    elif 2000 <= record.birth_weight < 2500:
                        return "AI5"
        
        return None
    
    def is_excluded(self, record: MedicalRecord) -> bool:
        """
        检查病例是否在排除列表中
        
        Args:
            record: 住院病例记录
            
        Returns:
            是否排除
        """
        return record.main_diag_code in self.exclusion_list
    
    def extract_icd4(self, icd_code: str) -> str:
        """
        提取ICD编码的4位码
        
        Args:
            icd_code: ICD编码
            
        Returns:
            4位ICD编码
        """
        if not icd_code:
            return ""
        # 去除扩展码部分
        code = icd_code.split('x')[0] if 'x' in icd_code else icd_code
        return code[:4] if len(code) >= 4 else code
    
    def is_surgery_or_intervention(self, proc_code: str) -> bool:
        """
        判断是否为手术或介入操作
        
        依据ICD-9-CM-3编码:
        - 01-17: 手术操作
        - 39-41: 血管手术
        - 45-54: 介入操作
        - 84-86: 其他手术
        
        Args:
            proc_code: 手术操作编码
            
        Returns:
            是否为手术或介入操作
        """
        if not proc_code:
            return False
        
        try:
            proc_num = int(proc_code[:2]) if proc_code[:2].isdigit() else 0
        except:
            return False
        
        # 手术/介入操作判定
        if (1 <= proc_num <= 17 or 
            39 <= proc_num <= 41 or 
            45 <= proc_num <= 54 or 
            84 <= proc_num <= 86):
            return True
        
        return False
    
    def has_related_operation(self, record: MedicalRecord, cost_threshold: float = 0.1) -> bool:
        """
        检查是否存在资源消耗较大的相关手术操作（≥10%）
        
        Args:
            record: 住院病例记录
            cost_threshold: 费用占比阈值，默认10%
            
        Returns:
            是否存在相关操作
        """
        if not record.related_oprn_code:
            return False
        
        # 简化处理：如果有相关手术操作代码且存在，认为有相关操作
        # 实际应用中需要根据费用明细计算
        return True
    
    def group_single_record(self, record: MedicalRecord) -> DiseaseGroup:
        """
        对单个病例进行分组
        
        依据DIP3.0规范分组顺序:
        1. 排除列表对照
        2. 先期分组
        3. 并项规则下的核心病种
        4. 基本规则下的核心病种
        
        Args:
            record: 住院病例记录
            
        Returns:
            病种组合
        """
        # 1. 排除列表检查
        if self.is_excluded(record):
            return DiseaseGroup(
                disease_code="EXCLUDED",
                disease_name="排除病种",
                main_diag_code=record.main_diag_code,
                main_diag_name=record.main_diag_name,
                group_type=GroupType.CORE
            )
        
        # 2. 先期分组检查
        advanced_group = self.classify_advanced_group(record)
        if advanced_group:
            return DiseaseGroup(
                disease_code=advanced_group,
                disease_name=f"先期分组-{advanced_group}",
                main_diag_code=record.main_diag_code,
                main_diag_name=record.main_diag_name,
                main_oprn_code=record.main_oprn_code,
                main_oprn_name=record.main_oprn_name,
                group_type=GroupType.ADVANCED
            )
        
        # 3. 基本规则分组（手术/介入操作自动入组手术组）
        return self._basic_grouping(record)
    
    def _basic_grouping(self, record: MedicalRecord) -> DiseaseGroup:
        """
        基本规则分组
        
        依据DIP3.0规范:
        - 内科诊疗病种：主要诊断（无手术操作）
        - 手术操作病种：主要诊断 + 主要手术操作
        - 手术/介入操作自动入组手术组
        
        Args:
            record: 住院病例记录
            
        Returns:
            病种组合
        """
        main_diag_code = record.main_diag_code
        
        # 没有手术操作 - 内科诊疗病种（格式：I21.0-00）
        if not record.main_oprn_code:
            return DiseaseGroup(
                disease_code=f"{main_diag_code}-00",
                disease_name=record.main_diag_name,
                main_diag_code=record.main_diag_code,
                main_diag_name=record.main_diag_name,
                group_type=GroupType.CORE
            )
        
        # 有手术操作 - 手术操作病种
        # 手术/介入操作自动入组手术组
        if self.is_surgery_or_intervention(record.main_oprn_code):
            # 查找DIP3.0目录库中的匹配编码
            dip_code = self._find_dip_code_with_procedure(main_diag_code, record.main_oprn_code)
            
            if dip_code:
                return DiseaseGroup(
                    disease_code=dip_code,
                    disease_name=f"{record.main_diag_name}-{record.main_oprn_name}",
                    main_diag_code=record.main_diag_code,
                    main_diag_name=record.main_diag_name,
                    main_oprn_code=record.main_oprn_code,
                    main_oprn_name=record.main_oprn_name,
                    group_type=GroupType.CORE
                )
            else:
                # 使用通用格式
                proc_suffix = self._get_procedure_suffix(record.main_oprn_code)
                return DiseaseGroup(
                    disease_code=f"{main_diag_code}-{proc_suffix}",
                    disease_name=f"{record.main_diag_name}-{record.main_oprn_name}",
                    main_diag_code=record.main_diag_code,
                    main_diag_name=record.main_diag_name,
                    main_oprn_code=record.main_oprn_code,
                    main_oprn_name=record.main_oprn_name,
                    group_type=GroupType.CORE
                )
        else:
            # 非手术/介入操作，归入内科病种（附带操作）
            return DiseaseGroup(
                disease_code=f"{main_diag_code}-00",
                disease_name=record.main_diag_name,
                main_diag_code=record.main_diag_code,
                main_diag_name=record.main_diag_name,
                group_type=GroupType.CORE
            )
    
    def _get_procedure_suffix(self, proc_code: str) -> str:
        """
        根据手术编码生成后缀
        
        Args:
            proc_code: 手术编码
            
        Returns:
            后缀代码
        """
        if not proc_code:
            return "00"
        
        try:
            proc_num = int(proc_code[:2]) if proc_code[:2].isdigit() else 0
        except:
            proc_num = 0
        
        # 手术操作
        if 1 <= proc_num <= 17:
            return "01"
        # 血管手术
        elif 39 <= proc_num <= 41:
            return "02"
        # 介入操作
        elif 45 <= proc_num <= 54:
            return "03"
        # 其他手术
        elif 84 <= proc_num <= 86:
            return "04"
        else:
            return "01"
    
    def _find_dip_code_with_procedure(self, diag_code: str, proc_code: str) -> str:
        """
        从DIP3.0目录库中查找匹配的DIP编码
        
        Args:
            diag_code: 诊断编码
            proc_code: 手术编码
            
        Returns:
            匹配的DIP编码，如果没有找到则返回None
        """
        try:
            import pandas as pd
            dip_dir = pd.read_excel("F:/DIP/data/DIP3.0国家目录库.xlsx")
            
            # 查找该诊断编码的所有DIP条目
            matching_entries = dip_dir[dip_dir['主要诊断编码'] == diag_code]
            
            for _, row in matching_entries.iterrows():
                dip_proc_code = str(row.get('主要手术操作编码', '')) if pd.notna(row.get('主要手术操作编码')) else ''
                # 检查手术编码是否包含在DIP目录的手术编码中（可能有多个用|分隔）
                if dip_proc_code and proc_code in dip_proc_code:
                    return str(row.get('DIP编码', ''))
            
            # 如果没有精确匹配，返回None
            return None
        except Exception:
            return None
    
    def group_records(self, records: List[MedicalRecord], 
                     optimize: bool = True) -> Dict[str, DiseaseGroup]:
        """
        批量分组并统计
        
        依据DIP3.0规范:
        1. 初始分组
        2. 区分核心病种和综合病种
        3. 优化分组（可选）
        
        Args:
            records: 住院病例记录列表
            optimize: 是否进行分组优化
            
        Returns:
            病种分组结果字典
        """
        if optimize:
            return self._group_records_optimized(records)
        else:
            return self._group_records_basic(records)
    
    def _group_records_basic(self, records: List[MedicalRecord]) -> Dict[str, DiseaseGroup]:
        """
        基本分组（不优化）
        
        Args:
            records: 住院病例记录列表
            
        Returns:
            病种分组结果字典
        """
        # 临时存储分组统计
        temp_groups = {}
        
        for record in records:
            group = self.group_single_record(record)
            key = group.disease_code
            
            if key in temp_groups:
                temp_groups[key].case_count += 1
                temp_groups[key].avg_cost += record.total_cost
            else:
                group.case_count = 1
                group.avg_cost = record.total_cost
                temp_groups[key] = group
        
        # 计算平均费用
        for key, group in temp_groups.items():
            if group.case_count > 0:
                group.avg_cost = group.avg_cost / group.case_count
        
        # 区分核心病种和综合病种
        self.core_groups = []
        self.mixed_groups = []
        
        for key, group in temp_groups.items():
            if group.case_count >= self.config.default_threshold:
                group.group_type = GroupType.CORE
                self.core_groups.append(group)
            else:
                group.group_type = GroupType.MIXED
                self.mixed_groups.append(group)
        
        # 构建返回结果
        result = {}
        for group in self.core_groups:
            result[group.disease_code] = group
        for group in self.mixed_groups:
            result[group.disease_code] = group
            
        return result
    
    def _group_records_optimized(self, records: List[MedicalRecord]) -> Dict[str, DiseaseGroup]:
        """
        优化分组
        
        依据DIP3.0规范:
        1. 目标覆盖率95%
        2. 可调临界值
        3. CV阈值控制
        4. 综合病种数量控制
        
        Args:
            records: 住院病例记录列表
            
        Returns:
            病种分组结果字典
        """
        # 使用优化器进行分组
        core_groups, mixed_groups, statistics = self.optimizer.optimize_grouping(records)
        
        self.core_groups = core_groups
        self.mixed_groups = mixed_groups
        self.statistics = statistics
        
        # 构建返回结果
        result = {}
        for group in core_groups:
            result[group.disease_code] = group
        for group in mixed_groups:
            result[group.disease_code] = group
            
        return result
    
    def merge_similar_mixed_groups(self, mixed_groups: List[DiseaseGroup]) -> List[DiseaseGroup]:
        """
        合并相似的综合病种
        
        根据3.0规范：将病例数在临界值以下的病种进行收敛
        依据治疗方式的具体属性聚类成组
        
        Args:
            mixed_groups: 综合病种列表
            
        Returns:
            合并后的综合病种列表
        """
        if not mixed_groups:
            return []
        
        # 按主要诊断4位码分组
        diag_groups = {}
        for group in mixed_groups:
            diag_4 = self.extract_icd4(group.main_diag_code)
            if diag_4 not in diag_groups:
                diag_groups[diag_4] = []
            diag_groups[diag_4].append(group)
        
        merged_groups = []
        for diag_4, groups in diag_groups.items():
            # 合并同诊断下的所有病种
            total_count = sum(g.case_count for g in groups)
            total_cost = sum(g.avg_cost * g.case_count for g in groups)
            avg_cost = total_cost / total_count if total_count > 0 else Decimal("0")
            
            merged_group = DiseaseGroup(
                disease_code=f"MIX_{diag_4}",
                disease_name=f"综合病种-{groups[0].main_diag_name}",
                main_diag_code=groups[0].main_diag_code,
                main_diag_name=groups[0].main_diag_name,
                group_type=GroupType.MIXED,
                case_count=total_count,
                avg_cost=avg_cost
            )
            merged_groups.append(merged_group)
        
        return merged_groups
    
    def get_grouping_statistics(self) -> Dict:
        """
        获取分组统计信息
        
        Returns:
            统计信息字典
        """
        if self.statistics:
            return {
                "core_group_count": self.statistics.core_group_count,
                "mixed_group_count": self.statistics.mixed_group_count,
                "advanced_group_count": len(self.advanced_groups),
                "total_core_cases": self.statistics.core_cases,
                "total_mixed_cases": self.statistics.mixed_cases,
                "coverage_rate": f"{self.statistics.coverage_rate:.2%}",
                "threshold_used": self.statistics.threshold_used,
                "overall_cv": f"{self.statistics.overall_cv:.4f}",
                "fisher_index": f"{self.statistics.fisher_index:.4f}"
            }
        
        return {
            "core_group_count": len(self.core_groups),
            "mixed_group_count": len(self.mixed_groups),
            "advanced_group_count": len(self.advanced_groups),
            "total_core_cases": sum(g.case_count for g in self.core_groups),
            "total_mixed_cases": sum(g.case_count for g in self.mixed_groups),
            "threshold": self.config.default_threshold
        }
    
    def get_suitability_report(self) -> Dict:
        """
        获取病种适宜性评估报告
        
        Returns:
            评估报告
        """
        return self.optimizer.get_suitability_report()


class DiagnosisClassifier:
    """疾病诊断分类器"""
    
    # 主要诊断排除列表（根据3.0规范）
    EXCLUSION_DIAGNOSIS_CODES = [
        # Z编码（影响健康状态的因素）
        "Z00", "Z01", "Z02", "Z03", "Z04", "Z05", "Z06", "Z07", "Z08", "Z09",
        # 特殊情况编码
        "R00", "R01", "R02", "R03", "R04", "R05", "R06", "R07", "R08", "R09",
    ]
    
    # 肿瘤相关诊断代码范围
    TUMOR_DIAGNOSIS_RANGES = [
        ("C00", "C97"),  # 恶性肿瘤
        ("D00", "D09"),  # 原位癌
        ("D10", "D36"),  # 良性肿瘤
        ("D37", "D48"),  # 动态未定肿瘤
    ]
    
    # 结核相关诊断代码
    TUBERCULOSIS_CODES = ["A15", "A16", "A17", "A18", "A19"]
    
    @classmethod
    def is_tumor_diagnosis(cls, diag_code: str) -> bool:
        """检查是否为肿瘤诊断"""
        code_prefix = diag_code[:3]
        for start, end in cls.TUMOR_DIAGNOSIS_RANGES:
            if start <= code_prefix <= end:
                return True
        return False
    
    @classmethod
    def is_tuberculosis(cls, diag_code: str) -> bool:
        """检查是否为结核诊断"""
        return diag_code[:3] in cls.TUBERCULOSIS_CODES
    
    @classmethod
    def get_tumor_type(cls, diag_code: str, related_diag_code: str) -> str:
        """
        获取肿瘤类型（用于辅助分型）
        
        Returns:
            肿瘤类型：实体瘤、血液病、淋巴瘤
        """
        if related_diag_code:
            code_prefix = related_diag_code[:3]
            if "C91" <= code_prefix <= "C95":
                return "血液病"
            elif "C81" <= code_prefix <= "C96":
                return "淋巴瘤"
        return "实体瘤"
