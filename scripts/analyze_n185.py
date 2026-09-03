import sys, os
sys.path.insert(0, r'F:/DIP')
os.chdir(r'F:/DIP')
import pandas as pd
from src.core.local_directory_generator import LocalDirectoryGenerator

path = r'F:/DIP/data/DIP3.0国家目录库.xlsx'
xl = pd.ExcelFile(path)
print("SHEETS:", xl.sheet_names)

# 1) 在国家目录库中搜索 N18.5 相关行
for sh in xl.sheet_names:
    df = xl.parse(sh)
    s = df.astype(str)
    mask = s.apply(lambda c: c.str.contains('N18.5', case=False, na=False)).any(axis=1)
    if mask.any():
        print(f"\n=== SHEET: {sh} | N18.5 rows: {int(mask.sum())} ===")
        print("COLUMNS:", list(df.columns))
        for _, row in df[mask].iterrows():
            print("--- ROW ---")
            for col in df.columns:
                print(f"  {col}: {row[col]}")

# 2) 直接验证查表函数：先期分组器官移植(肾移植55.6) + 主诊断 N18.5
gen = LocalDirectoryGenerator(threshold=15)
gen.load_national_directory(path)
print("\n[nat_dip_for_diag_oprn] N18.5 + 55.6 ->", gen._nat_dip_for_diag_oprn("N18.5", "55.6"))
print("[nat_dip_for_diag_oprn] N18.5 + 55.69 ->", gen._nat_dip_for_diag_oprn("N18.5", "55.69"))
# 旧先期分组反查 _nat_dip_for_op 已随种子回落移除
