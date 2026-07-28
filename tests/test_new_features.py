"""
DIP测算工具 - 新功能综合测试（真实断言版）
测试内容：
1. 医保结算清单导入（4101A接口）
2. 本地目录库输出（DIP3.0格式）
3. 辅助目录分型表格
4. 医疗机构等级系数选择
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decimal import Decimal
from src.utils.paths import get_output_dir
from pathlib import Path
from src.models.models import MedicalRecord, DiseaseGroup
from src.interfaces.settlement_importer import SettlementDataImporter, ImportConfig
from src.core.local_directory_exporter import LocalDirectoryExporter
from src.core.auxiliary_directory_exporter import AuxiliaryDirectoryExporter
from src.core.hospital_coefficient_selector import (
    HospitalCoefficientSelector, CoefficientCalculationConfig,
    CoefficientCalculationMethod,
    create_basic_only_config, create_bonus_only_config,
    create_basic_bonus_config, create_disease_level_config,
    create_comprehensive_config
)


def generate_test_records():
    """生成测试病例数据（2 个病种：I21-1×20, K35-1×15，共 35 例）"""
    records = []

    for i in range(20):  # 三级甲等 - 心内科 急性心肌梗死
        records.append(MedicalRecord(
            record_id=f"REC{i+1:04d}", settlement_id=f"SET{i+1:04d}", patient_id=f"P{i+1:04d}",
            visit_id=f"V{i+1:04d}", hospital_code="H001", hospital_name="市人民医院",
            hospital_level="三级甲等", main_diag_code="I21.0", main_diag_name="急性心肌梗死",
            related_diag_code="E11.9,I10", main_oprn_code="36.07",
            total_cost=Decimal(str(15000 + i * 500)), drug_cost=Decimal(str(6000 + i * 200)),
            material_cost=Decimal(str(4000 + i * 150)), admission_date="2024-01-15",
            discharge_date="2024-01-27", los=12, discharge_status="治愈",
            dip_disease_code="I21-1", disease_value=Decimal("150"),
        ))

    for i in range(15):  # 二级甲等 - 普外科 急性阑尾炎
        records.append(MedicalRecord(
            record_id=f"REC{i+21:04d}", settlement_id=f"SET{i+21:04d}", patient_id=f"P{i+21:04d}",
            visit_id=f"V{i+21:04d}", hospital_code="H002", hospital_name="区中心医院",
            hospital_level="二级甲等", main_diag_code="K35.9", main_diag_name="急性阑尾炎",
            main_oprn_code="47.0", total_cost=Decimal(str(10000 + i * 400)),
            drug_cost=Decimal(str(3000 + i * 150)), material_cost=Decimal(str(2500 + i * 100)),
            admission_date="2024-02-10", discharge_date="2024-02-18", los=8,
            discharge_status="治愈", dip_disease_code="K35-1", disease_value=Decimal("100"),
        ))

    return records


def test_settlement_import():
    """医保结算清单导入：2 条中文键记录应全部成功导入。"""
    importer = SettlementDataImporter()
    data_list = [
        {
            '住院号': 'IMP001', '结算ID': 'SET001', '人员编号': 'P001', '就诊ID': 'V001',
            '医院代码': 'H001', '医院名称': '测试医院', '医院等级': '三级甲等',
            '入院日期': '2024-01-15', '出院日期': '2024-01-25',
            '主诊断': 'I21.0', '主诊断名称': '急性心肌梗死',
            '总费用': 18000, '药品费用': 7000, '材料费用': 5000,
            '住院天数': 10, 'DIP编码': 'I21-1', '病种分值': 150,
        },
        {
            '住院号': 'IMP002', '结算ID': 'SET002', '人员编号': 'P002', '就诊ID': 'V002',
            '医院代码': 'H002', '医院名称': '社区医院', '医院等级': '二级甲等',
            '入院日期': '2024-02-10', '出院日期': '2024-02-18',
            '主诊断': 'K35.9', '主诊断名称': '急性阑尾炎',
            '总费用': 12000, '药品费用': 4000, '材料费用': 3000,
            '住院天数': 8, 'DIP编码': 'K35-1', '病种分值': 100,
        },
    ]

    result = importer.import_from_dict_list(data_list)
    assert result.total_rows == 2, f"总行数应 2，实际 {result.total_rows}"
    assert result.imported_rows == 2, f"应成功导入 2 条，实际 {result.imported_rows}，失败原因 {result.failed_reasons}"
    assert result.failed_rows == 0, f"失败行数应 0，实际 {result.failed_rows}"
    assert len(result.records) == 2
    assert result.records[0].hospital_name == '测试医院'
    assert result.records[0].main_diag_name == '急性心肌梗死'
    assert result.records[0].total_cost == Decimal("18000")


def test_local_directory_export():
    """本地目录库导出（DIP3.0 格式）：生成 2 个病种组并导出 Excel。"""
    records = generate_test_records()
    exporter = LocalDirectoryExporter()

    directory = exporter.generate_from_records(records)
    assert directory.version, "目录库版本不应为空"
    assert len(directory.records) == 2, f"应为 2 个病种组，实际 {len(directory.records)}"
    for rec in directory.records:
        assert rec.dip_code, f"病种编码不应为空: {rec.disease_name}"
        assert isinstance(rec.disease_value, Decimal)
        assert rec.disease_value >= 0, f"病种 {rec.dip_code} 的病种分值应非负"

    output_path = str(get_output_dir() / "test_local_directory_dip30.xlsx")
    exporter.export_to_excel(directory, output_path)
    assert Path(output_path).exists(), "DIP3.0 本地目录库未导出"


def test_auxiliary_directory_export():
    """辅助目录分型：35 条记录均应产出分型结果并导出 Excel。"""
    records = generate_test_records()
    exporter = AuxiliaryDirectoryExporter()

    classifications = exporter.classify_records(records)
    assert len(classifications) == 35, f"分型结果应 35 条，实际 {len(classifications)}"
    for c in classifications:
        assert c.max_coefficient is not None and c.max_coefficient > 0, "最高调节系数应 > 0"
        assert c.cci_type is not None and c.severity_type is not None and c.age_type is not None

    output_path = str(get_output_dir() / "test_auxiliary_directory.xlsx")
    exporter.export_to_excel(classifications, output_path)
    assert Path(output_path).exists(), "辅助目录分型表未导出"


def test_hospital_coefficient_selection():
    """医疗机构等级系数选择：5 种配置均能算出最终系数 > 0。"""
    records = generate_test_records()
    hospital_data_list = [
        {
            'hospital_code': 'H001', 'hospital_name': '市人民医院', 'hospital_level': '三级甲等',
            'avg_cost': 18000, 'medical_level': 0.85, 'specialty_score': 0.75,
            'cmi': 1.2, 'performance_score': 0.9, 'agreement_score': 0.85,
        },
        {
            'hospital_code': 'H002', 'hospital_name': '区中心医院', 'hospital_level': '二级甲等',
            'avg_cost': 12000, 'medical_level': 0.7, 'specialty_score': 0.65,
            'cmi': 0.9, 'performance_score': 0.8, 'agreement_score': 0.8,
        },
    ]

    configs = [
        ("仅基本系数", create_basic_only_config()),
        ("仅加成系数", create_bonus_only_config()),
        ("基本+加成系数", create_basic_bonus_config()),
        ("病种级别系数", create_disease_level_config()),
        ("综合系数", create_comprehensive_config()),
    ]

    for config_name, config in configs:
        selector = HospitalCoefficientSelector(config)
        results = selector.batch_calculate(hospital_data_list, records)
        assert len(results) == 2, f"【{config_name}】应返回 2 家医院，实际 {len(results)}"
        for r in results:
            assert r.basic_coefficient > 0, f"【{config_name}】{r.hospital_name} 基本系数应 > 0"
            assert r.final_coefficient > 0, f"【{config_name}】{r.hospital_name} 最终系数应 > 0"

    # 综合系数结果可导出
    selector = HospitalCoefficientSelector(create_comprehensive_config())
    results = selector.batch_calculate(hospital_data_list, records)
    output_path = str(get_output_dir() / "test_hospital_coefficients.xlsx")
    selector.export_coefficients(results, output_path)
    assert Path(output_path).exists(), "医院系数结果未导出"


if __name__ == "__main__":
    test_settlement_import()
    test_local_directory_export()
    test_auxiliary_directory_export()
    test_hospital_coefficient_selection()
    print("test_new_features 全部通过")
