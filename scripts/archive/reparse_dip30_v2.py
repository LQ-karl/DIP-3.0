import pdfplumber
import pandas as pd
from pathlib import Path
import re

pdf_path = Path(r'F:\DIP\data\DIP 3.0版分组征求地方意见的函.pdf')
output_path = Path(r'F:\DIP\data\DIP3.0国家目录库.xlsx')

print(f'正在重新解析: {pdf_path}')

# 提取所有表格数据
all_rows = []

with pdfplumber.open(pdf_path) as pdf:
    print(f'PDF总页数: {len(pdf.pages)}')
    
    for i, page in enumerate(pdf.pages):
        tables = page.extract_tables()
        if tables:
            for table in tables:
                for row in table:
                    if row and any(row):
                        cleaned_row = [str(cell).strip() if cell else '' for cell in row]
                        all_rows.append(cleaned_row)
        
        if (i + 1) % 20 == 0:
            print(f'已处理 {i + 1}/{len(pdf.pages)} 页')

print(f'共提取 {len(all_rows)} 行数据')

# 查找表头位置
header_pos = None
for i, row in enumerate(all_rows):
    row_str = ' '.join(row)
    if '序号' in row_str and '主要诊断' in row_str:
        header_pos = i
        print(f'找到表头 at 行 {i}: {row}')
        break

# 解析数据
dip_data = []
diag_counter = {}  # 统计每个诊断编码下的序号

if header_pos is not None:
    for i, row in enumerate(all_rows[header_pos+1:], start=1):
        try:
            if len(row) >= 3:
                seq_num = row[0].strip()
                diag_code = row[1].strip() if len(row) > 1 else ''
                diag_name = row[2].strip() if len(row) > 2 else ''
                proc_code = row[3].strip() if len(row) > 3 else ''
                proc_name = row[4].strip() if len(row) > 4 else ''
                rel_proc_code = row[5].strip() if len(row) > 5 else ''
                rel_proc_name = row[6].strip() if len(row) > 6 else ''
                
                # 清理换行符
                diag_name = diag_name.replace('\n', ' ')
                proc_code = proc_code.replace('\n', ' ')
                proc_name = proc_name.replace('\n', ' ')
                rel_proc_code = rel_proc_code.replace('\n', ' ')
                rel_proc_name = rel_proc_name.replace('\n', ' ')
                
                # 验证诊断编码格式
                if re.match(r'^[A-Z]\d{2}', diag_code):
                    # 统计每个诊断编码下的序号
                    if diag_code not in diag_counter:
                        diag_counter[diag_code] = 0
                    diag_counter[diag_code] += 1
                    
                    # 生成DIP编码：主要诊断编码 + 序号（从00开始）
                    dip_code = f"{diag_code}-{diag_counter[diag_code]-1:02d}"
                    
                    dip_data.append({
                        'DIP编码': dip_code,
                        '主要诊断编码': diag_code,
                        '主要诊断名称': diag_name,
                        '主要手术操作编码': proc_code,
                        '主要手术操作名称': proc_name,
                        '相关手术操作编码': rel_proc_code,
                        '相关手术操作名称': rel_proc_name
                    })
        except Exception as e:
            continue

print(f'解析出 {len(dip_data)} 条有效DIP记录')

# 创建DataFrame
df = pd.DataFrame(dip_data)

# 保存为Excel
df.to_excel(output_path, index=False, engine='openpyxl')

print(f'\nDIP3.0国家目录库已保存: {output_path}')
print(f'包含 {len(df)} 条记录')

# 显示I21.0相关记录
print('\nI21.0相关记录:')
i21_records = df[df['DIP编码'].str.startswith('I21.0', na=False)]
print(i21_records[['DIP编码', '主要诊断编码', '主要诊断名称', '主要手术操作编码', '主要手术操作名称']].to_string())

# 显示K35.9相关记录
print('\nK35.9相关记录:')
k35_records = df[df['DIP编码'].str.startswith('K35.9', na=False)]
print(k35_records[['DIP编码', '主要诊断编码', '主要诊断名称', '主要手术操作编码', '主要手术操作名称']].to_string())
