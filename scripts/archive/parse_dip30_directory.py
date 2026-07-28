import pdfplumber
import pandas as pd
from pathlib import Path
import re

pdf_path = Path(r'F:\DIP\data\DIP 3.0版分组征求地方意见的函.pdf')
output_path = Path(r'F:\DIP\data\DIP3.0国家目录库.xlsx')

print(f'正在读取: {pdf_path}')

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

# 解析数据
# 格式: 主要诊断编码 | 主要诊断名称 | 主要手术编码 | 主要手术名称
# 有些行是分类标题（如"血栓栓塞性疾病"），需要跳过

dip_data = []
current_disease = None

for row in all_rows:
    # 跳过表头行
    if any('主要诊断' in str(cell) or '主要手术' in str(cell) for cell in row):
        continue
    
    # 跳过分类标题行（通常只有2-3个元素）
    if len(row) <= 3:
        continue
    
    # 尝试解析为DIP目录格式
    try:
        # 第一列应该是诊断编码
        diag_code = row[0].strip() if row[0] else ''
        
        # 检查是否是有效的ICD编码格式（字母+数字）
        if re.match(r'^[A-Z]\d{2}', diag_code):
            diag_name = row[1].strip() if len(row) > 1 else ''
            proc_code = row[2].strip() if len(row) > 2 else ''
            proc_name = row[3].strip() if len(row) > 3 else ''
            
            # 清理换行符
            diag_name = diag_name.replace('\n', ' ')
            proc_code = proc_code.replace('\n', ' ')
            proc_name = proc_name.replace('\n', ' ')
            
            if diag_code and diag_name:
                dip_data.append({
                    '主要诊断编码': diag_code,
                    '主要诊断名称': diag_name,
                    '主要手术编码': proc_code,
                    '主要手术名称': proc_name
                })
    except Exception as e:
        continue

print(f'解析出 {len(dip_data)} 条有效DIP记录')

# 创建DIP编码
# 规则: 主要诊断编码 + 手术编码序号（如I21.0-01, I21.0-02等）
final_data = []
diag_proc_count = {}

for item in dip_data:
    diag_code = item['主要诊断编码']
    proc_code = item['主要手术编码']
    
    # 统计每个诊断编码下的手术数量
    if diag_code not in diag_proc_count:
        diag_proc_count[diag_code] = 0
    diag_proc_count[diag_code] += 1
    
    # 生成DIP编码
    if proc_code:
        dip_code = f"{diag_code}-{diag_proc_count[diag_code]:02d}"
    else:
        dip_code = f"{diag_code}-00"
    
    # 确定分组类型
    if proc_code:
        group_type = '手术'
    else:
        group_type = '内科'
    
    final_data.append({
        'DIP编码': dip_code,
        '主要诊断编码': diag_code,
        '主要诊断名称': item['主要诊断名称'],
        '主要手术编码': proc_code,
        '主要手术名称': item['主要手术名称'],
        '分组类型': group_type
    })

# 创建DataFrame
df = pd.DataFrame(final_data)

# 保存为Excel
df.to_excel(output_path, index=False, engine='openpyxl')

print(f'\nDIP3.0国家目录库已保存: {output_path}')
print(f'包含 {len(df)} 条记录')
print(f'\n前10条记录:')
print(df.head(10).to_string())

# 统计信息
print(f'\n统计信息:')
print(f'不同诊断编码数: {df["主要诊断编码"].nunique()}')
print(f'内科病种数: {len(df[df["分组类型"] == "内科"])}')
print(f'手术病种数: {len(df[df["分组类型"] == "手术"])}')
