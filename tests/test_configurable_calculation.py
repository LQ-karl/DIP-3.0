"""
测试可配置的测算参数功能（真实断言版）
"""
import sys
sys.path.insert(0, 'F:/DIP')

from decimal import Decimal
from src.core.calculation_config import (
    DIPCalculationConfig, CostType, CalculationType,
    CostCalculationConfig, StatisticalConfig,
    create_default_config, create_full_config,
    create_drug_material_config, create_simple_config
)
from src.core.local_directory_score_configurable import LocalDirectoryScoreCalculator
from src.models.models import MedicalRecord


def generate_test_records():
    """生成测试病例数据（2 个病种：I21-1×20, K35-1×15）"""
    records = []

    for i in range(20):  # 三级甲等 - 心内科 急性心肌梗死
        records.append(MedicalRecord(
            record_id=f"REC{i+1:04d}", settlement_id=f"SET{i+1:04d}", patient_id=f"P{i+1:04d}",
            visit_id=f"V{i+1:04d}", hospital_code="H001", hospital_name="市人民医院",
            hospital_level="三级甲等", main_diag_code="I21.0", main_diag_name="急性心肌梗死",
            related_diag_code="E11.9,I10", main_oprn_code="36.07",
            total_cost=Decimal(str(15000 + i * 500)), drug_cost=Decimal(str(6000 + i * 200)),
            material_cost=Decimal(str(4000 + i * 150)), consumable_cost=Decimal(str(2000 + i * 100)),
            exam_cost=Decimal(str(1500 + i * 50)), treatment_cost=Decimal(str(1000 + i * 30)),
            nursing_cost=Decimal(str(500 + i * 20)), admission_date="2024-01-15",
            discharge_date="2024-01-27", los=12, discharge_status="治愈", dip_disease_code="I21-1",
        ))

    for i in range(15):  # 二级甲等 - 普外科 急性阑尾炎
        records.append(MedicalRecord(
            record_id=f"REC{i+21:04d}", settlement_id=f"SET{i+21:04d}", patient_id=f"P{i+21:04d}",
            visit_id=f"V{i+21:04d}", hospital_code="H002", hospital_name="区中心医院",
            hospital_level="二级甲等", main_diag_code="K35.9", main_diag_name="急性阑尾炎",
            main_oprn_code="47.0", total_cost=Decimal(str(10000 + i * 400)),
            drug_cost=Decimal(str(3000 + i * 150)), material_cost=Decimal(str(2500 + i * 100)),
            consumable_cost=Decimal(str(1500 + i * 80)), exam_cost=Decimal(str(1000 + i * 40)),
            treatment_cost=Decimal(str(800 + i * 25)), nursing_cost=Decimal(str(400 + i * 15)),
            admission_date="2024-02-10", discharge_date="2024-02-18", los=8,
            discharge_status="治愈", dip_disease_code="K35-1",
        ))

    return records


def _assert_results_shape(results, expected_cases=None):
    """共享断言：结果含 I21-1/K35-1，病例数正确，final_score 与费用统计健全。"""
    assert isinstance(results, dict)
    assert set(results.keys()) == {"I21-1", "K35-1"}, f"病种键异常: {list(results.keys())}"
    if expected_cases:
        for code, n in expected_cases.items():
            assert results[code]['total_cases'] == n, \
                f"{code} 病例数应为 {n}，实际 {results[code]['total_cases']}"
    for code, r in results.items():
        assert r['final_score'] is not None and r['final_score'] > 0, f"{code} 最终分值应 > 0"
        assert isinstance(r['cost_statistics'], dict) and len(r['cost_statistics']) >= 1


def _cost_type_keys(results):
    keys = set()
    for r in results.values():
        for k in r['cost_statistics'].keys():
            keys.add(str(k))
    return keys


def test_default_config():
    """默认配置：只计算总费用（费用类型数 = 1）。"""
    config = create_default_config()
    calculator = LocalDirectoryScoreCalculator(config)
    results = calculator.batch_calculate_local_directory(generate_test_records())

    _assert_results_shape(results, expected_cases={"I21-1": 20, "K35-1": 15})
    for r in results.values():
        assert len(r['cost_statistics']) == 1, "默认配置应只含 1 个费用类型"
        assert any("总费用" in k for k in r['cost_statistics'].keys()), "默认配置应含 总费用"


def test_full_config():
    """完整配置：所有费用类型（数量应多于默认配置）。"""
    config = create_full_config()
    calculator = LocalDirectoryScoreCalculator(config)
    results = calculator.batch_calculate_local_directory(generate_test_records())

    _assert_results_shape(results)
    for r in results.values():
        assert len(r['cost_statistics']) >= 2, "完整配置应含多个费用类型"


def test_drug_material_config():
    """药品+材料配置：应包含 TOTAL 与 DRUG（及 MATERIAL）。"""
    config = create_drug_material_config()
    calculator = LocalDirectoryScoreCalculator(config)
    results = calculator.batch_calculate_local_directory(generate_test_records())

    _assert_results_shape(results)
    keys = _cost_type_keys(results)
    assert any("总费用" in k for k in keys), "应含 总费用"
    assert any("药品费用" in k for k in keys), "应含 药品费用"


def test_simple_config():
    """简单配置：不剔除异常值，仍含 TOTAL 且 final_score > 0。"""
    config = create_simple_config()
    calculator = LocalDirectoryScoreCalculator(config)
    results = calculator.batch_calculate_local_directory(generate_test_records())

    _assert_results_shape(results)
    assert any("总费用" in k for k in _cost_type_keys(results)), "简单配置应含 总费用"


def test_custom_config():
    """自定义配置：启用百分位 25/75，统计结果应含 p25/p75。"""
    config = DIPCalculationConfig(
        cost_configs=[
            CostCalculationConfig(cost_type=CostType.TOTAL, enabled=True),
            CostCalculationConfig(cost_type=CostType.DRUG, enabled=True),
        ],
        statistical_config=StatisticalConfig(
            calculate_mean=True, calculate_median=True,
            calculate_std=False, calculate_cv=False,
            calculate_percentiles=True, percentiles=[25, 75],
            remove_outliers=False,
        ),
        decimal_places=2,
    )
    calculator = LocalDirectoryScoreCalculator(config)
    results = calculator.batch_calculate_local_directory(generate_test_records())

    _assert_results_shape(results)
    for r in results.values():
        for stats in r['cost_statistics'].values():
            assert 'p25' in stats and 'p75' in stats, "自定义配置应计算 P25/P75 分位数"
    assert config.statistical_config.percentiles == [25, 75]


def test_dynamic_config():
    """动态修改配置：增删费用类型时，费用类型数应相应增减。"""
    config = create_default_config()
    calculator = LocalDirectoryScoreCalculator(config)
    records = generate_test_records()

    results = calculator.batch_calculate_local_directory(records)
    n0 = len(next(iter(results.values()))['cost_statistics'])
    assert n0 == 1, "初始默认配置应只有 1 个费用类型"

    config.add_cost_config(CostType.DRUG)
    results = calculator.batch_calculate_local_directory(records)
    n1 = len(next(iter(results.values()))['cost_statistics'])
    assert n1 > n0, "添加 DRUG 后费用类型数应增加"

    config.add_cost_config(CostType.MATERIAL)
    results = calculator.batch_calculate_local_directory(records)
    n2 = len(next(iter(results.values()))['cost_statistics'])
    assert n2 > n1, "添加 MATERIAL 后费用类型数应再增加"

    config.disable_cost_config(CostType.DRUG)
    results = calculator.batch_calculate_local_directory(records)
    n3 = len(next(iter(results.values()))['cost_statistics'])
    assert n3 < n2, "禁用 DRUG 后费用类型数应减少"


def test_config_export():
    """配置导出：to_dict 应含关键配置段。"""
    config = create_full_config()
    config_dict = config.to_dict()
    assert isinstance(config_dict, dict)
    for key in ('cost_configs', 'statistical_config', 'hospital_coefficient_config', 'auxiliary_config'):
        assert key in config_dict, f"导出字典缺少键: {key}"


if __name__ == "__main__":
    test_default_config()
    test_full_config()
    test_drug_material_config()
    test_simple_config()
    test_custom_config()
    test_dynamic_config()
    test_config_export()
    print("test_configurable_calculation 全部通过")
