#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
根据 ICD 对照表为测试数据补全「名称」列。

- 诊断编码(ICD-10)  -> 《ICD10国临版2.0对照医保版2.0_0125.xlsx》
      同时收纳「国临版编码/名称」「医保版2.0编码/名称」两列，兼容清单用国临版或医保版码。
- 手术操作编码(ICD-9) -> 《ICD9国临版3.0对照医保版2.0_0125.xlsx》
      同时收纳「国临3.0手术代码/名称」「医保2.0手术代码/名称」两列。

规则：
- 输入文件可为 .xlsx / .csv（csv 自动尝试 utf-8 / gbk）。
- 对每一对 (编码列, 名称列) 自动补全：若名称列缺失则新建；若名称列为空则填充；
  若已有值则保留原值（不覆盖）。
- 多值编码用 '|' 分隔时，名称按相同顺序用 '|' 拼接。
- 匹配优先级：精确 -> 去掉 x 扩展码 -> 前缀匹配。

用法：
  python scripts/fill_icd_names.py <输入文件> [--out <输出文件>] [--data-dir <data目录>]
"""
from __future__ import annotations

import argparse
import os
import re
import sys

import pandas as pd
from openpyxl import load_workbook

# 诊断 / 手术 编码列 -> 名称列 的配对
DIAG_PAIRS = [
    ("主要诊断编码", "主要诊断名称"),
    ("相关诊断编码", "相关诊断名称"),
]
OPRN_PAIRS = [
    ("主要手术操作编码", "主要手术操作名称"),
    ("相关手术操作编码", "相关手术操作名称"),
]


def _norm_code(code: str) -> str:
    return str(code).strip().upper()


def _strip_x_ext(code: str) -> str:
    """去掉 x 扩展码（如 T25.300x003 -> T25.300；54.5100x005 -> 54.5100）。"""
    return re.sub(r"X\d*$", "", code, flags=re.IGNORECASE)


def build_maps(data_dir: str):
    """返回 (diag_map, oprn_map)，均为 编码(大写) -> 名称。"""
    diag_map: dict[str, str] = {}
    oprn_map: dict[str, str] = {}

    # ---- ICD10 诊断 ----
    f10 = os.path.join(data_dir, "ICD10国临版2.0对照医保版2.0_0125.xlsx")
    if os.path.exists(f10):
        d10 = pd.read_excel(f10, dtype=str)
        cols = {str(c).strip(): c for c in d10.columns}
        for cc, nn in (("国临版编码", "国临版名称"), ("医保版2.0编码", "医保版2.0名称")):
            if cc in cols and nn in cols:
                for _, r in d10.iterrows():
                    c = _norm_code(r[cols[cc]])
                    n = str(r[cols[nn]]).strip()
                    if c and n and c not in diag_map:
                        diag_map[c] = n
    else:
        print(f"警告: 未找到 {f10}")

    # ---- ICD9 手术 ----
    f9 = os.path.join(data_dir, "ICD9国临版3.0对照医保版2.0_0125.xlsx")
    if os.path.exists(f9):
        d9 = pd.read_excel(f9, dtype=str)
        cols = {str(c).strip(): c for c in d9.columns}
        for cc, nn in (("国临3.0手术代码", "国临3.0手术名称"), ("医保2.0手术代码", "医保2.0手术名称")):
            if cc in cols and nn in cols:
                for _, r in d9.iterrows():
                    c = _norm_code(r[cols[cc]])
                    n = str(r[cols[nn]]).strip()
                    if c and n and c not in oprn_map:
                        oprn_map[c] = n
    else:
        print(f"警告: 未找到 {f9}")

    return diag_map, oprn_map


def lookup(code: str, mp: dict[str, str]) -> str:
    code = _norm_code(code)
    if not code:
        return ""
    if code in mp:
        return mp[code]
    s = _strip_x_ext(code)
    if s and s in mp:
        return mp[s]
    # 前缀匹配（取最短命中，避免过度泛化）
    hits = [k for k in mp if k.startswith(code)]
    if hits:
        return mp[min(hits, key=len)]
    return ""


def fill_column(series_codes, series_names, mp: dict[str, str]):
    """返回补全后的名称 Series（不覆盖已有非空值）。"""
    out = series_names.copy() if series_names is not None else pd.Series([""] * len(series_codes))
    filled = 0
    for i, raw in series_codes.items():
        if pd.isna(raw):
            continue
        existing = out.at[i] if i in out.index and not pd.isna(out.at[i]) else ""
        if str(existing).strip():
            continue  # 已有名称，保留
        codes = [c for c in str(raw).split("|") if c.strip()]
        names = [lookup(c, mp) for c in codes]
        if any(names):
            out.at[i] = "|".join(names)
            filled += 1
    return out, filled


def read_input(path: str) -> pd.DataFrame:
    # 按魔术字节嗅探真实格式（有些 .csv 实为 xlsx，避免扩展名误标）
    with open(path, "rb") as fh:
        magic = fh.read(4)
    if magic[:2] == b"PK":  # ZIP/OOXML -> xlsx
        return pd.read_excel(path)
    ext = os.path.splitext(path)[1].lower()
    if ext in (".csv", ".txt"):
        for enc in ("utf-8", "gbk"):
            try:
                return pd.read_csv(path, encoding=enc)
            except Exception:
                continue
        raise ValueError("CSV 编码无法识别(utf-8/gbk 均失败)")
    return pd.read_excel(path)


def _detect_text_id_columns(df: pd.DataFrame) -> list[str]:
    """识别应以文本写入的 ID 类列，避免超长数字被 Excel 存成科学计数法/丢精度。

    命中规则（任一）：
      - 列名含 id / record / setl / 结算（不区分大小写）；
      - 列为 object 且所有非空值均为「纯数字且长度≥15」的字符串/整数（如 24 位结算ID）。
    诊断/手术编码含字母、金额/年龄为数值，均不会被误判。
    """
    text_cols = []
    for col in df.columns:
        name = str(col).lower()
        if any(k in name for k in ("id", "record", "setl", "结算")):
            text_cols.append(col)
            continue
        if df[col].dtype == object:
            vals = df[col].dropna()
            if len(vals) and all(
                str(v).strip().isdigit() and len(str(v).strip()) >= 15 for v in vals
            ):
                text_cols.append(col)
    return text_cols


def write_excel_textsafe(df: pd.DataFrame, path: str) -> list[str]:
    """写出 xlsx，并把 ID 类列以『文本』写入，杜绝超长数字被 Excel 存成科学计数法/丢精度。

    关键点：必须在 to_excel 之前就把值转成 Python str。若先写成数字再回填，
    openpyxl 重读超大数字时会先转 float 四舍五入，str(float) 已经是损坏的科学计数法值。

    实现：先写到真正的 .xlsx 临时文件（规避历史文件扩展名误标为 .csv 导致的引擎校验失败），
    设好文本格式后再移动到目标路径。
    """
    import shutil
    import tempfile

    text_cols = _detect_text_id_columns(df)
    df = df.copy()
    for col in text_cols:
        df[col] = [str(v) if pd.notna(v) else v for v in df[col]]  # 转字符串（保留 NaN 不变）

    fd, tmp = tempfile.mkstemp(suffix=".xlsx")
    os.close(fd)
    try:
        df.to_excel(tmp, index=False, engine="openpyxl")
        if text_cols:
            # 兜底：再把对应单元格显式设为文本格式(@)，确保 Excel 不自动转数值
            wb = load_workbook(tmp)
            ws = wb.active
            header = [c.value for c in ws[1]]
            for col in text_cols:
                if col not in header:
                    continue
                ci = header.index(col) + 1
                for r in range(2, ws.max_row + 1):
                    ws.cell(row=r, column=ci).number_format = "@"
            wb.save(tmp)
        shutil.move(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    return text_cols


def main():
    ap = argparse.ArgumentParser(description="ICD 名称补全")
    ap.add_argument("input", help="输入 xlsx/csv")
    ap.add_argument("--out", help="输出文件(默认在输入名后加 _补全名称)")
    ap.add_argument("--data-dir", default=None, help="data 目录(默认项目 data/)")
    args = ap.parse_args()

    data_dir = args.data_dir or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    df = read_input(args.input)

    diag_map, oprn_map = build_maps(data_dir)
    print(f"诊断映射 {len(diag_map)} 条，手术映射 {len(oprn_map)} 条")

    total_filled = 0
    for code_col, name_col in DIAG_PAIRS + OPRN_PAIRS:
        if code_col not in df.columns:
            continue
        existing = df[name_col] if name_col in df.columns else None
        new_names, filled = fill_column(df[code_col], existing,
                                        diag_map if (code_col, name_col) in DIAG_PAIRS else oprn_map)
        df[name_col] = new_names
        if filled:
            print(f"  补全 [{name_col}] 来自 [{code_col}]: {filled} 行")
            total_filled += filled

    out = args.out
    if not out:
        base, ext = os.path.splitext(args.input)
        ext = ".xlsx"  # 输出统一为 xlsx，避免原文件扩展名误标问题
        out = f"{base}_补全名称{ext}"

    # 保证表头顺序：名称列紧跟其编码列之后；ID 类列强制文本格式避免科学计数法
    text_cols = write_excel_textsafe(df, out)
    print(f"已写出: {out} (共补全 {total_filled} 个名称列；文本ID列: {text_cols})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
