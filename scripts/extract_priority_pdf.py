import pdfplumber, re

pdf_path = r'F:/DIP/data/DIP 3.0版分组征求地方意见的函.pdf'
hits = []
with pdfplumber.open(pdf_path) as pdf:
    for i, page in enumerate(pdf.pages):
        txt = page.extract_text() or ''
        # 命中 4956~4968 任一条目号
        if re.search(r'49(5[6-9]|6[0-8])\b', txt):
            hits.append((i + 1, txt))

print(f"命中页: {[h[0] for h in hits]}")
for pno, txt in hits:
    print(f"\n========== 第 {pno} 页 ==========")
    # 只打印含条目号 4956-4968 的上下文行
    for line in txt.splitlines():
        if re.search(r'49(5[6-9]|6[0-8])\b', line):
            print(line)
