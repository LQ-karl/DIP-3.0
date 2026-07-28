import pdfplumber
import re
from pathlib import Path

pdf_path = Path(r'F:\DIP\data\DIP 3.0版分组征求地方意见的函.pdf')

print(f'正在读取: {pdf_path}')
print('='*60)

with pdfplumber.open(pdf_path) as pdf:
    print(f'PDF总页数: {len(pdf.pages)}')
    
    # 读取前10页内容
    for i in range(min(10, len(pdf.pages))):
        page = pdf.pages[i]
        text = page.extract_text()
        if text:
            print(f'\n--- 第{i+1}页 ---')
            print(text[:2000] if len(text) > 2000 else text)
