import pdfplumber
import pandas as pd
from pathlib import Path
import re

pdf_path = Path(r'F:\DIP\data\DIP 3.0版分组征求地方意见的函.pdf')
output_path = Path(r'F:\DIP\data\DIP3.0国家目录库.xlsx')

print(f'正在读取: {pdf_path}')

# 尝试提取表格数据
all_data = []

with pdfplumber.open(pdf_path) as pdf:
    print(f'PDF总页数: {len(pdf.pages)}')
    
    for i, page in enumerate(pdf.pages):
        # 尝试提取表格
        tables = page.extract_tables()
        if tables:
            for table in tables:
                for row in table:
                    if row and any(row):
                        # 清理数据
                        cleaned_row = [str(cell).strip() if cell else '' for cell in row]
                        if any(cleaned_row):
                            all_data.append(cleaned_row)
        
        # 每10页输出一次进度
        if (i + 1) % 10 == 0:
            print(f'已处理 {i + 1}/{len(pdf.pages)} 页，提取 {len(all_data)} 条记录')

print(f'\n共提取 {len(all_data)} 条记录')

# 查看前几条数据
if all_data:
    print('\n前5条数据:')
    for i, row in enumerate(all_data[:5]):
        print(f'{i}: {row}')

# 尝试解析为结构化数据
# DIP3.0目录库格式: 序号, DIP编码, 主要诊断编码, 主要诊断名称, 主要手术编码, 主要手术名称, ...
