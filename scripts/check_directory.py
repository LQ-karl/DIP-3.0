import pandas as pd

# 读取DIP3.0国家目录库
df = pd.read_excel('F:/DIP/data/DIP3.0国家目录库.xlsx')

print("=" * 60)
print(f"当前DIP3.0国家目录库记录数: {len(df)}")
print("=" * 60)
print()
print("列名:")
for c in df.columns:
    print(f"  [{c}]")

print()
print("各列非空记录数:")
for c in df.columns:
    non_null = df[c].notna().sum()
    print(f"  {c}: {non_null}")

print()
print("分组类型统计:")
col5 = df.columns[5]
print(df[col5].value_counts())

print()
print("病种类型统计:")
col6 = df.columns[6]
print(df[col6].value_counts())
