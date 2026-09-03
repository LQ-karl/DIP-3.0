"""临时校验：Web 核心/综合病种阈值折叠与 value_results 一致性（真实测试数据）。"""
import sys
import pandas as pd
from decimal import Decimal

sys.path.insert(0, ".")
import web.app as A
from web.app import _build_core_mixed, _merge_value_results_to_mixed
from src.models.models import DiseaseGroup, GroupType
from src.core.value_calculator_selectable import DIPValueCalculator, create_average_cost_config


def main():
    df = pd.read_excel("output/测试数据_附件生成_补全名称.xlsx")
    records = A._import_df_to_records(df)
    print("导入记录:", len(records))

    threshold = 5
    temp_groups = {}
    from src.utils.paths import get_data_dir
    try:
        dip_dir = pd.read_excel(str(get_data_dir() / "DIP3.0国家目录库.xlsx"))
    except Exception:
        dip_dir = pd.DataFrame(columns=["主要诊断编码", "主要手术操作编码", "DIP编码", "主要诊断名称", "主要手术操作名称"])
    for r in records:
        dip_code, dip_diag_code, dip_diag_name, dip_proc_code, dip_proc_name = A._calc_find_dip_code(
            dip_dir, r.main_diag_code, r.main_oprn_code)
        if dip_code:
            disease_code = dip_code
            disease_name = dip_diag_name
            main_oprn_code = dip_proc_code
            main_oprn_name = dip_proc_name
            main_diag_code = dip_diag_code
        else:
            if r.main_oprn_code:
                disease_code = f"{r.main_diag_code}-01"
            else:
                disease_code = f"{r.main_diag_code}-00"
            disease_name = r.main_diag_name
            main_oprn_code = r.main_oprn_code
            main_oprn_name = r.main_oprn_name
            main_diag_code = r.main_diag_code
        if disease_code in temp_groups:
            temp_groups[disease_code].case_count += 1
            temp_groups[disease_code].avg_cost += r.total_cost
        else:
            temp_groups[disease_code] = DiseaseGroup(
                disease_code=disease_code, disease_name=disease_name,
                main_diag_code=main_diag_code, main_diag_name=r.main_diag_name,
                main_oprn_code=main_oprn_code or "", main_oprn_name=main_oprn_name or "",
                group_type=GroupType.CORE, case_count=1, avg_cost=r.total_cost)
        r.dip_disease_code = disease_code
    for g in temp_groups.values():
        if g.case_count > 0:
            g.avg_cost = g.avg_cost / g.case_count

    core, mixed_spec, code_to_mixed = _build_core_mixed(temp_groups, threshold)
    print("原始聚类组数:", len(temp_groups))
    print("达阈值核心组:", len(core))
    print("综合病种组数:", len(mixed_spec))
    below = list(code_to_mixed)
    print("被折叠原病种数(<5例):", len(below))
    bad = [g.disease_code for g in temp_groups.values()
           if g.case_count < threshold and g.disease_code not in code_to_mixed]
    bad_core = [g.disease_code for g in core if g.case_count < threshold]
    print("未折叠的<5例组(应空):", bad)
    print("核心组里<5例的(应空):", bad_core)

    vc = DIPValueCalculator(create_average_cost_config())
    vals = vc.calculate_all_values(records)
    vals2 = _merge_value_results_to_mixed(vals, temp_groups, threshold, vc, records)
    leaked = [v.dip_code for v in vals2 if v.dip_code in code_to_mixed]
    mix_in_val = [v.dip_code for v in vals2 if str(v.dip_code).startswith("MIX_")]
    tot_before = sum(v.case_count for v in vals)
    tot_after = sum(v.case_count for v in vals2)
    mixed_cases = sum(v.case_count for v in vals2 if str(v.dip_code).startswith("MIX_"))
    below_cases = sum(temp_groups[k].case_count for k in below)
    print("value_results 合并前/后:", len(vals), len(vals2))
    print("残留被折叠原码(应空):", leaked)
    print("value 中综合病种组:", len(mix_in_val))
    print("病例总数守恒:", tot_before, "->", tot_after)
    print("综合病例合计==被折叠病例合计:", mixed_cases, below_cases, mixed_cases == below_cases)
    ok = (not bad) and (not bad_core) and (not leaked) and (tot_before == tot_after) and (mixed_cases == below_cases)
    print("\n全部校验通过 ✅" if ok else "\n❌ 校验失败")


if __name__ == "__main__":
    main()
