"""DIP 本地目录库测算 · 行为保持（behavior-preserving）稳定性校验脚本。

用途：在对成组/辅助分型做性能优化（如 iterrows -> itertuples）前后，
分别运行本脚本，对比两次产出的指纹（fingerprint）是否完全一致。
若一致，证明优化未改变任何测算逻辑与测算结果；若不一致，说明优化引入了
行为偏差，必须回退。

运行（在仓库根目录 F:/DIP）：
    python scripts/perf_stability_check.py <output_json_path>

例如：
    python scripts/perf_stability_check.py output/stability_before.json
    # ... 做优化 ...
    python scripts/perf_stability_check.py output/stability_after.json
    python -c "import json,sys; a=json.load(open('output/stability_before.json')); b=json.load(open('output/stability_after.json')); print('IDENTICAL' if a==b else 'DIFFERENT')"
"""
import sys
import os
import json
import hashlib
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from src.core.local_directory_generator import LocalDirectoryGenerator


def build_synthetic_df(n_per_group: int = 40, seed: int = 20260731) -> pd.DataFrame:
    """构造确定性的合成医保清单数据，覆盖四层成组 + 辅助分型的多维度触发。

    关键：用固定 seed 保证每次生成的数据完全一致（可复现对比）。
    - 年龄/ICU/死亡 状态与费用强相关，确保辅助分型会在 年龄/ICU/严重程度 维度触发拆分，
      从而让 _classify_members 对成员字段（age/icu_days/discharge_status/total_cost）的消费路径
      被纳入指纹校验。
    """
    import random
    rng = random.Random(seed)
    rows = []
    seq = 0

    # 每组：(主诊断, 名称, 主手术, 手术名, 相关手术, 相关名, 基础费, 年龄下限, 年龄上限, ICU概率, 死亡概率)
    specs = [
        ('K35.9', '急性阑尾炎', '47.0100', '腹腔镜下阑尾切除术', '', '', 12000, 20, 85, 0.10, 0.02),
        ('I21.0', '前壁急性透壁性心肌梗死', '36.0700', '药物洗脱冠状动脉支架置入', '88.7200', '冠状动脉造影', 45000, 35, 90, 0.30, 0.05),
        ('J18.9', '肺炎', '', '', '', '', 6000, 18, 92, 0.12, 0.03),
        ('M16.1', '髋关节骨关节病', '81.5100', '全髋关节置换术', '', '', 55000, 50, 88, 0.08, 0.01),
    ]

    for (md, mdn, mo, mon, ro, ron, base, a_lo, a_hi, icu_p, death_p) in specs:
        for _ in range(n_per_group):
            seq += 1
            age = rng.randint(a_lo, a_hi)
            # 年龄越大费用越高（触发年龄维度 CV 改善）
            age_factor = 1.0 + (age - a_lo) / max(1, (a_hi - a_lo)) * 1.2
            icu = rng.random() < icu_p
            death = rng.random() < death_p
            cost = int(base * age_factor * (1.6 if icu else 1.0) * (2.2 if death else 1.0)
                       * rng.uniform(0.9, 1.1))
            rows.append({
                '清单流水号': f'R{seq:06d}',
                '结算ID': f'S{seq:06d}',
                '人员编号': f'P{seq:06d}',
                '主要诊断代码': md,
                '主要诊断名称': mdn,
                '主要手术操作代码': mo,
                '主要手术操作名称': mon,
                '相关手术操作代码': ro,
                '相关手术操作名称': ron,
                '相关诊断代码': '',  # 本合成数据不刻意构造 CCI，年龄/ICU/严重程度维度已足够覆盖成员消费路径
                '医疗总费用': cost,
                '药品费用': int(cost * 0.25),
                '耗材费用': int(cost * 0.15),
                '住院天数': rng.randint(4, 20),
                '年龄': age,
                'ICU天数': rng.randint(1, 5) if icu else 0,
                '出院状态': '死亡' if death else '治愈',
            })

    # 低频病种（验证综合病种合并路径，不受影响）
    for code, name, oprn, oprn_name, cost in [
        ('A09', '感染性腹泻', '', '', 3000),
        ('E11.9', '2型糖尿病', '', '', 5000),
        ('I10', '原发性高血压', '', '', 4000),
    ]:
        for i in range(3):
            seq += 1
            rows.append({
                '清单流水号': f'R{seq:06d}', '结算ID': f'S{seq:06d}', '人员编号': f'P{seq:06d}',
                '主要诊断代码': code, '主要诊断名称': name,
                '主要手术操作代码': oprn, '主要手术操作名称': oprn_name,
                '相关手术操作代码': '', '相关手术操作名称': '',
                '相关诊断代码': '', '医疗总费用': cost + i * 200,
                '药品费用': cost // 3, '耗材费用': cost // 5, '住院天数': 5,
                '年龄': 50 + i, 'ICU天数': 0, '出院状态': '治愈',
            })

    return pd.DataFrame(rows)


def fingerprint(generator: LocalDirectoryGenerator, df: pd.DataFrame, threshold: int = 10) -> dict:
    generator.set_threshold(threshold)
    groups = generator.cluster_records_to_groups(df)
    groups = generator.apply_auxiliary_typing(groups)
    # 计算病种分值（确定性，依赖成组结果），纳入指纹增强覆盖
    all_groups = list(groups.values())
    all_groups = generator.calculate_all_disease_values(all_groups)

    group_fp = []
    for g in all_groups:
        group_fp.append({
            'code': g.disease_code,
            'name': g.disease_name,
            'layer': g.grouping_layer,
            'type': g.group_type.value,
            'case_count': g.case_count,
            'avg_cost': round(float(g.avg_cost), 2),
            'disease_value': round(float(g.disease_value), 4) if g.disease_value is not None else None,
            'aux_split': g.auxiliary_split,
            'aux_coef': round(float(g.auxiliary_coefficient), 4) if g.auxiliary_coefficient is not None else None,
            'ccci': int(g.cci_score) if g.cci_score is not None else None,
            'sev': g.severity_level,
        })
    group_fp.sort(key=lambda x: (x['code'], x['layer']))

    # 辅助分型触发报告（内部逐条分型产出，依赖成员字段消费）
    report = sorted(
        [
            {k: r[k] for k in ('disease_code', 'dimension', 'cv_before', 'cv_after',
                               'cv_improvement', 'trigger_coefficient', 'max_bucket_case_count', 'triggered')}
            for r in getattr(generator, 'auxiliary_trigger_report', [])
        ],
        key=lambda x: (x['disease_code'], x['dimension']),
    )

    return {
        'n_groups': len(group_fp),
        'groups': group_fp,
        'trigger_report': report,
        'overall_trim_rate': round(float(generator.overall_trim_rate), 6),
        'total_original_cases': generator.total_original_cases,
        'total_trimmed_cases': generator.total_trimmed_cases,
    }


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else 'output/stability_fingerprint.json'
    gen = LocalDirectoryGenerator()
    df = build_synthetic_df()
    fp = fingerprint(gen, df)
    os.makedirs(os.path.dirname(out_path) or '.', exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(fp, f, ensure_ascii=False, indent=2, sort_keys=True)
    digest = hashlib.sha256(
        json.dumps(fp, ensure_ascii=False, sort_keys=True).encode('utf-8')
    ).hexdigest()
    print(f"记录数: {len(df)}")
    print(f"病种组数: {fp['n_groups']}")
    print(f"触发报告条数: {len(fp['trigger_report'])}")
    print(f"指纹 SHA256: {digest}")
    print(f"已写入: {out_path}")


if __name__ == '__main__':
    main()
