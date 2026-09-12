# -*- coding: utf-8 -*-
"""由《按病种分值（DIP）付费3.0版分组方案》**官方 xlsx** 重建国家目录库。

背景：
    原 data/DIP3.0国家目录库.xlsx 由 PDF（dip3_group_plan_tmp.pdf）抽取生成，
    PDF 版面抽取引入了三类数据缺陷：
      1) 编码丢失小数点（如 BX-1710 主手术串中 78.6900x002 -> 786900x002）；
      2) 相邻两行编码被粘连成一行（如 U84.700U84.800），导致两个编码都不生效；
      3) 整行丢失（不纳入分组清单少 23/24 条）。
    本脚本改以官方 xlsx 为权威数据源重建，消除上述缺陷。

用法:
    python scripts/build_dip30_national_directory_from_xlsx.py [--xlsx 路径] [--out 路径]

产出（与原库同结构，5 sheet）:
    核心病种 / 不纳入分组_主要诊断 / 不纳入分组_主要手术操作 / 基层病种 / 结核耐药诊断列表

DIP 编码规则（沿用既有口径）:
    {主要诊断编码}-{主要手术操作编码}-{相关手术操作编码}[-{差异维度}]
    - 主要手术操作编码为空时记「保守治疗」
    - 多值码原样保留（| 分隔）
    - 差异维度：XQ 低出生体重儿=天龄|出生体重；FZ 烧伤=烧伤腐蚀伤面积；
                FZ 肿瘤=其他诊断编码；FZ 结核=是否耐药
"""
import sys
import re
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

DEFAULT_XLSX = Path(r"D:\Work\DIP\按病种分值（DIP）付费3.0版分组方案.xlsx")
DEFAULT_OUT = HERE / "data" / "DIP3.0国家目录库.xlsx"

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

SEC_META = {
    "XQ": ("一、先期分组", "XQ", "先期分组", ""),
    "BX": ("二、并项规则下的核心病种", "BX", "并项规则", ""),
    "FZ_BURN": ("三、诊断辅助细分-烧伤类病种", "FZ", "诊断辅助细分", "烧伤类"),
    "FZ_ONCO": ("三、诊断辅助细分-肿瘤类病种", "FZ", "诊断辅助细分", "肿瘤类"),
    "FZ_TB": ("三、诊断辅助细分-结核类病种", "FZ", "诊断辅助细分", "结核类"),
    "JC": ("四、基础规则下的核心病种", "JC", "基本规则", ""),
}

ENDOSCOPE_SCOPE = "A00-A09|C15-C26|D01|D12|D13|D37|I85|K20-K93"


def norm(v):
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s.lower() in ("nan", "none", "") else s


def norm_oprn_remark(raw: str):
    """把「说明」文本规整为 (处理规则, 限定主诊断范围)。

    注意：官方单元格内含换行（如范围串被折行），须先去掉所有空白字符再匹配，
    否则「A00-A09|…|K20-K93作为主要诊断，可作为主要手术操作」这类规则会失配。
    """
    s = re.sub(r"\s+", "", str(raw or ""))
    if not s:
        return "按保守治疗入组", ""
    m = re.match(r"^(.*?)作为主要诊断，可作为主要手术操作$", s)
    if m:
        return "限范围可作主要手术操作", m.group(1)
    if "不可作为主要手术操作" in s:
        return "不可作为主要手术操作", ""
    if "按保守治疗入组" in s:
        return "按保守治疗入组", ""
    return s, ""


def read_blocks(raw_df, sheet_name):
    """通用：按「表头行」切块，返回 dict 列表。

    官方表格存在「一张 sheet 内嵌多块子表」（如 XQ 的低出生体重儿子表），
    每块自带表头（首列为「分类」或「序号」）。这里以首列值 == '分类' 或
    首列为已知表头关键字来识别新表头。
    """
    header = None
    out = []
    for _, row in raw_df.iterrows():
        vals = [norm(v) for v in row.tolist()]
        if not any(vals):
            continue
        first = vals[0]
        if first in ("分类", "序号", "主要诊断编码", "主要手术操作编码"):
            header = vals
            continue
        if header is None:
            continue
        d = {}
        for i, h in enumerate(header):
            if not h or i >= len(vals):
                continue
            d[h] = vals[i]
        out.append(d)
    return out


def pick(d, *kws):
    """按关键字找列（官方肿瘤表表头含换行 \n，需模糊匹配）。"""
    for kw in kws:
        for k in d:
            if kw in k:
                return d[k]
    return ""


def make_dip_code(diag, main_oprn, rel_oprn="", extra=""):
    code = "-".join([diag or "", main_oprn or "保守治疗", rel_oprn or ""])
    return f"{code}-{extra}" if extra else code


def build_core(xl):
    rows = []
    for sec, (sheet, cls, layer, aux_kind) in SEC_META.items():
        raw = xl.parse(sheet, dtype=str, header=None)
        for d in read_blocks(raw, sheet):
            seq = norm(d.get("序号"))
            if not seq or not seq.isdigit():
                continue
            rec = {k: "" for k in CORE_COLS}
            rec["方案序号"] = f"{cls}-{seq}"
            rec["分类"] = cls
            rec["成组层次"] = layer
            rec["辅助细分类别"] = aux_kind
            rec["打印页码"] = ""

            diag = norm(d.get("主要诊断编码"))
            rec["主要诊断编码"] = diag
            rec["分组名称"] = norm(d.get("分组名称"))
            rec["主要诊断名称"] = norm(d.get("主要诊断名称"))

            if sec == "XQ":
                if norm(d.get("出生体重")) or norm(d.get("天龄")):
                    # 低出生体重儿子表：无手术，差异维度 = 天龄|出生体重
                    rec["天龄"] = norm(d.get("天龄"))
                    rec["出生体重"] = norm(d.get("出生体重"))
                    rec["主要诊断名称"] = ""
                    rec["说明"] = norm(d.get("说明")) or ""
                    extra = "|".join(x for x in (rec["天龄"], rec["出生体重"]) if x)
                    rec["DIP编码"] = make_dip_code(diag, "", "", extra)
                else:
                    rec["主要手术操作编码"] = norm(d.get("主要手术操作编码"))
                    rec["主要手术操作名称"] = norm(d.get("主要手术操作名称"))
                    rec["说明"] = norm(d.get("说明"))
                    rec["DIP编码"] = make_dip_code(diag, rec["主要手术操作编码"], "")

            elif sec == "BX":
                rec["主要手术操作编码"] = norm(d.get("主要手术操作编码"))
                rec["主要手术操作名称"] = norm(d.get("主要手术操作名称"))
                rec["相关手术操作编码"] = norm(d.get("相关手术操作编码"))
                rec["相关手术操作名称"] = norm(d.get("相关手术操作名称"))
                rec["DIP编码"] = make_dip_code(diag, rec["主要手术操作编码"],
                                              rec["相关手术操作编码"])

            elif sec == "FZ_BURN":
                degree = norm(d.get("烧伤腐蚀伤程度"))
                rec["烧伤腐蚀伤程度"] = degree
                rec["主要诊断名称"] = degree          # 沿用旧库约定
                rec["其他诊断编码"] = norm(d.get("其他诊断编码"))
                rec["其他诊断名称"] = norm(d.get("其他诊断名称"))
                rec["烧伤腐蚀伤面积"] = norm(d.get("烧伤腐蚀伤面积"))
                rec["主要手术操作编码"] = norm(d.get("主要手术操作编码"))
                rec["主要手术操作名称"] = norm(d.get("主要手术操作名称"))
                rec["相关手术操作编码"] = norm(d.get("相关手术操作编码"))
                rec["相关手术操作名称"] = norm(d.get("相关手术操作名称"))
                rec["DIP编码"] = make_dip_code(diag, rec["主要手术操作编码"],
                                              rec["相关手术操作编码"],
                                              rec["烧伤腐蚀伤面积"])

            elif sec == "FZ_ONCO":
                # 官方表头为「主要手术操作/\n相关手术操作编码」（合并列）
                rec["其他诊断编码"] = norm(d.get("其他诊断编码"))
                rec["其他诊断名称"] = norm(d.get("其他诊断名称"))
                rec["主要手术操作编码"] = pick(d, "主要手术操作", "手术操作编码")
                rec["主要手术操作名称"] = pick(d, "主要手术操作名称", "手术操作名称")
                rec["DIP编码"] = make_dip_code(diag, rec["主要手术操作编码"], "",
                                              rec["其他诊断编码"])

            elif sec == "FZ_TB":
                rec["主要手术操作编码"] = norm(d.get("主要手术操作编码"))
                rec["主要手术操作名称"] = norm(d.get("主要手术操作名称"))
                rec["是否耐药"] = norm(d.get("是否耐药"))
                rec["说明"] = norm(d.get("是否耐药说明"))
                rec["DIP编码"] = make_dip_code(diag, rec["主要手术操作编码"], "",
                                              rec["是否耐药"])

            else:  # JC
                rec["主要手术操作编码"] = norm(d.get("主要手术操作编码"))
                rec["主要手术操作名称"] = norm(d.get("主要手术操作名称"))
                rec["DIP编码"] = make_dip_code(diag, rec["主要手术操作编码"], "")

            rows.append(rec)
    return pd.DataFrame(rows, columns=CORE_COLS)


def build_excl_diag(xl):
    raw = xl.parse("五、不纳入分组的主要诊断", dtype=str, header=None)
    rows, seen = [], set()
    for d in read_blocks(raw, "EXCL_DIAG"):
        code = norm(d.get("主要诊断编码"))
        if not code or code in seen:
            continue
        seen.add(code)
        rows.append({"主要诊断编码": code, "主要诊断名称": norm(d.get("主要诊断名称"))})
    return pd.DataFrame(rows, columns=["主要诊断编码", "主要诊断名称"])


def build_excl_oprn(xl):
    raw = xl.parse("五、不纳入分组的主要手术操作", dtype=str, header=None)
    rows, seen = [], set()
    for d in read_blocks(raw, "EXCL_OPRN"):
        code = norm(d.get("主要手术操作编码"))
        if not code or code in seen:
            continue
        seen.add(code)
        remark = norm(d.get("说明"))
        rule, scope = norm_oprn_remark(remark)
        rows.append({
            "主要手术操作编码": code,
            "主要手术操作名称": norm(d.get("主要手术操作名称")),
            "处理规则": rule,
            "限定主诊断范围": scope or (ENDOSCOPE_SCOPE if rule == "限范围可作主要手术操作" else ""),
            "原始说明": remark,
        })
    return pd.DataFrame(rows, columns=[
        "主要手术操作编码", "主要手术操作名称", "处理规则", "限定主诊断范围", "原始说明"])


def build_grassroot(xl):
    raw = xl.parse("六、基层病种", dtype=str, header=None)
    rows = []
    for d in read_blocks(raw, "GRASSROOT"):
        seq = norm(d.get("序号"))
        if not seq.isdigit():
            continue
        rows.append({
            "序号": seq,
            "主要诊断编码": norm(d.get("主要诊断编码")),
            "主要诊断名称": norm(d.get("主要诊断名称")),
            "主要手术操作编码": norm(d.get("主要手术操作编码")),
            "主要手术操作名称": norm(d.get("主要手术操作名称")),
        })
    return pd.DataFrame(rows, columns=[
        "序号", "主要诊断编码", "主要诊断名称", "主要手术操作编码", "主要手术操作名称"])


def build_tb_dr(xl):
    raw = xl.parse("附表—结核耐药诊断", dtype=str, header=None)
    rows, seen = [], set()
    for d in read_blocks(raw, "TB_DR"):
        code = norm(d.get("主要诊断编码"))
        if not code or code in seen:
            continue
        seen.add(code)
        rows.append({"主要诊断编码": code, "主要诊断名称": norm(d.get("主要诊断名称"))})
    return pd.DataFrame(rows, columns=["主要诊断编码", "主要诊断名称"])


def main():
    xlsx = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_XLSX
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUT
    if not xlsx.exists():
        print(f"!! 未找到官方 xlsx：{xlsx}")
        return 1

    xl = pd.ExcelFile(xlsx)
    core = build_core(xl)
    excl_diag = build_excl_diag(xl)
    excl_oprn = build_excl_oprn(xl)
    grassroot = build_grassroot(xl)
    tb_dr = build_tb_dr(xl)

    for df in (core, excl_diag, excl_oprn, grassroot, tb_dr):
        for c in df.columns:
            df[c] = df[c].fillna("").astype(str).str.strip()

    print("== 重建结果 ==")
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
        print(core[core["DIP编码"].duplicated(keep=False)]["DIP编码"].head(10).to_string())

    if out.exists():
        stamp = datetime.now().strftime("%Y%m%d")
        backup = out.with_name(f"{out.stem}_PDF抽取版备份_{stamp}{out.suffix}")
        if backup.exists():
            print(f"\n备份已存在，跳过 -> {backup.name}")
        else:
            shutil.copy2(out, backup)
            print(f"\n旧库(PDF抽取版)已备份 -> {backup.name}")

    with pd.ExcelWriter(out, engine="openpyxl") as w:
        core.to_excel(w, sheet_name="核心病种", index=False)
        excl_diag.to_excel(w, sheet_name="不纳入分组_主要诊断", index=False)
        excl_oprn.to_excel(w, sheet_name="不纳入分组_主要手术操作", index=False)
        grassroot.to_excel(w, sheet_name="基层病种", index=False)
        tb_dr.to_excel(w, sheet_name="结核耐药诊断列表", index=False)
    print(f"新库已写出 -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
