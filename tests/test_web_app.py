"""web/app.py（Streamlit 真实产品界面）行为级测试。

使用 Streamlit 官方 AppTest 真正启动 web/app.py 并驱动界面交互，
覆盖：界面渲染、测试数据生成、分组测算、辅助分型（四层成组后的第三步）
全链路。

说明：此前 test_gui*.py 仅覆盖测试文件内部自带的 demo 类（DIPCalculationGUI），
并未触及真实交付界面；本文件首次把 web/app.py 纳入自动化测试。
"""
import os
os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")

import pytest

pytest.importorskip("streamlit")

from streamlit.testing.v1 import AppTest

APP = "web/app.py"


def _by_label(seq, label):
    for w in seq:
        if w.label == label:
            return w
    raise AssertionError(f"未找到控件: {label}")


def test_web_app_renders():
    """界面能正常渲染：侧边栏标题、默认数据导入页、导航 radio 存在。"""
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    assert "DIP3.0测算系统" in [t.value for t in at.title]
    assert "📊 数据导入" in [h.value for h in at.header]
    nav = _by_label(at.radio, "导航菜单")
    assert "📊 数据导入" in nav.options
    assert "🔬 分组测算" in nav.options


def test_web_app_auxiliary_typing_flow():
    """全链路：生成测试数据 → 分组测算 → 辅助分型产出 35 条结果，无异常。"""
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()

    # 1) 选择“测试数据”并生成
    sb = _by_label(at.selectbox, "选择文件类型")
    sb.set_value("测试数据")
    at.run()
    gen = _by_label(at.button, "生成测试数据")
    gen.click()
    at.run()
    records = at.session_state["records"]
    assert len(records) == 35, f"应生成 35 条测试数据，实际 {len(records)}"

    # 2) 切到 分组测算 页并点击 开始测算
    nav = _by_label(at.radio, "导航菜单")
    nav.set_value("🔬 分组测算")
    at.run()
    assert "🔬 分组测算" in [h.value for h in at.header]
    start = next(b for b in at.button if b.label.startswith("🚀"))
    start.click()
    at.run()

    # 3) 验证辅助分型结果（第三步）已写入 session_state，且无异常
    #    at.exception 在无异常时为空 ElementList（falsy），有异常时为非空列表
    assert not at.exception, f"测算抛出异常: {at.exception}"
    aux = at.session_state["auxiliary_results"]
    assert isinstance(aux, list)
    assert len(aux) <= 35, f"辅助目录子组应 <= 35，实际 {len(aux)}"
    for a in aux:
        assert a.coefficient is not None and a.coefficient > 0, "辅助分型系数应 > 0"
        assert isinstance(a.dimension, str) and a.dimension != ""
        assert isinstance(a.subtype, str) and a.subtype != ""
    # 分组测算结果也应存在
    assert len(at.session_state["value_results"]) >= 1


def test_import_df_to_records_alias_headers():
    """导入器兼容测试数据的英文/混合表头，并补读其他诊断、费用、年龄。"""
    import pandas as pd
    from decimal import Decimal
    from web.app import _import_df_to_records

    df = pd.DataFrame([{
        "record_id": "13018120260601001925402379",
        "hospital_code": "H001",
        "hospital_name": "市人民医院",
        "hospital_level": "三级甲等",
        "主要诊断编码": "I50.900",
        "主要诊断名称": "心力衰竭",
        "相关诊断编码": "I50.900|J44.1|I63.9",
        "相关诊断名称": "心力衰竭|慢性阻塞性肺病|脑梗死",
        "医疗总费用": 12345.6,
        "fund_pay": 9000,
        "年龄": 67,
    }])
    recs = _import_df_to_records(df)
    assert len(recs) == 1
    r = recs[0]
    assert r.record_id == "13018120260601001925402379"
    assert r.hospital_code == "H001"
    assert r.main_diag_code == "I50.900"
    # 其他诊断被补读（供 Web 辅助分型 CCI 使用）
    assert r.related_diag_code == "I50.900|J44.1|I63.9"
    assert r.related_diag_name == "心力衰竭|慢性阻塞性肺病|脑梗死"
    assert r.total_cost == Decimal("12345.6")
    assert r.fund_pay == Decimal("9000")
    assert r.age == 67


def test_import_df_to_records_standard_chinese_headers():
    """导入器仍兼容原有标准中文表头（向后兼容，不破坏既有上传路径）。"""
    import pandas as pd
    from decimal import Decimal
    from web.app import _import_df_to_records

    df = pd.DataFrame([{
        "清单流水号": "L001",
        "医院代码": "H002",
        "医院名称": "区中心医院",
        "医院等级": "二级甲等",
        "主要诊断编码": "K35",
        "主要诊断名称": "急性阑尾炎",
        "总费用": 8000,
        "住院天数": 8,
    }])
    recs = _import_df_to_records(df)
    r = recs[0]
    assert r.record_id == "L001"
    assert r.total_cost == Decimal("8000")
    assert r.los == 8
    # 无相关诊断列时默认为空，不应报错
    assert r.related_diag_code == ""


def test_web_grassroot_selection_flow():
    """Web 全链路基层病种遴选：一级医院 A09.9 保守治疗病例 → 核心组标记 is_grassroot。

    口径（用户 2026-09-04 确认）：名录候选 + 核心病种 + 基层占比≥50% + 组内CV≤0.7。
    """
    from decimal import Decimal
    from src.models.models import MedicalRecord

    at = AppTest.from_file(APP, default_timeout=120)
    at.run()

    # 注入 18 例 A09.9（基层名录·保守治疗行）一级医院病例，费用紧凑（CV 极小）
    records = []
    for i in range(18):
        records.append(MedicalRecord(
            record_id=f"G{i+1:04d}", settlement_id=f"GS{i+1:04d}",
            patient_id=f"GP{i+1:04d}", visit_id=f"GV{i+1:04d}",
            hospital_code="H101", hospital_name="社区卫生服务中心", hospital_level="一级",
            gender="男" if i % 2 == 0 else "女",
            birth_date=f"197{i%10}-05-01", age=40 + i % 10,
            insurance_type="城镇职工",
            main_diag_code="A09.9", main_diag_name="未特指病因的胃肠炎和结肠炎",
            admission_date="2024-03-01", discharge_date="2024-03-06", los=5,
            discharge_status="医嘱离院",
            total_cost=Decimal(str(2000 + (i % 3) * 40)),
            drug_cost=Decimal("600"), material_cost=Decimal("100"),
            consumable_cost=Decimal("100"), exam_cost=Decimal("300"),
            treatment_cost=Decimal("900"),
            fund_pay=Decimal("1600"), self_pay=Decimal("400"),
        ))
    at.session_state["records"] = records

    nav = _by_label(at.radio, "导航菜单")
    nav.set_value("🔬 分组测算")
    at.run()
    start = next(b for b in at.button if b.label.startswith("🚀"))
    start.click()
    at.run()
    assert not at.exception, f"测算抛出异常: {at.exception}"

    grp = at.session_state["grouping_results"]
    assert len(grp) >= 1
    grass = [g for g in grp if getattr(g, "is_grassroot", False)]
    assert grass, "A09.9 一级医院保守治疗组应被遴选为基层病种"
    assert all(g.main_diag_code.startswith("A09.9") for g in grass)
    # 该组病例数应为全部 18 例（基层占比 100%、CV≈0，三项校验全过）
    assert sum(g.case_count for g in grass) == 18


def test_web_dictionary_sheet_selector():
    """Web 字典查看页：国家目录库支持切换工作表，「不纳入分组」两个清单可见。

    修复前 `pd.read_excel(path)` 未指定 sheet，只显示第一个 sheet（核心病种），
    另 4 个 sheet（不纳入分组_主要诊断 4742 / 不纳入分组_主要手术操作 4111 /
    基层病种 127 / 结核耐药诊断列表 48）在界面上不可见。
    """
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()

    nav = _by_label(at.radio, "导航菜单")
    nav.set_value("📚 字典查看")
    at.run()
    assert not at.exception, f"字典页抛出异常: {at.exception}"

    # 默认字典 = DIP3.0国家目录库
    dict_sel = _by_label(at.selectbox, "选择字典")
    assert dict_sel.value == "DIP3.0国家目录库"

    # 多 sheet 才会出现「选择工作表」；两个排除清单必须在选项中
    sheet_sel = _by_label(at.selectbox, "选择工作表")
    assert sheet_sel.value == "核心病种"
    for s in ["不纳入分组_主要诊断", "不纳入分组_主要手术操作", "基层病种", "结核耐药诊断列表"]:
        assert s in sheet_sel.options, f"工作表选择器缺少 {s}"

    # 切到「不纳入分组_主要诊断」→ 4742 条
    sheet_sel.set_value("不纳入分组_主要诊断")
    at.run()
    assert not at.exception, f"切换工作表抛出异常: {at.exception}"
    subs = [s.value for s in at.subheader if "不纳入分组_主要诊断" in s.value]
    assert subs, f"未渲染工作表标题，现有: {[s.value for s in at.subheader]}"
    assert "4742" in subs[0], f"记录数不符: {subs[0]}"

    # 切到「不纳入分组_主要手术操作」→ 4111 条
    _by_label(at.selectbox, "选择工作表").set_value("不纳入分组_主要手术操作")
    at.run()
    assert not at.exception
    subs2 = [s.value for s in at.subheader if "不纳入分组_主要手术操作" in s.value]
    assert subs2, f"未渲染工作表标题，现有: {[s.value for s in at.subheader]}"
    assert "4111" in subs2[0], f"记录数不符: {subs2[0]}"


def test_web_dictionary_single_sheet_hides_selector():
    """单 sheet 字典（低标目录）不出现「选择工作表」，标题不含 sheet 后缀。"""
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()

    _by_label(at.radio, "导航菜单").set_value("📚 字典查看")
    at.run()

    _by_label(at.selectbox, "选择字典").set_value("低标目录")
    at.run()
    assert not at.exception, f"切换字典抛出异常: {at.exception}"
    labels = [s.label for s in at.selectbox]
    assert "选择工作表" not in labels, f"单 sheet 字典不应出现工作表选择器: {labels}"
    subs = [s.value for s in at.subheader if s.value.startswith("低标目录")]
    assert subs, f"未渲染标题，现有: {[s.value for s in at.subheader]}"
    assert "·" not in subs[0], f"单 sheet 标题不应带 sheet 后缀: {subs[0]}"


if __name__ == "__main__":
    test_web_app_renders()
    test_web_app_auxiliary_typing_flow()
    print("test_web_app.py 全部用例通过")
