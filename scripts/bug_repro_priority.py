"""验证先期分组「国家DIP码类目」与「病例主诊断前3位」一致（修复后复跑）。

复刻 web/app.py 新成组逻辑：
  1) 成组循环：对 先期分组·TRANSPLANT/LIFESUPPORT，按 (主诊断4位 + 手术) 查国家目录，
     将同一手术码下混有的多种主诊断拆成多个成组键(显示行);查不到则保留 PRI| 原键(诚实标记)。
  2) 完成块：国家DIP码直出;残留 PRI| 键保持原样，不再注入错误类目(如 A41.9)。
然后比对：国家DIP码内嵌「主要诊断类目」前3位 vs 组内病例主诊断前3位集合。
"""
import os
import sys
import pandas as pd

REPO = "F:/DIP"
sys.path.insert(0, REPO)

from decimal import Decimal
from src.core.local_directory_generator import LocalDirectoryGenerator
from src.models.models import MedicalRecord


# ---- 列名容错解析（与 web/app.py:_import_df_to_records 一致）----
def _resolve_col(row, *candidates):
    cols = {str(c).strip().lower(): c for c in row.index}
    for cand in candidates:
        key = str(cand).strip().lower()
        if key in cols:
            val = row[cols[key]]
            if val is None or (isinstance(val, float) and pd.isna(val)):
                continue
            if str(val).strip() == "":
                continue
            return val
    return None


def _to_str(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return str(v).strip()


def _to_int(v):
    s = _to_str(v)
    try:
        return int(float(s))
    except Exception:
        return 0


def _to_dec(v):
    s = _to_str(v)
    try:
        return Decimal(s)
    except Exception:
        return Decimal("0")


def df_to_records(df):
    recs = []
    for _, row in df.iterrows():
        recs.append(MedicalRecord(
            record_id=_to_str(_resolve_col(row, "病案号", "清单流水号", "record_id", "结算ID")),
            settlement_id=_to_str(_resolve_col(row, "结算ID", "settlement_id")),
            patient_id=_to_str(_resolve_col(row, "人员编号", "patient_id")),
            visit_id=_to_str(_resolve_col(row, "就诊ID", "visit_id")),
            hospital_code=_to_str(_resolve_col(row, "医院代码", "hospital_code", "定点医药机构代码")),
            hospital_name=_to_str(_resolve_col(row, "医院名称", "hospital_name")),
            birth_date=_to_str(_resolve_col(row, "出生日期", "birth_date")),
            age=_to_int(_resolve_col(row, "年龄", "age")),
            day_age=_to_int(_resolve_col(row, "年龄(天)", "天龄", "day_age")),
            birth_weight=_to_dec(_resolve_col(row, "出生体重", "birth_weight", "新生儿出生体重")),
            main_diag_code=_to_str(_resolve_col(row, "主要诊断编码", "main_diag_code", "主要诊断代码")),
            main_diag_name=_to_str(_resolve_col(row, "主要诊断名称", "main_diag_name", "主要诊断")),
            main_oprn_code=_to_str(_resolve_col(row, "主要手术操作代码", "主要手术编码", "main_oprn_code", "主要手术操作编码")),
            main_oprn_name=_to_str(_resolve_col(row, "主要手术名称", "main_oprn_name", "主要手术操作名称")),
            related_diag_code=_to_str(_resolve_col(row, "相关诊断代码", "相关诊断编码", "related_diag_code", "其他诊断编码")),
            related_oprn_code=_to_str(_resolve_col(row, "相关手术操作代码", "相关手术编码", "相关手术操作编码", "related_oprn_code", "其他手术编码")),
            admission_date=_to_str(_resolve_col(row, "入院日期", "admission_date", "入院时间")),
            discharge_date=_to_str(_resolve_col(row, "出院日期", "discharge_date", "出院时间")),
            total_cost=_to_dec(_resolve_col(row, "医疗费用总额(元)", "总费用", "医疗总费用", "total_cost", "金额合计")),
        ))
    return recs


def icd3(code):
    # ICD-10 前3位 = 类目（字母 + 2位数字），先去 x 扩展码再截断
    c = _to_str(code).upper().split("X")[0].split("X")[0].replace("X", "")
    return c[:3] if len(c) >= 3 else c


def main():
    xlsx = os.path.join(REPO, "output", "qk_merged_settlement.xlsx")
    nat_path = os.path.join(REPO, "data", "DIP3.0国家目录库.xlsx")
    df = pd.read_excel(xlsx, dtype=str)
    records = df_to_records(df)
    print(f"[+] 读取结算清单 {len(records)} 条")

    gen = LocalDirectoryGenerator(threshold=15)
    gen.load_national_directory(nat_path)
    print(f"[+] 国家目录库已加载，_nat_dip_codes 共 {len(getattr(gen, '_nat_dip_codes', set()))} 个")

    # 1) 逐条成组，复刻 app.py 新逻辑：先期分组按 (诊断+手术) 拆行
    groups = {}  # 显示键 -> {'cases': [main_diag_code,...], 'layer':...}
    for r in records:
        ck, layer = gen._refine_core_group_key(
            r.main_diag_code, r.main_oprn_code, r.related_oprn_code,
            r.related_diag_code, day_age=r.day_age, birth_weight=r.birth_weight,
            age=r.age, birth_date=r.birth_date, admission_date=r.admission_date,
        )
        # 新逻辑：先期分组·TRANSPLANT/LIFESUPPORT 按 (诊断4位+手术) 查国家目录拆行
        if layer == "先期分组" and (
            ck.startswith("PRI|LIFESUPPORT") or ck.startswith("PRI|TRANSPLANT")
        ):
            _parts = ck.split("|")
            _op = _parts[2] if len(_parts) > 2 else ""
            _diag4 = gen._extract_icd4(r.main_diag_code or "")
            if _op and _diag4:
                _ndip = gen._nat_dip_for_diag_oprn(_diag4, _op)
                if _ndip:
                    ck = _ndip
        g = groups.setdefault(ck, {"cases": [], "layer": layer})
        g["cases"].append(r.main_diag_code)
        g["layer"] = layer

    # 先期分组显示行：仅 layer=="先期分组"（排除 ③诊断辅助细分 的烧伤/肿瘤等）
    pri_keys = [k for k in groups if groups[k]["layer"] == "先期分组"]
    print(f"[+] 先期分组(line layer=先期分组)共 {len(pri_keys)} 个\n")

    mismatches = []
    unmatched = []
    print("="*100)
    print("先期分组逐组核对：显示键 -> 国家DIP码 -> 内嵌类目前3位 vs 病例主诊断前3位")
    print("="*100)
    for ck in sorted(pri_keys):
        cases = groups[ck]["cases"]
        # 复刻 app.py 完成块新逻辑取国家DIP码
        if ck in getattr(gen, '_nat_dip_codes', set()):
            ndip = ck
            matched = True
        elif ck.startswith("PRI|TRANSPLANT") or ck.startswith("PRI|LIFESUPPORT"):
            # 残留未匹配到的 PRI| 键：诚实保留，不注入错误类目
            ndip = ck
            matched = False
        else:
            ndip = ck  # LBW 已为国家码
            matched = True
        if not ndip:
            ndip = ck
            matched = False

        nat_row = gen._nat_rows_by_dip.get(ndip, {}) or {}
        nat_diag = _to_str(nat_row.get("主要诊断编码", "")) if nat_row else ""
        # DIP码"-"前段即内嵌主诊断
        dip_diag = ndip.split("-")[0] if "-" in ndip else nat_diag
        embedded_3 = icd3(dip_diag) or icd3(nat_diag)

        case3_set = sorted({icd3(c) for c in cases if icd3(c)})
        if not matched:
            # 诚实保留的残留 PRI| 键：不计入类目错位，单列标记
            unmatched.append((ck, ndip, case3_set))
            flag = "?? "
        else:
            # 是否一致：内嵌类目前3位 是否出现在 病例主诊断前3位集合中
            consistent = embedded_3 in case3_set if embedded_3 else False
            flag = "OK " if consistent else "XX "
            if not consistent:
                mismatches.append((ck, ndip, embedded_3, case3_set, cases))

        print(f"{flag}{ck}")
        print(f"     国家DIP码={ndip}  内嵌类目={dip_diag}(前3位={embedded_3})  国家行主要诊断编码={nat_diag}")
        print(f"     病例数={len(cases)}  病例主诊断前3位集合={case3_set}  "
              f"{'<- 未匹配(诚实保留)' if not matched else ('<-- 不一致' if not (embedded_3 in case3_set) else '')}")

    # 2) 汇总
    print("\n" + "="*100)
    print(f"类目错位组数(应为0): {len(mismatches)}")
    print(f"诚实保留未匹配 PRI| 组数: {len(unmatched)}")
    print("="*100)
    for ck, ndip, case3 in unmatched:
        print(f"\n[未匹配保留] 显示键={ck}  病例主诊断前3位: {case3}")
    for ck, ndip, emb3, case3, cases in mismatches:
        print(f"\n[错位] 显示键 : {ck}")
        print(f"国家DIP码   : {ndip}  (内嵌类目前3位={emb3})")
        print(f"病例主诊断前3位: {case3}")
        print(f"组内真实主诊断样本(前5): {cases[:5]}")


if __name__ == "__main__":
    main()
