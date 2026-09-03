# -*- coding: utf-8 -*-
"""解析《国家医疗保障按病种分值（DIP）付费 3.0 版分组方案》PDF -> 结构化 JSON/CSV。

用法:
    python scripts/parse_dip30_group_plan.py [PDF路径] [输出目录]

输出:
    <输出目录>/dip30_plan_sections.json  按章节分组的原始行
    <输出目录>/dip30_plan_rows.csv       全量扁平化行
    <输出目录>/dip30_plan_stats.txt      各章节统计
"""
import sys
import json
import re
from collections import Counter, OrderedDict
from pathlib import Path

import pdfplumber

# 打印页码(目录页号) -> 章节映射（PDF 页码 = 打印页码 + 2）
SECTION_BY_PAGE = [
    # (起, 止, 章节 key, 章节名)
    (1, 1, "XQ", "一、先期分组下的核心病种"),
    (2, 64, "BX", "二、并项规则下的核心病种"),
    (65, 66, "FZ_BURN", "三(一)烧伤类病种"),
    (67, 68, "FZ_ONCO", "三(二)肿瘤类病种"),
    (69, 71, "FZ_TB", "三(三)结核类病种"),
    (72, 72, "TB_DR", "附表—结核耐药诊断列表"),
    (73, 169, "JC", "四、基础规则下的核心病种"),
    (170, 244, "EXCL_DIAG", "五(一)不纳入分组的主要诊断列表"),
    (245, 304, "EXCL_OPRN", "五(二)不纳入分组的主要手术操作列表"),
    (305, 309, "GRASSROOT", "六、基层病种"),
]


def section_of(pno: int) -> str:
    for lo, hi, key, _ in SECTION_BY_PAGE:
        if lo <= pno <= hi:
            return key
    return "UNKNOWN"


def clean(s):
    return (s or "").replace("\n", "").strip()


def main():
    pdf_path = sys.argv[1] if len(sys.argv) > 1 else "F:/DIP/dip3_group_plan_tmp.pdf"
    out_dir = Path(sys.argv[2] if len(sys.argv) > 2 else "F:/DIP/output/dip30_plan")
    out_dir.mkdir(parents=True, exist_ok=True)

    sections = OrderedDict((t[2], []) for t in SECTION_BY_PAGE)
    sections["UNKNOWN"] = []
    header_by_section = {}

    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        for pi in range(2, total):  # 跳过封面 + 目录
            pno = pi - 1  # 打印页码
            sec = section_of(pno)
            page = pdf.pages[pi]
            for t in page.extract_tables():
                if not t:
                    continue
                hdr = [clean(c) for c in t[0]]
                header_by_section.setdefault(sec, []).append(hdr)
                # 表头行本身若是数据行（分页无表头的情况）则保留
                is_header = hdr and hdr[0] in ("分类", "序号", "主要诊断编码", "主要手术操作编码")
                start = 1 if is_header else 0
                for r in t[start:]:
                    cells = [clean(c) for c in r]
                    if not any(cells):
                        continue
                    if is_header and cells == hdr:
                        continue
                    sections[sec].append({"page": pno, "cells": cells})

    stats = []
    stats.append(f"PDF 总页数: {total}（正文 {total-2} 页）")
    stats.append("")
    flat = []
    for lo, hi, key, name in SECTION_BY_PAGE:
        rows = sections[key]
        stats.append(f"[{key}] {name}  (打印页 {lo}-{hi})  条目数 = {len(rows)}")
        hdrs = header_by_section.get(key, [])
        uniq = []
        for h in hdrs:
            if h not in uniq:
                uniq.append(h)
        for h in uniq[:3]:
            stats.append(f"      表头: {h}")
        for r in rows:
            flat.append({"section": key, "section_name": name, "page": r["page"],
                         **{f"c{i}": v for i, v in enumerate(r["cells"])}})
    if sections["UNKNOWN"]:
        stats.append(f"[UNKNOWN] 未归类条目数 = {len(sections['UNKNOWN'])}")

    (out_dir / "dip30_plan_sections.json").write_text(
        json.dumps(sections, ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / "dip30_plan_stats.txt").write_text("\n".join(stats), encoding="utf-8")

    import pandas as pd
    pd.DataFrame(flat).to_csv(out_dir / "dip30_plan_rows.csv", index=False, encoding="utf-8-sig")

    print("\n".join(stats))


if __name__ == "__main__":
    main()
