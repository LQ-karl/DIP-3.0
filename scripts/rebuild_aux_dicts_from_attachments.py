# -*- coding: utf-8 -*-
"""以 4 个官方附件重建本系统辅助字典（用户裁决 2026-09-14）。

产出：
  1) data/CCI.xlsx                <- 附件1 Charlson合并症指数CCI字典表（2292 条，医保版2.0编码）
  2) data/中重度分型诊断.xlsx      <- 附件3 原样纳入（中度1327 + 重度221 = 1548 条）
  3) data/综合病种字典表.xlsx      <- 附件4 原样纳入
备份：output/_dict_backup_20260914/（output/ 已 gitignore，不污染仓库）

裁决沿革（用户 2026-09-14）：
  - 中重度：先"以附件替换中/重度、保留原转移/放疗/化疗"，后经复核确认附件3
    仅含「重度诊断/中度诊断」两 sheet、不含转移/放疗/化疗，故改为
    **全部删除 363 条、严格以附件3为准**。
  - 「肿瘤转移并发」判定不依赖字典码集：规范（DIP3.0 技术规范）规定为
    "次要诊断中含有恶性肿瘤的诊断且所属类目与主要诊断不同，住院天数3天以上"，
    由 ICD-10 编码规则直接判定（C00-C96 ⊇ C77/C78/C79）。
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

old_example = pd.read_excel(os.path.join(DATA, "中重度分型诊断.xlsx"), sheet_name="示例和说明",
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

# 严格以附件3为准（用户裁决 2026-09-14）：不保留旧表的 转移(3)/放疗(4)/化疗(5) 共363条。
# 附件3 仅含「重度诊断/中度诊断」两个 sheet；「肿瘤转移并发」按规范由 ICD-10
# 编码规则判定（次要诊断含 C00-C96 且类目与主诊断不同 + 住院≥3天），不依赖该码集。
L("中重度：中/重度 =", new_sev_n, "（严格以附件3为准，不再保留旧表转移/放疗/化疗）")

gx = pd.DataFrame(rows, columns=COLS)
gx.insert(0, "序号", range(1, len(gx) + 1))
# 恢复 schema：原表无「序号」列，用 ID 承载行号
gx["ID"] = range(1, len(gx) + 1)
gx = gx[COLS]
L("中重度 新 GX_ASSI 行数 =", len(gx))

backup("中重度分型诊断.xlsx")
with pd.ExcelWriter(os.path.join(DATA, "中重度分型诊断.xlsx"), engine="openpyxl") as w:
    gx.to_excel(w, sheet_name="GX_ASSI", index=False)
    old_example.to_excel(w, sheet_name="示例和说明", index=False, header=False)
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
