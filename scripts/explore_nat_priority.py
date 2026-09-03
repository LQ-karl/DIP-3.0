import pandas as pd

path = r'F:/DIP/data/DIP3.0国家目录库.xlsx'
df = pd.read_excel(path, dtype=str)
for col in ['主要诊断编码', '主要手术操作编码', '相关手术操作编码']:
    df[col] = df[col].fillna('').astype(str).str.upper().str.strip()

print("ROWS:", len(df))

# A) 所有 39.95 开头的手术编码（区分 血液透析 39.9500 vs CRRT 39.9500x007）
print("\n=== 手术编码以 39.95 开头 的全部行（主要+相关）===")
for col in ['主要手术操作编码', '相关手术操作编码']:
    mask = df[col].str.startswith('39.95', na=False)
    sub = df[mask]
    print(f"\n-- 列 {col} --")
    print(sub[['DIP编码', '主要诊断编码', col]].to_string())

# B) 呼吸循环支持其余手术族（ECMO/呼吸机/无创通气/IABP）
for p in ['39.6', '96.7', '93.9', '37.6']:
    print(f"\n=== 手术编码以 {p} 开头 的行 ===")
    mask = df['主要手术操作编码'].str.startswith(p, na=False) | df['相关手术操作编码'].str.startswith(p, na=False)
    print(df[mask][['DIP编码', '主要诊断编码', '主要手术操作编码', '相关手术操作编码']].to_string())

# C) 器官移植手术族
for p in ['55.6', '50.51', '50.5', '41.0', '33.5', '52.8', '46.97', '37.51']:
    mask = df['主要手术操作编码'].str.startswith(p, na=False) | df['相关手术操作编码'].str.startswith(p, na=False)
    if mask.any():
        print(f"\n=== 移植手术 {p} 开头的行 ===")
        print(df[mask][['DIP编码', '主要诊断编码', '主要手术操作编码', '相关手术操作编码']].to_string())
