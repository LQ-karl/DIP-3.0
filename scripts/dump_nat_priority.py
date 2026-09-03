import sys, json
sys.path.insert(0, "F:/DIP/src")
import pandas as pd

PATH = "F:/DIP/data/DIP3.0国家目录库.xlsx"
xl = pd.ExcelFile(PATH)
print("SHEETS:", xl.sheet_names)
for sh in xl.sheet_names:
    df = xl.parse(sh)
    print(f"\n=== SHEET {sh!r} shape={df.shape} ===")
    print("COLS:", list(df.columns))
    # dump rows where main diagnosis is A41.9 or P07
    cols = list(df.columns)
    md_col = next((c for c in cols if "主要诊断编码" in c), None)
    dip_col = next((c for c in cols if "DIP" in c or "编码" in c and "DIP" in c), None)
    op_col = next((c for c in cols if "主要手术操作编码" in c), None)
    if md_col is None:
        continue
    sub = df[df[md_col].astype(str).str.contains(r'^(A41\.9|P07)', regex=True, na=False)]
    print(f"-- rows with main diag A41.9/P07: {len(sub)}")
    keep_cols = [c for c in cols if any(k in c for k in ["DIP","主要诊断","主要手术","相关手术","相关诊断","条目","序号","行"])]
    with pd.option_context('display.max_columns', None, 'display.width', 240):
        print(sub[keep_cols].head(80).to_string(index=False))
