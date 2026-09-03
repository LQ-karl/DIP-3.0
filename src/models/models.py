"""
DIP按病种分值分组测算工具 - 数据模型

依据: DIP3.0版技术规范（征求意见稿）第16-17页
- 成组的基础信息（表2-1 DIP聚类成组相关基础信息）
- 病人诊疗数据变量
- 医疗收费信息数据变量

编码标准:
- 《医疗保障疾病诊断分类与代码（ICD-10）》（2.0版）
- 《医疗保障手术操作分类与代码（ICD-9-CM-3）》
- 《中医疾病分类与代码》
- 《中医症候分类与代码》
- 《医保药品分类与代码》
- 《医保医用耗材分类与代码》
- 《医疗服务项目分类与代码》
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from decimal import Decimal
from enum import Enum


# ============================================================
# 规范字段标记
# ============================================================
# 标记为[DIP3.0规范]的字段为DIP3.0技术规范要求的必填字段
# 标记为[4101A]的字段为4101A接口要求的字段
# 标记为[标准编码]的字段需要使用国家统一编码标准


class GroupType(Enum):
    """病种分组类型"""
    CORE = "核心病种"
    MIXED = "综合病种"
    ADVANCED = "先期分组"


class GroupLayer(Enum):
    """核心病种四层成组层次（DIP3.0 规范顺序，用于本地目录库测算排序与标注）

    顺序：先期分组(①) → 并项规则(②) → 诊断辅助细分(③) → 基本规则(④)；
    综合病种为第二阶段，单列于最后。
    """
    PRIORITY = "先期分组"
    MERGE = "并项规则"
    DIAG_AUX = "诊断辅助细分"
    BASIC = "基本规则"
    MIXED = "综合病种"


class CalculationMethod(Enum):
    """分值计算方法"""
    AVERAGE_COST = "平均费用法"
    BENCHMARK_DISEASE = "基准病种费用法"
    STANDARD_QUOTA = "标准定额法"


class SeverityLevel(Enum):
    """疾病严重程度"""
    MILD = "轻度"
    MODERATE = "中度"
    SEVERE = "重度"
    DEATH = "死亡"


@dataclass
class DiseaseGroup:
    """病种组合"""
    disease_code: str  # 病种代码
    disease_name: str  # 病种名称
    main_diag_code: str  # 主要诊断代码
    main_diag_name: str  # 主要诊断名称
    main_oprn_code: str = ""  # 主要手术操作代码
    main_oprn_name: str = ""  # 主要手术操作名称
    related_oprn_code: str = ""  # 相关手术操作代码
    related_oprn_name: str = ""  # 相关手术操作名称
    group_type: GroupType = GroupType.CORE  # 分组类型
    case_count: int = 0  # 病例数
    avg_cost: Decimal = Decimal("0")  # 次均费用
    disease_value: Decimal = Decimal("0")  # 病种分值
    drug_value: Decimal = Decimal("0")  # 药品分值
    consumable_value: Decimal = Decimal("0")  # 耗材分值

    # 本地目录库测算所需的字典派生字段（范围：仅本地目录库 + 病种分值）
    cci_score: Decimal = Decimal("0")  # CCI评分（Charlson合并症指数，来自 CCI.xlsx 字典）
    severity_level: str = ""  # 疾病严重程度（来自 中重度分型诊断.xlsx 字典：重度/中度/轻度/转移/放疗/化疗）
    severity_type: str = ""   # 严重程度/辅助分型类型（如 QTZD / QTSS）

    # 极端病例裁剪（历史数据裁剪，按组内住院总费用 2.5% / 97.5% 分位数）
    original_case_count: int = 0   # 裁剪前病例数（用于核心/综合病种判定与覆盖统计）
    trimmed_case_count: int = 0    # 裁剪后有效病例数（RW 测算以该数为准）
    trim_lower_bound: Decimal = Decimal("0")  # 费用下限（2.5% 分位数）
    trim_upper_bound: Decimal = Decimal("0")  # 费用上限（97.5% 分位数）
    trim_count: int = 0            # 被裁剪剔除的极端病例数

    # 成组逻辑（核心病种 / 综合病种）
    # 综合病种子组：保守治疗组 / 诊断性操作组 / 治疗性操作组 / 相关手术组
    mixed_subtype: str = ""        # 综合病种子组类型（核心病种此列为空）
    op_category: str = ""          # 主手术操作类别（手术/治疗性操作/诊断性操作/介入治疗/无）
    grouping_layer: str = ""       # 成组层次（先期分组/并项规则/诊断辅助细分/基本规则/综合病种）

    # 国家目录库匹配
    national_dip_code: str = ""    # 匹配到的国家目录库 DIP 编码
    national_matched: bool = False # 是否匹配国家目录库
    national_seq: str = ""         # 命中的国家目录方案序号（如 BX-20 / JC-1858，全局唯一）
    is_grassroot: bool = False     # 基层病种标记（同病同价，不设医疗机构调节系数）

    # 综合病种质量控制
    cv: float = 0.0                # 组内变异系数（标准差/均值），用于综合病种合理性校验
    excluded: bool = False         # 质控剔除标记（聚类后仍低于阈值或 CV 过高，不纳入最终目录）

    # 成员记录（供第三步辅助分型逐条判定与真实 CV 前后计算；仅聚类时填充，不持久化）
    member_records: List[Dict] = field(default_factory=list)

    # 辅助分型（第三步）：对核心病种触发后拆分出的子组元数据
    auxiliary_type: str = ""       # 触发并拆分的辅助维度（严重程度/年龄特征/ICU天数/CCI）
    auxiliary_level: str = ""      # 该子组所属分型等级（如 重度/新生儿期/超长ICU/极严重）
    auxiliary_coefficient: Decimal = Decimal("1.0")  # 辅助分型调节系数（数据化 mj/M）
    auxiliary_trigger_coefficient: Decimal = Decimal("1.0")  # 触发系数（mj/M，用于多规则竞争）
    auxiliary_parent_code: str = ""  # 若为拆分出的子组，记录父核心病种代码
    auxiliary_split: bool = False  # 该核心病种是否已按辅助分型拆分

    # 辅助分型范围控制（B6）：中医优势病种 / 床日病种不纳入辅助分型
    is_tcm_advantage: bool = False  # 中医优势病种标记
    is_bed_day: bool = False        # 床日病种标记


@dataclass
class MedicalRecord:
    """
    住院病例记录
    
    依据: DIP3.0版技术规范（征求意见稿）第16-17页
    - 成组的基础信息（表2-1 DIP聚类成组相关基础信息）
    - 病人诊疗数据变量
    - 医疗收费信息数据变量
    
    编码标准:
    - 《医疗保障疾病诊断分类与代码（ICD-10）》（2.0版）[标准编码]
    - 《医疗保障手术操作分类与代码（ICD-9-CM-3）》[标准编码]
    - 《中医疾病分类与代码》[标准编码]
    - 《中医症候分类与代码》[标准编码]
    - 《医保药品分类与代码》[标准编码]
    - 《医保医用耗材分类与代码》[标准编码]
    - 《医疗服务项目分类与代码》[标准编码]
    """
    
    # ============================================================
    # 一、基础信息 [DIP3.0规范][4101A]
    # ============================================================
    record_id: str  # 清单流水号 [4101A]
    settlement_id: str  # 结算ID [4101A]
    patient_id: str  # 人员编号 [4101A]
    visit_id: str  # 就诊ID [4101A]
    hospital_code: str  # 定点医药机构代码 [DIP3.0规范][4101A]
    hospital_name: str  # 定点医药机构名称 [DIP3.0规范][4101A]
    hospital_level: str = ""  # 医保结算等级（医院等级） [DIP3.0规范][4101A]
    
    # ============================================================
    # 二、病人诊疗数据变量-基本信息 [DIP3.0规范]
    # ============================================================
    insurance_id: str = ""  # 医保编号 [DIP3.0规范]
    case_number: str = ""  # 病案号 [DIP3.0规范]
    gender: str = ""  # 性别 [DIP3.0规范][4101A]
    birth_date: str = ""  # 出生日期 [DIP3.0规范][4101A]
    age: int = 0  # 年龄 [DIP3.0规范][4101A]
    day_age: int = 0  # 天龄（年龄不足1周岁） [DIP3.0规范]
    id_type: str = ""  # 患者证件类别 [DIP3.0规范]
    id_number: str = ""  # 患者证件号码 [DIP3.0规范]
    occupation: str = ""  # 职业 [DIP3.0规范]
    insurance_type: str = ""  # 医保类型 [DIP3.0规范]
    special_person_type: str = ""  # 特殊人员类型 [DIP3.0规范]
    insurance_region: str = ""  # 参保地 [DIP3.0规范]
    birth_weight: Decimal = Decimal("0")  # 新生儿出生体重 [DIP3.0规范]
    admission_weight: Decimal = Decimal("0")  # 新生儿入院体重 [DIP3.0规范]
    
    # ============================================================
    # 三、病人诊疗数据变量-住院诊疗信息 [DIP3.0规范]
    # ============================================================
    visit_type: str = ""  # 住院医疗类型 [DIP3.0规范]
    admission_route: str = ""  # 入院途径 [DIP3.0规范]
    treatment_category: str = ""  # 治疗类别 [DIP3.0规范]
    admission_date: str = ""  # 入院时间 [DIP3.0规范][4101A]
    admission_dept: str = ""  # 入院科别 [DIP3.0规范]
    transfer_dept: str = ""  # 转科科别 [DIP3.0规范]
    discharge_date: str = ""  # 出院时间 [DIP3.0规范][4101A]
    discharge_dept: str = ""  # 出院科别 [DIP3.0规范]
    los: int = 0  # 实际住院天数 [DIP3.0规范][4101A]
    emergency_diag: str = ""  # 门（急）诊诊断 [DIP3.0规范]
    
    # ============================================================
    # 四、诊断信息 [DIP3.0规范][4101A][标准编码]
    # ============================================================
    main_diag_code: str = ""  # 主要诊断代码 [DIP3.0规范][4101A][标准编码:ICD-10]
    main_diag_name: str = ""  # 主要诊断名称 [DIP3.0规范][4101A]
    related_diag_code: str = ""  # 相关诊断代码（其他诊断1-5） [DIP3.0规范][4101A][标准编码:ICD-10]
    related_diag_name: str = ""  # 相关诊断名称 [DIP3.0规范][4101A]
    complication_code: str = ""  # 并发症/合并症代码 [DIP3.0规范][标准编码:ICD-10]
    complication_name: str = ""  # 并发症/合并症名称 [DIP3.0规范]
    admission_condition: str = ""  # 入院病情 [DIP3.0规范]
    diag_count: int = 0  # 诊断代码计数 [DIP3.0规范]
    
    # ============================================================
    # 五、手术操作信息 [DIP3.0规范][4101A][标准编码]
    # ============================================================
    main_oprn_code: str = ""  # 主要手术操作代码 [DIP3.0规范][4101A][标准编码:ICD-9-CM-3]
    main_oprn_name: str = ""  # 主要手术操作名称 [DIP3.0规范][4101A]
    related_oprn_code: str = ""  # 相关手术操作代码（其他手术1-5） [DIP3.0规范][4101A][标准编码:ICD-9-CM-3]
    related_oprn_name: str = ""  # 相关手术操作名称 [DIP3.0规范][4101A]
    oprn_count: int = 0  # 手术及操作代码计数 [DIP3.0规范]
    
    # ============================================================
    # 六、肿瘤及特殊治疗信息 [DIP3.0规范]
    # ============================================================
    tumor_metastasis: str = ""  # 肿瘤转移情况 [DIP3.0规范]
    tumor_stage: str = ""  # 肿瘤分期 [DIP3.0规范]
    chemo_status: str = ""  # 放化疗状态 [DIP3.0规范]
    
    # ============================================================
    # 七、医疗资源使用信息 [DIP3.0规范]
    # ============================================================
    ventilator_hours: int = 0  # 呼吸机使用时间（小时） [DIP3.0规范]
    coma_hours: int = 0  # 颅脑损伤患者昏迷时间（小时） [DIP3.0规范]
    icu_type: str = ""  # 重症监护病房类型 [DIP3.0规范]
    icu_hours: int = 0  # 进出重症监护室时间（小时） [DIP3.0规范]

    # 重症判断补充字段（国家未明确监护病房住院天数分型，业务以收费项目/病房类型 + 特级护理天数判断）
    spga_nurscare_days: int = 0   # 特级护理天数 [业务补充，用于重症判断 判断1/判断2]
    scs_cutd_ward_type: str = ""  # 重症监护病房类型 [业务补充，用于重症判断 判断2]
    charge_item_codes: List[str] = field(default_factory=list)  # 收费项目编码集合 [业务补充，用于重症判断 判断1]
    
    # ============================================================
    # 八、费用信息 [DIP3.0规范][4101A][标准编码]
    # ============================================================
    total_cost: Decimal = Decimal("0")  # 医疗总费用（金额合计） [DIP3.0规范][4101A]
    drug_cost: Decimal = Decimal("0")  # 药品费用 [DIP3.0规范][4101A]
    consumable_cost: Decimal = Decimal("0")  # 耗材费用 [DIP3.0规范][4101A]
    exam_cost: Decimal = Decimal("0")  # 检查费用 [DIP3.0规范][4101A]
    treatment_cost: Decimal = Decimal("0")  # 治疗费用 [DIP3.0规范][4101A]
    material_cost: Decimal = Decimal("0")  # 材料费用 [DIP3.0规范][4101A]
    nursing_cost: Decimal = Decimal("0")  # 护理费用 [DIP3.0规范][4101A]
    
    # ============================================================
    # 九、医保结算信息 [DIP3.0规范][4101A]
    # ============================================================
    fund_pay: Decimal = Decimal("0")  # 医保统筹基金支付 [DIP3.0规范][4101A]
    supplementary_pay: Decimal = Decimal("0")  # 补充医疗保险支付 [DIP3.0规范]
    medical_aid_pay: Decimal = Decimal("0")  # 医疗救助支付 [DIP3.0规范]
    other_pay: Decimal = Decimal("0")  # 其他支付 [DIP3.0规范]
    self_pay: Decimal = Decimal("0")  # 个人自付 [DIP3.0规范][4101A]
    self_expense: Decimal = Decimal("0")  # 个人自费 [DIP3.0规范]
    account_pay: Decimal = Decimal("0")  # 个人账户支付 [DIP3.0规范]
    cash_pay: Decimal = Decimal("0")  # 个人现金支付 [DIP3.0规范]
    payment_method: str = ""  # 医保支付方式 [DIP3.0规范]
    
    # ============================================================
    # 十、离院信息 [DIP3.0规范]
    # ============================================================
    discharge_status: str = ""  # 出院状态（死亡、医嘱出院、非医嘱出院、转院） [DIP3.0规范][4101A]
    discharge_method: str = ""  # 离院方式 [DIP3.0规范]
    readmission_plan: str = ""  # 出院31天内再住院计划 [DIP3.0规范]
    
    # ============================================================
    # 十一、编码标准化字段 [标准编码]
    # ============================================================
    main_diag_code_standard: str = ""  # 主要诊断代码-医保标准编码 [标准编码:ICD-10]
    related_diag_code_standard: str = ""  # 相关诊断代码-医保标准编码 [标准编码:ICD-10]
    main_oprn_code_standard: str = ""  # 主要手术代码-医保标准编码 [标准编码:ICD-9-CM-3]
    related_oprn_code_standard: str = ""  # 相关手术代码-医保标准编码 [标准编码:ICD-9-CM-3]
    
    # ============================================================
    # 十二、DIP分组结果
    # ============================================================
    dip_disease_code: str = ""  # DIP病种代码
    dip_disease_name: str = ""  # DIP病种名称
    disease_value: Decimal = Decimal("0")  # 病种分值
    drug_value: Decimal = Decimal("0")  # 药品分值
    consumable_value: Decimal = Decimal("0")  # 耗材分值
    payment_standard: Decimal = Decimal("0")  # 支付标准
    hospital_coefficient: Decimal = Decimal("1.0")  # 医院系数
    auxiliary_coefficient: Decimal = Decimal("1.0")  # 辅助分型系数


@dataclass
class HospitalCoefficient:
    """
    医疗机构调节系数
    
    依据: DIP3.0版技术规范（征求意见稿）第160-180页
    - 医疗机构等级调节系数
    - 遴选原则：该病种在不同等级类型医疗机构资源消耗差异大
    - 特殊情况：基层病种不区分医疗机构调节系数，实施同病同治同价
    """
    hospital_code: str  # 医疗机构代码 [DIP3.0规范]
    hospital_name: str  # 医疗机构名称 [DIP3.0规范]
    hospital_level: str  # 医疗机构等级 [DIP3.0规范]
    basic_coefficient: Decimal = Decimal("1.0")  # 基本系数
    bonus_coefficient: Decimal = Decimal("0")  # 加成系数
    total_coefficient: Decimal = Decimal("1.0")  # 总调节系数（基本系数 + 加成系数）
    
    # 统计信息
    case_count: int = 0  # 该医院该病种病例数
    avg_cost: Decimal = Decimal("0")  # 该医院该病种平均费用
    city_avg_cost: Decimal = Decimal("0")  # 全市该病种平均费用


@dataclass
class AuxiliaryClassification:
    """辅助分型"""
    classification_type: str  # 分型类型
    classification_name: str  # 分型名称
    trigger_condition: str  # 触发条件
    coefficient: Decimal = Decimal("1.0")  # 调节系数


@dataclass
class DIPSettlementResult:
    """
    DIP结算结果
    
    依据: DIP3.0版技术规范（征求意见稿）第16-17页
    - 医疗收费信息数据变量
    """
    record_id: str  # 清单流水号 [4101A]
    patient_id: str  # 人员编号 [4101A]
    hospital_code: str  # 医疗机构代码 [DIP3.0规范]
    disease_code: str  # 病种代码
    disease_name: str  # 病种名称
    
    # 分值信息
    disease_value: Decimal = Decimal("0")  # 病种分值
    drug_value: Decimal = Decimal("0")  # 药品分值
    consumable_value: Decimal = Decimal("0")  # 耗材分值
    
    # 系数信息
    hospital_coefficient: Decimal = Decimal("1.0")  # 医疗机构调节系数
    auxiliary_coefficient: Decimal = Decimal("1.0")  # 辅助分型调节系数
    
    # 费用信息
    point_value: Decimal = Decimal("0")  # 点值（每分值支付金额）
    payment_standard: Decimal = Decimal("0")  # 支付标准
    actual_cost: Decimal = Decimal("0")  # 实际费用
    
    # 医保结算信息 [DIP3.0规范]
    fund_pay: Decimal = Decimal("0")  # 医保统筹基金支付
    supplementary_pay: Decimal = Decimal("0")  # 补充医疗保险支付
    medical_aid_pay: Decimal = Decimal("0")  # 医疗救助支付
    other_pay: Decimal = Decimal("0")  # 其他支付
    self_pay: Decimal = Decimal("0")  # 个人自付
    self_expense: Decimal = Decimal("0")  # 个人自费
    account_pay: Decimal = Decimal("0")  # 个人账户支付
    cash_pay: Decimal = Decimal("0")  # 个人现金支付
    
    # 支付信息
    insurance_payment: Decimal = Decimal("0")  # 医保支付总额
    patient_payment: Decimal = Decimal("0")  # 个人支付总额
    payment_method: str = ""  # 医保支付方式


@dataclass
class SimulationParams:
    """
    模拟测算参数
    
    依据: DIP3.0版技术规范（征求意见稿）第160-180页
    - 分值计算方法
    - 时间权重
    - 临界值设定
    """
    total_fund: Decimal  # 医保基金DIP付费总额
    payment_ratio: Decimal = Decimal("0.85")  # 医保支付比例
    threshold: int = 15  # 核心病种临界值（病例数低于此值归入综合病种）
    calculation_method: CalculationMethod = CalculationMethod.AVERAGE_COST
    data_years: List[int] = field(default_factory=lambda: [2020, 2021, 2022])
    year_weights: List[float] = field(default_factory=lambda: [0.1, 0.2, 0.7])  # 时间权重比例1:2:7
    
    # 分组参数
    include_advanced_group: bool = True  # 是否包含先期分组
    include_core_disease: bool = True  # 是否包含核心病种
    include_mixed_disease: bool = True  # 是否包含综合病种
    
    # 基层病种参数
    basic_disease_same_price: bool = True  # 基层病种同病同治同价
    basic_disease_no_coefficient: bool = True  # 基层病种不区分医疗机构调节系数


@dataclass
class ValueCalculationResult:
    """分值计算结果"""
    calculation_method: str  # 计算方法
    value_per_point: Decimal = Decimal("0")  # 分值
    total_payment: Decimal = Decimal("0")  # 总支付金额
    total_cases: int = 0  # 病例数
    average_cost: Decimal = Decimal("0")  # 平均费用
    notes: str = ""  # 备注


@dataclass
class CodingStandard:
    """
    编码标准信息
    
    依据: DIP3.0版技术规范（征求意见稿）第932-947页
    - 《医疗保障疾病诊断分类与代码（ICD-10）》（2.0版）
    - 《医疗保障手术操作分类与代码（ICD-9-CM-3）》
    - 《中医疾病分类与代码》
    - 《中医症候分类与代码》
    - 《医保药品分类与代码》
    - 《医保医用耗材分类与代码》
    - 《医疗服务项目分类与代码》
    """
    standard_name: str  # 标准名称
    standard_code: str  # 标准代码
    standard_version: str  # 标准版本
    standard_type: str  # 标准类型（诊断/手术/药品/耗材/服务项目）
    issuer: str = ""  # 发布机构（国家卫健委/国家医保局）
    effective_date: str = ""  # 生效日期
    description: str = ""  # 描述


@dataclass
class DiseaseGroupStandard:
    """
    DIP病种目录标准
    
    依据: DIP3.0版技术规范（征求意见稿）
    - 国家DIP病种目录库（3.0版）
    """
    dip_code: str  # DIP编码
    main_diag_code: str  # 主要诊断编码 [标准编码:ICD-10]
    main_diag_name: str  # 主要诊断名称
    main_oprn_code: str = ""  # 主要手术操作编码 [标准编码:ICD-9-CM-3]
    main_oprn_name: str = ""  # 主要手术操作名称
    related_oprn_code: str = ""  # 相关手术操作编码 [标准编码:ICD-9-CM-3]
    related_oprn_name: str = ""  # 相关手术操作名称
    group_type: str = ""  # 分组类型（内科/手术）
    disease_type: str = ""  # 病种类型（核心病种/综合病种）
    case_count: int = 0  # 病例数
    disease_value: Decimal = Decimal("0")  # 病种分值
