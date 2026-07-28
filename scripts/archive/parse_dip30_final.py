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

# 查找所有表头位置
header_positions = []
for i, row in enumerate(all_rows):
    row_str = ' '.join(row)
    if '序号' in row_str and '主要诊断' in row_str:
        header_positions.append(i)
        print(f'找到表头 at 行 {i}: {row}')

# 解析数据（从行12开始的完整目录库）
dip_data = []
in_main_section = False

for i, row in enumerate(all_rows):
    # 跳过表头行
    if i in header_positions:
        in_main_section = True
        continue
    
    # 跳过先期分组和并项规则部分（行0-11）
    if i < 12:
        continue
    
    # 跳过其他表头
    if any('序号' in str(cell) and '主要诊断' in str(cell) for cell in row):
        continue
    
    # 跳过综合病种表头
    if any('综合病种' in str(cell) for cell in row):
        continue
    
    # 跳过排除列表表头
    if any('排除' in str(cell) for cell in row):
        continue
    
    # 尝试解析数据行
    try:
        # 格式: 序号, 主要诊断编码, 主要诊断名称, 主要手术编码, 主要手术名称, 分组类型, 病种类型
        if len(row) >= 5:
            # 检查第一列是否是数字（序号）
            seq_num = row[0].strip()
            if seq_num.isdigit():
                diag_code = row[1].strip() if len(row) > 1 else ''
                diag_name = row[2].strip() if len(row) > 2 else ''
                proc_code = row[3].strip() if len(row) > 3 else ''
                proc_name = row[4].strip() if len(row) > 4 else ''
                group_type = row[5].strip() if len(row) > 5 else ''
                disease_type = row[6].strip() if len(row) > 6 else ''
                
                # 清理换行符
                diag_name = diag_name.replace('\n', ' ')
                proc_code = proc_code.replace('\n', ' ')
                proc_name = proc_name.replace('\n', ' ')
                
                # 验证诊断编码格式
                if re.match(r'^[A-Z]\d{2}', diag_code):
                    # 根据手术编码确定分组类型
                    if proc_code and proc_code != '':
                        actual_group_type = '手术'
                    else:
                        actual_group_type = '内科'
                    
                    dip_data.append({
                        '主要诊断编码': diag_code,
                        '主要诊断名称': diag_name,
                        '主要手术编码': proc_code,
                        '主要手术名称': proc_name,
                        '分组类型': actual_group_type,
                        '病种类型': disease_type if disease_type else '核心病种'
                    })
    except Exception as e:
        continue

print(f'解析出 {len(dip_data)} 条有效DIP记录')

# 生成DIP编码
# 规则: 主要诊断编码 + 手术序号
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
    
    final_data.append({
        'DIP编码': dip_code,
        '主要诊断编码': diag_code,
        '主要诊断名称': item['主要诊断名称'],
        '主要手术编码': proc_code,
        '主要手术名称': item['主要手术名称'],
        '分组类型': item['分组类型'],
        '病种类型': item['病种类型']
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
