# -*- coding: utf-8 -*-
"""以 4 个官方附件重建本系统辅助字典（用户裁决 2026-09-14）。

产出：
  1) data/CCI.xlsx                <- 附件1 Charlson合并症指数CCI字典表（2292 条，医保版2.0编码）
  2) data/中重度分型诊断.xlsx      <- 附件3 中度/重度 替换；保留原 转移/放疗/化疗
  3) data/综合病种字典表.xlsx      <- 附件4 原样纳入
备份：output/_dict_backup_20260914/（output/ 已 gitignore，不污染仓库）
"""
import os
import shutil
import pandas as pd

DATA = r"F:\DIP\data"
OUT = r"F:\DIP\output"
BK = os.path.join(OUT, "_dict_backup_20260914")
os.makedirs(BK, exist_ok=True)
log = []


def L(*a):
    s = " ".join(str(x) for x in a)
    log.append(s)
    print(s)


def backup(name):
    src = os.path.join(DATA, name)
    if os.path.exists(src):
        shutil.copy2(src, os.path.join(BK, name))
        L(f"[备份] {name} -> output/_dict_backup_20260914/")


# ==================================================================
# 1) CCI.xlsx <- 附件1
# ==================================================================
A1 = r"D:\Work\DIP\Charlson合并症指数CCI字典表.xlsx"
att = pd.read_excel(A1, sheet_name="CCI查尔森合并症指数编码表", dtype=str,
                    keep_default_na=False, skiprows=2)
att.columns = [str(c).strip() for c in att.columns]
att = att[att["序号"].astype(str).str.strip().ne("")].copy()
for col in ["合并症中文名称", "权重", "Comorbidity (English)", "临床说明"]:
    att[col] = att[col].astype(str).str.strip().replace("", pd.NA).ffill()

cci = pd.DataFrame({
    "ICD10 code": att["医保版2.0编码"].astype(str).str.strip(),
    "Charlson component": att["合并症中文名称"].astype(str).str.strip(),
    "得分": att["权重"].astype(str).str.strip(),
})
cci = cci[(cci["ICD10 code"] != "") & (cci["得分"] != "")].reset_index(drop=True)
L("CCI 新表行数 =", len(cci), " 得分为空 =", int((cci['得分'] == '').sum()),
  " 唯一码 =", cci['ICD10 code'].nunique())
category_sheet = pd.read_excel(A1, sheet_name="CCI评分说明", dtype=str, keep_default_na=False, header=None)
backup("CCI.xlsx")
with pd.ExcelWriter(os.path.join(DATA, "CCI.xlsx"), engine="openpyxl") as w:
    cci.to_excel(w, sheet_name="Sheet1", index=False)
    category_sheet.to_excel(w, sheet_name="CCI评分说明", index=False, header=False)
L("[写出] data/CCI.xlsx")

# ==================================================================
# 2) 中重度分型诊断.xlsx <- 附件3 替换 中/重度
# ==================================================================
A3 = r"D:\Work\DIP\中重度分型字典表.xlsx"
sev = pd.read_excel(A3, sheet_name="重度诊断", dtype=str, keep_default_na=False)
mod = pd.read_excel(A3, sheet_name="中度诊断", dtype=str, keep_default_na=False)
sev.columns = [str(c).strip() for c in sev.columns]
mod.columns = [str(c).strip() for c in mod.columns]

old = pd.read_excel(os.path.join(DATA, "中重度分型诊断.xlsx"), sheet_name="GX_ASSI",
                    dtype=str, keep_default_na=False)
old.columns = [str(c).strip() for c in old.columns]
example = pd.read_excel(os.path.join(DATA, "中重度分型诊断.xlsx"), sheet_name="示例和说明",
                        dtype=str, keep_default_na=False, header=None)

COLS = ["ID", "DIP_MAIN_CODE_TYPE", "DIP_MAIN_NAME_TYPE", "DIP_FX_TYPE", "DIP_FX_NAME_TYPE",
        "DIP_ASSISTANT_TYPE", "DIP_ASSISTANT_CODE", "DIP_ASSISTANT_NAME",
        "ASSI_ITEM_ID", "ASSI_ITEM_NAME", "REMARK"]

rows = []
for code, name, src in [("1", "中度", mod), ("2", "重度", sev)]:
    for _, r in src.iterrows():
        c = str(r["疾病编码"]).strip()
        n = str(r["疾病名称"]).strip()
        if not c:
            continue
        rows.append({
            "ID": "", "DIP_MAIN_CODE_TYPE": "", "DIP_MAIN_NAME_TYPE": "",
            "DIP_FX_TYPE": "ALL", "DIP_FX_NAME_TYPE": "ALL",
            "DIP_ASSISTANT_TYPE": "QTZD", "DIP_ASSISTANT_CODE": code,
            "DIP_ASSISTANT_NAME": name, "ASSI_ITEM_ID": c, "ASSI_ITEM_NAME": n, "REMARK": "",
        })
new_sev_n = len(rows)

# 保留原文件的 转移(3) / 放疗(4) / 化疗(5) 行（不属于附件3 覆盖范围，引擎仍在使用转移）
keep = old[old["DIP_ASSISTANT_CODE"].astype(str).str.strip().isin(["3", "4", "5"])].copy()
keep = keep[COLS]
kept_n = len(keep)
L("中重度：新增 中/重度 =", new_sev_n, " 保留 转移/放疗/化疗 =", kept_n,
  "（转移", int((keep['DIP_ASSISTANT_CODE'] == '3').sum()),
  "放疗", int((keep['DIP_ASSISTANT_CODE'] == '4').sum()),
  "化疗", int((keep['DIP_ASSISTANT_CODE'] == '5').sum()), "）")

gx = pd.concat([pd.DataFrame(rows, columns=COLS), keep], ignore_index=True)
gx.insert(0, "序号", range(1, len(gx) + 1))
# 恢复 schema：原表无「序号」列，用 ID 承载行号
gx["ID"] = range(1, len(gx) + 1)
gx = gx[COLS]
L("中重度 新 GX_ASSI 行数 =", len(gx))

backup("中重度分型诊断.xlsx")
with pd.ExcelWriter(os.path.join(DATA, "中重度分型诊断.xlsx"), engine="openpyxl") as w:
    gx.to_excel(w, sheet_name="GX_ASSI", index=False)
    example.to_excel(w, sheet_name="示例和说明", index=False, header=False)
L("[写出] data/中重度分型诊断.xlsx")

# ==================================================================
# 3) 综合病种字典表.xlsx <- 附件4 原样纳入
# ==================================================================
A4 = r"D:\Work\DIP\综合病种字典表.xlsx"
dst = os.path.join(DATA, "综合病种字典表.xlsx")
shutil.copy2(A4, dst)
zh = pd.read_excel(dst, sheet_name="综合病种字典表", dtype=str, keep_default_na=False)
L("[写出] data/综合病种字典表.xlsx 行数 =", len(zh), " 组数 =", zh["组编号"].nunique(),
  " 分类码 =", zh["ICD-10分类码"].nunique())

with open(os.path.join(OUT, "_rebuild_dicts_log.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(log))
print("ALL DONE")
