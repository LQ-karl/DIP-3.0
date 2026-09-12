# -*- coding: utf-8 -*-
"""由《DIP 3.0 版分组方案》PDF 构建国家目录库 xlsx。

⚠️ 已由 PDF 抽取方案退役（2026-09-12）：
    PDF 版面抽取存在数据缺陷（编码丢小数点、相邻编码粘连、整行丢失），已确认共
    丢失/损坏 78 条记录。现行权威构建脚本改为
    `scripts/build_dip30_national_directory_from_xlsx.py`（直接读取官方 xlsx）。
    本脚本仅保留作历史追溯，请勿再用它重建目录库；
    一致性核验请用 `scripts/verify_national_directory.py`。

用法:
    python scripts/build_dip30_national_directory.py [--pdf 路径] [--out 路径] [--no-backup]

产出 sheet:
    核心病种                 5125 行（XQ 19 + BX 1725 + FZ 烧伤25/肿瘤42/结核46 + JC 3268）
    不纳入分组_主要诊断       4720 行
    不纳入分组_主要手术操作   4087 行（含处理规则 + 限定主诊断范围）
    基层病种                 127 行
    结核耐药诊断列表          48 行

DIP 编码规则（已与用户确认）:
    {主要诊断编码}-{主要手术操作编码}-{相关手术操作编码}[-{差异维度}]
    - 主要手术操作编码为空时记「保守治疗」
    - 多值码一律原样保留（| 分隔）
    - 三段无法唯一定位时追补第 4 段「差异维度」：
        XQ 低出生体重儿 -> 天龄|出生体重
        FZ 烧伤        -> 烧伤腐蚀伤面积
        FZ 肿瘤        -> 其他诊断编码（肿瘤范围）
        FZ 结核        -> 是否耐药
    解析约定：ICD-9-CM-3 操作码不含 '-'，故用 rsplit('-', 3) 可从右往左正确拆段，
    不会与主要诊断编码 A15-A16 自带的 '-' 冲突。
"""
import sys
import re
import json
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

DEFAULT_PDF = HERE / "dip3_group_plan_tmp.pdf"
DEFAULT_OUT = HERE / "data" / "DIP3.0国家目录库.xlsx"
SECTIONS_JSON = HERE / "output" / "dip30_plan" / "dip30_plan_sections.json"

# 章节 -> (分类, 成组层次, 辅助细分类别)
SEC_META = {
    "XQ":       ("XQ", "先期分组", ""),
    "BX":       ("BX", "并项规则", ""),
    "FZ_BURN":  ("FZ", "诊断辅助细分", "烧伤类"),
    "FZ_ONCO":  ("FZ", "诊断辅助细分", "肿瘤类"),
    "FZ_TB":    ("FZ", "诊断辅助细分", "结核类"),
    "JC":       ("JC", "基本规则", ""),
}

CORE_COLS = [
    "方案序号", "DIP编码", "分类", "成组层次", "辅助细分类别", "分组名称",
    "主要诊断编码", "主要诊断名称",
    "主要手术操作编码", "主要手术操作名称",
    "相关手术操作编码", "相关手术操作名称",
    "其他诊断编码", "其他诊断名称",
    "烧伤腐蚀伤程度", "烧伤腐蚀伤面积",
    "是否耐药", "天龄", "出生体重",
    "说明", "打印页码",
]

# 不纳入分组·主要手术操作：说明文本 -> (处理规则, 限定主诊断范围)
OPRN_RULE_MAP = [
    ("作为主要诊断，可作为主要手术操作", "限范围可作主要手术操作"),
    ("不可作为主要手术操作", "不可作为主要手术操作"),
    ("按保守治疗入组", "按保守治疗入组"),
]
ENDOSCOPE_SCOPE = "A00-A09|C15-C26|D01|D12|D13|D37|I85|K20-K93"


def norm_oprn_remark(raw: str):
    """把 PDF 说明文本规整为 (处理规则, 限定主诊断范围)。"""
    s = (raw or "").replace(" ", "").strip()
    if not s:
        return "按保守治疗入组", ""
    # 提取「…作为主要诊断」前的范围串
    m = re.match(r"^(.*?)作为主要诊断，可作为主要手术操作$", s)
    if m:
        scope = m.group(1).replace("|", "|")
        return "限范围可作主要手术操作", scope
    if "不可作为主要手术操作" in s:
        return "不可作为主要手术操作", ""
    if "按保守治疗入组" in s:
        return "按保守治疗入组", ""
    return s, ""


def make_dip_code(diag: str, main_oprn: str, rel_oprn: str, extra: str = "") -> str:
    parts = [diag or "", main_oprn or "保守治疗", rel_oprn or ""]
    code = "-".join(parts)
    if extra:
        code = f"{code}-{extra}"
    return code


def build_core(d: dict) -> pd.DataFrame:
    """把六段原始行规整为核心病种表。"""
    rows = []
    for sec, (cls, layer, aux_kind) in SEC_META.items():
        for item in d.get(sec, []):
            c = list(item["cells"]) + [""] * 16
            # 跳过混入的表头行
            if c[0] in ("分类", "序号", "主要诊断编码"):
                continue
            if not re.fullmatch(r"\d+", (c[1] or "").strip()):
                continue
            seq = c[1].strip()

            rec = {k: "" for k in CORE_COLS}
            rec["方案序号"] = f"{cls}-{seq}"
            rec["分类"] = cls
            rec["成组层次"] = layer
            rec["辅助细分类别"] = aux_kind
            rec["打印页码"] = item["page"]

            if sec == "XQ":
                # ['XQ','序号','主要诊断编码','分组名称','主要手术操作编码','主要手术操作名称','说明']
                # LBW 子表: ['XQ','序号','P07','分组名称','天龄','出生体重','']
                diag, name_or_group, f4, f5, f6 = c[2], c[3], c[4], c[5], c[6]
                rec["分组名称"] = name_or_group.strip()
                rec["主要诊断编码"] = diag.strip()
                if diag.strip() == "P07":
                    # 低出生体重儿子表：第 5 列是天龄、第 6 列是出生体重
                    rec["天龄"] = f4.strip()
                    rec["出生体重"] = f5.strip()
                    rec["主要诊断名称"] = ""
                    extra = f"{f4.strip()}|{f5.strip()}" if f4.strip() or f5.strip() else ""
                    code = make_dip_code(diag.strip(), "", "", extra)
                else:
                    rec["主要诊断名称"] = "所有诊断"
                    rec["主要手术操作编码"] = f4.strip()
                    rec["主要手术操作名称"] = f5.strip()
                    rec["说明"] = f6.strip()
                    code = make_dip_code(diag.strip(), f4.strip(), "")

            elif sec == "BX":
                # 8 列
                rec["主要诊断编码"] = c[2].strip()
                rec["主要诊断名称"] = c[3].strip()
                rec["主要手术操作编码"] = c[4].strip()
                rec["主要手术操作名称"] = c[5].strip()
                rec["相关手术操作编码"] = c[6].strip()
                rec["相关手术操作名称"] = c[7].strip()
                code = make_dip_code(c[2].strip(), c[4].strip(), c[6].strip())

            elif sec == "FZ_BURN":
                # 10 列: 分类 序号 主诊断 程度 其他诊断(面积码) 面积 主手术码 主手术名 相关手术码 相关手术名
                rec["主要诊断编码"] = c[2].strip()
                rec["主要诊断名称"] = c[3].strip()
                rec["烧伤腐蚀伤程度"] = c[3].strip()
                rec["其他诊断编码"] = c[4].strip()
                rec["烧伤腐蚀伤面积"] = c[5].strip()
                rec["主要手术操作编码"] = c[6].strip()
                rec["主要手术操作名称"] = c[7].strip()
                rec["相关手术操作编码"] = c[8].strip()
                rec["相关手术操作名称"] = c[9].strip()
                code = make_dip_code(c[2].strip(), c[6].strip(), c[8].strip(), c[5].strip())

            elif sec == "FZ_ONCO":
                # 8 列: 分类 序号 主诊断码 主诊断名 其他诊断码 其他诊断名 操作码 操作名
                rec["主要诊断编码"] = c[2].strip()
                rec["主要诊断名称"] = c[3].strip()
                rec["其他诊断编码"] = c[4].strip()
                rec["其他诊断名称"] = c[5].strip()
                rec["主要手术操作编码"] = c[6].strip()
                rec["主要手术操作名称"] = c[7].strip()
                code = make_dip_code(c[2].strip(), c[6].strip(), "", c[4].strip())

            elif sec == "FZ_TB":
                # 8 列: 分类 序号 主诊断码 主诊断名 主手术码 主手术名 是否耐药 耐药说明
                rec["主要诊断编码"] = c[2].strip()
                rec["主要诊断名称"] = c[3].strip()
                rec["主要手术操作编码"] = c[4].strip()
                rec["主要手术操作名称"] = c[5].strip()
                rec["是否耐药"] = c[6].strip()
                rec["说明"] = c[7].strip()
                code = make_dip_code(c[2].strip(), c[4].strip(), "", c[6].strip())

            else:  # JC
                rec["主要诊断编码"] = c[2].strip()
                rec["主要诊断名称"] = c[3].strip()
                rec["主要手术操作编码"] = c[4].strip()
                rec["主要手术操作名称"] = c[5].strip()
                code = make_dip_code(c[2].strip(), c[4].strip(), "")

            rec["DIP编码"] = code
            rows.append(rec)

    df = pd.DataFrame(rows, columns=CORE_COLS)
    return df


def build_excl_diag(d):
    rows = []
    seen = set()
    for item in d.get("EXCL_DIAG", []):
        c = list(item["cells"]) + ["", ""]
        code, name = c[0].strip(), c[1].strip()
        if not code or code == "主要诊断编码":
            continue
        if code in seen:
            continue
        seen.add(code)
        rows.append({"主要诊断编码": code, "主要诊断名称": name})
    return pd.DataFrame(rows, columns=["主要诊断编码", "主要诊断名称"])


def build_excl_oprn(d):
    rows = []
    seen = set()
    for item in d.get("EXCL_OPRN", []):
        c = list(item["cells"]) + ["", "", ""]
        code, name = c[0].strip(), c[1].strip()
        if not code or code == "主要手术操作编码":
            continue
        if code in seen:
            continue
        seen.add(code)
        rule, scope = norm_oprn_remark(c[2])
        rows.append({
            "主要手术操作编码": code,
            "主要手术操作名称": name,
            "处理规则": rule,
            "限定主诊断范围": scope or (ENDOSCOPE_SCOPE if rule == "限范围可作主要手术操作" else ""),
            "原始说明": c[2].strip(),
        })
    return pd.DataFrame(rows, columns=[
        "主要手术操作编码", "主要手术操作名称", "处理规则", "限定主诊断范围", "原始说明"])


def build_grassroot(d):
    rows = []
    for item in d.get("GRASSROOT", []):
        c = list(item["cells"]) + [""] * 5
        if not re.fullmatch(r"\d+", (c[0] or "").strip()):
            continue
        rows.append({
            "序号": c[0].strip(),
            "主要诊断编码": c[1].strip(),
            "主要诊断名称": c[2].strip(),
            "主要手术操作编码": c[3].strip(),
            "主要手术操作名称": c[4].strip(),
        })
    return pd.DataFrame(rows, columns=[
        "序号", "主要诊断编码", "主要诊断名称", "主要手术操作编码", "主要手术操作名称"])


def build_tb_dr(d):
    rows = []
    seen = set()
    for item in d.get("TB_DR", []):
        c = list(item["cells"]) + ["", ""]
        code, name = c[0].strip(), c[1].strip()
        if not code or code == "主要诊断编码" or code in seen:
            continue
        seen.add(code)
        rows.append({"主要诊断编码": code, "主要诊断名称": name})
    return pd.DataFrame(rows, columns=["主要诊断编码", "主要诊断名称"])


def main():
    pdf = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PDF
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUT

    if not SECTIONS_JSON.exists():
        sys.path.insert(0, str(HERE / "scripts"))
        from parse_dip30_group_plan import main as parse_main
        sys.argv = ["parse", str(pdf)]
        parse_main()

    d = json.loads(SECTIONS_JSON.read_text(encoding="utf-8"))

    core = build_core(d)
    excl_diag = build_excl_diag(d)
    excl_oprn = build_excl_oprn(d)
    grassroot = build_grassroot(d)
    tb_dr = build_tb_dr(d)

    # 统一把 NaN 归一为空串，避免后续字符串匹配出错
    for _df in (core, excl_diag, excl_oprn, grassroot, tb_dr):
        for _c in _df.columns:
            _df[_c] = _df[_c].fillna("").astype(str).str.strip()

    # ---- 一致性校验 ----
    print("== 构建结果 ==")
    print(f"核心病种                {len(core)} 行")
    print(core["成组层次"].value_counts().to_string())
    print(f"不纳入分组_主要诊断     {len(excl_diag)} 行")
    print(f"不纳入分组_主要手术操作 {len(excl_oprn)} 行")
    print(excl_oprn["处理规则"].value_counts().to_string())
    print(f"基层病种                {len(grassroot)} 行")
    print(f"结核耐药诊断列表        {len(tb_dr)} 行")

    dup_seq = core["方案序号"].duplicated().sum()
    dup_code = core["DIP编码"].duplicated().sum()
    print(f"\n方案序号重复 {dup_seq} | DIP编码重复 {dup_code}")
    if dup_code:
        print("!! DIP 编码仍有重复，样例：")
        print(core[core["DIP编码"].duplicated(keep=False)]["DIP编码"].head(10).to_string())

    # ---- 备份旧库并写出（备份已存在则不覆盖，避免重跑时把新库备份成旧库）----
    if out.exists():
        stamp = datetime.now().strftime("%Y%m%d")
        backup = out.with_name(f"{out.stem}_征求意见稿备份_{stamp}{out.suffix}")
        if backup.exists():
            print(f"\n备份已存在，跳过备份 -> {backup.name}")
        else:
            try:
                out.chmod(0o666)
            except Exception:
                pass
            shutil.copy2(out, backup)
            print(f"\n旧库已备份 -> {backup.name}")

    with pd.ExcelWriter(out, engine="openpyxl") as w:
        core.to_excel(w, sheet_name="核心病种", index=False)
        excl_diag.to_excel(w, sheet_name="不纳入分组_主要诊断", index=False)
        excl_oprn.to_excel(w, sheet_name="不纳入分组_主要手术操作", index=False)
        grassroot.to_excel(w, sheet_name="基层病种", index=False)
        tb_dr.to_excel(w, sheet_name="结核耐药诊断列表", index=False)

    print(f"新库已写出 -> {out}")
    core.to_csv(HERE / "output" / "dip30_plan" / "core_preview.csv",
                index=False, encoding="utf-8-sig")


if __name__ == "__main__":
    main()
