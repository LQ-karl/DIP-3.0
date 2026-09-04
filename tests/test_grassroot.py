"""基层病种本地目录测算 - 回归测试（DIP3.0 技术规范 第三章第四节）

口径（用户 2026-09-04 确认）：
  候选池 = 《分组方案》基层病种 sheet 名录（成组时初判 is_grassroot）
  校验项 = ① 属核心病种 ② 基层医疗机构病例占比 ≥ 50% ③ 组内 CV ≤ 0.7
  分值   = 全样本合并测算（不分机构等级）；不设医疗机构调节系数（同病同治同价）
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import pytest
from decimal import Decimal

from src.core.local_directory_generator import LocalDirectoryGenerator
from src.core.hospital_coefficient_selector import HospitalCoefficientSelector
from src.models.models import DiseaseGroup, GroupType

THRESHOLD = 10


def _rows(diag_code, diag_name, costs, levels, oprn_code="", oprn_name=""):
    rows = []
    for i, (cost, level) in enumerate(zip(costs, levels)):
        rows.append({
            '清单流水号': f'{diag_code}-{i:03d}',
            '主要诊断代码': diag_code,
            '主要诊断名称': diag_name,
            '主要手术操作代码': oprn_code,
            '主要手术操作名称': oprn_name,
            '相关手术操作代码': '',
            '相关手术操作名称': '',
            '医疗总费用': cost,
            '药品费用': int(cost * 0.3),
            '住院天数': 6,
            '年龄': 50,
            '医院等级': level,
        })
    return rows


def _build_sample_df():
    """名录候选 × 三种结果：入选 / 占比不足落选 / CV 超标落选 / 病例不足(综合病种)。"""
    data = []
    # A09.9：名录命中 + 基层占比 60% + CV 低 → 入选
    data += _rows('A09.9', '未特指病因的胃肠炎和结肠炎',
                  [5000 + i * 100 for i in range(10)],
                  ['一级'] * 6 + ['三级甲等'] * 4)
    # E11.9：名录命中 + 基层占比 20% → 落选
    data += _rows('E11.9', '2型糖尿病不伴有并发症',
                  [6000 + i * 100 for i in range(10)],
                  ['一级'] * 2 + ['三级甲等'] * 8)
    # D64.9：名录命中 + 费用离散(CV≈1.97) → 落选
    data += _rows('D64.9', '未特指的贫血',
                  [1000] * 9 + [20000],
                  ['一级'] * 8 + ['三级甲等'] * 2)
    # G43.9：名录命中但病例数不足 → 折叠为综合病种，不得入选
    data += _rows('G43.9', '未特指的偏头痛',
                  [4000, 4200, 4300], ['一级'] * 3)
    return pd.DataFrame(data)


@pytest.fixture(scope="module")
def selected():
    """聚类 + 基层病种遴选（模块级复用，避免重复加载字典）。"""
    gen = LocalDirectoryGenerator(threshold=THRESHOLD)
    groups = gen.cluster_records_to_groups(_build_sample_df())
    groups = gen.select_grassroot_groups(groups)
    return gen, groups


def _report_of(gen, diag_code):
    for r in gen.grassroot_report:
        if r['主要诊断编码'] == diag_code:
            return r
    return None


def test_grassroot_selected_when_all_criteria_met(selected):
    """名录命中 + 基层占比达标 + CV 达标 → 入选基层病种。"""
    _gen, groups = selected
    hit = [g for g in groups.values() if g.main_diag_code == 'A09.9']
    assert hit, "A09.9 应形成核心病种组"
    assert all(g.is_grassroot for g in hit), "A09.9 应入选基层病种"
    rep = _report_of(_gen, 'A09.9')
    assert rep is not None and rep['是否入选'] == '是'
    assert rep['基层机构病例占比'] == pytest.approx(0.6, abs=1e-6)
    assert rep['基层机构病例数'] == 6
    assert rep['组内CV(裁剪后)'] <= 0.7


def test_grassroot_rejected_by_low_basic_ratio(selected):
    """名录命中但基层机构病例占比不足 → 落选，并记录原因。"""
    _gen, groups = selected
    hit = [g for g in groups.values() if g.main_diag_code == 'E11.9']
    assert hit and not any(g.is_grassroot for g in hit)
    rep = _report_of(_gen, 'E11.9')
    assert rep['是否入选'] == '否'
    assert '基层机构病例占比' in rep['未入选原因']


def test_grassroot_rejected_by_high_cv(selected):
    """名录命中但组内 CV 超过 0.7 → 落选，并记录原因。"""
    _gen, groups = selected
    hit = [g for g in groups.values() if g.main_diag_code == 'D64.9']
    assert hit and not any(g.is_grassroot for g in hit)
    rep = _report_of(_gen, 'D64.9')
    assert rep['是否入选'] == '否'
    assert '组内CV' in rep['未入选原因']
    assert rep['组内CV(裁剪后)'] > 0.7


def test_grassroot_excludes_mixed_groups(selected):
    """基层病种是核心病种中的一个类别；综合病种一律不标记。"""
    _gen, groups = selected
    mixed = [g for g in groups.values() if g.group_type == GroupType.MIXED]
    assert mixed, "样本应产生综合病种（G43.9 病例数不足）"
    assert not any(g.is_grassroot for g in mixed)


def test_grassroot_directory_export_and_statistics(selected):
    """基层病种目录 / 遴选依据表 / 统计报告 三项输出。"""
    gen, groups = selected
    core = [g for g in groups.values() if g.group_type == GroupType.CORE]
    mixed = [g for g in groups.values() if g.group_type == GroupType.MIXED]
    all_groups = sorted(core + gen.merge_mixed_groups(mixed), key=gen._layer_sort_key)
    all_groups = gen.calculate_all_disease_values(all_groups)

    gr_df = gen._export_grassroot_directory(all_groups)
    assert len(gr_df) == 1, "仅 A09.9 入选"
    row = gr_df.iloc[0]
    assert row['主要诊断编码'] == 'A09.9'
    assert row['病种分值'] > 0
    assert row['医疗机构调节系数'] == '不设（同病同治同价）'

    sel_df = gen._export_grassroot_selection()
    assert len(sel_df) == len(gen.grassroot_report) == 3, "候选池 3 个（A09.9/E11.9/D64.9）"

    stats = gen._export_statistics(all_groups)
    n = int(stats.loc[stats['统计项目'] == '基层病种数', '数值'].iloc[0])
    assert n == 1


def test_grassroot_no_hospital_coefficient():
    """基层病种不设医疗机构调节系数（同病同治同价）。"""
    selector = HospitalCoefficientSelector()
    _gen, groups = LocalDirectoryGenerator(threshold=THRESHOLD), None
    gen = _gen
    g2 = gen.cluster_records_to_groups(_build_sample_df())
    g2 = gen.select_grassroot_groups(g2)
    gr = [g for g in g2.values() if g.is_grassroot]
    assert gr, "应存在入选的基层病种"
    coef = selector.calculate_coefficient(
        {'hospital_code': 'H001', 'hospital_name': '市人民医院', 'hospital_level': '三级甲等'},
        dip_code=gr[0].disease_code,
    )
    assert float(coef.final_coefficient) == 1.0, "基层病种机构系数须为 1.0"


def test_grassroot_inherited_by_auxiliary_subgroup():
    """辅助分型拆分后的子组继承父核心病种的基层属性。"""
    gen = LocalDirectoryGenerator(threshold=THRESHOLD)
    parent = DiseaseGroup(
        disease_code='JC-1868', disease_name='未特指病因的胃肠炎和结肠炎',
        main_diag_code='A09.9', main_diag_name='未特指病因的胃肠炎和结肠炎',
        group_type=GroupType.CORE, case_count=2,
    )
    parent.is_grassroot = True
    members = [{'total_cost': Decimal('5000'), 'hospital_level': '一级'},
               {'total_cost': Decimal('5200'), 'hospital_level': '一级'}]
    sub = gen._build_auxiliary_subgroup(
        parent=parent, dimension='年龄特征', level='中年组',
        members=members, coeff=Decimal('1.0'),
    )
    assert sub.is_grassroot is True


def test_grassroot_disabled_keeps_directory_flag():
    """关闭遴选时保留名录初判结果，不做本地校验覆盖。"""
    gen = LocalDirectoryGenerator(threshold=THRESHOLD, enable_grassroot=False)
    groups = gen.cluster_records_to_groups(_build_sample_df())
    groups = gen.select_grassroot_groups(groups)
    # E11.9（占比不足）在未启用遴选时仍为名录初判 True
    hit = [g for g in groups.values() if g.main_diag_code == 'E11.9']
    assert hit and all(g.is_grassroot for g in hit)
    assert gen.grassroot_report == []


def test_grassroot_old_prefix_fallback_disabled():
    """旧前缀回退清单已停用（用户 2026-09-04 裁决）：

    基层病种判定一律以《分组方案》基层病种 sheet 名录（引擎）为唯一权威；
    旧式序号码（如 K35-1）与名录外诊断（如 I20 保守治疗）一律不判为基层病种。
    """
    selector = HospitalCoefficientSelector()
    # 新方案形态编码走引擎权威判定：名录内 → True
    assert selector.is_basic_disease_group('JC-1868') is True        # A09.9 保守治疗行
    assert selector.is_basic_disease_group('A09.9-保守治疗-') is True
    assert selector.is_basic_disease_group('D24-85.2300x001-') is True
    # 名录外新形态编码 → False（I20 已不在新名录）
    assert selector.is_basic_disease_group('I20-保守治疗-') is False
    # 旧式序号码不再回退旧 34 前缀清单 → False
    assert selector.is_basic_disease_group('K35-1') is False
    assert selector.is_basic_disease_group('I21-1') is False


def test_grassroot_institution_level_matching():
    """基层机构等级匹配口径（用户 2026-09-05 裁决：前缀匹配 + 扩展）。

    - 一级系列写法（一级 / 一级甲等 / 一级乙等 / 一级丙等）全部计入分子；
    - 社区卫生服务中心 / 社区卫生服务站 / 乡镇卫生院 计入；
    - 二级、三级甲等、空值 不计入（避免占比被高估）。
    """
    gen = LocalDirectoryGenerator(threshold=THRESHOLD)
    judge = gen.is_grassroot_institution

    for lv in ('一级', '一级甲等', '一级乙等', '一级丙等',
               '社区卫生服务中心', '社区卫生服务站', '乡镇卫生院'):
        assert judge(lv) is True, f"{lv} 应计入基层机构病例数"

    for lv in ('二级', '二级甲等', '三级', '三级甲等', '三级乙等', '', '   ', None):
        assert judge(lv) is False, f"{lv!r} 不应计入基层机构病例数"


def test_grassroot_ratio_counts_variant_level_writings():
    """等级写法不统一时的占比统计：一级/一级甲等/卫生服务站 均计入分子。

    10 例中 6 例为基层机构（2 例「一级」+2 例「一级甲等」+1 例「社区卫生服务站」
    +1 例「乡镇卫生院」）→ 占比 60% ≥ 50% 且 CV 低 → 应入选；若按旧精确匹配
    仅 2 例计入（20%）则会落选，故本用例同时锁定该回归。
    """
    levels = (['一级'] * 2 + ['一级甲等'] * 2 + ['社区卫生服务站'] * 1
              + ['乡镇卫生院'] * 1 + ['三级甲等'] * 4)
    df = pd.DataFrame(_rows('A09.9', '未特指病因的胃肠炎和结肠炎',
                            [5000 + i * 100 for i in range(10)], levels))
    gen = LocalDirectoryGenerator(threshold=THRESHOLD)
    groups = gen.cluster_records_to_groups(df)
    groups = gen.select_grassroot_groups(groups)

    rep = _report_of(gen, 'A09.9')
    assert rep is not None, "A09.9 应进入基层病种遴选"
    assert rep['基层机构病例数'] == 6, f"基层机构病例数应为 6，实际 {rep['基层机构病例数']}"
    assert abs(rep['基层机构病例占比'] - 0.6) < 1e-6
    assert rep['是否入选'] == '是', f"占比 60% 应入选，实际：{rep['未入选原因']}"
    hit = [g for g in groups.values() if g.main_diag_code == 'A09.9']
    assert hit and all(g.is_grassroot for g in hit)
