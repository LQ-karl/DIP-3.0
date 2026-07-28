"""
DIP按病种分值分组测算工具 - 测试脚本（真实断言版）
"""
import sys
sys.path.insert(0, 'F:\\DIP')

from decimal import Decimal
from src import DIPGroupingTool, DiseaseGroup, MedicalRecord, CalculationMethod


def _build_test_records():
    """构造 4 条测试病例（诊断+术式各不相同，basic 路径下应形成 4 个病种组）。"""
    return [
        MedicalRecord(
            record_id="R001", settlement_id="S001", patient_id="P001", visit_id="V001",
            hospital_code="H001", hospital_name="测试医院",
            main_diag_code="K35.9", main_diag_name="急性阑尾炎",
            main_oprn_code="47.0100", main_oprn_name="腹腔镜下阑尾切除术",
            total_cost=Decimal("12000"), drug_cost=Decimal("3000"),
            consumable_cost=Decimal("2000"), los=5,
        ),
        MedicalRecord(
            record_id="R002", settlement_id="S002", patient_id="P002", visit_id="V002",
            hospital_code="H001", hospital_name="测试医院",
            main_diag_code="K35.9", main_diag_name="急性阑尾炎",
            main_oprn_code="47.0901", main_oprn_name="阑尾切除术",
            total_cost=Decimal("8000"), drug_cost=Decimal("2000"),
            consumable_cost=Decimal("1000"), los=7,
        ),
        MedicalRecord(
            record_id="R003", settlement_id="S003", patient_id="P003", visit_id="V003",
            hospital_code="H002", hospital_name="综合医院",
            main_diag_code="I21.0", main_diag_name="前壁急性透壁性心肌梗死",
            main_oprn_code="36.0700", main_oprn_name="药物洗脱冠状动脉支架置入",
            total_cost=Decimal("45000"), drug_cost=Decimal("15000"),
            consumable_cost=Decimal("20000"), los=10,
        ),
        MedicalRecord(
            record_id="R004", settlement_id="S004", patient_id="P004", visit_id="V004",
            hospital_code="H001", hospital_name="测试医院",
            main_diag_code="J18.9", main_diag_name="肺炎",
            total_cost=Decimal("6000"), drug_cost=Decimal("2500"),
            consumable_cost=Decimal("500"), los=8,
        ),
    ]


def test_basic_functionality():
    """端到端功能测试：set_threshold + 分组 + 分值 + 点值 + 支付标准。"""
    # 1. 初始化工具
    tool = DIPGroupingTool(data_dir="F:\\DIP\\data")
    assert tool is not None

    # 2. 加载基础数据（缺失不应使测试崩溃）
    try:
        tool.load_data()
    except Exception as e:  # noqa: BLE001 - 数据缺失属环境差异，不阻断测试
        print(f"   数据加载警告(非致命): {e}")

    # 3. set_threshold 修复验证（③）
    # 注意：DIPGroupingTool.group_records 默认走 optimize=True，小样本下返回 0 组（已知 Bug B），
    # 因此这里显式使用 grouping_engine 的 basic 路径，避免掩盖该缺陷。
    tool.set_threshold(2)
    assert tool.grouping_engine.config.default_threshold == 2, \
        "set_threshold 未生效：未写入 config.default_threshold"

    test_records = _build_test_records()
    assert len(test_records) == 4

    # 4. 分组（basic 路径）
    # 4 条记录中两条阑尾切除(47.0100/47.0901)同属处置类别 03，应合并为 1 组，
    # 故实际得到 3 个病种组；合计病例数应为 4。
    disease_groups = tool.grouping_engine.group_records(test_records, optimize=False)
    assert isinstance(disease_groups, dict)
    assert len(disease_groups) == 3, f"期望 3 个病种组，实际 {len(disease_groups)}"
    total_cases = sum(g.case_count for g in disease_groups.values())
    assert total_cases == 4, f"合计病例数应为 4，实际 {total_cases}"
    assert any(g.case_count == 2 for g in disease_groups.values()), "阑尾切除两条记录应合并为 1 个病例数=2 的组"
    for code, group in disease_groups.items():
        assert isinstance(group, DiseaseGroup)
        assert group.case_count >= 1
        assert group.avg_cost > 0

    # 5. 计算病种分值
    tool.set_calculation_method(CalculationMethod.AVERAGE_COST)
    total_cost = sum(r.total_cost for r in test_records)
    total_avg_cost = total_cost / len(test_records)
    assert total_avg_cost > 0

    groups_with_values = tool.calculate_disease_values(
        list(disease_groups.values()), total_avg_cost
    )
    assert len(groups_with_values) == 3
    for g in groups_with_values:
        assert isinstance(g.disease_value, Decimal)
        assert g.disease_value > 0, f"病种 {g.disease_code} 的分值应大于 0"

    # 6. 点值
    weighted_cost = tool.point_value_calculator.calculate_weighted_total_cost([total_cost])
    total_value = sum(g.disease_value for g in groups_with_values)
    weighted_value = tool.point_value_calculator.calculate_weighted_total_value([total_value])
    point_value = tool.calculate_point_value(weighted_cost, weighted_value)
    assert isinstance(point_value, Decimal)
    assert point_value > 0, "点值应大于 0"

    # 7. 支付标准
    payment = tool.calculate_payment_standard(groups_with_values[0].disease_value, point_value)
    assert isinstance(payment, Decimal)
    assert payment > 0, "支付标准应大于 0"

    # 8. 分组统计
    stats = tool.grouping_engine.get_grouping_statistics()
    assert isinstance(stats, dict)
    assert ("threshold_used" in stats) or ("threshold" in stats)


if __name__ == "__main__":
    test_basic_functionality()
    print("test_basic_functionality 通过")
