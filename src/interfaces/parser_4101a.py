"""
DIP按病种分值分组测算工具 - 4101A接口数据解析模块

基于《医疗保障信息平台定点医药机构接口规范》
依据: DIP3.0版技术规范（征求意见稿）第16-17页
- 病人诊疗数据变量
- 医疗收费信息数据变量

编码标准:
- 《医疗保障疾病诊断分类与代码（ICD-10）》（2.0版）
- 《医疗保障手术操作分类与代码（ICD-9-CM-3）》
"""
import json
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Any
from decimal import Decimal
from datetime import datetime

from ..models.models import MedicalRecord


class Interface4101AParser:
    """
    4101A接口数据解析器
    
    依据: DIP3.0版技术规范（征求意见稿）第16-17页
    - 病人诊疗数据变量
    - 医疗收费信息数据变量
    """
    
    # ============================================================
    # 接口字段映射（依据DIP3.0规范字段）
    # ============================================================
    FIELD_MAPPING = {
        # 一、基础信息 [DIP3.0规范][4101A]
        "setl_list_id": "record_id",  # 清单流水号
        "setl_id": "settlement_id",  # 结算ID
        "psn_no": "patient_id",  # 人员编号
        "mdtrt_id": "visit_id",  # 就诊ID
        "fixmedins_code": "hospital_code",  # 定点医药机构代码
        "fixmedins_name": "hospital_name",  # 定点医药机构名称
        "fixmedins_lv": "hospital_level",  # 医保结算等级
        
        # 二、病人诊疗数据变量-基本信息 [DIP3.0规范]
        "psn_name": "patient_name",  # 患者姓名
        "psn_sex": "gender",  # 性别
        "brdy": "birth_date",  # 出生日期
        "age": "age",  # 年龄
        "day_age": "day_age",  # 天龄
        "certno": "id_number",  # 证件号码
        "psn_type": "insurance_type",  # 医保类型
        
        # 三、病人诊疗数据变量-住院诊疗信息 [DIP3.0规范]
        "med_type": "visit_type",  # 住院医疗类型
        "adm_route": "admission_route",  # 入院途径
        "treat_type": "treatment_category",  # 治疗类别
        "adm_time": "admission_date",  # 入院时间
        "adm_dept_code": "admission_dept",  # 入院科别
        "dscg_time": "discharge_date",  # 出院时间
        "dscg_dept_codg": "discharge_dept",  # 出院科别
        "real_hosp_days": "los",  # 实际住院天数
        
        # 四、诊断信息 [DIP3.0规范][4101A][标准编码:ICD-10]
        "main_diag_code": "main_diag_code",  # 主要诊断代码
        "main_diag_name": "main_diag_name",  # 主要诊断名称
        "scd_dscg_main_diag_code": "related_diag_code",  # 相关诊断代码
        "scd_dscg_main_diag_name": "related_diag_name",  # 相关诊断名称
        
        # 五、手术操作信息 [DIP3.0规范][4101A][标准编码:ICD-9-CM-3]
        "oprn_oprt_code": "main_oprn_code",  # 主要手术操作代码
        "oprn_oprt_name": "main_oprn_name",  # 主要手术操作名称
        
        # 六、费用信息 [DIP3.0规范][4101A]
        "totamt": "total_cost",  # 医疗总费用
        "fund_pay": "fund_pay",  # 医保统筹基金支付
        "suppay": "supplementary_pay",  # 补充医疗保险支付
        "medical_aid_pay": "medical_aid_pay",  # 医疗救助支付
        "self_pay": "self_pay",  # 个人自付
        "self_exp": "self_expense",  # 个人自费
        "acct_pay": "account_pay",  # 个人账户支付
        "cash_pay": "cash_pay",  # 个人现金支付
        
        # 七、离院信息 [DIP3.0规范]
        "out_invst_flag": "discharge_status",  # 出院状态
        "dscg_way": "discharge_method",  # 离院方式
        "readmit_plan": "readmission_plan",  # 出院31天内再住院计划
    }
    
    # 节点标识
    NODE_IDENTIFIERS = {
        "data": "主数据节点",
        "basicinfo": "基本信息节点",
        "medinsinfo": "医疗机构信息节点",
        "diaginfo": "诊断信息节点",
        "oprninfo": "手术操作信息节点",
        "feedetl": "费用明细节点",
        "icuinfo": "重症监护信息节点",
        "bldinfo": "输血信息节点",
    }
    
    # 费用类别映射（依据《医保药品分类与代码》《医保医用耗材分类与代码》《医疗服务项目分类与代码》）
    FEE_CATEGORY_MAPPING = {
        "11": "西药费",  # 《医保药品分类与代码》西药
        "12": "中成药费",  # 《医保药品分类与代码》中成药
        "13": "中草药费",  # 《医保药品分类与代码》中药饮片
        "21": "检查费",  # 《医疗服务项目分类与代码》检查
        "22": "治疗费",  # 《医疗服务项目分类与代码》治疗
        "23": "手术费",  # 《医疗服务项目分类与代码》手术
        "24": "护理费",  # 《医疗服务项目分类与代码》护理
        "25": "材料费",  # 《医保医用耗材分类与代码》
        "26": "床位费",  # 《医疗服务项目分类与代码》床位
        "27": "其他费",  # 其他费用
    }
    
    def __init__(self):
        self.errors = []
        self.warnings = []
    
    def parse_json(self, json_data: str) -> List[MedicalRecord]:
        """
        解析JSON格式的4101A接口数据
        
        Args:
            json_data: JSON格式数据
            
        Returns:
            医疗记录列表
        """
        try:
            data = json.loads(json_data)
            return self._parse_json_data(data)
        except json.JSONDecodeError as e:
            self.errors.append(f"JSON解析错误: {str(e)}")
            return []
    
    def parse_json_file(self, file_path: str) -> List[MedicalRecord]:
        """
        解析JSON文件格式的4101A接口数据
        
        Args:
            file_path: JSON文件路径
            
        Returns:
            医疗记录列表
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return self._parse_json_data(data)
        except Exception as e:
            self.errors.append(f"文件读取错误: {str(e)}")
            return []
    
    def _parse_json_data(self, data: Dict) -> List[MedicalRecord]:
        """
        解析JSON数据
        
        Args:
            data: 解析后的JSON数据
            
        Returns:
            医疗记录列表
        """
        records = []
        
        # 处理单条或多条数据
        if "data" in data:
            data_node = data["data"]
            if isinstance(data_node, list):
                for item in data_node:
                    record = self._parse_single_record(item)
                    if record:
                        records.append(record)
            elif isinstance(data_node, dict):
                record = self._parse_single_record(data_node)
                if record:
                    records.append(record)
        
        return records
    
    def _parse_single_record(self, data: Dict) -> Optional[MedicalRecord]:
        """
        解析单条记录
        
        依据: DIP3.0版技术规范（征求意见稿）第16-17页
        - 病人诊疗数据变量
        - 医疗收费信息数据变量
        
        Args:
            data: 单条记录数据
            
        Returns:
            医疗记录
        """
        try:
            # ============================================================
            # 一、基础信息 [DIP3.0规范][4101A]
            # ============================================================
            record = MedicalRecord(
                record_id=str(data.get("setl_list_id", "")),  # 清单流水号
                settlement_id=str(data.get("setl_id", "")),  # 结算ID
                patient_id=str(data.get("psn_no", "")),  # 人员编号
                visit_id=str(data.get("mdtrt_id", "")),  # 就诊ID
                hospital_code=str(data.get("fixmedins_code", "")),  # 定点医药机构代码
                hospital_name=str(data.get("fixmedins_name", "")),  # 定点医药机构名称
                hospital_level=str(data.get("fixmedins_lv", "")),  # 医保结算等级
            )
            
            # ============================================================
            # 二、病人诊疗数据变量-基本信息 [DIP3.0规范]
            # ============================================================
            record.insurance_id = str(data.get("ins_no", ""))  # 医保编号
            record.case_number = str(data.get("case_no", ""))  # 病案号
            record.gender = self._map_gender(str(data.get("psn_sex", "")))  # 性别
            record.birth_date = str(data.get("brdy", ""))  # 出生日期
            record.age = int(data.get("age", 0))  # 年龄
            record.day_age = int(data.get("day_age", 0))  # 天龄
            record.id_type = str(data.get("cert_type", ""))  # 患者证件类别
            record.id_number = str(data.get("certno", ""))  # 患者证件号码
            record.occupation = str(data.get("occu_type", ""))  # 职业
            record.insurance_type = str(data.get("psn_type", ""))  # 医保类型
            record.special_person_type = str(data.get("spc_psn_type", ""))  # 特殊人员类型
            record.insurance_region = str(data.get("ins_area", ""))  # 参保地
            record.birth_weight = Decimal(str(data.get("birty_wt", 0)))  # 新生儿出生体重
            record.admission_weight = Decimal(str(data.get("adm_wt", 0)))  # 新生儿入院体重
            
            # ============================================================
            # 三、病人诊疗数据变量-住院诊疗信息 [DIP3.0规范]
            # ============================================================
            record.visit_type = str(data.get("med_type", ""))  # 住院医疗类型
            record.admission_route = str(data.get("adm_route", ""))  # 入院途径
            record.treatment_category = str(data.get("treat_type", ""))  # 治疗类别
            record.admission_date = str(data.get("adm_time", ""))  # 入院时间
            record.admission_dept = str(data.get("adm_dept_code", ""))  # 入院科别
            record.transfer_dept = str(data.get("trns_dept_code", ""))  # 转科科别
            record.discharge_date = str(data.get("dscg_time", ""))  # 出院时间
            record.discharge_dept = str(data.get("dscg_dept_codg", ""))  # 出院科别
            record.los = int(data.get("real_hosp_days", 0))  # 实际住院天数
            record.emergency_diag = str(data.get("er_diag_code", ""))  # 门（急）诊诊断
            
            # ============================================================
            # 四、诊断信息 [DIP3.0规范][4101A][标准编码:ICD-10]
            # ============================================================
            diag_info = data.get("diaginfo", [])
            if diag_info:
                related_diag_codes = []
                related_diag_names = []
                for diag in diag_info:
                    if diag.get("maindiag_flag") == "1":  # 主诊断标志
                        record.main_diag_code = str(diag.get("diag_code", ""))  # 主要诊断代码
                        record.main_diag_name = str(diag.get("diag_name", ""))  # 主要诊断名称
                    else:
                        related_diag_codes.append(str(diag.get("diag_code", "")))
                        related_diag_names.append(str(diag.get("diag_name", "")))
                
                # 相关诊断代码（其他诊断1-5）
                record.related_diag_code = "|".join(related_diag_codes[:5])
                record.related_diag_name = "|".join(related_diag_names[:5])
            
            record.admission_condition = str(data.get("adm_cond", ""))  # 入院病情
            record.diag_count = int(data.get("diag_cnt", 0))  # 诊断代码计数
            
            # ============================================================
            # 五、手术操作信息 [DIP3.0规范][4101A][标准编码:ICD-9-CM-3]
            # ============================================================
            oprn_info = data.get("oprninfo", [])
            if oprn_info:
                related_oprn_codes = []
                related_oprn_names = []
                for oprn in oprn_info:
                    if oprn.get("main_oprn_flag") == "1":  # 主要手术标志
                        record.main_oprn_code = str(oprn.get("oprn_oprt_code", ""))  # 主要手术操作代码
                        record.main_oprn_name = str(oprn.get("oprn_oprt_name", ""))  # 主要手术操作名称
                    else:
                        related_oprn_codes.append(str(oprn.get("oprn_oprt_code", "")))
                        related_oprn_names.append(str(oprn.get("oprn_oprt_name", "")))
                
                # 相关手术操作代码（其他手术1-5）
                record.related_oprn_code = "|".join(related_oprn_codes[:5])
                record.related_oprn_name = "|".join(related_oprn_names[:5])
            
            record.oprn_count = int(data.get("oprn_cnt", 0))  # 手术及操作代码计数
            
            # ============================================================
            # 六、肿瘤及特殊治疗信息 [DIP3.0规范]
            # ============================================================
            record.tumor_metastasis = str(data.get("tumor_metastasis", ""))  # 肿瘤转移情况
            record.tumor_stage = str(data.get("tumor_stage", ""))  # 肿瘤分期
            record.chemo_status = str(data.get("chemo_status", ""))  # 放化疗状态
            
            # ============================================================
            # 七、医疗资源使用信息 [DIP3.0规范]
            # ============================================================
            record.ventilator_hours = int(data.get("ventilator_hours", 0))  # 呼吸机使用时间
            record.coma_hours = int(data.get("coma_hours", 0))  # 颅脑损伤患者昏迷时间
            record.icu_type = str(data.get("icu_type", ""))  # 重症监护病房类型
            record.icu_hours = int(data.get("icu_hours", 0))  # 进出重症监护室时间
            
            # ============================================================
            # 八、费用信息 [DIP3.0规范][4101A]
            # ============================================================
            fee_details = data.get("feedetl", [])
            if fee_details:
                self._parse_fee_details(record, fee_details)
            else:
                # 尝试从顶层提取费用
                record.total_cost = Decimal(str(data.get("totamt", 0)))
            
            # 医保结算信息
            record.fund_pay = Decimal(str(data.get("fund_pay", 0)))  # 医保统筹基金支付
            record.supplementary_pay = Decimal(str(data.get("suppay", 0)))  # 补充医疗保险支付
            record.medical_aid_pay = Decimal(str(data.get("medical_aid_pay", 0)))  # 医疗救助支付
            record.other_pay = Decimal(str(data.get("other_pay", 0)))  # 其他支付
            record.self_pay = Decimal(str(data.get("self_pay", 0)))  # 个人自付
            record.self_expense = Decimal(str(data.get("self_exp", 0)))  # 个人自费
            record.account_pay = Decimal(str(data.get("acct_pay", 0)))  # 个人账户支付
            record.cash_pay = Decimal(str(data.get("cash_pay", 0)))  # 个人现金支付
            record.payment_method = str(data.get("pay_type", ""))  # 医保支付方式
            
            # ============================================================
            # 九、离院信息 [DIP3.0规范]
            # ============================================================
            discharge_status = data.get("out_invst_flag", "")
            record.discharge_status = self._map_discharge_status(discharge_status)  # 出院状态
            record.discharge_method = str(data.get("dscg_way", ""))  # 离院方式
            record.readmission_plan = str(data.get("readmit_plan", ""))  # 出院31天内再住院计划
            
            return record
            
        except Exception as e:
            self.errors.append(f"记录解析错误: {str(e)}")
            return None
    
    def _parse_fee_details(self, record: MedicalRecord, fee_details: List[Dict]):
        """
        解析费用明细
        
        Args:
            record: 医疗记录
            fee_details: 费用明细列表
        """
        total_cost = Decimal("0")
        drug_cost = Decimal("0")
        consumable_cost = Decimal("0")
        exam_cost = Decimal("0")
        treatment_cost = Decimal("0")
        material_cost = Decimal("0")
        nursing_cost = Decimal("0")
        
        for fee in fee_details:
            amount = Decimal(str(fee.get("amt", 0)))
            fee_type = str(fee.get("med_chrgitm_type", ""))
            
            total_cost += amount
            
            # 根据费用类别分类
            if fee_type in ["11", "12", "13"]:  # 药品
                drug_cost += amount
            elif fee_type == "21":  # 检查
                exam_cost += amount
            elif fee_type == "22":  # 治疗
                treatment_cost += amount
            elif fee_type == "25":  # 材料
                material_cost += amount
            elif fee_type == "24":  # 护理
                nursing_cost += amount
        
        record.total_cost = total_cost
        record.drug_cost = drug_cost
        record.consumable_cost = consumable_cost
        record.exam_cost = exam_cost
        record.treatment_cost = treatment_cost
        record.material_cost = material_cost
        record.nursing_cost = nursing_cost
    
    def _map_discharge_status(self, status_code: str) -> str:
        """
        映射出院状态
        
        依据: DIP3.0版技术规范（征求意见稿）第16-17页
        - 出院状态（死亡、医嘱出院、非医嘱出院、转院）
        
        Args:
            status_code: 出院状态代码
            
        Returns:
            出院状态名称
        """
        status_mapping = {
            "1": "医嘱离院",
            "2": "医嘱转院",
            "3": "医嘱转社区",
            "4": "非医嘱离院",
            "5": "死亡",
            "9": "其他"
        }
        return status_mapping.get(status_code, "其他")
    
    def _map_gender(self, gender_code: str) -> str:
        """
        映射性别
        
        依据: DIP3.0版技术规范（征求意见稿）第16-17页
        - 性别
        
        Args:
            gender_code: 性别代码
            
        Returns:
            性别名称
        """
        gender_mapping = {
            "1": "男",
            "2": "女",
            "9": "未说明",
            "0": "未说明"
        }
        return gender_mapping.get(gender_code, "未说明")
    
    def parse_xml(self, xml_data: str) -> List[MedicalRecord]:
        """
        解析XML格式的4101A接口数据
        
        Args:
            xml_data: XML格式数据
            
        Returns:
            医疗记录列表
        """
        try:
            root = ET.fromstring(xml_data)
            return self._parse_xml_data(root)
        except ET.ParseError as e:
            self.errors.append(f"XML解析错误: {str(e)}")
            return []
    
    def _parse_xml_data(self, root: ET.Element) -> List[MedicalRecord]:
        """
        解析XML数据
        
        Args:
            root: XML根节点
            
        Returns:
            医疗记录列表
        """
        records = []
        
        # 查找所有记录节点
        for record_elem in root.findall(".//record"):
            record = self._parse_xml_record(record_elem)
            if record:
                records.append(record)
        
        return records
    
    def _parse_xml_record(self, elem: ET.Element) -> Optional[MedicalRecord]:
        """
        解析单条XML记录
        
        Args:
            elem: XML元素
            
        Returns:
            医疗记录
        """
        try:
            record = MedicalRecord(
                record_id=self._get_xml_text(elem, "setl_list_id"),
                settlement_id=self._get_xml_text(elem, "setl_id"),
                patient_id=self._get_xml_text(elem, "psn_no"),
                visit_id=self._get_xml_text(elem, "mdtrt_id"),
                hospital_code=self._get_xml_text(elem, "fixmedins_code"),
                hospital_name=self._get_xml_text(elem, "fixmedins_name")
            )
            
            # 提取其他字段...
            record.main_diag_code = self._get_xml_text(elem, "main_diag_code")
            record.main_diag_name = self._get_xml_text(elem, "main_diag_name")
            record.main_oprn_code = self._get_xml_text(elem, "oprn_oprt_code")
            record.main_oprn_name = self._get_xml_text(elem, "oprn_oprt_name")
            
            # 费用信息
            total_cost_text = self._get_xml_text(elem, "totamt")
            if total_cost_text:
                record.total_cost = Decimal(total_cost_text)
            
            # 住院信息
            record.los = int(self._get_xml_text(elem, "real_hosp_days") or "0")
            
            return record
            
        except Exception as e:
            self.errors.append(f"XML记录解析错误: {str(e)}")
            return None
    
    def _get_xml_text(self, elem: ET.Element, tag: str) -> str:
        """获取XML元素文本"""
        child = elem.find(tag)
        return child.text if child is not None and child.text else ""
    
    def parse_excel(self, file_path: str) -> List[MedicalRecord]:
        """
        解析Excel格式的费用数据
        
        Args:
            file_path: Excel文件路径
            
        Returns:
            医疗记录列表
        """
        try:
            import pandas as pd
            df = pd.read_excel(file_path)
            return self._parse_dataframe(df)
        except Exception as e:
            self.errors.append(f"Excel解析错误: {str(e)}")
            return []
    
    def _parse_dataframe(self, df) -> List[MedicalRecord]:
        """
        解析DataFrame数据
        
        Args:
            df: pandas DataFrame
            
        Returns:
            医疗记录列表
        """
        records = []
        
        for _, row in df.iterrows():
            try:
                record = MedicalRecord(
                    record_id=str(row.get("清单流水号", "")),
                    settlement_id=str(row.get("结算ID", "")),
                    patient_id=str(row.get("人员编号", "")),
                    visit_id=str(row.get("就诊ID", "")),
                    hospital_code=str(row.get("定点医药机构编号", "")),
                    hospital_name=str(row.get("定点医药机构名称", ""))
                )
                
                # 诊断信息
                record.main_diag_code = str(row.get("主要诊断代码", ""))
                record.main_diag_name = str(row.get("主要诊断名称", ""))
                record.related_diag_code = str(row.get("相关诊断代码", ""))
                record.related_diag_name = str(row.get("相关诊断名称", ""))
                
                # 手术操作信息
                record.main_oprn_code = str(row.get("主要手术操作代码", ""))
                record.main_oprn_name = str(row.get("主要手术操作名称", ""))
                record.related_oprn_code = str(row.get("相关手术操作代码", ""))
                record.related_oprn_name = str(row.get("相关手术操作名称", ""))
                
                # 费用信息
                record.total_cost = Decimal(str(row.get("医疗总费用", 0)))
                record.drug_cost = Decimal(str(row.get("药品费用", 0)))
                record.consumable_cost = Decimal(str(row.get("耗材费用", 0)))
                record.exam_cost = Decimal(str(row.get("检查费用", 0)))
                record.treatment_cost = Decimal(str(row.get("治疗费用", 0)))
                
                # 住院信息
                record.admission_date = str(row.get("入院日期", ""))
                record.discharge_date = str(row.get("出院日期", ""))
                record.los = int(row.get("住院天数", 0))
                record.discharge_status = str(row.get("出院状态", ""))
                
                records.append(record)
                
            except Exception as e:
                self.errors.append(f"行解析错误: {str(e)}")
                continue
        
        return records
    
    def get_errors(self) -> List[str]:
        """获取解析错误列表"""
        return self.errors
    
    def get_warnings(self) -> List[str]:
        """获取解析警告列表"""
        return self.warnings
    
    def clear_messages(self):
        """清空错误和警告信息"""
        self.errors.clear()
        self.warnings.clear()
