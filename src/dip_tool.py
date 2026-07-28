"""
DIP按病种分值分组测算工具 - 主模块
提供统一的API接口
"""
from typing import List, Dict, Optional
from decimal import Decimal
from pathlib import Path

import pandas as pd

from .models.models import (
    DiseaseGroup, MedicalRecord, HospitalCoefficient,
    DIPSettlementResult, SimulationParams, CalculationMethod
)
from .core.grouping_engine import DIPGroupingEngine
from .core.value_calculator import (
    ValueCalculator, HospitalCoefficientCalculator, AuxiliaryClassifier
)
from .core.payment_calculator import (
    PointValueCalculator, PaymentStandardCalculator, SettlementCalculator
)
from .core.local_directory_generator import LocalDirectoryGenerator
from .interfaces.parser_4101a import Interface4101AParser
from .utils.data_loader import DataLoader, DiseaseGroupLoader
from .utils.paths import get_data_dir, get_output_dir


class DIPGroupingTool:
    """DIP按病种分值分组测算工具"""
    
    def __init__(self, data_dir: str = None):
        """
        初始化工具
        
        Args:
            data_dir: 数据目录路径
        """
        self.data_dir = Path(data_dir) if data_dir else get_data_dir()
        
        # 初始化各模块
        self.grouping_engine = DIPGroupingEngine()
        self.value_calculator = ValueCalculator()
        self.hospital_coeff_calculator = HospitalCoefficientCalculator()
        self.auxiliary_classifier = AuxiliaryClassifier()
        self.point_value_calculator = PointValueCalculator()
        self.payment_calculator = PaymentStandardCalculator()
        
        # 数据加载器
        self.data_loader = DataLoader(data_dir)
        self.disease_group_loader = DiseaseGroupLoader(data_dir)
        
        # 本地目录库生成器
        self.local_directory_generator = LocalDirectoryGenerator()
        
        # 4101A接口解析器
        self.parser_4101a = Interface4101AParser()
        
        # 加载的数据
        self.disease_groups = {}
        self.hospital_coefficients = {}
        self.icd10_mapping = {}
        self.icd9_mapping = {}
        self.cci_mapping = {}
    
    def load_data(self):
        """加载所有基础数据"""
        try:
            self.icd10_mapping = self.data_loader.get_icd10_mapping()
            self.icd9_mapping = self.data_loader.get_icd9_mapping()
            self.cci_mapping = self.data_loader.get_cci_mapping()
            print(f"数据加载完成: ICD-10映射 {len(self.icd10_mapping)} 条, "
                  f"ICD-9映射 {len(self.icd9_mapping)} 条, "
                  f"CCI映射 {len(self.cci_mapping)} 条")
        except Exception as e:
            print(f"数据加载警告: {e}")
    
    def set_threshold(self, threshold: int):
        """
        设置核心病种临界值
        
        Args:
            threshold: 临界值
        """
        self.grouping_engine.set_threshold(threshold)
    
    def set_calculation_method(self, method: CalculationMethod):
        """
        设置分值计算方法
        
        Args:
            method: 计算方法
        """
        self.value_calculator.method = method
    
    def group_records(self, records: List[MedicalRecord]) -> Dict[str, DiseaseGroup]:
        """
        对病例记录进行分组
        
        Args:
            records: 住院病例记录列表
            
        Returns:
            病种分组结果
        """
        return self.grouping_engine.group_records(records)
    
    def calculate_disease_values(
        self,
        groups: List[DiseaseGroup],
        total_avg_cost: Decimal
    ) -> List[DiseaseGroup]:
        """
        计算病种分值
        
        Args:
            groups: 病种组合列表
            total_avg_cost: 全局平均住院费用
            
        Returns:
            更新分值后的病种组合列表
        """
        return self.value_calculator.batch_calculate_values(groups, total_avg_cost)
    
    def calculate_hospital_coefficients(
        self,
        hospital_data: List[Dict],
        city_avg_cost: Decimal
    ) -> List[HospitalCoefficient]:
        """
        计算医疗机构调节系数
        
        Args:
            hospital_data: 医疗机构数据列表
            city_avg_cost: 全市平均住院费用
            
        Returns:
            调节系数列表
        """
        return self.hospital_coeff_calculator.calculate_hospital_coefficients(
            hospital_data, city_avg_cost
        )
    
    def calculate_point_value(
        self,
        weighted_total_cost: Decimal,
        weighted_total_value: Decimal
    ) -> Decimal:
        """
        计算点值
        
        Args:
            weighted_total_cost: 加权年度住院总费用
            weighted_total_value: 加权年度总分值
            
        Returns:
            点值
        """
        return self.point_value_calculator.calculate_initial_point_value(
            weighted_total_cost, weighted_total_value
        )
    
    def calculate_settlement_point_value(
        self,
        fund_amount: Decimal,
        payment_ratio: Decimal,
        total_dip_value: Decimal
    ) -> Decimal:
        """
        计算结算点值
        
        Args:
            fund_amount: 当年医保基金DIP付费总额
            payment_ratio: 医保支付比例
            total_dip_value: 当年度DIP总分值
            
        Returns:
            结算点值
        """
        return self.point_value_calculator.calculate_settlement_point_value(
            fund_amount, payment_ratio, total_dip_value
        )
    
    def calculate_payment_standard(
        self,
        disease_value: Decimal,
        point_value: Decimal,
        hospital_coefficient: Decimal = Decimal("1.0"),
        auxiliary_coefficient: Decimal = Decimal("1.0")
    ) -> Decimal:
        """
        计算支付标准
        
        Args:
            disease_value: 病种分值
            point_value: 点值
            hospital_coefficient: 医疗机构调节系数
            auxiliary_coefficient: 辅助分型调节系数
            
        Returns:
            支付标准
        """
        self.payment_calculator.set_point_value(point_value)
        return self.payment_calculator.calculate_adjusted_payment_standard(
            disease_value, hospital_coefficient, auxiliary_coefficient
        )
    
    def parse_4101a_data(self, data) -> List[MedicalRecord]:
        """
        解析4101A接口数据
        
        Args:
            data: JSON字符串、XML字符串或文件路径
            
        Returns:
            医疗记录列表
        """
        if isinstance(data, str):
            if data.endswith('.json'):
                return self.parser_4101a.parse_json_file(data)
            elif data.endswith('.xml'):
                with open(data, 'r', encoding='utf-8') as f:
                    xml_data = f.read()
                return self.parser_4101a.parse_xml(xml_data)
            elif data.strip().startswith('{') or data.strip().startswith('['):
                return self.parser_4101a.parse_json(data)
            elif data.strip().startswith('<'):
                return self.parser_4101a.parse_xml(data)
        elif isinstance(data, dict):
            return self.parser_4101a.parse_json(str(data))
        
        return []
    
    def load_cost_data_from_excel(self, file_path: str) -> List[MedicalRecord]:
        """
        从Excel文件加载费用数据
        
        Args:
            file_path: Excel文件路径
            
        Returns:
            医疗记录列表
        """
        return self.parser_4101a.parse_excel(file_path)
    
    def simulate_settlement(
        self,
        records: List[MedicalRecord],
        params: SimulationParams
    ) -> Dict:
        """
        模拟测算
        
        Args:
            records: 住院病例记录列表
            params: 模拟测算参数
            
        Returns:
            模拟测算结果
        """
        # 1. 分组
        disease_groups = self.group_records(records)
        
        # 2. 计算分值
        total_cost = sum(r.total_cost for r in records)
        total_avg_cost = total_cost / len(records) if records else Decimal("0")
        
        groups_list = list(disease_groups.values())
        groups_with_values = self.calculate_disease_values(groups_list, total_avg_cost)
        
        # 3. 更新分组结果
        for group in groups_with_values:
            disease_groups[group.disease_code] = group
        
        # 4. 计算总分值
        total_value = Decimal("0")
        for record in records:
            disease_code = record.dip_disease_code
            if disease_code in disease_groups:
                total_value += disease_groups[disease_code].disease_value
        
        # 5. 计算点值
        weighted_total_cost = self.point_value_calculator.calculate_weighted_total_cost(
            [total_cost]  # 简化：使用单年数据
        )
        weighted_total_value = self.point_value_calculator.calculate_weighted_total_value(
            [total_value]
        )
        
        point_value = self.calculate_point_value(weighted_total_cost, weighted_total_value)
        
        # 6. 设置支付标准计算器
        self.payment_calculator.set_point_value(point_value)
        
        # 7. 生成报告
        report = {
            "grouping_statistics": self.grouping_engine.get_grouping_statistics(),
            "value_calculation": {
                "total_cost": float(total_cost),
                "total_avg_cost": float(total_avg_cost),
                "total_value": float(total_value),
                "point_value": float(point_value)
            },
            "disease_groups": [
                {
                    "code": g.disease_code,
                    "name": g.disease_name,
                    "case_count": g.case_count,
                    "avg_cost": float(g.avg_cost),
                    "disease_value": float(g.disease_value)
                }
                for g in groups_with_values
            ]
        }
        
        return report
    
    def generate_report(self, results: Dict, output_dir: str = None) -> str:
        """
        生成报告文件
        
        Args:
            results: 计算结果
            output_dir: 输出目录
            
        Returns:
            报告文件路径
        """
        output_dir = output_dir if output_dir else str(get_output_dir())
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        # 生成分值汇总表
        if "disease_groups" in results:
            df = pd.DataFrame(results["disease_groups"])
            report_path = output_path / "disease_values_report.xlsx"
            df.to_excel(report_path, index=False)
            return str(report_path)
        
        return ""
    
    def generate_local_directory(
        self,
        settlement_file: str,
        national_directory_file: str = None,
        threshold: int = 15,
        output_dir: str = None
    ) -> str:
        """
        生成本地目录库（核心功能）
        
        根据医院上传的医保清单数据 + 国家目录库 → 生成本地DIP目录库
        
        Args:
            settlement_file: 医保清单数据文件路径（Excel/CSV）
            national_directory_file: 国家目录库文件路径（可选）
            threshold: 核心病种临界值（病例数阈值）
            output_dir: 输出目录
            
        Returns:
            本地目录库文件路径
        """
        self.local_directory_generator.set_threshold(threshold)
        
        return self.local_directory_generator.generate_local_directory(
            settlement_file=settlement_file,
            national_directory_file=national_directory_file,
            output_dir=output_dir if output_dir else str(get_output_dir())
        )
