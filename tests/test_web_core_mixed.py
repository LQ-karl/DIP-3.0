"""Web 测算：核心病种阈值折叠 + 综合病种归集 + value_results 一致性的回归测试。

回归重点：阈值设置后，未达阈值的病种必须折叠为综合病种（而非各自成组），
且分组结果与分值结果必须一致标注 核心病种/综合病种。
"""
import sys
from decimal import Decimal

sys.path.insert(0, ".")
import web.app as A
from web.app import _build_core_mixed, _merge_value_results_to_mixed
from src.models.models import DiseaseGroup, GroupType
from src.core.value_calculator_selectable import (
    DIPValueCalculator, create_average_cost_config, ValueCalculationResult,
)


def _mk(code, diag, cases, avg):
    return DiseaseGroup(
        disease_code=code, disease_name=diag, main_diag_code=diag,
        main_diag_name=diag, group_type=GroupType.CORE,
        case_count=cases, avg_cost=Decimal(str(avg)),
    )


def test_build_core_mixed_folds_below_threshold():
    tg = {
        "A00.1-00": _mk("A00.1-00", "A00.1", 10, 1000),  # 核心
        "B00.1-00": _mk("B00.1-00", "B00.1", 2, 2000),   # <5 -> MIX_内科诊疗组_B00
        "B00.2-00": _mk("B00.2-00", "B00.2", 3, 2500),   # <5 同 diag3 -> MIX_内科诊疗组_B00
        "C00.1-00": _mk("C00.1-00", "C00.1", 1, 900),    # <5 -> MIX_内科诊疗组_C00
    }
    core, mixed_spec, code_to_mixed = _build_core_mixed(tg, 5)
    assert len(core) == 1
    assert core[0].disease_code == "A00.1-00"
    assert core[0].group_type == GroupType.CORE
    # 未达阈值的码全部映射走（无手术操作 -> 内科诊疗组）
    assert code_to_mixed == {
        "B00.1-00": "MIX_内科诊疗组_B00",
        "B00.2-00": "MIX_内科诊疗组_B00",
        "C00.1-00": "MIX_内科诊疗组_C00",
    }
    assert set(mixed_spec.keys()) == {"MIX_内科诊疗组_B00", "MIX_内科诊疗组_C00"}
    # MIX_内科诊疗组_B00 聚合 B00.1(2)+B00.2(3)=5 例，加权费用=2000*2+2500*3=11500
    assert mixed_spec["MIX_内科诊疗组_B00"]["case_count"] == 5
    assert mixed_spec["MIX_内科诊疗组_B00"]["cost_sum"] == Decimal("11500")


def test_merge_value_results_consistent():
    tg = {
        "A00.1-00": _mk("A00.1-00", "A00.1", 10, 1000),
        "B00.1-00": _mk("B00.1-00", "B00.1", 2, 2000),
        "B00.2-00": _mk("B00.2-00", "B00.2", 3, 2500),
    }
    vals = [
        ValueCalculationResult(
            dip_code=code, disease_name=g.disease_name, case_count=g.case_count,
            total_cost=Decimal(str(g.case_count * 1000)), avg_cost=Decimal("1000"),
            disease_value=Decimal("50"), drug_value=Decimal("0"), consumable_value=Decimal("0"),
        )
        for code, g in tg.items()
    ]
    vc = DIPValueCalculator(create_average_cost_config())
    out = _merge_value_results_to_mixed(vals, tg, 5, vc, records=[])
    codes = {v.dip_code for v in out}
    assert "A00.1-00" in codes                       # 核心保留
    assert "B00.1-00" not in codes and "B00.2-00" not in codes  # 已折叠
    mix = [v for v in out if v.dip_code == "MIX_内科诊疗组_B00"]
    assert len(mix) == 1
    assert mix[0].case_count == 5
    assert sum(v.case_count for v in out) == 15      # 病例总数守恒
