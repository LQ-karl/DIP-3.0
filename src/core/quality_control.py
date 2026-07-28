"""
DIP3.0本地目录测算系统 - 质量控制模块
实现病例数不足检查、费用异常检查、编码错误检查、病种漂移检测等
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from decimal import Decimal
import pandas as pd
import numpy as np
from datetime import datetime


@dataclass
class QualityCheckResult:
    """质量检查结果"""
    check_name: str  # 检查名称
    check_type: str  # 检查类型
    is_passed: bool  # 是否通过
    risk_level: str  # 风险等级(高/中/低)
    risk_count: int = 0  # 风险病例数
    risk_rate: float = 0.0  # 风险比例
    detail_info: str = ""  # 详细信息
    suggestion: str = ""  # 处理建议


@dataclass
class QualityControlReport:
    """质量控制报告"""
    report_time: str = ""  # 报告时间
    total_records: int = 0  # 总记录数
    check_results: List[QualityCheckResult] = field(default_factory=list)
    overall_risk_level: str = "低"  # 整体风险等级
    summary: str = ""  # 总结


class QualityController:
    """质量控制器"""
    
    def __init__(self, threshold_core: int = 15, threshold_mixed: int = 5):
        """
        初始化质量控制器
        
        Args:
            threshold_core: 核心病种最小病例数阈值
            threshold_mixed: 综合病种最小病例数阈值
        """
        self.threshold_core = threshold_core
        self.threshold_mixed = threshold_mixed
    
    def check_case_count(self, disease_groups: pd.DataFrame) -> QualityCheckResult:
        """
        检查病例数不足
        
        Args:
            disease_groups: 病种分组数据
            
        Returns:
            QualityCheckResult
        """
        risk_count = 0
        risk_details = []
        
        for _, row in disease_groups.iterrows():
            case_count = row.get('case_count', 0)
            group_type = row.get('group_type', '')
            disease_code = row.get('disease_code', '')
            
            if group_type == '核心病种' and case_count < self.threshold_core:
                risk_count += 1
                risk_details.append(f"{disease_code}: {case_count}例(阈值{self.threshold_core})")
            elif group_type == '综合病种' and case_count < self.threshold_mixed:
                risk_count += 1
                risk_details.append(f"{disease_code}: {case_count}例(阈值{self.threshold_mixed})")
        
        total_diseases = len(disease_groups)
        risk_rate = risk_count / total_diseases if total_diseases > 0 else 0
        
        is_passed = risk_count == 0
        risk_level = "低" if risk_rate < 0.1 else ("中" if risk_rate < 0.3 else "高")
        
        detail_info = f"病例数不足的病种: {risk_count}个\n"
        if risk_details[:10]:  # 只显示前10个
            detail_info += "\n".join(risk_details[:10])
            if len(risk_details) > 10:
                detail_info += f"\n...等共{len(risk_details)}个"
        
        suggestion = "建议增加病例数或调整分组阈值" if not is_passed else "病例数检查通过"
        
        return QualityCheckResult(
            check_name="病例数不足检查",
            check_type="病例数",
            is_passed=is_passed,
            risk_level=risk_level,
            risk_count=risk_count,
            risk_rate=risk_rate,
            detail_info=detail_info,
            suggestion=suggestion
        )
    
    def check_cost_anomaly(self, records: pd.DataFrame, disease_groups: pd.DataFrame) -> QualityCheckResult:
        """
        检查费用异常
        
        Args:
            records: 病例数据
            disease_groups: 病种分组数据
            
        Returns:
            QualityCheckResult
        """
        risk_count = 0
        risk_details = []
        
        # 计算每个病种的费用统计
        for _, group in disease_groups.iterrows():
            disease_code = group.get('disease_code', '')
            avg_cost = group.get('avg_cost', 0)
            std_cost = group.get('std_cost', 0)
            
            if avg_cost <= 0 or std_cost <= 0:
                continue
            
            # 获取该病种的病例
            disease_records = records[records['dip_disease_code'] == disease_code]
            
            for _, record in disease_records.iterrows():
                total_cost = record.get('total_cost', 0)
                
                # 检查费用是否异常（超过3倍标准差）
                if total_cost > avg_cost + 3 * std_cost:
                    risk_count += 1
                    risk_details.append(f"{disease_code}: 费用{total_cost}超过阈值{avg_cost + 3 * std_cost}")
                elif total_cost < avg_cost - 3 * std_cost and total_cost > 0:
                    risk_count += 1
                    risk_details.append(f"{disease_code}: 费用{total_cost}低于阈值{avg_cost - 3 * std_cost}")
        
        total_records = len(records)
        risk_rate = risk_count / total_records if total_records > 0 else 0
        
        is_passed = risk_rate < 0.05  # 5%以下视为通过
        risk_level = "低" if risk_rate < 0.02 else ("中" if risk_rate < 0.05 else "高")
        
        detail_info = f"费用异常病例: {risk_count}例，占比{risk_rate:.2%}"
        suggestion = "建议核查费用异常病例" if not is_passed else "费用检查通过"
        
        return QualityCheckResult(
            check_name="费用异常检查",
            check_type="费用",
            is_passed=is_passed,
            risk_level=risk_level,
            risk_count=risk_count,
            risk_rate=risk_rate,
            detail_info=detail_info,
            suggestion=suggestion
        )
    
    def check_encoding_error(self, records: pd.DataFrame, icd10_valid: List[str] = None, icd9_valid: List[str] = None) -> QualityCheckResult:
        """
        检查编码错误
        
        Args:
            records: 病例数据
            icd10_valid: 有效的ICD-10编码列表
            icd9_valid: 有效的ICD-9-CM-3编码列表
            
        Returns:
            QualityCheckResult
        """
        risk_count = 0
        risk_details = []
        
        for _, record in records.iterrows():
            main_diag_code = record.get('main_diag_code', '')
            main_oprn_code = record.get('main_oprn_code', '')
            
            # 检查主要诊断编码
            if main_diag_code and icd10_valid and main_diag_code not in icd10_valid:
                risk_count += 1
                risk_details.append(f"无效诊断编码: {main_diag_code}")
            
            # 检查主要手术编码
            if main_oprn_code and icd9_valid and main_oprn_code not in icd9_valid:
                risk_count += 1
                risk_details.append(f"无效手术编码: {main_oprn_code}")
        
        total_records = len(records)
        risk_rate = risk_count / total_records if total_records > 0 else 0
        
        is_passed = risk_rate < 0.01  # 1%以下视为通过
        risk_level = "低" if risk_rate < 0.005 else ("中" if risk_rate < 0.01 else "高")
        
        detail_info = f"编码错误病例: {risk_count}例，占比{risk_rate:.2%}"
        suggestion = "建议核查编码错误病例" if not is_passed else "编码检查通过"
        
        return QualityCheckResult(
            check_name="编码错误检查",
            check_type="编码",
            is_passed=is_passed,
            risk_level=risk_level,
            risk_count=risk_count,
            risk_rate=risk_rate,
            detail_info=detail_info,
            suggestion=suggestion
        )
    
    def check_disease_drift(self, current_data: pd.DataFrame, historical_data: pd.DataFrame) -> QualityCheckResult:
        """
        检查病种漂移
        
        Args:
            current_data: 当前年度数据
            historical_data: 历史年度数据
            
        Returns:
            QualityCheckResult
        """
        # 计算当前年度病种分布
        current_dist = current_data.groupby('dip_disease_code').size() / len(current_data)
        
        # 计算历史年度病种分布
        historical_dist = historical_data.groupby('dip_disease_code').size() / len(historical_data)
        
        # 计算KL散度（分布差异）
        risk_count = 0
        risk_details = []
        
        for disease_code in current_dist.index:
            current_rate = current_dist.get(disease_code, 0)
            historical_rate = historical_dist.get(disease_code, 0)
            
            # 如果病种比例变化超过50%，视为漂移
            if historical_rate > 0:
                change_rate = abs(current_rate - historical_rate) / historical_rate
                if change_rate > 0.5:
                    risk_count += 1
                    risk_details.append(f"{disease_code}: 变化率{change_rate:.2%}")
        
        total_diseases = len(current_dist)
        risk_rate = risk_count / total_diseases if total_diseases > 0 else 0
        
        is_passed = risk_rate < 0.1  # 10%以下视为通过
        risk_level = "低" if risk_rate < 0.05 else ("中" if risk_rate < 0.1 else "高")
        
        detail_info = f"病种漂移: {risk_count}个病种"
        suggestion = "建议核查病种漂移原因" if not is_passed else "病种漂移检查通过"
        
        return QualityCheckResult(
            check_name="病种漂移检查",
            check_type="病种漂移",
            is_passed=is_passed,
            risk_level=risk_level,
            risk_count=risk_count,
            risk_rate=risk_rate,
            detail_info=detail_info,
            suggestion=suggestion
        )
    
    def check_upcoding(self, records: pd.DataFrame) -> QualityCheckResult:
        """
        检查高套分组（编码升级）
        
        Args:
            records: 病例数据
            
        Returns:
            QualityCheckResult
        """
        # 简化实现：检查费用异常高的病例
        risk_count = 0
        risk_details = []
        
        # 计算全市平均费用
        avg_cost = records['total_cost'].mean()
        std_cost = records['total_cost'].std()
        
        for _, record in records.iterrows():
            total_cost = record.get('total_cost', 0)
            disease_code = record.get('dip_disease_code', '')
            
            # 检查费用是否异常高（超过4倍标准差）
            if total_cost > avg_cost + 4 * std_cost:
                risk_count += 1
                risk_details.append(f"{disease_code}: 费用{total_cost}异常高")
        
        total_records = len(records)
        risk_rate = risk_count / total_records if total_records > 0 else 0
        
        is_passed = risk_rate < 0.02  # 2%以下视为通过
        risk_level = "低" if risk_rate < 0.01 else ("中" if risk_rate < 0.02 else "高")
        
        detail_info = f"疑似高套分组病例: {risk_count}例，占比{risk_rate:.2%}"
        suggestion = "建议核查高套分组病例" if not is_passed else "高套分组检查通过"
        
        return QualityCheckResult(
            check_name="高套分组检查",
            check_type="高套分组",
            is_passed=is_passed,
            risk_level=risk_level,
            risk_count=risk_count,
            risk_rate=risk_rate,
            detail_info=detail_info,
            suggestion=suggestion
        )
    
    def check_point_risk(self, records: pd.DataFrame, disease_groups: pd.DataFrame) -> QualityCheckResult:
        """
        检查冲点数风险
        
        Args:
            records: 病例数据
            disease_groups: 病种分组数据
            
        Returns:
            QualityCheckResult
        """
        risk_count = 0
        risk_details = []
        
        # 检查费用低于平均费用50%的病例
        avg_cost = records['total_cost'].mean()
        
        for _, record in records.iterrows():
            total_cost = record.get('total_cost', 0)
            disease_code = record.get('dip_disease_code', '')
            
            if total_cost < avg_cost * 0.5 and total_cost > 0:
                risk_count += 1
                risk_details.append(f"{disease_code}: 费用{total_cost}过低")
        
        total_records = len(records)
        risk_rate = risk_count / total_records if total_records > 0 else 0
        
        is_passed = risk_rate < 0.05  # 5%以下视为通过
        risk_level = "低" if risk_rate < 0.02 else ("中" if risk_rate < 0.05 else "高")
        
        detail_info = f"疑似冲点数风险病例: {risk_count}例，占比{risk_rate:.2%}"
        suggestion = "建议核查冲点数风险病例" if not is_passed else "冲点数风险检查通过"
        
        return QualityCheckResult(
            check_name="冲点数风险检查",
            check_type="冲点数风险",
            is_passed=is_passed,
            risk_level=risk_level,
            risk_count=risk_count,
            risk_rate=risk_rate,
            detail_info=detail_info,
            suggestion=suggestion
        )
    
    def run_all_checks(self, records: pd.DataFrame, disease_groups: pd.DataFrame, 
                       historical_data: pd.DataFrame = None,
                       icd10_valid: List[str] = None, 
                       icd9_valid: List[str] = None) -> QualityControlReport:
        """
        运行所有质量检查
        
        Args:
            records: 病例数据
            disease_groups: 病种分组数据
            historical_data: 历史数据（可选）
            icd10_valid: 有效的ICD-10编码列表（可选）
            icd9_valid: 有效的ICD-9-CM-3编码列表（可选）
            
        Returns:
            QualityControlReport
        """
        check_results = []
        
        # 1. 病例数不足检查
        check_results.append(self.check_case_count(disease_groups))
        
        # 2. 费用异常检查
        check_results.append(self.check_cost_anomaly(records, disease_groups))
        
        # 3. 编码错误检查
        check_results.append(self.check_encoding_error(records, icd10_valid, icd9_valid))
        
        # 4. 病种漂移检查（需要历史数据）
        if historical_data is not None and len(historical_data) > 0:
            check_results.append(self.check_disease_drift(records, historical_data))
        
        # 5. 高套分组检查
        check_results.append(self.check_upcoding(records))
        
        # 6. 冲点数风险检查
        check_results.append(self.check_point_risk(records, disease_groups))
        
        # 计算整体风险等级
        risk_levels = [r.risk_level for r in check_results]
        if "高" in risk_levels:
            overall_risk_level = "高"
        elif "中" in risk_levels:
            overall_risk_level = "中"
        else:
            overall_risk_level = "低"
        
        # 生成总结
        passed_count = sum(1 for r in check_results if r.is_passed)
        total_count = len(check_results)
        summary = f"共执行{total_count}项检查，通过{passed_count}项，未通过{total_count - passed_count}项。整体风险等级: {overall_risk_level}"
        
        return QualityControlReport(
            report_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            total_records=len(records),
            check_results=check_results,
            overall_risk_level=overall_risk_level,
            summary=summary
        )
    
    def generate_report(self, report: QualityControlReport) -> str:
        """
        生成质量控制报告文本
        
        Args:
            report: 质量控制报告
            
        Returns:
            报告文本
        """
        lines = []
        lines.append("=" * 60)
        lines.append("DIP3.0质量控制报告")
        lines.append("=" * 60)
        lines.append(f"报告时间: {report.report_time}")
        lines.append(f"总记录数: {report.total_records}")
        lines.append(f"整体风险等级: {report.overall_risk_level}")
        lines.append("")
        
        lines.append("-" * 60)
        lines.append("检查项目详情:")
        lines.append("-" * 60)
        
        for result in report.check_results:
            status = "✓ 通过" if result.is_passed else "✗ 未通过"
            lines.append(f"\n【{result.check_name}】{status}")
            lines.append(f"  风险等级: {result.risk_level}")
            lines.append(f"  风险病例数: {result.risk_count}")
            lines.append(f"  风险比例: {result.risk_rate:.2%}")
            lines.append(f"  详细信息: {result.detail_info}")
            lines.append(f"  处理建议: {result.suggestion}")
        
        lines.append("")
        lines.append("=" * 60)
        lines.append(report.summary)
        lines.append("=" * 60)
        
        return "\n".join(lines)
