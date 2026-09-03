"""辅助分型测算回归测试（子组级 + DIP3.0 §5.2 触发闸门 + 维度竞争）。

验证统一辅助分型引擎 AuxiliaryDirectoryCalculator.build_auxiliary_subgroups
（经 AuxiliaryDirectoryExporter.classify_records 委托）：

  1. 辅助分型发生在「核心病种聚类成组之后」，返回子组级列表
     （核心病种 × 维度 × 子型），而非逐病例一条。
  2. 触发条件（§5.2 三条）：
     (1) 病种病例数 > min_core_cases；
     (2) 某分型评估病例数 > min_subtype_cases；
     (3) 组内费用变异系数偏大（cv_before >= cv_before_threshold，默认 0.7）
         且 经该维度分型后组内费用 CV 下降 >= cv_improvement_threshold
         （默认 0.2，即 20% 以上）；
     三者同时成立才算该维度达标；所有维度均未达标 → 零子组（同质不测算）。
  3. 维度竞争（§(二)）：多个达标维度中取「触发系数(mj/M)最高」者胜出。
  4. 仅对核心病种测算：传 core_disease_codes 时过滤，综合病种不混入。
  5. cv_before 闸门阈值可调（含放宽场景）。
"""
from decimal import Decimal

from src.models.models import MedicalRecord
from src.core.auxiliary_directory_exporter import AuxiliaryDirectoryExporter
from src.core.auxiliary_directory import AuxiliaryDirectoryCalculator


def _rec(record_id, dip, age=50, cost=1000.0, name="测试病种"):
    return MedicalRecord(
        record_id=record_id,
        settlement_id=record_id,
        patient_id=record_id,
        visit_id=record_id,
        hospital_code="H001",
        hospital_name="测试医院",
        dip_disease_code=dip,
        dip_disease_name=name,
        total_cost=Decimal(str(cost)),
        main_diag_code="I50.900",
        related_diag_code="",
        age=age,
    )


def _age_split_records(dip, n=12, elderly_cost=7000.0, adult_cost=1000.0):
    """构造年龄维度高差异病种：一半 85 岁（高费）、一半 40 岁（低费）。

    默认 elderly=7000 / adult=1000 → 组内费用 CV = (7000-1000)/(7000+1000) = 0.75
    （偏大，≥0.7），分型后子型组内 CV≈0 → 下降幅度≈100%（≥20%），触发条件(3)达成。
    """
    recs = []
    half = n // 2
    for i in range(half):
        recs.append(_rec(f"{dip}-E{i}", dip, age=85, cost=elderly_cost))
    for i in range(half):
        recs.append(_rec(f"{dip}-A{i}", dip, age=40, cost=adult_cost))
    return recs


def test_clear_difference_produces_subgroups():
    """组内存在明显费用差异（cv_before=0.75≥0.7 且下降≥20%）→ 拆出子组。"""
    exp = AuxiliaryDirectoryExporter()
    recs = _age_split_records("CORE", n=12)
    subs = exp.classify_records(recs)
    assert len(subs) > 0, "明显差异应产生辅助子组"
    assert all(s.case_count > 0 for s in subs)
    assert all(s.coefficient > 0 for s in subs)
    # 触发维度为年龄特征，且触发时组内 CV 偏大、分型后下降≥20%
    age_subs = [s for s in subs if s.dimension == "年龄特征"]
    assert age_subs, "应沿年龄特征维度分型"
    assert all(s.cv_before >= 0.7 for s in age_subs)
    assert all(s.cv_reduction >= 0.2 for s in age_subs)
    # 竞争胜出维度应被标记
    assert any(s.is_winning_dimension for s in age_subs)


def test_homogeneous_group_no_subgroups():
    """组内同质（所有记录年龄/费用一致）→ 零子组（不测算辅助分型）。"""
    exp = AuxiliaryDirectoryExporter()
    recs = [_rec(f"H{i}", "HOM", age=50, cost=1000.0) for i in range(12)]
    subs = exp.classify_records(recs)
    assert subs == [], "同质病种不应产生任何辅助子组"


def test_core_filter_excludes_non_core():
    """core_disease_codes 过滤：综合病种（未达阈值）不出现在辅助目录中。"""
    exp = AuxiliaryDirectoryExporter()
    recs = _age_split_records("CORE", n=12) + _age_split_records("OTHER", n=12)
    subs = exp.classify_records(recs, core_disease_codes={"CORE"})
    assert len(subs) > 0
    assert all(s.disease_code == "CORE" for s in subs)
    assert not any(s.disease_code == "OTHER" for s in subs)


def test_cv_before_threshold_tuning():
    """cv_before 闸门阈值可调：cv_before=0.5 时默认(0.7)不拆，放宽(0.4)则拆。"""
    exp = AuxiliaryDirectoryExporter()
    # 年龄组均值 1000 vs 3000 → 组内 CV = (3000-1000)/(3000+1000) = 0.5
    recs = _age_split_records("TUNE", n=12, elderly_cost=1000.0, adult_cost=3000.0)
    # 默认闸门 0.7：0.5 < 0.7 → 不测算
    subs_default = exp.classify_records(recs)
    assert subs_default == []
    # 放宽闸门 0.4：0.5 >= 0.4，且分型后下降≈100% ≥20% → 测算
    subs_loose = exp.classify_records(recs, aux_cv_before_threshold=0.4)
    assert len(subs_loose) > 0
    assert all(s.cv_before >= 0.4 for s in subs_loose)


def test_min_core_cases_gate():
    """核心病种病例数不足 min_core_cases → 不测算（样本太少）。"""
    exp = AuxiliaryDirectoryExporter()
    recs = _age_split_records("SMALL", n=8)  # 8 < 默认 10
    subs = exp.classify_records(recs)
    assert subs == []


def test_reduction_gate_blocks_despite_high_cv():
    """组内 CV 偏大但分型后差异未明显改善（下降<20%）→ 不测算。

    构造：青年组与老年组内部费用同样呈高/低双峰（1000/7000 各半），
    沿年龄分型并不能把高费/低费病例分开 → 分型后组内 CV 几乎不变 → 下降≈0。
    """
    exp = AuxiliaryDirectoryExporter()
    recs = []
    for i in range(3):
        recs.append(_rec(f"Y-H{i}", "RED", age=40, cost=7000.0))
        recs.append(_rec(f"Y-L{i}", "RED", age=40, cost=1000.0))
        recs.append(_rec(f"O-H{i}", "RED", age=85, cost=7000.0))
        recs.append(_rec(f"O-L{i}", "RED", age=85, cost=1000.0))
    # 整体费用 6×7000 + 6×1000 → cv_before ≈ 0.75（偏大）
    subs = exp.classify_records(recs)
    assert subs == [], "分型未明显改善差异的病种不应产生辅助子组"


def test_competition_selects_highest_trigger_coefficient():
    """维度竞争（§(二)）：多个达标维度中取触发系数(mj/M)最高者胜出。"""
    calc = AuxiliaryDirectoryCalculator()
    # 两维度均达标；CCI 触发系数(1.8) > 年龄(1.3) → CCI 胜出
    cands = [
        {"dimension": "年龄特征", "cv_before": 0.8, "reduction": 0.30, "trigger": 1.3},
        {"dimension": "CCI", "cv_before": 0.8, "reduction": 0.50, "trigger": 1.8},
    ]
    assert calc._select_winning_dimension(cands, 0.7, 0.2, 0.5) == "CCI"

    # 仅一个维度达标（另一 cv_before/下降未达门槛）→ 该维度胜出
    cands2 = [
        {"dimension": "年龄特征", "cv_before": 0.5, "reduction": 0.10, "trigger": 1.8},
        {"dimension": "CCI", "cv_before": 0.8, "reduction": 0.30, "trigger": 1.3},
    ]
    assert calc._select_winning_dimension(cands2, 0.7, 0.2, 0.5) == "CCI"

    # 无任何维度达标 → 返回 None（该病种不测算）
    cands3 = [{"dimension": "X", "cv_before": 0.5, "reduction": 0.10, "trigger": 2.0}]
    assert calc._select_winning_dimension(cands3, 0.7, 0.2, 0.5) is None


if __name__ == "__main__":
    test_clear_difference_produces_subgroups()
    test_homogeneous_group_no_subgroups()
    test_core_filter_excludes_non_core()
    test_cv_before_threshold_tuning()
    test_min_core_cases_gate()
    test_reduction_gate_blocks_despite_high_cv()
    test_competition_selects_highest_trigger_coefficient()
    print("test_auxiliary_gate.py 全部用例通过")
