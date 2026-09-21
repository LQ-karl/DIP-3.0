# -*- coding: utf-8 -*-
"""以《DIP_疾病严重程度分型字典_3.0修订研究版.xlsx》重建 data/中重度分型诊断.xlsx。

背景（用户裁决 2026-09-21）：
  附件《DIP_疾病严重程度分型字典_3.0修订研究版.xlsx》的『DIP中重度候选字典』sheet
  共 998 条候选，分三档：
    - 重度候选 147 条：全部"是（核心候选）" → 可直接触发
    - 中度候选 498 条：全部"是（核心候选）" → 可直接触发
    - 条件候选 353 条：全部"否，需病例级验证" → 不进入自动触发表
  引擎（src/core/auxiliary_directory.py）只识别 GX_ASSI 表里 DIP_ASSISTANT_CODE
  两级（'2'=重度 / '1'=中度），没有"条件候选"承载位置。
  用户裁决：**条件候选 353 条先排除，后续单独评估**；本次仅用
  重度候选(147)+中度候选(498)=645 条替换原字典，引擎双层级结构不变。

产出：
  1) data/中重度分型诊断.xlsx  <- 仅含可直接触发的 重症/中度（645 条），GX_ASSI + 示例和说明
  2) output/中重度_条件候选_待评估.xlsx  <- 条件候选 353 条（保留原列，供后续评估）
备份：
  output/_dict_backup_20260921/中重度分型诊断.xlsx  <- 替换前原文件（已存在即跳过覆盖）

GX_ASSI schema（与历史格式保持一致，保证 auxiliary_directory / local_directory_generator 读取不变）：
  ID, DIP_MAIN_CODE_TYPE, DIP_MAIN_NAME_TYPE, DIP_FX_TYPE, DIP_FX_NAME_TYPE,
  DIP_ASSISTANT_TYPE, DIP_ASSISTANT_CODE, DIP_ASSISTANT_NAME,
  ASSI_ITEM_ID, ASSI_ITEM_NAME, REMARK
  - DIP_ASSISTANT_TYPE = 'QTZD'（其他诊断/次要诊断）
  - DIP_ASSISTANT_CODE = '2'(重度) / '1'(中度)
  - DIP_ASSISTANT_NAME = '重度' / '中度'
  - ASSI_ITEM_ID = 疾病编码（保留 +/* 剑号星号写法）
  - ASSI_ITEM_NAME = 疾病名称
  - 引擎按 ASSI_ITEM_ID 取前 3 位（去点）作为匹配键；+/* 后缀原样保留。
"""
import os
import shutil
import datetime as dt
import pandas as pd

ROOT = r"F:\DIP"
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "output")
SRC = r"D:\Work\DIP\DIP_疾病严重程度分型字典_3.0修订研究版.xlsx"
BK = os.path.join(OUT, "_dict_backup_20260921")

# 引擎 GX_ASSI 列顺序（不可改，加载器按列名读取）
COLS = ["ID", "DIP_MAIN_CODE_TYPE", "DIP_MAIN_NAME_TYPE", "DIP_FX_TYPE",
        "DIP_FX_NAME_TYPE", "DIP_ASSISTANT_TYPE", "DIP_ASSISTANT_CODE",
        "DIP_ASSISTANT_NAME", "ASSI_ITEM_ID", "ASSI_ITEM_NAME", "REMARK"]

# 候选档 -> (DIP_ASSISTANT_CODE, DIP_ASSISTANT_NAME)
LEVEL_MAP = {"重度候选": ("2", "重度"), "中度候选": ("1", "中度")}

log = []


def L(*a):
    s = " ".join(str(x) for x in a)
    log.append(s)
    print(s)


def backup_old():
    os.makedirs(BK, exist_ok=True)
    dst = os.path.join(BK, "中重度分型诊断.xlsx")
    src = os.path.join(DATA, "中重度分型诊断.xlsx")
    if os.path.exists(src) and not os.path.exists(dst):
        shutil.copy2(src, dst)
        L(f"[备份] {src} -> {dst}")


def load_candidates():
    raw = pd.read_excel(SRC, sheet_name="DIP中重度候选字典", dtype=str,
                        keep_default_na=False)
    raw.columns = [str(c).strip() for c in raw.columns]
    need = {"疾病编码", "疾病名称", "DIP候选层级"}
    assert need.issubset(set(raw.columns)), f"候选字典缺少列: {need - set(raw.columns)}"
    return raw


def build_gx_assi(raw):
    rows = []
    seen = set()  # (code_value, assi_id) 去重
    counts = {}
    for _, r in raw.iterrows():
        level = str(r.get("DIP候选层级", "")).strip()
        if level not in LEVEL_MAP:
            continue  # 条件候选（及任何未知档）跳过
        code_value, name = LEVEL_MAP[level]
        code = str(r.get("疾病编码", "")).strip()
        dname = str(r.get("疾病名称", "")).strip()
        if not code or code.lower() in ("nan", "none"):
            continue
        key = (code_value, code)
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "ID": "", "DIP_MAIN_CODE_TYPE": "", "DIP_MAIN_NAME_TYPE": "",
            "DIP_FX_TYPE": "ALL", "DIP_FX_NAME_TYPE": "ALL",
            "DIP_ASSISTANT_TYPE": "QTZD", "DIP_ASSISTANT_CODE": code_value,
            "DIP_ASSISTANT_NAME": name, "ASSI_ITEM_ID": code,
            "ASSI_ITEM_NAME": dname, "REMARK": "",
        })
        counts[level] = counts.get(level, 0) + 1

    # ID 顺序承载行号（重度在前、中度在后，与历史一致）
    order = {"2": 0, "1": 1}
    rows.sort(key=lambda x: (order.get(x["DIP_ASSISTANT_CODE"], 9), x["ASSI_ITEM_ID"]))
    for i, r in enumerate(rows, 1):
        r["ID"] = i
    gx = pd.DataFrame(rows, columns=COLS)
    L(f"GX_ASSI 行数 = {len(gx)}  重度={counts.get('重度候选',0)} 中度={counts.get('中度候选',0)}")
    return gx


def build_example(gx):
    today = dt.date.today().isoformat()
    n_sev = int((gx["DIP_ASSISTANT_CODE"] == "2").sum())
    n_mod = int((gx["DIP_ASSISTANT_CODE"] == "1").sum())
    # 3 位前缀冲突（同前缀同时出现在重度与中度，引擎按重度优先）
    def pref(c):
        return str(c).replace(".", "").upper()[:3]
    sev = set(gx.loc[gx["DIP_ASSISTANT_CODE"] == "2", "ASSI_ITEM_ID"].map(pref))
    mod = set(gx.loc[gx["DIP_ASSISTANT_CODE"] == "1", "ASSI_ITEM_ID"].map(pref))
    overlap = sorted(sev & mod)
    lines = [
        "说明：本字典由《DIP_疾病严重程度分型字典_3.0修订研究版.xlsx》的『DIP中重度候选字典』sheet 重建。",
        f"重建日期：{today}。",
        "口径（用户裁决 2026-09-21）：",
        f"  - 仅纳入可直接触发的 重度候选 + 中度候选，GX_ASSI 共 {len(gx)} 条（重度 {n_sev} / 中度 {n_mod}）。",
        "  - 条件候选 353 条（标注“否，需病例级验证”）按裁决暂排除，未进入自动触发表；",
        "    清单保留于 output/中重度_条件候选_待评估.xlsx，待后续单独评估。",
        "  - 引擎仅识别 DIP_ASSISTANT_CODE 两级：'2'=重度 / '1'=中度，结构不变。",
        f"  - 3 位前缀（去点）冲突 {len(overlap)} 个，引擎按重度优先解析：{', '.join(overlap)}",
        "legend：QTZD=其他诊断（次要诊断）；DIP_FX_TYPE=ALL 表示适用全部辅助分型场景。",
        "匹配键：引擎对 ASSI_ITEM_ID 取前 3 位（去点）匹配病历次要诊断；+/* 剑号星号原样保留。",
    ]
    # 造一个含表头的 DataFrame；第 0 行做标题占位，下面逐行说明
    df = pd.DataFrame({"说明": lines})
    return df


def save_conditional(raw):
    cond = raw[raw["DIP候选层级"].astype(str).str.strip() == "条件候选"].copy()
    cond = cond[cond["疾病编码"].astype(str).str.strip() != ""]
    path = os.path.join(OUT, "中重度_条件候选_待评估.xlsx")
    cond.to_excel(path, index=False)
    L(f"[写出] {path}  条件候选条数 = {len(cond)}")


def main():
    backup_old()
    raw = load_candidates()
    total = len(raw)
    L(f"候选字典原始行数（含表头外）= {total}")

    gx = build_gx_assi(raw)
    example = build_example(gx)

    # GX_ASSI 必须为第一个 sheet（data_loader.load_excel 默认读首表）
    out_path = os.path.join(DATA, "中重度分型诊断.xlsx")
    with pd.ExcelWriter(out_path, engine="openpyxl") as w:
        gx.to_excel(w, sheet_name="GX_ASSI", index=False)
        example.to_excel(w, sheet_name="示例和说明", index=False)
    L(f"[写出] {out_path}")

    save_conditional(raw)

    log_path = os.path.join(OUT, "_rebuild_zhongzhongdu_research_log.txt")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(log))
    print("ALL DONE")


if __name__ == "__main__":
    main()
