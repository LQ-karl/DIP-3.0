import pandas as pd
from pathlib import Path

# 4101A接口字段与中文名称对应关系
field_mapping = {
    # 基本信息
    'medcasno': '病案号',
    'setl_id': '结算ID',
    'psn_no': '人员编号',
    'mdtrt_id': '就诊ID',
    'hi_no': '医保编号',
    
    # 医院信息
    'fixmedins_code': '定点医药机构编号',
    'fixmedins_name': '定点医药机构名称',
    'fixmedins_lv': '医疗机构等级',
    
    # 入院信息
    'adm_time': '入院时间',
    'adm_dept_codg': '入院科室编码',
    'adm_dept_name': '入院科室名称',
    'adm_way': '入院途径',
    
    # 出院信息
    'dscg_time': '出院时间',
    'dscg_dept_codg': '出院科室编码',
    'dscg_dept_name': '出院科室名称',
    'dscg_way': '出院方式',
    
    # 诊断信息
    'wm_dise_code': '西医疾病代码(主诊断)',
    'otp_wm_dise': '诊断名称',
    'dise_type_1': '其他诊断1类型',
    'wm_dise_code_1': '其他诊断1代码',
    'otp_wm_dise_1': '其他诊断1名称',
    'dise_type_2': '其他诊断2类型',
    'wm_dise_code_2': '其他诊断2代码',
    'otp_wm_dise_2': '其他诊断2名称',
    'dise_type_3': '其他诊断3类型',
    'wm_dise_code_3': '其他诊断3代码',
    'otp_wm_dise_3': '其他诊断3名称',
    'dise_type_4': '其他诊断4类型',
    'wm_dise_code_4': '其他诊断4代码',
    'otp_wm_dise_4': '其他诊断4名称',
    'dise_type_5': '其他诊断5类型',
    'wm_dise_code_5': '其他诊断5代码',
    'otp_wm_dise_5': '其他诊断5名称',
    
    # 手术操作信息
    'oprn_oprt_code': '手术操作代码(主手术)',
    'oprn_oprt_name': '手术操作名称',
    'oprn_type_1': '其他手术1类型',
    'oprn_oprt_code_1': '其他手术1代码',
    'oprn_oprt_name_1': '其他手术1名称',
    'oprn_type_2': '其他手术2类型',
    'oprn_oprt_code_2': '其他手术2代码',
    'oprn_oprt_name_2': '其他手术2名称',
    'oprn_type_3': '其他手术3类型',
    'oprn_oprt_code_3': '其他手术3代码',
    'oprn_oprt_name_3': '其他手术3名称',
    'oprn_type_4': '其他手术4类型',
    'oprn_oprt_code_4': '其他手术4代码',
    'oprn_oprt_name_4': '其他手术4名称',
    'oprn_type_5': '其他手术5类型',
    'oprn_oprt_code_5': '其他手术5代码',
    'oprn_oprt_name_5': '其他手术5名称',
    
    # 费用信息
    'medfee_sumamt': '医疗总费用',
    'fund_pay_sumamt': '基金支付总额',
    'psn_pay_sumamt': '个人支付总额',
    'drug_fee': '药品费用',
    'west_med_fee': '西药费',
    'chinese_med_fee': '中成药费',
    'chinese_herb_med_fee': '中草药费',
    'matl_fee': '材料费',
    'consumable_fee': '耗材费用',
    'exam_fee': '检查费',
    'test_fee': '检验费',
    'treat_fee': '治疗费',
    'operation_fee': '手术费',
    'nurs_fee': '护理费',
    'bed_fee': '床位费',
    'other_fee': '其他费用',
    
    # 住院天数
    'los': '实际住院天数',
    
    # 重症监护
    'icu_dura': '重症监护时长',
    
    # DIP分组信息
    'dip_code': 'DIP编码',
    'dip_name': 'DIP名称',
}

# 创建示例数据
template_data = {
    'medcasno': ['R0001', 'R0002', 'R0003', 'R0004', 'R0005'],
    'setl_id': ['S0001', 'S0002', 'S0003', 'S0004', 'S0005'],
    'psn_no': ['P0001', 'P0002', 'P0003', 'P0004', 'P0005'],
    'mdtrt_id': ['V0001', 'V0002', 'V0003', 'V0004', 'V0005'],
    'hi_no': ['', '', '', '', ''],
    'fixmedins_code': ['H001', 'H001', 'H002', 'H002', 'H001'],
    'fixmedins_name': ['市人民医院', '市人民医院', '区中心医院', '区中心医院', '市人民医院'],
    'fixmedins_lv': ['三级甲等', '三级甲等', '二级甲等', '二级甲等', '三级甲等'],
    'adm_time': ['2024-01-15', '2024-01-16', '2024-02-10', '2024-02-11', '2024-01-20'],
    'adm_dept_codg': ['', '', '', '', ''],
    'adm_dept_name': ['心内科', '心内科', '普外科', '普外科', '心内科'],
    'adm_way': ['急诊', '急诊', '门诊', '门诊', '急诊'],
    'dscg_time': ['2024-01-27', '2024-01-28', '2024-02-18', '2024-02-19', '2024-02-05'],
    'dscg_dept_codg': ['', '', '', '', ''],
    'dscg_dept_name': ['心内科', '心内科', '普外科', '普外科', '心内科'],
    'dscg_way': ['医嘱离院', '医嘱离院', '医嘱离院', '医嘱离院', '医嘱离院'],
    'wm_dise_code': ['I21.0', 'I21.0', 'K35.9', 'K35.9', 'I50.9'],
    'otp_wm_dise': ['急性心肌梗死', '急性心肌梗死', '急性阑尾炎', '急性阑尾炎', '心力衰竭'],
    'dise_type_1': ['主诊断', '主诊断', '主诊断', '主诊断', '主诊断'],
    'wm_dise_code_1': ['I21.0', 'I21.0', 'K35.9', 'K35.9', 'I50.9'],
    'otp_wm_dise_1': ['急性心肌梗死', '急性心肌梗死', '急性阑尾炎', '急性阑尾炎', '心力衰竭'],
    'dise_type_2': ['其他诊断', '其他诊断', '其他诊断', '其他诊断', '其他诊断'],
    'wm_dise_code_2': ['E11.9', 'I10', 'E11.9', 'I10', 'E11.9'],
    'otp_wm_dise_2': ['2型糖尿病', '高血压', '2型糖尿病', '高血压', '2型糖尿病'],
    'dise_type_3': ['其他诊断', '', '其他诊断', '', '其他诊断'],
    'wm_dise_code_3': ['I10', '', 'I10', '', 'J18.9'],
    'otp_wm_dise_3': ['高血压', '', '高血压', '', '肺炎'],
    'dise_type_4': ['其他诊断', '', '', '', '其他诊断'],
    'wm_dise_code_4': ['J18.9', '', '', '', 'N18.9'],
    'otp_wm_dise_4': ['肺炎', '', '', '', '慢性肾脏病'],
    'dise_type_5': ['', '', '', '', ''],
    'wm_dise_code_5': ['', '', '', '', ''],
    'otp_wm_dise_5': ['', '', '', '', ''],
    'oprn_oprt_code': ['36.1500', '36.1500', '', '', ''],
    'oprn_oprt_name': ['冠状动脉支架植入术', '冠状动脉支架植入术', '', '', ''],
    'oprn_type_1': ['其他手术', '其他手术', '', '', ''],
    'oprn_oprt_code_1': ['00.6600', '00.6600', '', '', ''],
    'oprn_oprt_name_1': ['冠状动脉球囊扩张术', '冠状动脉球囊扩张术', '', '', ''],
    'oprn_type_2': ['', '', '', '', ''],
    'oprn_oprt_code_2': ['', '', '', '', ''],
    'oprn_oprt_name_2': ['', '', '', '', ''],
    'oprn_type_3': ['', '', '', '', ''],
    'oprn_oprt_code_3': ['', '', '', '', ''],
    'oprn_oprt_name_3': ['', '', '', '', ''],
    'oprn_type_4': ['', '', '', '', ''],
    'oprn_oprt_code_4': ['', '', '', '', ''],
    'oprn_oprt_name_4': ['', '', '', '', ''],
    'oprn_type_5': ['', '', '', '', ''],
    'oprn_oprt_code_5': ['', '', '', '', ''],
    'oprn_oprt_name_5': ['', '', '', '', ''],
    'medfee_sumamt': [15000, 15500, 10000, 10400, 25000],
    'fund_pay_sumamt': [12000, 12400, 8000, 8320, 20000],
    'psn_pay_sumamt': [3000, 3100, 2000, 2080, 5000],
    'drug_fee': [6000, 6200, 3000, 3150, 10000],
    'west_med_fee': [4000, 4100, 2000, 2100, 7000],
    'chinese_med_fee': [1000, 1050, 500, 525, 1500],
    'chinese_herb_med_fee': [1000, 1050, 500, 525, 1500],
    'matl_fee': [4000, 4150, 2500, 2600, 6000],
    'consumable_fee': [2500, 2600, 1800, 1900, 4000],
    'exam_fee': [1200, 1250, 1500, 1550, 2500],
    'test_fee': [800, 850, 1000, 1050, 1500],
    'treat_fee': [800, 850, 700, 750, 1500],
    'operation_fee': [1500, 1550, 0, 0, 0],
    'nurs_fee': [500, 550, 500, 550, 1000],
    'bed_fee': [200, 210, 150, 155, 300],
    'other_fee': [0, 0, 0, 0, 0],
    'los': [12, 12, 8, 8, 16],
    'icu_dura': [0, 0, 0, 0, 2],
    'dip_code': ['MI21.0', 'MI21.0', 'MK35.9', 'MK35.9', 'MI50.9'],
    'dip_name': ['急性心肌梗死-内科', '急性心肌梗死-内科', '急性阑尾炎-内科', '急性阑尾炎-内科', '心力衰竭-内科'],
}

# 创建DataFrame
df = pd.DataFrame(template_data)

# 创建中文字段名行
chinese_row = {col: field_mapping.get(col, '') for col in df.columns}

# 插入中文字段名行到第一行
chinese_df = pd.DataFrame([chinese_row])
final_df = pd.concat([chinese_df, df], ignore_index=True)

# 创建目录
output_dir = Path('F:/DIP/templates')
output_dir.mkdir(exist_ok=True)

# 保存为Excel
output_path = output_dir / '4101A医保结算清单模板.xlsx'
with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
    final_df.to_excel(writer, index=False, sheet_name='模板')
    
    # 设置第一行（中文字段名）为粗体
    worksheet = writer.sheets['模板']
    from openpyxl.styles import Font
    bold_font = Font(bold=True)
    for cell in worksheet[1]:
        cell.font = bold_font

print(f'4101A标准模板已创建: {output_path}')
print(f'第一行为中文字段名，第二行为示例数据')
print(f'共 {len(df.columns)} 个字段')
