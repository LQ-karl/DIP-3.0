"""回归测试：Web 测算的病种分值必须真正计算并在分组结果表格中可见。

根因：之前分组表格(tab1)直接从 grouping_results(DiseaseGroup) 取 disease_value，
而 DiseaseGroup 的该字段默认 0（成组阶段从未赋值）；真实分值在 value_results 上。
本测试保证 calculate_all_values 算出非零分值，且 _merge_value_results_to_mixed
折叠后与 grouping 的成组键完全对齐，使 tab1 的 value_map 取得到值。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from decimal import Decimal

from src.models.models import MedicalRecord, DiseaseGroup, GroupType
from src.core.value_calculator_selectable import (
    DIPValueCalculator, create_average_cost_config, ValueCalculationResult,
)
import web.app as A


def _mk(code, cost, dip):
    return MedicalRecord(
        record_id=code, settlement_id=code, patient_id=code, visit_id=code,
        hospital_code="H1", hospital_name="H",
        hospital_level="三级", main_diag_code=code.split("-")[0], main_diag_name="诊断",
        main_oprn_code="", main_oprn_name="", total_cost=Decimal(str(cost)),
        drug_cost=Decimal("0"), material_cost=Decimal("0"),
        dip_disease_code=dip,
    )


def _group(code, diag3, case_count, avg_cost):
    return DiseaseGroup(
        disease_code=code, disease_name="n", main_diag_code=diag3, main_diag_name="n",
        main_oprn_code="", main_oprn_name="", group_type=GroupType.CORE,
        case_count=case_count, avg_cost=Decimal(str(avg_cost)),
    )


def test_calculate_all_values_nonzero():
    recs = [
        _mk("I50.9-00", 10000, "I50.9-00"),
        _mk("I50.9-00", 12000, "I50.9-00"),
        _mk("E11.9-00", 8000, "E11.9-00"),
    ]
    vc = DIPValueCalculator(create_average_cost_config())
    vals = vc.calculate_all_values(recs)
    # 每个病种都应算出非零病种分值
    for v in vals:
        assert float(v.disease_value) > 0, f"{v.dip_code} 病种分值为 0"
        assert float(v.city_avg_cost) > 0


def test_merge_value_alignment_with_grouping():
    # 构造聚类：2 个核心(I50.9 5例 / E11.9 6例) + 3 个未达阈值(<5)按 diag3 折叠为综合
    temp_groups = {
        "I50.9-00": _group("I50.9-00", "I50", 5, 10000),
        "E11.9-00": _group("E11.9-00", "E11", 6, 8000),
        "J44.1-00": _group("J44.1-00", "J44", 2, 9000),   # <5 -> MIX_J44
        "J44.2-00": _group("J44.2-00", "J44", 1, 9500),   # <5 -> MIX_J44
        "N18.5-00": _group("N18.5-00", "N18", 3, 7000),   # <5 -> MIX_N18
    }
    recs = [
        _mk("I50.9-00", 10000, "I50.9-00"),
        _mk("E11.9-00", 8000, "E11.9-00"),
        _mk("J44.1-00", 9000, "J44.1-00"),
        _mk("J44.2-00", 9500, "J44.2-00"),
        _mk("N18.5-00", 7000, "N18.5-00"),
    ]
    threshold = 5
    core, mixed_spec, code_to_mixed = A._build_core_mixed(temp_groups, threshold)
    # grouping 侧的成组键
    grouping_codes = [g.disease_code for g in core] + list(mixed_spec.keys())

    vc = DIPValueCalculator(create_average_cost_config())
    vals = vc.calculate_all_values(recs)
    merged = A._merge_value_results_to_mixed(vals, temp_groups, threshold, vc, recs)

    # 1) 合并后不再残留被折叠的原码
    leaked = [v.dip_code for v in merged if v.dip_code in code_to_mixed]
    assert not leaked, f"仍残留被折叠原码: {leaked}"

    # 2) 每个 grouping 成组键都能在 value_results 找到 -> tab1 的 value_map 取得到值
    val_map = {v.dip_code: v for v in merged}
    missing = [c for c in grouping_codes if c not in val_map]
    assert not missing, f"分组键在 value_results 缺失: {missing}"

    # 3) 综合病种分值应为非零（加权平均）
    for mk in mixed_spec:
        assert float(val_map[mk].disease_value) > 0, f"{mk} 综合病种分值为 0"

    # 4) 病例总数守恒
    assert sum(v.case_count for v in merged) == 5
