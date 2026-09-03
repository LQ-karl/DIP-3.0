"""从《ICD-10医保2.0版.pdf》抽取 3 位类目码 -> 医保2.0 类目名称 映射。

PDF 为结构化表格，含列：章代码范围/章名称/节代码范围/节名称/类目代码/类目名称/
亚目代码/亚目名称/诊断代码/诊断名称。本脚本仅取 (类目代码, 类目名称) 唯一对，
输出为 data/icd10_category_map.json，供综合病种命名查询使用。
"""
import json
import os
import re
import sys

import pdfplumber

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF = os.path.join(ROOT, "data", "ICD-10医保2.0版.pdf")
OUT = os.path.join(ROOT, "data", "icd10_category_map.json")

CAT_RE = re.compile(r"^[A-Z]\d{2}$")  # 3 位类目码：字母+2数字


def main():
    cat_map = {}
    pages_total = 0
    pages_used = 0
    with pdfplumber.open(PDF) as pdf:
        pages_total = len(pdf.pages)
        for idx, page in enumerate(pdf.pages):
            try:
                tables = page.extract_tables()
            except Exception:
                tables = []
            for tbl in tables:
                # 找到 类目代码 / 类目名称 列的索引
                header = tbl[0] if tbl else []
                code_i = name_i = None
                for i, h in enumerate(header):
                    hs = str(h or "").replace("\n", "")
                    if hs == "类目代码":
                        code_i = i
                    elif hs == "类目名称":
                        name_i = i
                if code_i is None or name_i is None:
                    # 无表头则按位置猜（经验：第5、6列）
                    if len(header) >= 7:
                        code_i, name_i = 5, 6
                    else:
                        continue
                pages_used += 1
                for row in tbl[1:]:
                    if len(row) <= max(code_i, name_i):
                        continue
                    code = str(row[code_i] or "").strip().upper()
                    name = str(row[name_i] or "").replace("\n", "").replace("\r", "").strip()
                    if CAT_RE.match(code) and name:
                        cat_map.setdefault(code, name)
            if (idx + 1) % 200 == 0:
                print(f"进度 {idx+1}/{pages_total} 已收集 {len(cat_map)} 个类目", flush=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(cat_map, f, ensure_ascii=False, indent=2)
    print(f"完成: 共 {len(cat_map)} 个类目名称, 扫描 {pages_total} 页(含表格 {pages_used} 页)")
    print(f"输出: {OUT}")


if __name__ == "__main__":
    main()
