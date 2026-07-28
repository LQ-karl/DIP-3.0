import pandas as pd
from pathlib import Path

# 创建空模板（只有表头）
columns = [
    '住院号', '结算ID', '人员编号', '就诊ID',
    '医院代码', '医院名称', '医院等级',
    '入院日期', '出院日期',
    '主诊断', '主诊断名称',
    '其他诊断1', '其他诊断1名称',
    '其他诊断2', '其他诊断2名称',
    '其他诊断3', '其他诊断3名称',
    '其他诊断4', '其他诊断4名称',
    '其他诊断5', '其他诊断5名称',
    '主手术', '主手术名称',
    '其他手术1', '其他手术1名称',
    '其他手术2', '其他手术2名称',
    '其他手术3', '其他手术3名称',
    '其他手术4', '其他手术4名称',
    '其他手术5', '其他手术5名称',
    '总费用', '药品费用', '材料费用', '耗材费用',
    '检查费用', '治疗费用', '护理费用',
    '住院天数', '出院方式'
]

df = pd.DataFrame(columns=columns)

# 创建目录
output_dir = Path('F:/DIP/templates')
output_dir.mkdir(exist_ok=True)

# 保存空模板
output_path = output_dir / '医保结算清单导入模板_空白.xlsx'
df.to_excel(output_path, index=False, engine='openpyxl')

print(f'空白模板已创建: {output_path}')
print(f'共 {len(columns)} 个字段')
print(f'其他诊断: 5列 (其他诊断1-5)')
print(f'其他手术: 5列 (其他手术1-5)')
