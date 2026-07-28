"""
DIP测算工具 - 分值测算可选方法测试（真实断言版）
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decimal import Decimal
from src.models.models import MedicalRecord
from src.utils.paths import get_output_dir
from src.core.value_calculator_selectable import (
    DIPValueCalculator, ValueCalculationConfig, ValueCalculationMethod,
    create_average_cost_config, create_reference_disease_config,
    create_standard_quota_config, create_drug_value_config,
    create_consumable_value_config
)


def generate_test_records():
    """生成测试病例数据（3 个病种，共 45 例）"""
    records = []

    for i in range(20):  # 三级甲等 - 心内科 急性心肌梗死
        records.append(MedicalRecord(
            record_id=f"REC{i+1:04d}", settlement_id=f"SET{i+1:04d}", patient_id=f"P{i+1:04d}",
            visit_id=f"V{i+1:04d}", hospital_code="H001", hospital_name="市人民医院",
            hospital_level="三级甲等", main_diag_code="I21.0", main_diag_name="急性心肌梗死",
            total_cost=Decimal(str(15000 + i * 500)), drug_cost=Decimal(str(6000 + i * 200)),
            material_cost=Decimal(str(4000 + i * 150)), admission_date="2024-01-15",
            discharge_date="2024-01-27", los=12, discharge_status="治愈", dip_disease_code="I21-1",
        ))

    for i in range(15):  # 二级甲等 - 普外科 急性阑尾炎
        records.append(MedicalRecord(
            record_id=f"REC{i+21:04d}", settlement_id=f"SET{i+21:04d}", patient_id=f"P{i+21:04d}",
            visit_id=f"V{i+21:04d}", hospital_code="H002", hospital_name="区中心医院",
            hospital_level="二级甲等", main_diag_code="K35.9", main_diag_name="急性阑尾炎",
            total_cost=Decimal(str(10000 + i * 400)), drug_cost=Decimal(str(3000 + i * 150)),
            material_cost=Decimal(str(2500 + i * 100)), admission_date="2024-02-10",
            discharge_date="2024-02-18", los=8, discharge_status="治愈", dip_disease_code="K35-1",
        ))

    for i in range(10):  # 儿科 急性上呼吸道感染
        records.append(MedicalRecord(
            record_id=f"REC{i+36:04d}", settlement_id=f"SET{i+36:04d}", patient_id=f"P{i+36:04d}",
            visit_id=f"V{i+36:04d}", hospital_code="H001", hospital_name="市人民医院",
            hospital_level="三级甲等", main_diag_code="J06.9", main_diag_name="急性上呼吸道感染",
            total_cost=Decimal(str(3000 + i * 200)), drug_cost=Decimal(str(1200 + i * 80)),
            material_cost=Decimal(str(500 + i * 50)), admission_date="2024-03-10",
            discharge_date="2024-03-15", los=5, discharge_status="治愈", dip_disease_code="J06-1",
        ))

    return records


def _assert_value_results(results, value_attr="disease_value", n_groups=3, total_cases=45):
    """共享断言：结果应为 3 个病种、合计 45 例，且指定分值字段均 > 0。"""
    assert isinstance(results, list), "计算结果应为列表"
    assert len(results) == n_groups, f"期望 {n_groups} 个病种，实际 {len(results)}"
    assert sum(r.case_count for r in results) == total_cases, "病例数合计应为 45"
    for r in results:
        val = getattr(r, value_attr)
        assert isinstance(val, Decimal), f"{value_attr} 应为 Decimal"
        assert val > 0, f"病种 {getattr(r, 'dip_code', '?')} 的 {value_attr} 应大于 0"


def _by_code(results, code):
    for r in results:
        if r.dip_code == code:
            return r
    raise AssertionError(f"未找到病种 {code}")


def test_average_cost_method():
    """平均费用法 RWi = mi / M × 1000"""
    records = generate_test_records()
    calculator = DIPValueCalculator(create_average_cost_config())
    results = calculator.calculate_all_values(records)

    _assert_value_results(results)
    # 费用最高的 I21-1 应获得最高的病种分值
    top = max(results, key=lambda r: r.disease_value)
    assert top.dip_code == "I21-1", "急性心肌梗死(费用最高)应获得最高分值"

    out = str(get_output_dir() / "test_value_average_cost.xlsx")
    calculator.export_results(results, out)
    from pathlib import Path
    assert Path(out).exists(), "平均费用法结果未导出"


def test_reference_disease_method():
    """基准病种费用法，K35-1 作为基准病种(费用≈12800)其 RW 应≈1000"""
    records = generate_test_records()
    config = create_reference_disease_config(
        reference_code="K35-1", reference_cost=Decimal("12800")
    )
    calculator = DIPValueCalculator(config)
    results = calculator.calculate_all_values(records)

    _assert_value_results(results)
    k35 = _by_code(results, "K35-1")
    # mi(K35-1)=12800, M=12800 → RW = 1000
    assert abs(float(k35.disease_value) - 1000) < 1.0, f"基准病种 K35-1 的 RW 应≈1000，实际 {k35.disease_value}"

    out = str(get_output_dir() / "test_value_reference_disease.xlsx")
    calculator.export_results(results, out)
    from pathlib import Path
    assert Path(out).exists()


def test_standard_quota_method():
    """标准定额法，K35-1 的 RW = mi/标准定额 = 12800/100 = 128"""
    records = generate_test_records()
    config = create_standard_quota_config(standard_quota=Decimal("100"))
    calculator = DIPValueCalculator(config)
    results = calculator.calculate_all_values(records)

    _assert_value_results(results)
    k35 = _by_code(results, "K35-1")
    assert abs(float(k35.disease_value) - 128) < 1.0, f"标准定额法下 K35-1 的 RW 应≈128，实际 {k35.disease_value}"


def test_drug_value_method():
    """药品分值法，各病种药品分值应 > 0"""
    records = generate_test_records()
    calculator = DIPValueCalculator(create_drug_value_config())
    results = calculator.calculate_all_values(records)

    _assert_value_results(results, value_attr="drug_value")
    # 急性心肌梗死药费最高，药品分值应最高
    top = max(results, key=lambda r: r.drug_value)
    assert top.dip_code == "I21-1"

    out = str(get_output_dir() / "test_value_drug.xlsx")
    calculator.export_results(results, out)
    from pathlib import Path
    assert Path(out).exists()


def test_consumable_value_method():
    """耗材分值法，各病种耗材分值应 > 0"""
    records = generate_test_records()
    calculator = DIPValueCalculator(create_consumable_value_config())
    results = calculator.calculate_all_values(records)

    _assert_value_results(results, value_attr="consumable_value")
    out = str(get_output_dir() / "test_value_consumable.xlsx")
    calculator.export_results(results, out)
    from pathlib import Path
    assert Path(out).exists()


def test_custom_config():
    """自定义配置：疾病/药品/耗材分值均启用且 > 0，并生成报告"""
    records = generate_test_records()
    config = ValueCalculationConfig(
        calculation_method=ValueCalculationMethod.AVERAGE_COST,
        base_value=Decimal("500"),
        enable_drug_value=True,
        enable_consumable_value=True,
        year_weights={
            2022: Decimal("0.15"), 2023: Decimal("0.25"), 2024: Decimal("0.60"),
        },
    )
    calculator = DIPValueCalculator(config)
    results = calculator.calculate_all_values(records)

    _assert_value_results(results)
    for r in results:
        assert r.drug_value > 0, "自定义配置已启用药品分值，应 > 0"
        assert r.consumable_value > 0, "自定义配置已启用耗材分值，应 > 0"

    report = calculator.generate_report(results)
    assert report, "generate_report 应返回非空报告"


if __name__ == "__main__":
    test_average_cost_method()
    test_reference_disease_method()
    test_standard_quota_method()
    test_drug_value_method()
    test_consumable_value_method()
    test_custom_config()
    print("test_value_calculation 全部通过")
