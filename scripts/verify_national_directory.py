# -*- coding: utf-8 -*-
"""国家目录库一致性校验：官方《分组方案》xlsx vs 本系统 data/DIP3.0国家目录库.xlsx。

用于随时复核本系统目录库是否与官方方案完全一致（防止 PDF 抽取类数据缺陷回归）。

用法:
    python scripts/verify_national_directory.py [--official 官方xlsx路径] [--local 本系统xlsx路径]

校验项:
    1. 各 sheet 行数对齐；
    2. 核心病种按「方案序号」逐字段比对（诊断/主手术/相关手术/其他诊断/是否耐药/烧伤程度）；
    3. 不纳入分组（诊断、手术操作）编码集合双向比对；
    4. 基层病种（诊断+手术对）、结核耐药诊断列表比对。

退出码：0=完全一致；1=存在差异（差异明细同时写入 output/目录库校验报告.txt）
"""
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

DEFAULT_OFFICIAL = Path(r"D:\Work\DIP\按病种分值（DIP）付费3.0版分组方案.xlsx")
DEFAULT_LOCAL = HERE / "data" / "DIP3.0国家目录库.xlsx"
REPORT = HERE / "output" / "目录库校验报告.txt"

CORE_FIELDS = ["主要诊断编码", "主要手术操作编码", "相关手术操作编码",
               "其他诊断编码", "是否耐药", "烧伤腐蚀伤程度"]


def norm(v):
    s = str(v).strip()
    return "" if s.lower() in ("nan", "none", "") else s


def blocks(raw):
    """按块读取官方 sheet（官方表存在内嵌子表头，如先期分组的低出生体重儿子表）。"""
    header, out = None, []
    for _, row in raw.iterrows():
        vals = [norm(v) for v in row.tolist()]
        if not any(vals):
            continue
        if vals[0] in ("分类", "序号", "主要诊断编码", "主要手术操作编码"):
            header = vals
            continue
        if header is None:
            continue
        out.append({h: (vals[i] if i < len(vals) else "") for i, h in enumerate(header) if h})
    return out


def pick(d, *kws):
    """模糊取列（官方肿瘤表表头含换行，如「主要手术操作/\\n相关手术操作编码」）。"""
    for kw in kws:
        for k in d:
            if kw in k:
                return d[k]
    return ""


def load_official(path):
    xl = pd.ExcelFile(path)
    return {
        "XQ": blocks(xl.parse("一、先期分组", dtype=str, header=None)),
        "BX": blocks(xl.parse("二、并项规则下的核心病种", dtype=str, header=None)),
        "FZ_BURN": blocks(xl.parse("三、诊断辅助细分-烧伤类病种", dtype=str, header=None)),
        "FZ_ONCO": blocks(xl.parse("三、诊断辅助细分-肿瘤类病种", dtype=str, header=None)),
        "FZ_TB": blocks(xl.parse("三、诊断辅助细分-结核类病种", dtype=str, header=None)),
        "JC": blocks(xl.parse("四、基础规则下的核心病种", dtype=str, header=None)),
        "EXCL_DIAG": blocks(xl.parse("五、不纳入分组的主要诊断", dtype=str, header=None)),
        "EXCL_OPRN": blocks(xl.parse("五、不纳入分组的主要手术操作", dtype=str, header=None)),
        "GRASS": blocks(xl.parse("六、基层病种", dtype=str, header=None)),
        "TB_DR": blocks(xl.parse("附表—结核耐药诊断", dtype=str, header=None)),
    }


def verify(official_path=DEFAULT_OFFICIAL, local_path=DEFAULT_LOCAL):
    lines = []
    problems = 0

    def log(s=""):
        lines.append(str(s))
        print(s)

    if not official_path.exists():
        log(f"!! 未找到官方 xlsx：{official_path}")
        return 1, lines

    off = load_official(official_path)
    sheets = {s: pd.ExcelFile(local_path).parse(s, dtype=str)
              for s in pd.ExcelFile(local_path).sheet_names}
    core = sheets["核心病种"]
    core["方案序号"] = core["方案序号"].map(norm)
    core["分类"] = core["分类"].map(norm)

    log("=" * 92)
    log("一、行数对齐")
    log("=" * 92)
    expect = {
        "XQ": sum(1 for r in off["XQ"] if norm(r.get("序号")).isdigit()),
        "BX": sum(1 for r in off["BX"] if norm(r.get("序号")).isdigit()),
        "FZ": sum(sum(1 for r in off[k] if norm(r.get("序号")).isdigit())
                  for k in ("FZ_BURN", "FZ_ONCO", "FZ_TB")),
        "JC": sum(1 for r in off["JC"] if norm(r.get("序号")).isdigit()),
    }
    got = core["分类"].value_counts().to_dict()
    for k in ("XQ", "BX", "FZ", "JC"):
        ok = expect[k] == got.get(k, 0)
        problems += 0 if ok else 1
        log(f"[{'OK ' if ok else '差异'}] 核心病种 {k}: 官方={expect[k]} 本系统={got.get(k, 0)}")

    for name, rows, sheet, key in [
        ("不纳入分组_主要诊断", off["EXCL_DIAG"], "不纳入分组_主要诊断", "主要诊断编码"),
        ("不纳入分组_主要手术操作", off["EXCL_OPRN"], "不纳入分组_主要手术操作", "主要手术操作编码"),
    ]:
        os_ = {norm(r.get(key)) for r in rows if norm(r.get(key))}
        ls_ = {norm(v) for v in sheets[sheet][key].tolist() if norm(v)}
        lack, red = sorted(os_ - ls_), sorted(ls_ - os_)
        ok = not lack and not red
        problems += 0 if ok else 1
        log(f"[{'OK ' if ok else '差异'}] {name}: 官方={len(os_)} 本系统={len(ls_)} "
            f"缺={len(lack)} 多={len(red)}")
        if lack:
            log(f"    缺: {lack[:40]}")
        if red:
            log(f"    多: {red[:40]}")

    og = {(pick(r, "主要诊断编码"), pick(r, "主要手术操作编码"))
          for r in off["GRASS"] if pick(r, "主要诊断编码")}
    lg = {(norm(r["主要诊断编码"]), norm(r["主要手术操作编码"]))
          for _, r in sheets["基层病种"].iterrows()}
    ok = og == lg
    problems += 0 if ok else 1
    log(f"[{'OK ' if ok else '差异'}] 基层病种: 官方={len(og)} 本系统={len(lg)}")

    ot = {norm(r.get("主要诊断编码")) for r in off["TB_DR"] if norm(r.get("主要诊断编码"))}
    lt = {norm(v) for v in sheets["结核耐药诊断列表"]["主要诊断编码"].tolist() if norm(v)}
    ok = ot == lt
    problems += 0 if ok else 1
    log(f"[{'OK ' if ok else '差异'}] 结核耐药诊断列表: 官方={len(ot)} 本系统={len(lt)}")

    log("")
    log("=" * 92)
    log("二、核心病种逐字段比对")
    log("=" * 92)
    ndiff = 0
    for sec, cls in [("XQ", "XQ"), ("BX", "BX"), ("FZ_BURN", "FZ"),
                     ("FZ_ONCO", "FZ"), ("FZ_TB", "FZ"), ("JC", "JC")]:
        for r in off[sec]:
            seq = norm(r.get("序号"))
            if not seq.isdigit():
                continue
            key = f"{cls}-{seq}"
            sub = core[core["方案序号"] == key]
            if sub.empty:
                ndiff += 1
                log(f"!! 本系统缺少 {key}")
                continue
            lr = sub.iloc[0]
            diffs = []
            for f in CORE_FIELDS:
                ov = norm(r.get(f))
                if sec == "FZ_ONCO" and f == "主要手术操作编码":
                    ov = pick(r, "主要手术操作", "手术操作编码")
                lv = norm(lr.get(f))
                if ov != lv:
                    diffs.append((f, ov, lv))
            if diffs:
                ndiff += 1
                if ndiff <= 20:
                    log(f"差异 {key}:")
                    for f, a, b in diffs:
                        log(f"    {f}: 官方={a[:90]!r}")
                        log(f"         本系统={b[:90]!r}")
    problems += ndiff
    log(f"存在差异的核心病种行数 = {ndiff}")

    log("")
    log("结论：" + ("完全一致 ✓" if problems == 0 else f"存在 {problems} 处差异 ✗"))
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    log(f"报告已写入 {REPORT}")
    return (0 if problems == 0 else 1), lines


def main():
    args = sys.argv[1:]
    official = DEFAULT_OFFICIAL
    local = DEFAULT_LOCAL
    if "--official" in args:
        official = Path(args[args.index("--official") + 1])
    if "--local" in args:
        local = Path(args[args.index("--local") + 1])
    code, _ = verify(official, local)
    return code


if __name__ == "__main__":
    sys.exit(main())
