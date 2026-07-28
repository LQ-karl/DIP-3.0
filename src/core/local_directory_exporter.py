"""
DIP按病种分值分组测算工具 - 本地目录库输出模块
基于《国家医疗保障按病种分值(DIP)付费3.0版技术规范》
功能：生成与国家DIP3.0目录库一致的本地目录库输出
"""
import pandas as pd
from typing import List, Dict, Optional
from decimal import Decimal, ROUND_HALF_UP
from dataclasses import dataclass, field
from pathlib import Path

from ..models.models import MedicalRecord, DiseaseGroup


@dataclass
class LocalDirectoryRecord:
    """本地目录库记录"""
    # 基本信息
    disease_code: str  # 病种代码
    disease_name: str  # 病种名称
    main_diag_code: str  # 主要诊断代码
    main_diag_name: str  # 主要诊断名称
    main_oprn_code: str = ""  # 主要手术操作代码
    main_oprn_name: str = ""  # 主要手术操作名称
    
    # 分组信息
    dip_code: str = ""  # DIP编码
    dip_name: str = ""  # DIP名称
    group_type: str = "核心病种"  # 分组类型：核心病种/综合病种
    
    # 统计信息
    case_count: int = 0  # 病例数
    avg_cost: Decimal = Decimal("0")  # 次均费用
    avg_drug_cost: Decimal = Decimal("0")  # 次均药品费用
    avg_material_cost: Decimal = Decimal("0")  # 次均材料费用
    avg_los: Decimal = Decimal("0")  # 平均住院天数
    
    # 分值信息
    disease_value: Decimal = Decimal("0")  # 病种分值
    drug_value: Decimal = Decimal("0")  # 药品分值
    consumable_value: Decimal = Decimal("0")  # 耗材分值
    
    # 辅助信息
    cci_score: Decimal = Decimal("0")  # CCI评分
    severity_level: str = ""  # 疾病严重程度
    age_type: str = ""  # 年龄特征
    icu_days: Decimal = Decimal("0")  # ICU天数
    
    # 特殊标识
    is_basic_group: bool = False  # 是否为基层病种
    is_advanced_group: bool = False  # 是否为先期分组
    is_excluded: bool = False  # 是否为排除病种


@dataclass
class DIP30DirectoryFormat:
    """DIP3.0目录库格式"""
    # 表头信息
    version: str = "3.0"  # 版本号
    publish_date: str = ""  # 发布日期
    effective_date: str = ""  # 生效日期
    region: str = ""  # 适用地区
    
    # 数据
    records: List[LocalDirectoryRecord] = field(default_factory=list)


class LocalDirectoryExporter:
    """本地目录库导出器"""
    
    # 国家DIP3.0目录库表头格式
    DIP30_HEADERS = [
        '病种代码',
        '病种名称',
        '主要诊断代码',
        '主要诊断名称',
        '主要手术操作代码',
        '主要手术操作名称',
        'DIP编码',
        'DIP名称',
        '分组类型',
        '病例数',
        '次均费用',
        '次均药品费用',
        '次均材料费用',
        '平均住院天数',
        '病种分值',
        '药品分值',
        '耗材分值',
        'CCI评分',
        '疾病严重程度',
        '年龄特征',
        'ICU天数',
        '是否基层病种',
        '是否先期分组',
        '是否排除病种'
    ]
    
    def __init__(self):
        pass
    
    def generate_from_records(
        self,
        records: List[MedicalRecord],
        disease_groups: List[DiseaseGroup] = None
    ) -> DIP30DirectoryFormat:
        """
        从病例记录生成本地目录库
        
        Args:
            records: 病例记录列表
            disease_groups: 病种分组列表
            
        Returns:
            DIP3.0目录库格式
        """
        # 按DIP分组统计
        dip_stats = self._calculate_dip_statistics(records)
        
        # 创建目录库记录
        directory_records = []
        
        for dip_code, stats in dip_stats.items():
            # 获取病种分组信息
            disease_group = None
            if disease_groups:
                disease_group = next(
                    (g for g in disease_groups if g.disease_code == dip_code),
                    None
                )
            
            # 创建目录库记录
            record = LocalDirectoryRecord(
                disease_code=disease_group.disease_code if disease_group else dip_code,
                disease_name=disease_group.disease_name if disease_group else dip_code,
                main_diag_code=disease_group.main_diag_code if disease_group else "",
                main_diag_name=disease_group.main_diag_name if disease_group else "",
                main_oprn_code=disease_group.main_oprn_code if disease_group else "",
                main_oprn_name=disease_group.main_oprn_name if disease_group else "",
                dip_code=dip_code,
                dip_name=disease_group.disease_name if disease_group else dip_code,
                group_type=self._get_group_type(disease_group),
                case_count=stats['case_count'],
                avg_cost=stats['avg_cost'],
                avg_drug_cost=stats['avg_drug_cost'],
                avg_material_cost=stats['avg_material_cost'],
                avg_los=stats['avg_los'],
                disease_value=disease_group.disease_value if disease_group else Decimal("0"),
                drug_value=disease_group.drug_value if disease_group else Decimal("0"),
                consumable_value=disease_group.consumable_value if disease_group else Decimal("0"),
                cci_score=stats.get('cci_score', Decimal("0")),
                severity_level=stats.get('severity_level', ''),
                age_type=stats.get('age_type', ''),
                icu_days=stats.get('icu_days', Decimal("0")),
                is_basic_group=getattr(disease_group, 'is_basic_group', False) if disease_group else False,
                is_advanced_group=getattr(disease_group, 'is_advanced', False) if disease_group else False,
                is_excluded=getattr(disease_group, 'is_excluded', False) if disease_group else False
            )
            
            directory_records.append(record)
        
        return DIP30DirectoryFormat(
            version="3.0",
            records=directory_records
        )
    
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
                    'total_material_cost': Decimal("0"),
                    'total_los': 0,
                    'cci_scores': [],
                    'severity_levels': [],
                    'age_types': [],
                    'icu_days_list': []
                }
            
            stats = dip_stats[dip_code]
            stats['case_count'] += 1
            stats['total_cost'] += record.total_cost
            stats['total_drug_cost'] += record.drug_cost
            stats['total_material_cost'] += record.material_cost
            stats['total_los'] += record.los
            
            # 收集辅助信息
            if hasattr(record, 'cci_score') and record.cci_score:
                stats['cci_scores'].append(record.cci_score)
            if hasattr(record, 'severity_level') and record.severity_level:
                stats['severity_levels'].append(record.severity_level)
            if hasattr(record, 'age_type') and record.age_type:
                stats['age_types'].append(record.age_type)
            if hasattr(record, 'icu_days') and record.icu_days:
                stats['icu_days_list'].append(record.icu_days)
        
        # 计算平均值
        for dip_code, stats in dip_stats.items():
            if stats['case_count'] > 0:
                stats['avg_cost'] = (stats['total_cost'] / stats['case_count']).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                stats['avg_drug_cost'] = (stats['total_drug_cost'] / stats['case_count']).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                stats['avg_material_cost'] = (stats['total_material_cost'] / stats['case_count']).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                stats['avg_los'] = (Decimal(str(stats['total_los'])) / stats['case_count']).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            else:
                stats['avg_cost'] = Decimal("0")
                stats['avg_drug_cost'] = Decimal("0")
                stats['avg_material_cost'] = Decimal("0")
                stats['avg_los'] = Decimal("0")
            
            # 辅助信息统计
            if stats['cci_scores']:
                stats['cci_score'] = (sum(stats['cci_scores']) / len(stats['cci_scores'])).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            else:
                stats['cci_score'] = Decimal("0")
            
            if stats['severity_levels']:
                from collections import Counter
                severity_counter = Counter(stats['severity_levels'])
                stats['severity_level'] = severity_counter.most_common(1)[0][0]
            else:
                stats['severity_level'] = ''
            
            if stats['age_types']:
                from collections import Counter
                age_counter = Counter(stats['age_types'])
                stats['age_type'] = age_counter.most_common(1)[0][0]
            else:
                stats['age_type'] = ''
            
            if stats['icu_days_list']:
                stats['icu_days'] = (sum(stats['icu_days_list']) / len(stats['icu_days_list'])).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            else:
                stats['icu_days'] = Decimal("0")
        
        return dip_stats
    
    def _get_group_type(self, disease_group) -> str:
        """获取分组类型"""
        if not disease_group:
            return "核心病种"
        
        if hasattr(disease_group, 'is_advanced') and disease_group.is_advanced:
            return "先期分组"
        elif hasattr(disease_group, 'is_basic_group') and disease_group.is_basic_group:
            return "综合病种"
        else:
            return "核心病种"
    
    def export_to_excel(
        self,
        directory: DIP30DirectoryFormat,
        output_path: str,
        include_metadata: bool = True
    ) -> str:
        """
        导出到Excel
        
        Args:
            directory: DIP3.0目录库格式
            output_path: 输出文件路径
            include_metadata: 是否包含元数据
            
        Returns:
            输出文件路径
        """
        # 创建工作簿
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            # 1. 主目录表
            main_data = []
            for i, record in enumerate(directory.records, 1):
                main_data.append({
                    '序号': i,
                    '病种代码': record.disease_code,
                    '病种名称': record.disease_name,
                    '主要诊断代码': record.main_diag_code,
                    '主要诊断名称': record.main_diag_name,
                    '主要手术操作代码': record.main_oprn_code,
                    '主要手术操作名称': record.main_oprn_name,
                    'DIP编码': record.dip_code,
                    'DIP名称': record.dip_name,
                    '分组类型': record.group_type,
                    '病例数': record.case_count,
                    '次均费用': float(record.avg_cost),
                    '次均药品费用': float(record.avg_drug_cost),
                    '次均材料费用': float(record.avg_material_cost),
                    '平均住院天数': float(record.avg_los),
                    '病种分值': float(record.disease_value),
                    '药品分值': float(record.drug_value),
                    '耗材分值': float(record.consumable_value),
                    'CCI评分': float(record.cci_score),
                    '疾病严重程度': record.severity_level,
                    '年龄特征': record.age_type,
                    'ICU天数': float(record.icu_days),
                    '是否基层病种': '是' if record.is_basic_group else '否',
                    '是否先期分组': '是' if record.is_advanced_group else '否',
                    '是否排除病种': '是' if record.is_excluded else '否'
                })
            
            main_df = pd.DataFrame(main_data)
            main_df.to_excel(writer, sheet_name='本地目录库', index=False)
            
            # 2. 元数据表
            if include_metadata:
                metadata = [
                    {'项目': '版本号', '值': directory.version},
                    {'项目': '发布日期', '值': directory.publish_date},
                    {'项目': '生效日期', '值': directory.effective_date},
                    {'项目': '适用地区', '值': directory.region},
                    {'项目': '记录总数', '值': len(directory.records)},
                    {'项目': '核心病种数', '值': sum(1 for r in directory.records if r.group_type == '核心病种')},
                    {'项目': '综合病种数', '值': sum(1 for r in directory.records if r.group_type == '综合病种')},
                    {'项目': '先期分组数', '值': sum(1 for r in directory.records if r.is_advanced_group)},
                    {'项目': '基层病种数', '值': sum(1 for r in directory.records if r.is_basic_group)},
                ]
                metadata_df = pd.DataFrame(metadata)
                metadata_df.to_excel(writer, sheet_name='元数据', index=False)
            
            # 3. 统计汇总表
            summary_data = self._generate_summary(directory)
            summary_df = pd.DataFrame(summary_data)
            summary_df.to_excel(writer, sheet_name='统计汇总', index=False)
        
        return output_path
    
    def _generate_summary(self, directory: DIP30DirectoryFormat) -> List[Dict]:
        """生成统计汇总"""
        records = directory.records
        
        if not records:
            return []
        
        # 按分组类型统计
        group_types = {}
        for record in records:
            gt = record.group_type
            if gt not in group_types:
                group_types[gt] = {
                    'count': 0,
                    'total_cases': 0,
                    'total_cost': Decimal("0")
                }
            group_types[gt]['count'] += 1
            group_types[gt]['total_cases'] += record.case_count
            group_types[gt]['total_cost'] += record.avg_cost * record.case_count
        
        summary = []
        for gt, stats in group_types.items():
            avg_cost = (stats['total_cost'] / stats['total_cases']).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            ) if stats['total_cases'] > 0 else Decimal("0")
            
            summary.append({
                '统计项': f'{gt}汇总',
                'DIP数量': stats['count'],
                '病例总数': stats['total_cases'],
                '平均费用': float(avg_cost),
                '费用占比': ''
            })
        
        # 总计
        total_cases = sum(r.case_count for r in records)
        total_cost = sum(r.avg_cost * r.case_count for r in records)
        avg_cost = (total_cost / total_cases).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        ) if total_cases > 0 else Decimal("0")
        
        summary.append({
            '统计项': '总计',
            'DIP数量': len(records),
            '病例总数': total_cases,
            '平均费用': float(avg_cost),
            '费用占比': '100%'
        })
        
        return summary
    
    def export_to_csv(
        self,
        directory: DIP30DirectoryFormat,
        output_path: str
    ) -> str:
        """导出到CSV"""
        data = []
        for i, record in enumerate(directory.records, 1):
            data.append({
                '序号': i,
                '病种代码': record.disease_code,
                '病种名称': record.disease_name,
                '主要诊断代码': record.main_diag_code,
                '主要诊断名称': record.main_diag_name,
                '主要手术操作代码': record.main_oprn_code,
                '主要手术操作名称': record.main_oprn_name,
                'DIP编码': record.dip_code,
                'DIP名称': record.dip_name,
                '分组类型': record.group_type,
                '病例数': record.case_count,
                '次均费用': float(record.avg_cost),
                '次均药品费用': float(record.avg_drug_cost),
                '次均材料费用': float(record.avg_material_cost),
                '平均住院天数': float(record.avg_los),
                '病种分值': float(record.disease_value),
                '药品分值': float(record.drug_value),
                '耗材分值': float(record.consumable_value),
                'CCI评分': float(record.cci_score),
                '疾病严重程度': record.severity_level,
                '年龄特征': record.age_type,
                'ICU天数': float(record.icu_days),
                '是否基层病种': '是' if record.is_basic_group else '否',
                '是否先期分组': '是' if record.is_advanced_group else '否',
                '是否排除病种': '是' if record.is_excluded else '否'
            })
        
        df = pd.DataFrame(data)
        df.to_csv(output_path, index=False, encoding='utf-8-sig')
        return output_path


def create_exporter() -> LocalDirectoryExporter:
    """创建导出器"""
    return LocalDirectoryExporter()
