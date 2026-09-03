"""验证 Web「按国家目录分组、国家格式显示」的新逻辑（不依赖 Streamlit）。

模拟 web/app.py _calc_run_stage 的关键步骤：
  load national dir -> _refine_core_group_key(四层) -> match_with_national_directory -> 移植/呼吸循环补映射
并报告：各层国家 DIP 码、综合病种(本地阈值折叠)、LBW/PRI/烧伤 是否呈国家标准码。
"""
import sys, os
sys.path.insert(0, '.')
import pandas as pd
from decimal import Decimal
from src.core.local_directory_generator import LocalDirectoryGenerator
from src.models.models import DiseaseGroup, GroupType, MedicalRecord

XLSX = 'output/qk_merged_settlement.xlsx'
df = pd.read_excel(XLSX)
print(f"载入 {len(df)} 行")

gen = LocalDirectoryGenerator(threshold=15)
gen.load_national_directory('data/DIP3.0国家目录库.xlsx')
print(f"国家目录已加载：_nat_dip_codes={len(gen._nat_dip_codes)} 条")

# 直接按合并表列名映射（与 Web _import_df_to_records 同义），避免触发 streamlit import
def s(row, *names):
    for n in names:
        if n in df.columns:
            v = row.get(n)
            if pd.notna(v):
                return str(v)
    return ""
def i(row, *names):
    v = s(row, *names)
    try:
        return int(float(v))
    except Exception:
        return 0
def d(row, *names):
    v = s(row, *names)
    try:
        return Decimal(str(float(v)))
    except Exception:
        return Decimal("0")

records = []
for _, row in df.iterrows():
    records.append(MedicalRecord(
        record_id=s(row, "结算ID"), settlement_id=s(row, "结算ID"),
        patient_id=s(row, "结算ID"), visit_id=s(row, "结算ID"),
        hospital_code=s(row, "医院代码"), hospital_name=s(row, "医院名称"),
        hospital_level=s(row, "医院等级"),
        age=i(row, "年龄"), day_age=i(row, "年龄(天)"),
        birth_weight=d(row, "新生儿出生体重", "出生体重"),
        birth_date=s(row, "出生日期"), admission_date=s(row, "入院时间"),
        main_diag_code=s(row, "主要诊断代码", "主要诊断编码"),
        main_diag_name=s(row, "主要诊断名称"),
        main_oprn_code=s(row, "主要手术操作代码", "主要手术编码"),
        main_oprn_name=s(row, "主要手术操作名称"),
        related_diag_code=s(row, "相关诊断代码", "相关诊断编码"),
        related_oprn_code=s(row, "相关手术操作代码", "相关手术编码"),
        total_cost=d(row, "医疗费用总额(元)", "总费用"),
    ))
print(f"解析为 {len(records)} 条记录")

# 逐条四层成组
temp = {}
for r in records:
    ck, layer = gen._refine_core_group_key(
        r.main_diag_code, r.main_oprn_code, r.related_oprn_code, r.related_diag_code,
        day_age=r.day_age, birth_weight=r.birth_weight, age=r.age,
        birth_date=r.birth_date, admission_date=r.admission_date,
    )
    if ck in temp:
        temp[ck].case_count += 1
        temp[ck].avg_cost += r.total_cost
    else:
        temp[ck] = DiseaseGroup(
            disease_code=ck, disease_name=r.main_diag_name,
            main_diag_code=r.main_diag_code, main_diag_name=r.main_diag_name,
            main_oprn_code=r.main_oprn_code or '', main_oprn_name=r.main_oprn_name or '',
            related_oprn_code=r.related_oprn_code, related_oprn_name=r.related_oprn_name,
            group_type=GroupType.CORE, case_count=1, avg_cost=r.total_cost,
            grouping_layer=layer,
        )

# 回填国家 DIP 码（与 web/app.py 新逻辑一致：轻量索引查表，避免全表扫描）
cluster_to_national = {}
for g in temp.values():
    orig = g.disease_code
    ndip = ""
    matched = False
    if orig in getattr(gen, '_nat_dip_codes', set()):
        ndip = orig
        matched = True
    else:
        diag4 = gen._extract_icd4(g.main_diag_code)
        ndip = gen._nat_dip_for_diag_oprn(diag4, g.main_oprn_code)
        matched = bool(ndip)
    if not ndip:
        ndip = orig
    g.disease_code = ndip
    cluster_to_national[orig] = ndip
    g.national_matched = matched

# 阈值折叠（综合病种）
def build_mixed(temp_groups, threshold):
    core, mixed_spec = [], {}
    for g in temp_groups.values():
        is_national_core = g.grouping_layer in ('先期分组', '并项规则', '诊断辅助细分')
        if g.case_count >= threshold or is_national_core:
            g.group_type = GroupType.CORE
            core.append(g)
        else:
            mixed_spec[g.disease_code] = g.case_count
    return core, mixed_spec

core, mixed = build_mixed(temp, 15)

# 统计
from collections import Counter
layer_counter = Counter(g.grouping_layer for g in core)
print("\n=== 核心病种（按国家目录四层）===")
for layer in ('先期分组', '并项规则', '诊断辅助细分', '基本规则'):
    gs = [g for g in core if g.grouping_layer == layer]
    print(f"  {layer}: {len(gs)} 组")
    for g in sorted(gs, key=lambda x: -x.case_count)[:4]:
        print(f"      {g.disease_code}  n={g.case_count}  matched={g.national_matched}")

print(f"\n综合病种(本地阈值折叠): {len(mixed)} 组")

# 关键断言
print("\n=== 关键组核查 ===")
all_codes = {g.disease_code: g for g in core}
lbw = [c for c in all_codes if c.startswith('P07-0')]
burn = [c for c in all_codes if c[:4] in ('5016','5017','5018','5019','5020','5021','5022','5023','5024','5025','5026','5027')]
tumor = [c for c in all_codes if c.startswith('Z51.')]
tb = [c for c in all_codes if c.startswith('A15') or c.startswith('A17') or c.startswith('A18') or c.startswith('A19')]
pri = [c for c in all_codes if c.startswith('PRI|')]
print(f"  LBW 国家DIP(P07-0X): {lbw}")
print(f"  烧伤 国家DIP(5016-5039): {burn[:6]} ... 共 {len(burn)} 组")
print(f"  肿瘤 国家DIP(Z51.): {tumor[:4]} ... 共 {len(tumor)} 组")
print(f"  结核 国家DIP(A15-A19): {tb[:4]} ... 共 {len(tb)} 组")
print(f"  先期分组残留本地键(PRI|...): {pri}  (应为空)")
# 本地键残留检查
local_keys = [c for c in all_codes if c.startswith('PRI|') or c.startswith('AUX|') or c.startswith('BASIC|')]
print(f"\n  残留本地成组键(应为空): {local_keys}")
print("\nOK" if not local_keys and lbw and burn else "\nWARN: 仍有本地键或未出先期/诊断辅助细分")
