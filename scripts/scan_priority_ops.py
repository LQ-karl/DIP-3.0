import sys, re
sys.path.insert(0, "F:/DIP/src")
import pandas as pd

PATH = "F:/DIP/data/DIP3.0国家目录库.xlsx"
df = pd.read_excel(PATH, dtype=str)

# 扫描《函》4956-4968 白名单手术码在目录中的出现与对应 DIP 码
ops = ["39.6500", "96.7101", "39.9500x007", "96.7201", "50.9200x001", "37.5200x001",
       "55.6100", "55.6901", "37.5100", "33.5000", "33.6", "41.0200", "41.0300",
       "41.0000", "93.9000", "37.6101"]
print("=== 白名单手术码在目录中的命中 ===")
for op in ops:
    hits = df[df['主要手术操作编码'].astype(str).str.contains(re.escape(op), regex=True, na=False)]
    if len(hits):
        for _, r in hits.iterrows():
            print(f"  {op:14s} -> DIP={r['DIP编码']:10s} 主诊={r['主要诊断编码']:8s} 主诊名={str(r['主要诊断名称'])[:18]:18s} op名={r['主要手术操作名称']}")
    else:
        print(f"  {op:14s} -> (目录中无命中)")

# 看 96.7201 / 96.7101 是否共线
print("\n=== 含 96.7 的行 ===")
for _, r in df[df['主要手术操作编码'].astype(str).str.startswith('96.7', na=False)].iterrows():
    print(f"  DIP={r['DIP编码']:10s} 主诊={r['主要诊断编码']:8s} op={r['主要手术操作编码']:14s} {r['主要手术操作名称']}")

# 看目录里 P07 全部行 + 是否还有其它主诊断占位
print("\n=== 主诊断 A41.9 / P07 各出现几次，主诊断唯一值 top ===")
print("A41.9 count:", (df['主要诊断编码']=='A41.9').sum())
print("P07 count:", df['主要诊断编码'].astype(str).str.startswith('P07').sum())
