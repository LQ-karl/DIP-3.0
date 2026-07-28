import pdfplumber
import pandas as pd
from pathlib import Path
import re

pdf_path = Path(r'F:\DIP\data\DIP 3.0版分组征求地方意见的函.pdf')

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

# 分析数据结构
print('\n数据结构分析:')
print('前20行:')
for i, row in enumerate(all_rows[:20]):
    print(f'{i}: len={len(row)} | {row}')

# 查找表头
print('\n查找表头...')
for i, row in enumerate(all_rows):
    row_str = ' '.join(row)
    if '主要诊断' in row_str or '主要手术' in row_str or 'DIP' in row_str:
        print(f'行 {i}: {row}')
