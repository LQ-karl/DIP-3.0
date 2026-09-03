"""基层病种本地目录测算验证脚本（DIP3.0 技术规范 第三章第四节）。

验证《分组方案》基层病种名录为候选池 + 本地数据校验的三条口径：
  ① 属核心病种  ② 基层医疗机构病例占比 ≥ 50%  ③ 组内 CV ≤ 0.7
并验证导出（基层病种目录 / 遴选依据表 / 统计含基层病种数）与分值同病同治同价。
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
from decimal import Decimal

from src.core.local_directory_generator import LocalDirectoryGenerator
from src.core.hospital_coefficient_selector import HospitalCoefficientSelector
from src.models.models import GroupType

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


def build_df():
    data = []

    # ① 名录命中 + 基层占比 60% + 低 CV → 应入选
    data += _rows('A09.9', '未特指病因的胃肠炎和结肠炎',
                  [5000 + i * 100 for i in range(10)],
                  ['一级'] * 6 + ['三级甲等'] * 4)

    # ② 名录命中 + 基层占比 20%（不足）→ 应落选（原因：基层机构病例占比不足）
    data += _rows('E11.9', '2型糖尿病不伴有并发症',
                  [6000 + i * 100 for i in range(10)],
                  ['一级'] * 2 + ['三级甲等'] * 8)

    # ③ 名录命中 + 费用离散（CV 高）→ 应落选（原因：组内CV 超标）
    data += _rows('D64.9', '未特指的贫血',
                  [1000] * 9 + [20000],
                  ['一级'] * 8 + ['三级甲等'] * 2)

    # ④ 名录命中但病例数不足（< 阈值）→ 折叠为综合病种，不得入选
    data += _rows('G43.9', '未特指的偏头痛',
                  [4000, 4200, 4300],
                  ['一级'] * 3)

    return pd.DataFrame(data)


def main():
    gen = LocalDirectoryGenerator(threshold=THRESHOLD)
    df = build_df()
    groups = gen.cluster_records_to_groups(df)
    groups = gen.select_grassroot_groups(groups)

    print("=" * 72)
    print("一、遴选结果")
    print("=" * 72)
    for r in gen.grassroot_report:
        print(f"  {r['主要诊断编码']:<8} {r['主要诊断名称'][:14]:<16} "
              f"病例{r['病例数']:>3} 基层{r['基层机构病例数']:>3} "
              f"占比{r['基层机构病例占比']:>6.2%} CV{r['组内CV(裁剪后)']:>6.3f} "
              f"→ {r['是否入选']}  {r['未入选原因']}")

    expect = {'A09.9': True, 'E11.9': False, 'D64.9': False}
    ok = True
    for code, want in expect.items():
        got = any(g.main_diag_code == code and g.is_grassroot for g in groups.values())
        flag = "OK " if got == want else "FAIL"
        ok &= (got == want)
        print(f"  [{flag}] {code} is_grassroot = {got}（期望 {want}）")

    # 综合病种不得为基层病种
    mixed_bad = [g.disease_code for g in groups.values()
                 if g.group_type == GroupType.MIXED and g.is_grassroot]
    print(f"  [{'OK ' if not mixed_bad else 'FAIL'}] 综合病种无基层标记（违规 {mixed_bad}）")
    ok &= not mixed_bad

    # 二、分值（同病同治同价：全样本合并）
    print("\n" + "=" * 72)
    print("二、分值与医疗机构系数（同病同治同价）")
    print("=" * 72)
    core = [g for g in groups.values() if g.group_type == GroupType.CORE]
    mixed = [g for g in groups.values() if g.group_type == GroupType.MIXED]
    merged = gen.merge_mixed_groups(mixed)
    all_groups = sorted(core + merged, key=gen._layer_sort_key)
    all_groups = gen.calculate_all_disease_values(all_groups)
    selector = HospitalCoefficientSelector()
    for g in all_groups:
        if g.main_diag_code not in ('A09.9', 'E11.9'):
            continue
        coef = selector.calculate_coefficient(
            {'hospital_code': 'H001', 'hospital_name': '市人民医院',
             'hospital_level': '三级甲等'}, dip_code=g.disease_code
        )
        print(f"  {g.main_diag_code:<8} 分值={float(g.disease_value):>10.4f} "
              f"基层={'是' if g.is_grassroot else '否'} "
              f"三级甲等机构系数={float(coef.final_coefficient)}")
        if g.is_grassroot:
            good = float(coef.final_coefficient) == 1.0
            print(f"  [{'OK ' if good else 'FAIL'}] 基层病种不设医疗机构调节系数（=1.0）")
            ok &= good

    # 三、导出
    print("\n" + "=" * 72)
    print("三、导出表")
    print("=" * 72)
    gr_df = gen._export_grassroot_directory(all_groups)
    print(f"  基层病种目录行数: {len(gr_df)}")
    if not gr_df.empty:
        print(gr_df[['病种代码', '主要诊断编码', '病例数', '基层机构病例占比',
                     '组内CV(裁剪后)', '病种分值', '医疗机构调节系数']].to_string(index=False))
    sel_df = gen._export_grassroot_selection()
    print(f"  遴选依据表行数: {len(sel_df)}（候选池）")
    stats_df = gen._export_statistics(all_groups)
    row = stats_df[stats_df['统计项目'] == '基层病种数']
    n = int(row['数值'].iloc[0]) if not row.empty else -1
    print(f"  统计报告 基层病种数: {n}")
    ok &= (n == 1)

    print("\n" + "=" * 72)
    print("结论:", "全部通过" if ok else "存在失败项")
    print("=" * 72)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
