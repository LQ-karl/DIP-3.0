# DIP3.0技术规范字段整理

## 一、成组的基础信息（表2-1 DIP聚类成组相关基础信息）

| 组合轴心 | 信息/数据 | 信息业务编码类别 | 规范字段 |
|----------|-----------|------------------|----------|
| 疾病严重程度及特异性特征 | 主要诊断、相关诊断、并发症/合并症、个体因素（如年龄、性别等） | 《医疗保障疾病诊断分类与代码（ICD-10）》（2.0版）<br>《医疗保障手术操作分类与代码（ICD-9-CM-3）》<br>《中医疾病分类与代码》<br>《中医症候分类与代码》<br>《医保结算清单》填报口径 | main_diag_code<br>related_diag_code<br>complication_code<br>age<br>gender |
| 治疗方式的属性 | 保守治疗、诊断性操作、治疗性操作、相关手术 | 《医疗保障疾病诊断分类与代码（ICD-10）》（2.0版）<br>《医疗保障手术操作分类与代码（ICD-9-CM-3）》<br>《医保结算清单》填报口径 | main_oprn_code<br>related_oprn_code<br>treatment_type |
| 肿瘤严重程度 | 肿瘤转移、放化疗等，疾病发展阶段 | 《医疗保障疾病诊断分类与代码（ICD-10）》（2.0版）<br>《医保结算清单》填报口径 | tumor_metastasis<br>chemo_status |
| 资源消耗 | 医疗费用（医保药品、耗材、医疗服务项目分类与代码）、住院天数 | 《医疗服务项目分类与代码》<br>《医保药品分类与代码》<br>《医保医用耗材分类与代码》<br>《医保结算清单》填报口径 | total_cost<br>drug_cost<br>material_cost<br>los |
| 医疗结果 | 出院状态（死亡、医嘱出院、非医嘱出院、转院） | 《医保结算清单》填报口径 | discharge_status |
| 医疗付费 | 医保支付、个人支付、支付方式 | 《医保结算清单》填报口径 | insurance_pay<br>self_pay<br>payment_method |

---

## 二、病人诊疗数据变量

### 2.1 基本信息
| 字段名称 | 说明 | 规范字段 |
|----------|------|----------|
| 定点医药机构名称 | 医院名称 | hospital_name |
| 定点医药机构代码 | 医院代码 | hospital_code |
| 医保结算等级 | 医院等级 | hospital_level |
| 医保编号 | 医保卡号 | insurance_id |
| 病案号 | 病案号 | case_number |
| 性别 | 患者性别 | gender |
| 出生日期 | 出生日期 | birth_date |
| 年龄 | 年龄 | age |
| 天龄 | 年龄不足1周岁 | day_age |
| 患者证件类别 | 证件类型 | id_type |
| 患者证件号码 | 证件号码 | id_number |
| 职业 | 职业 | occupation |
| 医保类型 | 医保类型 | insurance_type |
| 特殊人员类型 | 特殊人员 | special_person_type |
| 参保地 | 参保地区 | insurance_region |
| 新生儿出生体重 | 新生儿体重 | birth_weight |
| 新生儿入院体重 | 入院体重 | admission_weight |

### 2.2 住院诊疗信息
| 字段名称 | 说明 | 规范字段 |
|----------|------|----------|
| 住院医疗类型 | 住院类型 | visit_type |
| 入院途径 | 入院途径 | admission_route |
| 治疗类别 | 治疗类别 | treatment_category |
| 入院时间 | 入院日期 | admission_date |
| 入院科别 | 入院科室 | admission_dept |
| 转科科别 | 转科科室 | transfer_dept |
| 出院时间 | 出院日期 | discharge_date |
| 出院科别 | 出院科室 | discharge_dept |
| 实际住院天数 | 住院天数 | los |
| 门（急）诊诊断 | 门诊诊断 | emergency_diag |
| 出院诊断-主要诊断 | 主要诊断 | main_diag_code |
| 出院诊断-相关诊断 | 相关诊断 | related_diag_code |
| 入院病情 | 入院病情 | admission_condition |
| 诊断代码计数 | 诊断数量 | diag_count |
| 主要手术及操作 | 主要手术 | main_oprn_code |
| 相关手术及操作 | 相关手术 | related_oprn_code |
| 手术及操作代码计数 | 手术数量 | oprn_count |
| 呼吸机使用时间 | 呼吸机时间 | ventilator_hours |
| 颅脑损伤患者昏迷时间 | 昏迷时间 | coma_hours |
| 重症监护病房类型 | ICU类型 | icu_type |
| 进出重症监护室时间 | ICU时间 | icu_hours |
| 离院方式 | 离院方式 | discharge_method |
| 出院31天内再住院计划 | 再住院计划 | readmission_plan |

---

## 三、医疗收费信息数据变量

| 字段名称 | 说明 | 规范字段 |
|----------|------|----------|
| 业务流水号 | 业务流水号 | business_serial |
| 票据代码 | 票据代码 | bill_code |
| 票据号码 | 票据号码 | bill_number |
| 结算期间 | 结算期间 | settlement_period |
| 金额合计 | 总费用 | total_cost |
| 医保统筹基金支付 | 统筹支付 | fund_pay |
| 补充医疗保险支付 | 补充保险支付 | supplementary_pay |
| 医疗救助支付 | 医疗救助支付 | medical_aid_pay |
| 其他支付 | 其他支付 | other_pay |
| 个人自付 | 个人自付 | self_pay |
| 个人自费 | 个人自费 | self_expense |
| 个人账户支付 | 账户支付 | account_pay |
| 个人现金支付 | 现金支付 | cash_pay |
| 医保支付方式 | 支付方式 | payment_method |

---

## 四、编码标准

### 4.1 疾病诊断编码
- **标准**: 《医疗保障疾病诊断分类与代码（ICD-10）》（2.0版）
- **用途**: 主要诊断、相关诊断、并发症/合并症编码

### 4.2 手术操作编码
- **标准**: 《医疗保障手术操作分类与代码（ICD-9-CM-3）》
- **用途**: 主要手术、相关手术操作编码

### 4.3 中医编码
- **标准**: 《中医疾病分类与代码》、《中医症候分类与代码》
- **用途**: 中医疾病和症候编码

### 4.4 医疗服务项目编码
- **标准**: 《医疗服务项目分类与代码》
- **用途**: 医疗服务项目编码

### 4.5 药品编码
- **标准**: 《医保药品分类与代码》（西药、中成药、中药饮片、医疗机构制剂）
- **用途**: 药品编码

### 4.6 医用耗材编码
- **标准**: 《医保医用耗材分类与代码》
- **用途**: 医用耗材编码

---

## 五、与4101A接口字段对照

| 规范字段 | 4101A字段 | 备注 |
|----------|-----------|------|
| hospital_code | 医疗机构代码 | |
| hospital_name | 医疗机构名称 | |
| insurance_id | 社会保障号码 | |
| case_number | 病案号 | |
| gender | 性别 | |
| birth_date | 出生日期 | |
| age | 年龄 | |
| main_diag_code | 主要诊断编码 | |
| main_diag_name | 主要诊断名称 | |
| related_diag_code | 其他诊断编码 | 1-5 |
| main_oprn_code | 主要手术编码 | |
| main_oprn_name | 主要手术名称 | |
| related_oprn_code | 其他手术编码 | 1-5 |
| total_cost | 总费用 | |
| drug_cost | 药品费用 | |
| material_cost | 耗材费用 | |
| admission_date | 入院日期 | |
| discharge_date | 出院日期 | |
| los | 住院天数 | |
| discharge_status | 出院状态 | |
| fund_pay | 基金支付 | |
| self_pay | 个人支付 | |
