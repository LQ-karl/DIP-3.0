"""
DIP按病种分值分组测算工具 - 医保结算清单导入模块
基于《医疗保障信息平台定点医药机构接口规范》4101A接口
功能：支持Excel/CSV/XML/JSON格式的医保结算清单数据导入
"""
import pandas as pd
import json
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional, Union
from decimal import Decimal, ROUND_HALF_UP
from dataclasses import dataclass, field
from pathlib import Path
import os

from ..models.models import MedicalRecord


@dataclass
class ImportConfig:
    """导入配置"""
    file_format: str = "excel"  # excel, csv, xml, json
    encoding: str = "utf-8"  # 文件编码
    sheet_name: str = 0  # Excel工作表名称或索引
    header_row: int = 0  # 表头行号
    data_start_row: int = 1  # 数据起始行号


@dataclass
class ImportResult:
    """导入结果"""
    total_rows: int
    imported_rows: int
    failed_rows: int
    failed_reasons: Dict[str, int] = field(default_factory=dict)
    records: List[MedicalRecord] = field(default_factory=list)
    import_log: List[str] = field(default_factory=list)


class SettlementDataImporter:
    """医保结算清单导入器"""
    
    # 4101A接口字段映射
    FIELD_MAPPING_4101A = {
        # 基本信息
        'psn_no': 'patient_id',  # 人员编号
        'mdtrt_id': 'visit_id',  # 就诊ID
        'setl_id': 'settlement_id',  # 结算ID
        'medcasno': 'record_id',  # 病案号
        'hi_no': 'insurance_no',  # 医保编号
        
        # 医院信息
        'fixmedins_code': 'hospital_code',  # 定点医药机构编号
        'fixmedins_name': 'hospital_name',  # 定点医药机构名称
        'fixmedins_lv': 'hospital_level',  # 医疗机构等级
        
        # 入院信息
        'adm_time': 'admission_date',  # 入院时间
        'adm_dept_codg': 'admission_department',  # 入院科室编码
        'adm_dept_name': 'admission_department_name',  # 入院科室名称
        'adm_way': 'admission_type',  # 入院途径
        
        # 出院信息
        'dscg_time': 'discharge_date',  # 出院时间
        'dscg_dept_codg': 'discharge_department',  # 出院科室编码
        'dscg_dept_name': 'discharge_department_name',  # 出院科室名称
        'dscg_way': 'discharge_status',  # 出院方式
        
        # 诊断信息
        'otp_wm_dise': 'main_diag_name',  # 门(急)诊诊断(西医诊断)
        'wm_dise_code': 'main_diag_code',  # 西医疾病代码
        'otp_tcm_dise': 'tcm_diag_name',  # 门(急)诊诊断(中医诊断)
        'tcm_dise_code': 'tcm_diag_code',  # 中医疾病代码
        
        # 手术操作信息
        'oprn_oprt_name': 'main_oprn_name',  # 手术操作名称
        'oprn_oprt_code': 'main_oprn_code',  # 手术操作代码
        
        # 费用信息
        'medfee_sumamt': 'total_cost',  # 医疗总费用
        'fund_pay_sumamt': 'fund_payment',  # 基金支付总额
        'psn_pay_sumamt': 'patient_payment',  # 个人支付总额
        
        # 药品费用
        'drug_fee': 'drug_cost',  # 药品费用
        'west_med_fee': 'western_medicine_cost',  # 西药费
        'chinese_med_fee': 'chinese_medicine_cost',  # 中成药费
        'chinese_herb_med_fee': 'chinese_herb_cost',  # 中草药费
        
        # 耗材费用
        'matl_fee': 'material_cost',  # 材料费
        'consumable_fee': 'consumable_cost',  # 耗材费用
        
        # 检查费用
        'exam_fee': 'exam_cost',  # 检查费
        'test_fee': 'test_cost',  # 检验费
        
        # 治疗费用
        'treat_fee': 'treatment_cost',  # 治疗费
        'operation_fee': 'operation_cost',  # 手术费
        
        # 护理费用
        'nurs_fee': 'nursing_cost',  # 护理费
        
        # 其他费用
        'bed_fee': 'bed_cost',  # 床位费
        'feed_fee': 'food_cost',  # 伙食费
        'other_fee': 'other_cost',  # 其他费用
        
        # 住院天数
        'los': 'los',  # 实际住院天数
        
        # 新生儿信息
        'nwb_bir_wt': 'newborn_birth_weight',  # 新生儿出生体重
        'nwb_adm_wt': 'newborn_admission_weight',  # 新生儿入院体重
        
        # 重症监护
        'icu_dura': 'icu_days',  # 重症监护时长
        'vent_used_dura': 'ventilator_days',  # 呼吸机使用时长
        
        # DIP分组信息
        'dip_code': 'dip_disease_code',  # DIP编码
        'dip_name': 'dip_disease_name',  # DIP名称
        'disease_value': 'disease_value',  # 病种分值
    }
    
    # 简化字段映射（用于Excel/CSV导入）
    SIMPLE_FIELD_MAPPING = {
        '住院号': 'record_id',
        '病案号': 'record_id',
        '结算ID': 'settlement_id',
        '人员编号': 'patient_id',
        '就诊ID': 'visit_id',
        '医院代码': 'hospital_code',
        '医院编号': 'hospital_code',
        '医院名称': 'hospital_name',
        '医疗机构代码': 'hospital_code',
        '医疗机构名称': 'hospital_name',
        '医疗机构等级': 'hospital_level',
        '医院等级': 'hospital_level',
        '入院日期': 'admission_date',
        '入院时间': 'admission_date',
        '出院日期': 'discharge_date',
        '出院时间': 'discharge_date',
        '主诊断': 'main_diag_code',
        '主要诊断': 'main_diag_code',
        '主诊断名称': 'main_diag_name',
        '主要诊断名称': 'main_diag_name',
        '其他诊断1': 'related_diag_code_1',
        '其他诊断1名称': 'related_diag_name_1',
        '其他诊断2': 'related_diag_code_2',
        '其他诊断2名称': 'related_diag_name_2',
        '其他诊断3': 'related_diag_code_3',
        '其他诊断3名称': 'related_diag_name_3',
        '其他诊断4': 'related_diag_code_4',
        '其他诊断4名称': 'related_diag_name_4',
        '其他诊断5': 'related_diag_code_5',
        '其他诊断5名称': 'related_diag_name_5',
        '主手术': 'main_oprn_code',
        '主要手术': 'main_oprn_code',
        '主手术名称': 'main_oprn_name',
        '主要手术名称': 'main_oprn_name',
        '其他手术1': 'related_oprn_code_1',
        '其他手术1名称': 'related_oprn_name_1',
        '其他手术2': 'related_oprn_code_2',
        '其他手术2名称': 'related_oprn_name_2',
        '其他手术3': 'related_oprn_code_3',
        '其他手术3名称': 'related_oprn_name_3',
        '其他手术4': 'related_oprn_code_4',
        '其他手术4名称': 'related_oprn_name_4',
        '其他手术5': 'related_oprn_code_5',
        '其他手术5名称': 'related_oprn_name_5',
        '总费用': 'total_cost',
        '医疗总费用': 'total_cost',
        '药品费用': 'drug_cost',
        '药费': 'drug_cost',
        '材料费用': 'material_cost',
        '材料费': 'material_cost',
        '耗材费用': 'consumable_cost',
        '耗材费': 'consumable_cost',
        '检查费用': 'exam_cost',
        '检查费': 'exam_cost',
        '治疗费用': 'treatment_cost',
        '治疗费': 'treatment_cost',
        '护理费用': 'nursing_cost',
        '护理费': 'nursing_cost',
        '住院天数': 'los',
        '天数': 'los',
        '出院方式': 'discharge_status',
        '出院情况': 'discharge_status',
        'DIP编码': 'dip_disease_code',
        'DIP代码': 'dip_disease_code',
        'DIP名称': 'dip_disease_name',
        '病种分值': 'disease_value',
    }
    
    def __init__(self, config: ImportConfig = None):
        """
        初始化导入器
        
        Args:
            config: 导入配置
        """
        self.config = config or ImportConfig()
    
    def import_file(self, file_path: str) -> ImportResult:
        """
        导入文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            导入结果
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            return ImportResult(
                total_rows=0,
                imported_rows=0,
                failed_rows=0,
                import_log=[f"文件不存在: {file_path}"]
            )
        
        # 根据文件类型选择导入方法
        suffix = file_path.suffix.lower()
        
        if suffix in ['.xlsx', '.xls']:
            return self.import_excel(file_path)
        elif suffix == '.csv':
            return self.import_csv(file_path)
        elif suffix == '.xml':
            return self.import_xml(file_path)
        elif suffix == '.json':
            return self.import_json(file_path)
        else:
            return ImportResult(
                total_rows=0,
                imported_rows=0,
                failed_rows=0,
                import_log=[f"不支持的文件格式: {suffix}"]
            )
    
    def import_excel(self, file_path: str) -> ImportResult:
        """导入Excel文件"""
        try:
            df = pd.read_excel(
                file_path,
                sheet_name=self.config.sheet_name,
                header=self.config.header_row,
                encoding=self.config.encoding if hasattr(pd, 'read_excel') else None
            )
            return self._process_dataframe(df)
        except Exception as e:
            return ImportResult(
                total_rows=0,
                imported_rows=0,
                failed_rows=0,
                import_log=[f"导入Excel文件失败: {str(e)}"]
            )
    
    def import_csv(self, file_path: str) -> ImportResult:
        """导入CSV文件"""
        try:
            df = pd.read_csv(
                file_path,
                header=self.config.header_row,
                encoding=self.config.encoding
            )
            return self._process_dataframe(df)
        except Exception as e:
            return ImportResult(
                total_rows=0,
                imported_rows=0,
                failed_rows=0,
                import_log=[f"导入CSV文件失败: {str(e)}"]
            )
    
    def import_xml(self, file_path: str) -> ImportResult:
        """导入XML文件"""
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            
            records = []
            failed_reasons = {}
            
            for elem in root.findall('.//record'):
                try:
                    data = {}
                    for child in elem:
                        data[child.tag] = child.text
                    
                    record = self._convert_to_medical_record(data)
                    if record:
                        records.append(record)
                    else:
                        failed_reasons["数据转换失败"] = failed_reasons.get("数据转换失败", 0) + 1
                except Exception as e:
                    failed_reasons[str(e)] = failed_reasons.get(str(e), 0) + 1
            
            return ImportResult(
                total_rows=len(root.findall('.//record')),
                imported_rows=len(records),
                failed_rows=len(root.findall('.//record')) - len(records),
                failed_reasons=failed_reasons,
                records=records,
                import_log=[f"成功导入{len(records)}条记录"]
            )
        except Exception as e:
            return ImportResult(
                total_rows=0,
                imported_rows=0,
                failed_rows=0,
                import_log=[f"导入XML文件失败: {str(e)}"]
            )
    
    def import_json(self, file_path: str) -> ImportResult:
        """导入JSON文件"""
        try:
            with open(file_path, 'r', encoding=self.config.encoding) as f:
                data = json.load(f)
            
            if isinstance(data, list):
                records_data = data
            elif isinstance(data, dict) and 'records' in data:
                records_data = data['records']
            else:
                records_data = [data]
            
            records = []
            failed_reasons = {}
            
            for item in records_data:
                try:
                    record = self._convert_to_medical_record(item)
                    if record:
                        records.append(record)
                    else:
                        failed_reasons["数据转换失败"] = failed_reasons.get("数据转换失败", 0) + 1
                except Exception as e:
                    failed_reasons[str(e)] = failed_reasons.get(str(e), 0) + 1
            
            return ImportResult(
                total_rows=len(records_data),
                imported_rows=len(records),
                failed_rows=len(records_data) - len(records),
                failed_reasons=failed_reasons,
                records=records,
                import_log=[f"成功导入{len(records)}条记录"]
            )
        except Exception as e:
            return ImportResult(
                total_rows=0,
                imported_rows=0,
                failed_rows=0,
                import_log=[f"导入JSON文件失败: {str(e)}"]
            )
    
    def _process_dataframe(self, df: pd.DataFrame) -> ImportResult:
        """处理DataFrame数据"""
        records = []
        failed_reasons = {}
        
        # 列名映射
        column_mapping = self._map_columns(df.columns.tolist())
        
        for idx, row in df.iterrows():
            try:
                # 转换为字典
                data = {}
                for col in df.columns:
                    mapped_name = column_mapping.get(col, col)
                    data[mapped_name] = row[col]
                
                record = self._convert_to_medical_record(data)
                if record:
                    records.append(record)
                else:
                    failed_reasons["数据转换失败"] = failed_reasons.get("数据转换失败", 0) + 1
            except Exception as e:
                failed_reasons[str(e)] = failed_reasons.get(str(e), 0) + 1
        
        return ImportResult(
            total_rows=len(df),
            imported_rows=len(records),
            failed_rows=len(df) - len(records),
            failed_reasons=failed_reasons,
            records=records,
            import_log=[f"成功导入{len(records)}条记录"]
        )
    
    def _map_columns(self, columns: List[str]) -> Dict[str, str]:
        """映射列名"""
        mapping = {}
        
        for col in columns:
            col_lower = col.lower().strip()
            
            # 尝试4101A字段映射
            if col_lower in self.FIELD_MAPPING_4101A:
                mapping[col] = self.FIELD_MAPPING_4101A[col_lower]
            # 尝试简化字段映射
            elif col in self.SIMPLE_FIELD_MAPPING:
                mapping[col] = self.SIMPLE_FIELD_MAPPING[col]
            # 尝试去除空格后的匹配
            else:
                col_no_space = col.replace(' ', '')
                if col_no_space in self.SIMPLE_FIELD_MAPPING:
                    mapping[col] = self.SIMPLE_FIELD_MAPPING[col_no_space]
        
        return mapping
    
    def _convert_to_medical_record(self, data: Dict) -> Optional[MedicalRecord]:
        """转换为MedicalRecord对象"""
        try:
            # 获取字段值，提供默认值
            def get_value(key, default=""):
                value = data.get(key, default)
                if value is None or pd.isna(value):
                    return default
                return str(value).strip()
            
            def get_decimal(key, default=Decimal("0")):
                value = data.get(key, default)
                if value is None or pd.isna(value):
                    return default
                try:
                    return Decimal(str(value))
                except:
                    return default
            
            def get_int(key, default=0):
                value = data.get(key, default)
                if value is None or pd.isna(value):
                    return default
                try:
                    return int(float(value))
                except:
                    return default
            
            # 创建MedicalRecord
            record = MedicalRecord(
                record_id=get_value('record_id'),
                settlement_id=get_value('settlement_id'),
                patient_id=get_value('patient_id'),
                visit_id=get_value('visit_id'),
                hospital_code=get_value('hospital_code'),
                hospital_name=get_value('hospital_name'),
                hospital_level=get_value('hospital_level'),
                main_diag_code=get_value('main_diag_code'),
                main_diag_name=get_value('main_diag_name'),
                related_diag_code=get_value('related_diag_code_1'),
                main_oprn_code=get_value('main_oprn_code'),
                main_oprn_name=get_value('main_oprn_name'),
                related_oprn_code=get_value('related_oprn_code_1'),
                total_cost=get_decimal('total_cost'),
                drug_cost=get_decimal('drug_cost'),
                material_cost=get_decimal('material_cost'),
                consumable_cost=get_decimal('consumable_cost'),
                exam_cost=get_decimal('exam_cost'),
                treatment_cost=get_decimal('treatment_cost'),
                nursing_cost=get_decimal('nursing_cost'),
                admission_date=get_value('admission_date'),
                discharge_date=get_value('discharge_date'),
                los=get_int('los'),
                discharge_status=get_value('discharge_status'),
                dip_disease_code=get_value('dip_disease_code'),
                dip_disease_name=get_value('dip_disease_name'),
                disease_value=get_decimal('disease_value')
            )
            
            # 存储其他诊断和其他手术信息（用于后续处理）
            record.other_diag_codes = [
                get_value('related_diag_code_1'),
                get_value('related_diag_code_2'),
                get_value('related_diag_code_3'),
                get_value('related_diag_code_4'),
                get_value('related_diag_code_5')
            ]
            record.other_oprn_codes = [
                get_value('related_oprn_code_1'),
                get_value('related_oprn_code_2'),
                get_value('related_oprn_code_3'),
                get_value('related_oprn_code_4'),
                get_value('related_oprn_code_5')
            ]
            
            # 验证必填字段
            if not record.record_id and not record.settlement_id:
                return None
            if not record.hospital_code:
                return None
            
            return record
            
        except Exception as e:
            return None
    
    def import_from_dataframe(self, df: pd.DataFrame) -> ImportResult:
        """从DataFrame导入数据"""
        return self._process_dataframe(df)
    
    def _map_item(self, item: Dict) -> Dict:
        """将单条记录的中文/4101A 字段名映射为内部英文键（与 import_from_dataframe 一致）。"""
        mapped = {}
        for col, value in item.items():
            col_lower = str(col).lower().strip()
            if col_lower in self.FIELD_MAPPING_4101A:
                mapped[self.FIELD_MAPPING_4101A[col_lower]] = value
            elif col in self.SIMPLE_FIELD_MAPPING:
                mapped[self.SIMPLE_FIELD_MAPPING[col]] = value
            else:
                col_no_space = str(col).replace(' ', '')
                if col_no_space in self.SIMPLE_FIELD_MAPPING:
                    mapped[self.SIMPLE_FIELD_MAPPING[col_no_space]] = value
                else:
                    mapped[col] = value
        return mapped

    def import_from_dict_list(self, data_list: List[Dict]) -> ImportResult:
        """从字典列表导入数据"""
        records = []
        failed_reasons = {}

        for item in data_list:
            try:
                # 先按中文字段映射为内部英文键，再转换为 MedicalRecord
                mapped_item = self._map_item(item)
                record = self._convert_to_medical_record(mapped_item)
                if record:
                    records.append(record)
                else:
                    failed_reasons["数据转换失败"] = failed_reasons.get("数据转换失败", 0) + 1
            except Exception as e:
                failed_reasons[str(e)] = failed_reasons.get(str(e), 0) + 1
        
        return ImportResult(
            total_rows=len(data_list),
            imported_rows=len(records),
            failed_rows=len(data_list) - len(records),
            failed_reasons=failed_reasons,
            records=records,
            import_log=[f"成功导入{len(records)}条记录"]
        )


def create_importer() -> SettlementDataImporter:
    """创建默认导入器"""
    return SettlementDataImporter()


def create_importer_with_config(config: ImportConfig) -> SettlementDataImporter:
    """创建带配置的导入器"""
    return SettlementDataImporter(config)
