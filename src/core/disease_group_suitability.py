"""
DIP按病种分值分组测算工具 - 病种适宜性评估模块

依据: DIP3.0版技术规范（征求意见稿）第三章
- 病种单元的适宜性：组内资源消耗差异小、组间资源消耗差异大
- 核心病种成组：覆盖病例数达到95%或达到固定临界值（可人工调整）
- 综合病种：依据治疗方式属性聚类成组，控制数量，CV低于阈值
"""
import pandas as pd
import numpy as np
from typing import List, Dict, Tuple, Optional
from decimal import Decimal
from dataclasses import dataclass

from ..models.models import DiseaseGroup, GroupType, MedicalRecord


@dataclass
class GroupingConfig:
    """分组配置"""
    # 核心病种参数
    target_coverage: float = 0.95  # 目标覆盖率（95%）
    min_core_threshold: int = 10  # 最小核心病种临界值
    max_core_threshold: int = 50  # 最大核心病种临界值
    default_threshold: int = 15  # 默认临界值
    
    # 综合病种参数
    max_mixed_groups: int = 100  # 最大综合病种数量
    cv_threshold: float = 1.0  # 组内变异系数(CV)阈值（默认100%）
    min_mixed_cases: int = 5  # 综合病种最小病例数
    
    # 适宜性参数
    min_fisher_index: float = 1.0  # 最小Fisher指数
    target_between_group_variance: float = 0.5  # 目标组间方差占比


@dataclass
class GroupingStatistics:
    """分组统计信息"""
    total_cases: int  # 总病例数
    core_cases: int  # 核心病种病例数
    mixed_cases: int  # 综合病种病例数
    excluded_cases: int  # 排除病例数
    advanced_cases: int  # 先期分组病例数
    
    core_group_count: int  # 核心病种组数
    mixed_group_count: int  # 综合病种组数
    
    coverage_rate: float  # 核心病种覆盖率
    threshold_used: int  # 使用的临界值
    cv_values: List[float]  # 各组CV值
    
    overall_cv: float  # 总体CV
    between_group_variance: float  # 组间方差
    within_group_variance: float  # 组内方差
    fisher_index: float  # Fisher指数


class DiseaseGroupingOptimizer:
    """病种分组优化器"""
    
    def __init__(self, config: Optional[GroupingConfig] = None):
        """
        初始化分组优化器
        
        Args:
            config: 分组配置
        """
        self.config = config or GroupingConfig()
        self.statistics = None
        
    def calculate_cv(self, costs: List[float]) -> float:
        """
        计算变异系数(CV)
        
        CV = 标准差 / 均值
        
        Args:
            costs: 费用列表
            
        Returns:
            变异系数
        """
        if not costs or len(costs) < 2:
            return 0.0
        
        costs_array = np.array(costs, dtype=float)
        mean_cost = np.mean(costs_array)
        
        if mean_cost == 0:
            return 0.0
        
        std_cost = np.std(costs_array, ddof=1)  # 样本标准差
        cv = std_cost / mean_cost
        
        return cv
    
    def calculate_fisher_index(self, groups: List[DiseaseGroup], records: List[MedicalRecord]) -> float:
        """
        计算Fisher指数（组间方差/组内方差）
        
        Fisher指数越大，说明组间差异越大、组内差异越小，分组越合理
        
        Args:
            groups: 病种分组列表
            records: 病例记录列表
            
        Returns:
            Fisher指数
        """
        if not groups or not records:
            return 0.0
        
        # 按分组组织费用数据
        group_costs = {}
        for record in records:
            # 查找该病例所属的分组
            for group in groups:
                if (record.main_diag_code == group.main_diag_code and 
                    record.main_oprn_code == group.main_oprn_code):
                    if group.disease_code not in group_costs:
                        group_costs[group.disease_code] = []
                    group_costs[group.disease_code].append(float(record.total_cost))
                    break
        
        # 计算总均值
        all_costs = [float(r.total_cost) for r in records]
        overall_mean = np.mean(all_costs)
        
        # 计算组间方差（Between-group variance）
        between_variance = 0.0
        total_within_variance = 0.0
        
        for group in groups:
            if group.disease_code in group_costs:
                costs = group_costs[group.disease_code]
                if len(costs) > 1:
                    group_mean = np.mean(costs)
                    group_var = np.var(costs, ddof=1)
                    
                    # 组间方差贡献
                    between_variance += len(costs) * (group_mean - overall_mean) ** 2
                    
                    # 组内方差贡献
                    total_within_variance += (len(costs) - 1) * group_var
        
        n = len(records)
        k = len([g for g in groups if g.disease_code in group_costs])
        
        if k <= 1 or n <= k:
            return 0.0
        
        # 均方
        ms_between = between_variance / (k - 1)
        ms_within = total_within_variance / (n - k)
        
        if ms_within == 0:
            return float('inf')
        
        fisher_index = ms_between / ms_within
        
        return fisher_index
    
    def find_optimal_threshold(self, records: List[MedicalRecord]) -> int:
        """
        寻找最优临界值（使覆盖率达到目标）
        
        Args:
            records: 病例记录列表
            
        Returns:
            最优临界值
        """
        if not records:
            return self.config.default_threshold
        
        # 统计各病种的病例数
        disease_counts = {}
        for record in records:
            key = f"{record.main_diag_code}_{record.main_oprn_code}"
            disease_counts[key] = disease_counts.get(key, 0) + 1
        
        # 按病例数排序
        sorted_counts = sorted(disease_counts.values(), reverse=True)
        total_cases = len(records)
        target_cases = int(total_cases * self.config.target_coverage)
        
        # 寻找达到目标覆盖率的最小临界值
        cumulative = 0
        optimal_threshold = self.config.min_core_threshold
        
        for count in sorted_counts:
            cumulative += count
            if cumulative >= target_cases:
                optimal_threshold = count
                break
        
        # 限制在合理范围内
        optimal_threshold = max(self.config.min_core_threshold, 
                               min(optimal_threshold, self.config.max_core_threshold))
        
        return optimal_threshold
    
    def evaluate_group_suitability(self, group: DiseaseGroup, costs: List[float]) -> Dict:
        """
        评估单个病种组的适宜性
        
        Args:
            group: 病种分组
            costs: 该组病例的费用列表
            
        Returns:
            适宜性评估结果
        """
        cv = self.calculate_cv(costs)
        mean_cost = np.mean(costs) if costs else 0
        std_cost = np.std(costs, ddof=1) if len(costs) > 1 else 0
        
        return {
            'disease_code': group.disease_code,
            'case_count': group.case_count,
            'mean_cost': mean_cost,
            'std_cost': std_cost,
            'cv': cv,
            'cv_acceptable': cv <= self.config.cv_threshold,
            'suitability_score': max(0, 1 - cv)  # CV越小，适宜性越高
        }
    
    def optimize_grouping(self, records: List[MedicalRecord]) -> Tuple[List[DiseaseGroup], List[DiseaseGroup], GroupingStatistics]:
        """
        优化分组
        
        Args:
            records: 病例记录列表
            
        Returns:
            (核心病种列表, 综合病种列表, 统计信息)
        """
        # 1. 初始分组
        initial_groups = self._initial_grouping(records)
        
        # 2. 寻找最优临界值
        optimal_threshold = self.find_optimal_threshold(records)
        self.config.default_threshold = optimal_threshold
        
        # 3. 区分核心病种和综合病种
        core_groups = []
        mixed_candidates = []
        
        for group in initial_groups:
            if group.case_count >= optimal_threshold:
                core_groups.append(group)
            else:
                mixed_candidates.append(group)
        
        # 4. 优化综合病种（控制数量、合并相似组）
        mixed_groups = self._optimize_mixed_groups(mixed_candidates, records)
        
        # 5. 计算统计信息
        statistics = self._calculate_statistics(core_groups, mixed_groups, records)
        
        self.statistics = statistics
        
        return core_groups, mixed_groups, statistics
    
    def _initial_grouping(self, records: List[MedicalRecord]) -> List[DiseaseGroup]:
        """
        初始分组（按DIP3.0规则）
        
        Args:
            records: 病例记录列表
            
        Returns:
            病种分组列表
        """
        group_dict = {}
        
        for record in records:
            # 生成病种代码
            if record.main_oprn_code:
                # 手术/介入操作 -> 入组手术组
                disease_code = f"{record.main_diag_code}-{self._get_procedure_suffix(record.main_oprn_code)}"
                disease_name = f"{record.main_diag_name}-{record.main_oprn_name}"
                group_type = "手术"
            else:
                # 内科病种
                disease_code = f"{record.main_diag_code}-00"
                disease_name = record.main_diag_name
                group_type = "内科"
            
            if disease_code not in group_dict:
                group_dict[disease_code] = DiseaseGroup(
                    disease_code=disease_code,
                    disease_name=disease_name,
                    main_diag_code=record.main_diag_code,
                    main_diag_name=record.main_diag_name,
                    main_oprn_code=record.main_oprn_code,
                    main_oprn_name=record.main_oprn_name,
                    group_type=GroupType.CORE
                )
                group_dict[disease_code].costs = []
            
            group_dict[disease_code].case_count += 1
            group_dict[disease_code].costs.append(float(record.total_cost))
        
        # 计算平均费用和CV
        for group in group_dict.values():
            if group.case_count > 0:
                costs = group.costs if hasattr(group, 'costs') else []
                group.avg_cost = Decimal(str(np.mean(costs))) if costs else Decimal("0")
        
        return list(group_dict.values())
    
    def _get_procedure_suffix(self, proc_code: str) -> str:
        """
        根据手术编码生成后缀
        
        手术/介入操作 -> 入组手术组
        
        Args:
            proc_code: 手术编码
            
        Returns:
            后缀代码
        """
        # 手术/介入操作编码范围（ICD-9-CM-3）
        # 01-17: 手术操作
        # 39-41: 血管手术
        # 84-86: 其他手术
        
        if not proc_code:
            return "00"
        
        # 提取手术编码的前两位数字
        try:
            proc_num = int(proc_code[:2]) if proc_code[:2].isdigit() else 0
        except:
            proc_num = 0
        
        # 手术/介入操作判定
        if 1 <= proc_num <= 17 or 39 <= proc_num <= 41 or 84 <= proc_num <= 86:
            # 手术操作
            return "01"  # 默认后缀，实际应根据DIP目录库匹配
        elif 45 <= proc_num <= 54:
            # 介入操作
            return "02"  # 介入操作后缀
        else:
            # 其他操作
            return "01"
    
    def _optimize_mixed_groups(self, mixed_candidates: List[DiseaseGroup], records: List[MedicalRecord]) -> List[DiseaseGroup]:
        """
        优化综合病种
        
        依据DIP3.0规范：
        1. 控制综合病种数量
        2. 组内CV应低于阈值
        3. 病例数未达临界值可剔除
        
        Args:
            mixed_candidates: 候选综合病种列表
            records: 病例记录列表
            
        Returns:
            优化后的综合病种列表
        """
        if not mixed_candidates:
            return []
        
        # 1. 按诊断4位码分组合并
        diag_groups = {}
        for group in mixed_candidates:
            diag_4 = group.main_diag_code[:4] if len(group.main_diag_code) >= 4 else group.main_diag_code
            if diag_4 not in diag_groups:
                diag_groups[diag_4] = []
            diag_groups[diag_4].append(group)
        
        merged_groups = []
        for diag_4, groups in diag_groups.items():
            total_count = sum(g.case_count for g in groups)
            total_cost = sum(float(g.avg_cost) * g.case_count for g in groups)
            avg_cost = total_cost / total_count if total_count > 0 else 0
            
            # 收集该组所有费用
            all_costs = []
            for group in groups:
                if hasattr(group, 'costs'):
                    all_costs.extend(group.costs)
            
            # 计算CV
            cv = self.calculate_cv(all_costs)
            
            # 检查是否满足CV阈值
            if cv <= self.config.cv_threshold and total_count >= self.config.min_mixed_cases:
                merged_group = DiseaseGroup(
                    disease_code=f"MIX_{diag_4}",
                    disease_name=f"综合病种-{groups[0].main_diag_name}",
                    main_diag_code=groups[0].main_diag_code,
                    main_diag_name=groups[0].main_diag_name,
                    group_type=GroupType.MIXED,
                    case_count=total_count,
                    avg_cost=Decimal(str(avg_cost))
                )
                merged_group.cv = cv
                merged_groups.append(merged_group)
        
        # 2. 如果综合病种数量超过限制，合并CV最大的组
        while len(merged_groups) > self.config.max_mixed_groups:
            # 找到CV最大的两个相邻组合并
            merged_groups = self._merge_highest_cv_groups(merged_groups)
        
        return merged_groups
    
    def _merge_highest_cv_groups(self, groups: List[DiseaseGroup]) -> List[DiseaseGroup]:
        """
        合并CV最高的相邻组
        
        Args:
            groups: 病种分组列表
            
        Returns:
            合并后的列表
        """
        if len(groups) <= 1:
            return groups
        
        # 找到CV最高的组（简化：合并第一个和第二个）
        # 实际应用中应找相邻且诊断相似的组
        merged = DiseaseGroup(
            disease_code=f"MIX_MERGED",
            disease_name="合并综合病种",
            main_diag_code=groups[0].main_diag_code,
            main_diag_name="合并病种",
            group_type=GroupType.MIXED,
            case_count=sum(g.case_count for g in groups[:2]),
            avg_cost=Decimal(str(np.mean([float(g.avg_cost) for g in groups[:2]])))
        )
        
        return [merged] + groups[2:]
    
    def _calculate_statistics(self, core_groups: List[DiseaseGroup], 
                            mixed_groups: List[DiseaseGroup], 
                            records: List[MedicalRecord]) -> GroupingStatistics:
        """
        计算分组统计信息
        
        Args:
            core_groups: 核心病种列表
            mixed_groups: 综合病种列表
            records: 病例记录列表
            
        Returns:
            分组统计信息
        """
        total_cases = len(records)
        core_cases = sum(g.case_count for g in core_groups)
        mixed_cases = sum(g.case_count for g in mixed_groups)
        
        coverage_rate = core_cases / total_cases if total_cases > 0 else 0
        
        # 计算各组CV值
        cv_values = []
        for group in core_groups + mixed_groups:
            if hasattr(group, 'cv'):
                cv_values.append(group.cv)
        
        # 计算总体CV
        all_costs = [float(r.total_cost) for r in records]
        overall_cv = self.calculate_cv(all_costs)
        
        # 计算Fisher指数
        fisher_index = self.calculate_fisher_index(core_groups + mixed_groups, records)
        
        return GroupingStatistics(
            total_cases=total_cases,
            core_cases=core_cases,
            mixed_cases=mixed_cases,
            excluded_cases=0,
            advanced_cases=0,
            core_group_count=len(core_groups),
            mixed_group_count=len(mixed_groups),
            coverage_rate=coverage_rate,
            threshold_used=self.config.default_threshold,
            cv_values=cv_values,
            overall_cv=overall_cv,
            between_group_variance=0,  # 需要计算
            within_group_variance=0,  # 需要计算
            fisher_index=fisher_index
        )
    
    def get_suitability_report(self) -> Dict:
        """
        获取适宜性评估报告
        
        Returns:
            评估报告
        """
        if not self.statistics:
            return {"error": "尚未执行分组优化"}
        
        return {
            "summary": {
                "total_cases": self.statistics.total_cases,
                "core_cases": self.statistics.core_cases,
                "mixed_cases": self.statistics.mixed_cases,
                "coverage_rate": f"{self.statistics.coverage_rate:.2%}",
                "threshold_used": self.statistics.threshold_used
            },
            "suitability": {
                "overall_cv": f"{self.statistics.overall_cv:.4f}",
                "fisher_index": f"{self.statistics.fisher_index:.4f}",
                "cv_acceptable": self.statistics.overall_cv <= self.config.cv_threshold,
                "fisher_acceptable": self.statistics.fisher_index >= self.config.min_fisher_index
            },
            "recommendations": self._generate_recommendations()
        }
    
    def _generate_recommendations(self) -> List[str]:
        """
        生成优化建议
        
        Returns:
            建议列表
        """
        recommendations = []
        
        if self.statistics.coverage_rate < self.config.target_coverage:
            recommendations.append(
                f"核心病种覆盖率({self.statistics.coverage_rate:.2%})低于目标({self.config.target_coverage:.2%})，"
                "建议降低临界值或检查分组规则"
            )
        
        if self.statistics.overall_cv > self.config.cv_threshold:
            recommendations.append(
                f"总体变异系数({self.statistics.overall_cv:.4f})超过阈值({self.config.cv_threshold})，"
                "建议增加分组维度或调整分组规则"
            )
        
        if self.statistics.fisher_index < self.config.min_fisher_index:
            recommendations.append(
                f"Fisher指数({self.statistics.fisher_index:.4f})低于阈值({self.config.min_fisher_index})，"
                "建议增加组间差异或减少组内差异"
            )
        
        return recommendations


def create_default_optimizer() -> DiseaseGroupingOptimizer:
    """创建默认分组优化器"""
    config = GroupingConfig(
        target_coverage=0.95,
        min_core_threshold=10,
        max_core_threshold=50,
        default_threshold=15,
        max_mixed_groups=100,
        cv_threshold=1.0,
        min_mixed_cases=5
    )
    return DiseaseGroupingOptimizer(config)
