"""多值其他诊断(related_diag_code '|' 分隔)支持 · 回归测试。

背景：4101A 解析器与数据库模型约定其他诊断/手术用 '|' 拼接多值，
但修复前 CCI 计算仅用 split(',') 且成组 diag_codes 把整串当单码 add，
导致合并症 CCI 算不全。本次修复统一 '|' 为规范多值分隔符，并在所有 CCI
消费点逐码拆分；单值('A00.0')/空串结果完全不变（行为保持）。

覆盖三层消费点：
  - CCICalculator.calculate_cci 入口兜底拆分（守卫所有调用方）
  - 成组组级 CCI（local_directory_generator 的 diag_codes 收集）
  - Web/exporter 路径 AuxiliaryDirectoryCalculator.calculate_all_auxiliary_coefficients
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from decimal import Decimal

from src.core.local_directory_generator import LocalDirectoryGenerator
from src.core.auxiliary_directory import AuxiliaryDirectoryCalculator
from src.models.models import MedicalRecord


def _make_df(main, related, n=2, base_cost=6000):
    return pd.DataFrame([
        {
            '主要诊断编码': main, '主要诊断名称': 'x',
            '医疗总费用': base_cost + i * 100,
            '相关诊断编码': related, '年龄': 70 + i, '住院天数': 10, '出院状态': '治愈',
        }
        for i in range(n)
    ])


def test_cci_calculator_splits_pipe_multi_value():
    """CCICalculator 入口兜底拆分：'|' 多值被正确累计，单值/空串/兼容分隔符不变。"""
    c = LocalDirectoryGenerator().cci_calculator
    # 单值
    assert c.calculate_cci(['I50.9']) == 1
    # 规范多值分隔符 '|'：I50(权重1) + J44(权重1) = 2
    assert c.calculate_cci(['I50.9|J44.1']) == 2
    # 向后兼容：';' / ',' 历史分隔符同样生效
    assert c.calculate_cci(['I50.9;J44.1']) == 2
    assert c.calculate_cci(['I50.9,J44.1']) == 2
    # 空串/空前缀不影响（结果不变）
    assert c.calculate_cci(['']) == 0
    assert c.calculate_cci([]) == 0


def test_group_level_cci_includes_multi_value_related():
    """成组阶段：多值其他诊断逐码纳入组级 diag_codes，组级 CCI 算全。"""
    gen = LocalDirectoryGenerator()
    gen.set_threshold(2)
    groups = gen.cluster_records_to_groups(_make_df('J18.9', 'I50.9|J44.1', n=2))
    g = [grp for grp in groups.values() if grp.main_diag_code == 'J18.9'][0]
    assert g.cci_score == 2, f"组级 CCI 应累加多值其他诊断, got {g.cci_score}"
    # 单值对照（修复前后结果一致，行为保持）
    groups2 = gen.cluster_records_to_groups(_make_df('J18.9', 'I50.9', n=2))
    g2 = [grp for grp in groups2.values() if grp.main_diag_code == 'J18.9'][0]
    assert g2.cci_score == 1, f"单值 CCI 应为 1, got {g2.cci_score}"


def test_auxiliary_calculator_record_related_multi_value():
    """Web/exporter 路径：record.related_diag_code 多值被正确拆分计 CCI。"""
    calc = AuxiliaryDirectoryCalculator()
    rec = MedicalRecord(
        record_id='R1', settlement_id='S1', patient_id='P1', visit_id='V1',
        hospital_code='H1', hospital_name='测试医院',
        main_diag_code='J18.9', related_diag_code='I50.9|J44.1')
    res = calc.calculate_all_auxiliary_coefficients(rec, disease_avg_cost=Decimal('6000'))
    assert res['cci']['score'] == 2, f"record 多值 CCI 应为 2, got {res['cci']['score']}"
    # 单值对照
    rec1 = MedicalRecord(
        record_id='R2', settlement_id='S2', patient_id='P2', visit_id='V2',
        hospital_code='H2', hospital_name='测试医院2',
        main_diag_code='J18.9', related_diag_code='I50.9')
    res1 = calc.calculate_all_auxiliary_coefficients(rec1, disease_avg_cost=Decimal('6000'))
    assert res1['cci']['score'] == 1, f"record 单值 CCI 应为 1, got {res1['cci']['score']}"


def test_import_folds_numbered_other_diag_columns():
    """宽表导入器：其他诊断编码1~5 等分列应折叠进 related_diag_code(| 分隔)，而非被忽略。"""
    gen = LocalDirectoryGenerator()
    raw = pd.DataFrame([
        {
            '主要诊断编码': 'J18.9', '主要诊断名称': '肺炎',
            '其他诊断编码1': 'I50.9', '其他诊断编码2': 'J44.1', '其他诊断编码3': 'I63.9',
            '其他诊断编码1名称': '心力衰竭', '其他诊断编码2名称': '慢阻肺',
            '医疗总费用': 8000, '年龄': 70, '住院天数': 10, '出院状态': '治愈',
        }
    ])
    norm = gen._normalize_column_names(raw)
    # 分列已折叠进单一字段
    assert 'related_diag_code' in norm.columns
    folded = str(norm['related_diag_code'].iloc[0])
    assert folded == 'I50.9|J44.1|I63.9', f"分列应折叠为 | 串, got {folded}"
    # 原分列已删除（不再作为冗余列）
    assert '其他诊断编码1' not in norm.columns
    assert '其他诊断编码3' not in norm.columns
    # 名称同样折叠
    assert str(norm['related_diag_name'].iloc[0]) == '心力衰竭|慢阻肺'
    # 经成组后组级 CCI 应累加全部三个合并症（I50+J44+I63 均为权重1的不同前缀，合计=3）
    gen.set_threshold(1)
    groups = gen.cluster_records_to_groups(raw)
    g = [grp for grp in groups.values() if grp.main_diag_code == 'J18.9'][0]
    assert g.cci_score == 3, f"折叠后组级 CCI 应累加 3 个合并症, got {g.cci_score}"


def test_import_single_related_column_unchanged():
    """行为保持：仅单列(相关诊断编码)输入时，折叠不触发，结果与原先完全一致。"""
    gen = LocalDirectoryGenerator()
    raw = pd.DataFrame([
        {'主要诊断编码': 'J18.9', '相关诊断编码': 'I50.9|J44.1', '医疗总费用': 8000, '年龄': 70}
    ])
    norm = gen._normalize_column_names(raw)
    assert str(norm['related_diag_code'].iloc[0]) == 'I50.9|J44.1'
    # 无任何分列 → 不触发删除，亦无 related_diag_name 注入（保持原样）
    assert '其他诊断编码1' not in norm.columns


def test_import_folds_other_oprn_columns():
    """宽表导入器：其他手术操作编码1~N 分列应折叠进 related_oprn_code(| 分隔)。"""
    gen = LocalDirectoryGenerator()
    raw = pd.DataFrame([
        {
            '主要诊断编码': 'K35.9', '主要手术操作编码': '47.0100',
            '其他手术操作编码1': '54.5100x005', '其他手术操作编码2': '88.7201',
            '医疗总费用': 10000, '年龄': 45,
        }
    ])
    norm = gen._normalize_column_names(raw)
    assert str(norm['related_oprn_code'].iloc[0]) == '54.5100x005|88.7201'
    assert '其他手术操作编码1' not in norm.columns
