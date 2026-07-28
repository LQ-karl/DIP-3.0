"""
DIP3.0本地目录测算系统 - 数据库模型
使用SQLAlchemy ORM设计，支持SQLite和MySQL
"""
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, DateTime, 
    Boolean, Text, ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from datetime import datetime
from typing import Optional, List
import os

Base = declarative_base()


class MedicalRecord(Base):
    """病例表 - 存储医保结算清单数据"""
    __tablename__ = 'medical_records'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    record_id = Column(String(50), unique=True, nullable=False, comment='清单流水号')
    settlement_id = Column(String(50), comment='结算ID')
    patient_id = Column(String(50), comment='人员编号')
    visit_id = Column(String(50), comment='就诊ID')
    
    # 医疗机构信息
    hospital_code = Column(String(20), nullable=False, comment='定点医药机构编号')
    hospital_name = Column(String(100), comment='定点医药机构名称')
    hospital_level = Column(String(20), comment='医疗机构等级')
    
    # 诊断信息
    main_diag_code = Column(String(20), comment='主要诊断代码')
    main_diag_name = Column(String(200), comment='主要诊断名称')
    related_diag_code = Column(String(200), comment='相关诊断代码(多个用|分隔)')
    related_diag_name = Column(String(500), comment='相关诊断名称')
    
    # 手术操作信息
    main_oprn_code = Column(String(20), comment='主要手术操作代码')
    main_oprn_name = Column(String(200), comment='主要手术操作名称')
    related_oprn_code = Column(String(200), comment='相关手术操作代码(多个用|分隔)')
    related_oprn_name = Column(String(500), comment='相关手术操作名称')
    
    # 费用信息
    total_cost = Column(Float, default=0, comment='医疗总费用')
    drug_cost = Column(Float, default=0, comment='药品费用')
    consumable_cost = Column(Float, default=0, comment='耗材费用')
    exam_cost = Column(Float, default=0, comment='检查费用')
    treatment_cost = Column(Float, default=0, comment='治疗费用')
    material_cost = Column(Float, default=0, comment='材料费用')
    nursing_cost = Column(Float, default=0, comment='护理费用')
    
    # 住院信息
    admission_date = Column(String(10), comment='入院日期')
    discharge_date = Column(String(10), comment='出院日期')
    los = Column(Integer, default=0, comment='实际住院天数')
    discharge_status = Column(String(20), comment='出院状态')
    
    # 年龄信息
    birth_date = Column(String(10), comment='出生日期')
    age = Column(Integer, default=0, comment='年龄')
    gender = Column(String(5), comment='性别')
    
    # 分组结果
    dip_disease_code = Column(String(50), comment='DIP病种代码')
    dip_disease_name = Column(String(200), comment='DIP病种名称')
    group_type = Column(String(20), comment='分组类型(核心/综合/先期)')
    
    # 分值和支付
    disease_value = Column(Float, default=0, comment='病种分值')
    hospital_coefficient = Column(Float, default=1.0, comment='医院调节系数')
    auxiliary_coefficient = Column(Float, default=1.0, comment='辅助分型系数')
    payment_standard = Column(Float, default=0, comment='支付标准')
    actual_payment = Column(Float, default=0, comment='实际支付金额')
    
    # 数据质量
    data_quality_flag = Column(String(20), default='正常', comment='数据质量标记')
    is_abnormal = Column(Boolean, default=False, comment='是否异常病例')
    is_high_rate = Column(Boolean, default=False, comment='是否高倍率病例')
    is_low_rate = Column(Boolean, default=False, comment='是否低倍率病例')
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')
    
    # 索引
    __table_args__ = (
        Index('idx_hospital_code', 'hospital_code'),
        Index('idx_main_diag_code', 'main_diag_code'),
        Index('idx_dip_disease_code', 'dip_disease_code'),
        Index('idx_admission_date', 'admission_date'),
        Index('idx_hospital_level', 'hospital_level'),
    )


class DiseaseGroup(Base):
    """病种表 - 存储DIP病种分组信息"""
    __tablename__ = 'disease_groups'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    disease_code = Column(String(50), unique=True, nullable=False, comment='病种代码')
    disease_name = Column(String(200), comment='病种名称')
    
    # 诊断信息
    main_diag_code = Column(String(20), comment='主要诊断代码')
    main_diag_name = Column(String(200), comment='主要诊断名称')
    main_oprn_code = Column(String(20), comment='主要手术操作代码')
    main_oprn_name = Column(String(200), comment='主要手术操作名称')
    related_oprn_code = Column(String(200), comment='相关手术操作代码')
    related_oprn_name = Column(String(500), comment='相关手术操作名称')
    
    # 分组信息
    group_type = Column(String(20), comment='分组类型(核心/综合/先期)')
    case_count = Column(Integer, default=0, comment='病例数')
    
    # 费用统计
    avg_cost = Column(Float, default=0, comment='平均费用')
    median_cost = Column(Float, default=0, comment='中位费用')
    std_cost = Column(Float, default=0, comment='费用标准差')
    min_cost = Column(Float, default=0, comment='最低费用')
    max_cost = Column(Float, default=0, comment='最高费用')
    cv_cost = Column(Float, default=0, comment='费用变异系数')
    
    # 分值信息
    disease_value = Column(Float, default=0, comment='病种分值')
    drug_value = Column(Float, default=0, comment='药品分值')
    consumable_value = Column(Float, default=0, comment='耗材分值')
    
    # 支付信息
    avg_payment = Column(Float, default=0, comment='平均支付金额')
    payment_standard = Column(Float, default=0, comment='支付标准')
    
    # 高低倍率
    high_rate_threshold = Column(Float, default=0, comment='高倍率阈值')
    low_rate_threshold = Column(Float, default=0, comment='低倍率阈值')
    high_rate_count = Column(Integer, default=0, comment='高倍率病例数')
    low_rate_count = Column(Integer, default=0, comment='低倍率病例数')
    
    # 时间权重
    year_weight = Column(Float, default=1.0, comment='时间权重')
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')
    
    # 索引
    __table_args__ = (
        Index('idx_main_diag', 'main_diag_code'),
        Index('idx_group_type', 'group_type'),
        Index('idx_case_count', 'case_count'),
    )


class DIPDirectory(Base):
    """DIP目录表 - 存储国家DIP3.0目录库"""
    __tablename__ = 'dip_directory'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    dip_code = Column(String(50), unique=True, nullable=False, comment='DIP编码')
    
    # 诊断信息
    main_diag_code = Column(String(20), comment='主要诊断编码')
    main_diag_name = Column(String(200), comment='主要诊断名称')
    main_oprn_code = Column(String(20), comment='主要手术操作编码')
    main_oprn_name = Column(String(200), comment='主要手术操作名称')
    related_oprn_code = Column(String(200), comment='相关手术操作编码')
    related_oprn_name = Column(String(500), comment='相关手术操作名称')
    
    # 分组信息
    group_type = Column(String(20), comment='分组类型')
    disease_type = Column(String(20), comment='病种类型')
    
    # 版本信息
    version = Column(String(20), comment='目录版本')
    effective_date = Column(String(10), comment='生效日期')
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    
    # 索引
    __table_args__ = (
        Index('idx_dip_main_diag', 'main_diag_code'),
    )


class DiseaseValue(Base):
    """分值表 - 存储病种分值计算结果"""
    __tablename__ = 'disease_values'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    disease_code = Column(String(50), nullable=False, comment='病种代码')
    calculation_method = Column(String(50), comment='计算方法')
    
    # 分值信息
    disease_value = Column(Float, default=0, comment='病种分值')
    drug_value = Column(Float, default=0, comment='药品分值')
    consumable_value = Column(Float, default=0, comment='耗材分值')
    
    # 计算参数
    city_avg_cost = Column(Float, default=0, comment='全市平均费用')
    disease_avg_cost = Column(Float, default=0, comment='病种平均费用')
    benchmark_cost = Column(Float, default=0, comment='基准病种费用')
    
    # 时间权重
    year = Column(Integer, comment='年度')
    weight = Column(Float, default=1.0, comment='时间权重')
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    
    # 索引
    __table_args__ = (
        Index('idx_dv_disease_code', 'disease_code'),
        Index('idx_dv_year', 'year'),
    )


class ICD10(Base):
    """ICD-10编码表"""
    __tablename__ = 'icd10'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(20), unique=True, nullable=False, comment='ICD-10编码')
    name = Column(String(200), comment='诊断名称')
    category = Column(String(50), comment='疾病分类')
    is_valid = Column(Boolean, default=True, comment='是否有效')
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')


class ICD9CM3(Base):
    """ICD-9-CM-3编码表"""
    __tablename__ = 'icd9_cm3'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(20), unique=True, nullable=False, comment='ICD-9-CM-3编码')
    name = Column(String(200), comment='手术操作名称')
    category = Column(String(50), comment='手术分类')
    is_valid = Column(Boolean, default=True, comment='是否有效')
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')


class Hospital(Base):
    """医院表 - 存储医疗机构信息"""
    __tablename__ = 'hospitals'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    hospital_code = Column(String(20), unique=True, nullable=False, comment='医疗机构代码')
    hospital_name = Column(String(100), comment='医疗机构名称')
    hospital_level = Column(String(20), comment='医疗机构等级')
    hospital_type = Column(String(20), comment='医疗机构类型')
    region_code = Column(String(20), comment='所属区域代码')
    region_name = Column(String(50), comment='所属区域名称')
    
    # 基本信息
    bed_count = Column(Integer, comment='床位数')
    staff_count = Column(Integer, comment='员工数')
    
    # 状态
    is_active = Column(Boolean, default=True, comment='是否 active')
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')


class HospitalCoefficient(Base):
    """等级系数表 - 存储医院调节系数"""
    __tablename__ = 'hospital_coefficients'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    hospital_code = Column(String(20), nullable=False, comment='医疗机构代码')
    hospital_level = Column(String(20), comment='医疗机构等级')
    
    # 系数信息
    basic_coefficient = Column(Float, default=1.0, comment='基本系数')
    bonus_coefficient = Column(Float, default=0, comment='加成系数')
    total_coefficient = Column(Float, default=1.0, comment='总调节系数')
    
    # 计算参数
    disease_code = Column(String(50), comment='病种代码(可选)')
    avg_cost = Column(Float, default=0, comment='该医院该病种平均费用')
    city_avg_cost = Column(Float, default=0, comment='全市该病种平均费用')
    
    # 年度
    year = Column(Integer, comment='年度')
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    
    # 索引
    __table_args__ = (
        Index('idx_hc_hospital', 'hospital_code'),
        Index('idx_hc_level', 'hospital_level'),
        Index('idx_hc_disease', 'disease_code'),
    )


class AuxiliaryClassification(Base):
    """辅助分型表 - 存储辅助目录分型信息"""
    __tablename__ = 'auxiliary_classifications'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    disease_code = Column(String(50), nullable=False, comment='病种代码')
    classification_type = Column(String(50), comment='分型类型(年龄/CCI/严重程度/ICU)')
    classification_name = Column(String(100), comment='分型名称')
    
    # 分型规则
    trigger_condition = Column(Text, comment='触发条件')
    trigger_coefficient = Column(Float, default=1.0, comment='触发系数')
    
    # 调节系数
    auxiliary_coefficient = Column(Float, default=1.0, comment='辅助分型调节系数')
    
    # 统计信息
    case_count = Column(Integer, default=0, comment='该分型病例数')
    avg_cost = Column(Float, default=0, comment='该分型平均费用')
    
    # 年度
    year = Column(Integer, comment='年度')
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    
    # 索引
    __table_args__ = (
        Index('idx_ac_disease', 'disease_code'),
        Index('idx_ac_type', 'classification_type'),
    )


class QualityCheckResult(Base):
    """质量控制结果表"""
    __tablename__ = 'quality_check_results'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    check_type = Column(String(50), comment='检查类型')
    check_name = Column(String(100), comment='检查名称')
    
    # 检查结果
    is_passed = Column(Boolean, comment='是否通过')
    risk_level = Column(String(20), comment='风险等级(高/中/低)')
    risk_count = Column(Integer, default=0, comment='风险病例数')
    risk_rate = Column(Float, default=0, comment='风险比例')
    
    # 详细信息
    detail_info = Column(Text, comment='详细信息')
    suggestion = Column(Text, comment='处理建议')
    
    # 年度
    year = Column(Integer, comment='年度')
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')


class OperationLog(Base):
    """操作日志表"""
    __tablename__ = 'operation_logs'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    operation_type = Column(String(50), comment='操作类型')
    operation_name = Column(String(100), comment='操作名称')
    operator = Column(String(50), comment='操作人')
    
    # 操作详情
    input_params = Column(Text, comment='输入参数')
    output_result = Column(Text, comment='输出结果')
    status = Column(String(20), comment='状态(成功/失败)')
    error_msg = Column(Text, comment='错误信息')
    
    # 耗时
    start_time = Column(DateTime, comment='开始时间')
    end_time = Column(DateTime, comment='结束时间')
    duration = Column(Float, comment='耗时(秒)')
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')


class DatabaseManager:
    """数据库管理器"""
    
    def __init__(self, db_url: str = None):
        """
        初始化数据库管理器
        
        Args:
            db_url: 数据库连接URL，例如：
                - SQLite: sqlite:///dip3.db
                - MySQL: mysql+pymysql://user:pass@host/db
        """
        if db_url is None:
            # 默认使用SQLite
            db_path = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'dip3.db')
            db_url = f"sqlite:///{db_path}"
        
        self.engine = create_engine(db_url, echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine)
    
    def create_tables(self):
        """创建所有表"""
        Base.metadata.create_all(self.engine)
        print("数据库表创建完成")
    
    def drop_tables(self):
        """删除所有表"""
        Base.metadata.drop_all(self.engine)
        print("数据库表删除完成")
    
    def get_session(self):
        """获取数据库会话"""
        return self.SessionLocal()
    
    def init_database(self):
        """初始化数据库"""
        self.create_tables()
        print("数据库初始化完成")


# 便捷函数
def get_database_manager(db_url: str = None) -> DatabaseManager:
    """获取数据库管理器实例"""
    return DatabaseManager(db_url)


def create_database_tables(db_url: str = None):
    """创建数据库表"""
    manager = get_database_manager(db_url)
    manager.create_tables()
    return manager
