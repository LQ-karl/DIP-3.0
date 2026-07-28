"""
DIP3.0本地目录测算系统 - Web界面
基于Streamlit构建
"""
import streamlit as st
import pandas as pd
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from decimal import Decimal
from src.models.models import MedicalRecord, GroupType
from src.core.grouping_engine import DIPGroupingEngine
from src.utils.paths import get_data_dir
from src.core.value_calculator_selectable import (
    DIPValueCalculator, ValueCalculationConfig, ValueCalculationMethod,
    create_average_cost_config, create_reference_disease_config, create_standard_quota_config
)
from src.core.hospital_coefficient_selector import (
    HospitalCoefficientSelector, CoefficientCalculationConfig, CoefficientCalculationMethod,
    create_basic_bonus_config
)
from src.core.auxiliary_directory_exporter import AuxiliaryDirectoryExporter
from src.core.quality_control import QualityController
from src.core.high_low_rate_handler import HighLowRateHandler

# 页面配置
st.set_page_config(
    page_title="DIP3.0本地目录测算系统",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 自定义样式
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        padding: 1rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        border-radius: 10px;
        padding: 1rem;
        text-align: center;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 2px;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 10px 20px;
    }
</style>
""", unsafe_allow_html=True)


def init_session_state():
    """初始化会话状态"""
    if 'records' not in st.session_state:
        st.session_state.records = []
    if 'grouping_results' not in st.session_state:
        st.session_state.grouping_results = []
    if 'value_results' not in st.session_state:
        st.session_state.value_results = []
    if 'hospital_results' not in st.session_state:
        st.session_state.hospital_results = []
    if 'auxiliary_results' not in st.session_state:
        st.session_state.auxiliary_results = []


def generate_test_data():
    """生成测试数据（包含DIP3.0规范字段）"""
    records = []
    for i in range(20):
        records.append(MedicalRecord(
            record_id=f"R{i+1:04d}", settlement_id=f"S{i+1:04d}",
            patient_id=f"P{i+1:04d}", visit_id=f"V{i+1:04d}",
            hospital_code="H001", hospital_name="市人民医院", hospital_level="三级甲等",
            # 病人诊疗数据变量-基本信息
            gender="男" if i % 2 == 0 else "女",
            birth_date=f"196{i%10}-01-15",
            age=50 + i,
            insurance_type="城镇职工",
            # 病人诊疗数据变量-住院诊疗信息
            main_diag_code="I21.0", main_diag_name="前壁急性透壁性心肌梗死",
            admission_date="2024-01-15", discharge_date="2024-01-27", los=12,
            discharge_status="医嘱离院",
            # 费用信息
            total_cost=Decimal(str(15000 + i * 500)),
            drug_cost=Decimal(str(6000 + i * 200)),
            material_cost=Decimal(str(4000 + i * 150)),
            consumable_cost=Decimal(str(3000 + i * 100)),
            exam_cost=Decimal(str(2000 + i * 50)),
            treatment_cost=Decimal(str(4000 + i * 200)),
            # 医保结算信息
            fund_pay=Decimal(str(12000 + i * 400)),
            self_pay=Decimal(str(3000 + i * 100)),
        ))
    for i in range(15):
        records.append(MedicalRecord(
            record_id=f"R{i+21:04d}", settlement_id=f"S{i+21:04d}",
            patient_id=f"P{i+21:04d}", visit_id=f"V{i+21:04d}",
            hospital_code="H002", hospital_name="区中心医院", hospital_level="二级甲等",
            # 病人诊疗数据变量-基本信息
            gender="男" if i % 2 == 0 else "女",
            birth_date=f"197{i%10}-03-20",
            age=45 + i,
            insurance_type="城镇居民",
            # 病人诊疗数据变量-住院诊疗信息（严格按照DIP3.0目录库）
            main_diag_code="K35", main_diag_name="急性阑尾炎",
            main_oprn_code="47.0100", main_oprn_name="腹腔镜下阑尾切除术",
            related_oprn_code="54.5100x005", related_oprn_name="腹腔镜下腹腔粘连松解术",
            admission_date="2024-02-10", discharge_date="2024-02-18", los=8,
            discharge_status="医嘱离院",
            # 费用信息
            total_cost=Decimal(str(10000 + i * 400)),
            drug_cost=Decimal(str(3000 + i * 150)),
            material_cost=Decimal(str(2500 + i * 100)),
            consumable_cost=Decimal(str(2000 + i * 80)),
            exam_cost=Decimal(str(1500 + i * 40)),
            treatment_cost=Decimal(str(3000 + i * 120)),
            # 医保结算信息
            fund_pay=Decimal(str(8000 + i * 300)),
            self_pay=Decimal(str(2000 + i * 100)),
        ))
    return records


def page_data_import():
    """数据导入页面"""
    st.header("📊 数据导入")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("导入医保结算清单")
        
        file_type = st.selectbox(
            "选择文件类型",
            ["Excel (.xlsx)", "CSV (.csv)", "测试数据"]
        )
        
        if file_type == "测试数据":
            if st.button("生成测试数据", type="primary"):
                with st.spinner("正在生成测试数据..."):
                    st.session_state.records = generate_test_data()
                st.success(f"✅ 已生成 {len(st.session_state.records)} 条测试数据")
        else:
            uploaded_file = st.file_uploader("上传文件", type=['xlsx', 'csv'])
            if uploaded_file:
                with st.spinner("正在导入数据..."):
                    if file_type == "Excel (.xlsx)":
                        df = pd.read_excel(uploaded_file)
                    else:
                        df = pd.read_csv(uploaded_file)
                    
                    # 转换为MedicalRecord对象
                    records = []
                    for _, row in df.iterrows():
                        records.append(MedicalRecord(
                            record_id=str(row.get('清单流水号', '')),
                            settlement_id=str(row.get('结算ID', '')),
                            patient_id=str(row.get('人员编号', '')),
                            visit_id=str(row.get('就诊ID', '')),
                            hospital_code=str(row.get('医院代码', '')),
                            hospital_name=str(row.get('医院名称', '')),
                            hospital_level=str(row.get('医院等级', '')),
                            main_diag_code=str(row.get('主要诊断编码', '')),
                            main_diag_name=str(row.get('主要诊断名称', '')),
                            main_oprn_code=str(row.get('主要手术编码', '')),
                            main_oprn_name=str(row.get('主要手术名称', '')),
                            total_cost=Decimal(str(row.get('总费用', 0))),
                            drug_cost=Decimal(str(row.get('药品费用', 0))),
                            material_cost=Decimal(str(row.get('耗材费用', 0))),
                            admission_date=str(row.get('入院日期', '')),
                            discharge_date=str(row.get('出院日期', '')),
                            los=int(row.get('住院天数', 0)),
                        ))
                    st.session_state.records = records
                
                st.success(f"✅ 已导入 {len(st.session_state.records)} 条数据")
    
    with col2:
        st.subheader("数据概览")
        if st.session_state.records:
            st.metric("总病例数", len(st.session_state.records))
            
            # 统计信息
            total_cost = sum(r.total_cost for r in st.session_state.records)
            st.metric("总费用", f"¥{float(total_cost):,.2f}")
            
            avg_cost = total_cost / len(st.session_state.records) if st.session_state.records else 0
            st.metric("平均费用", f"¥{float(avg_cost):,.2f}")
            
            # 显示数据预览
            if st.button("预览数据"):
                preview_data = []
                for r in st.session_state.records[:10]:
                    preview_data.append({
                        '记录ID': r.record_id,
                        '医院': r.hospital_name,
                        '主要诊断': r.main_diag_name,
                        '总费用': float(r.total_cost),
                        '住院天数': r.los
                    })
                st.dataframe(pd.DataFrame(preview_data), use_container_width=True)
        else:
            st.info("请先导入数据")


def page_grouping():
    """分组测算页面"""
    st.header("🔬 分组测算")
    
    if not st.session_state.records:
        st.warning("⚠️ 请先导入数据")
        return
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("分组配置")
        
        # 分值计算方法
        value_method = st.selectbox(
            "分值计算方法",
            ["平均费用法", "基准病种费用法", "标准定额法"]
        )
        
        # 医院系数方法
        hospital_method = st.selectbox(
            "医院系数方法",
            ["基本系数法", "加成系数法", "基本+加成系数法"]
        )
        
        # 核心病种阈值
        threshold = st.slider("核心病种病例数阈值", 5, 50, 15)
    
    with col2:
        st.subheader("测算控制")
        
        if st.button("🚀 开始测算", type="primary", use_container_width=True):
            try:
                with st.spinner("正在进行DIP分组..."):
                    from src.models.models import DiseaseGroup, GroupType
                    
                    # 加载DIP3.0目录库
                    dip_dir = pd.read_excel(str(get_data_dir() / "DIP3.0国家目录库.xlsx"))
                    
                    def find_dip_code_from_dir(diag_code, oprn_code):
                        """从DIP3.0目录库查找匹配的DIP编码"""
                        # 查找该诊断编码的所有DIP条目
                        matching = dip_dir[dip_dir['主要诊断编码'] == diag_code]
                        for _, row in matching.iterrows():
                            dip_proc = str(row.get('主要手术操作编码', '')) if pd.notna(row.get('主要手术操作编码')) else ''
                            # 内科病种（无手术操作）
                            if not oprn_code and not dip_proc:
                                return str(row.get('DIP编码', '')), str(row.get('主要诊断编码', '')), str(row.get('主要诊断名称', '')), dip_proc, str(row.get('主要手术操作名称', '') if pd.notna(row.get('主要手术操作名称')) else '')
                            # 手术病种（有手术操作，精确匹配）
                            if oprn_code and dip_proc and oprn_code == dip_proc:
                                return str(row.get('DIP编码', '')), str(row.get('主要诊断编码', '')), str(row.get('主要诊断名称', '')), dip_proc, str(row.get('主要手术操作名称', '') if pd.notna(row.get('主要手术操作名称')) else '')
                        return None, None, None, None, None
                    
                    temp_groups = {}
                    for record in st.session_state.records:
                        dip_code, dip_diag_code, dip_diag_name, dip_proc_code, dip_proc_name = find_dip_code_from_dir(
                            record.main_diag_code, record.main_oprn_code
                        )
                        
                        if dip_code:
                            disease_code = dip_code
                            disease_name = dip_diag_name
                            main_oprn_code = dip_proc_code
                            main_oprn_name = dip_proc_name
                            main_diag_code = dip_diag_code
                        else:
                            # 未匹配到DIP目录库，使用默认格式
                            if record.main_oprn_code:
                                disease_code = f"{record.main_diag_code}-01"
                                disease_name = f"{record.main_diag_name}"
                            else:
                                disease_code = f"{record.main_diag_code}-00"
                                disease_name = record.main_diag_name
                            main_oprn_code = record.main_oprn_code
                            main_oprn_name = record.main_oprn_name
                            main_diag_code = record.main_diag_code
                        
                        if disease_code in temp_groups:
                            temp_groups[disease_code].case_count += 1
                            temp_groups[disease_code].avg_cost += record.total_cost
                        else:
                            temp_groups[disease_code] = DiseaseGroup(
                                disease_code=disease_code,
                                disease_name=disease_name,
                                main_diag_code=main_diag_code,
                                main_diag_name=record.main_diag_name,
                                main_oprn_code=main_oprn_code or "",
                                main_oprn_name=main_oprn_name or "",
                                related_oprn_code=record.related_oprn_code,
                                related_oprn_name=record.related_oprn_name,
                                group_type=GroupType.CORE,
                                case_count=1,
                                avg_cost=record.total_cost
                            )
                        
                        record.dip_disease_code = disease_code
                        record.dip_disease_name = disease_name
                    
                    for group in temp_groups.values():
                        if group.case_count > 0:
                            group.avg_cost = group.avg_cost / group.case_count
                    
                    grouping_results = []
                    for group in temp_groups.values():
                        if group.case_count >= threshold:
                            group.group_type = GroupType.CORE
                        else:
                            group.group_type = GroupType.MIXED
                        grouping_results.append(group)
                    
                    st.session_state.grouping_results = grouping_results
                
                with st.spinner("正在计算病种分值..."):
                    if value_method == "平均费用法":
                        value_config = create_average_cost_config()
                    elif value_method == "基准病种费用法":
                        value_config = create_reference_disease_config()
                    else:
                        value_config = create_standard_quota_config()
                    
                    value_calculator = DIPValueCalculator(value_config)
                    st.session_state.value_results = value_calculator.calculate_all_values(st.session_state.records)
                
                with st.spinner("正在计算医院系数..."):
                    hospital_config = create_basic_bonus_config()
                    hospital_selector = HospitalCoefficientSelector(hospital_config)
                    # 构建医院数据列表
                    hospital_set = {}
                    for r in st.session_state.records:
                        if r.hospital_code not in hospital_set:
                            hospital_set[r.hospital_code] = {
                                'hospital_code': r.hospital_code,
                                'hospital_name': r.hospital_name,
                                'hospital_level': r.hospital_level
                            }
                    hospital_data_list = list(hospital_set.values())
                    st.session_state.hospital_results = hospital_selector.batch_calculate(
                        hospital_data_list, st.session_state.records
                    )
                
                with st.spinner("正在生成辅助目录..."):
                    auxiliary_exporter = AuxiliaryDirectoryExporter()
                    st.session_state.auxiliary_results = auxiliary_exporter.classify_records(
                        st.session_state.records
                    )
                
                st.success("✅ 测算完成！")
                st.balloons()
                
            except Exception as e:
                st.error(f"测算过程中发生错误: {str(e)}")
    
    # 显示测算结果统计
    if st.session_state.value_results:
        st.subheader("📊 测算结果统计")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("病种分组数", len(st.session_state.value_results))
        
        with col2:
            total_cases = sum(r.case_count for r in st.session_state.value_results)
            st.metric("总病例数", total_cases)
        
        with col3:
            avg_value = sum(float(r.disease_value) for r in st.session_state.value_results) / len(st.session_state.value_results)
            st.metric("平均分值", f"{avg_value:.2f}")
        
        with col4:
            st.metric("医院数量", len(st.session_state.hospital_results))


def page_results():
    """结果展示页面"""
    st.header("📈 测算结果")
    
    if not st.session_state.value_results:
        st.warning("⚠️ 请先进行分组测算")
        return
    
    # 选项卡
    tab1, tab2, tab3, tab4 = st.tabs(["分组测算结果", "医院系数结果", "辅助目录结果", "统计汇总"])
    
    with tab1:
        st.subheader("分组测算结果")
        
        # 加载DIP3.0目录库
        try:
            dip_dir = pd.read_excel(str(get_data_dir() / "DIP3.0国家目录库.xlsx"))
            dip_info_map = {}
            for _, row in dip_dir.iterrows():
                dip_code = str(row.get('DIP编码', ''))
                diag_code = str(row.get('主要诊断编码', '')) if pd.notna(row.get('主要诊断编码')) else ''
                diag_name = str(row.get('主要诊断名称', '')) if pd.notna(row.get('主要诊断名称')) else ''
                proc_code = str(row.get('主要手术操作编码', '')) if pd.notna(row.get('主要手术操作编码')) else ''
                proc_name = str(row.get('主要手术操作名称', '')) if pd.notna(row.get('主要手术操作名称')) else ''
                dip_info_map[dip_code] = (diag_code, diag_name, proc_code, proc_name)
        except:
            dip_info_map = {}
        
        # 构建结果表格（直接从分组结果获取信息）
        result_data = []
        for idx, r in enumerate(st.session_state.grouping_results, 1):
            # 从病例记录中获取相关手术操作信息
            related_oprn_code = ""
            related_oprn_name = ""
            for record in st.session_state.records:
                if record.dip_disease_code == r.disease_code:
                    related_oprn_code = record.related_oprn_code
                    related_oprn_name = record.related_oprn_name
                    break
            
            result_data.append({
                '序号': idx,
                '主要诊断编码': r.main_diag_code,
                '主要诊断名称': r.main_diag_name,
                '主要手术操作编码': r.main_oprn_code if r.main_oprn_code else '',
                '主要手术操作名称': r.main_oprn_name if r.main_oprn_name else '',
                '相关手术操作编码': related_oprn_code,
                '相关手术操作名称': related_oprn_name,
                '病例数': r.case_count,
                '病种分值': f"{float(r.disease_value):.2f}",
                '药品分值': f"{float(r.drug_value):.2f}",
                '耗材分值': f"{float(r.consumable_value):.2f}",
                '平均费用': f"¥{float(r.avg_cost):,.2f}"
            })
        
        st.dataframe(pd.DataFrame(result_data), use_container_width=True, height=400)
    
    with tab2:
        st.subheader("医院系数结果")
        
        if st.session_state.hospital_results:
            hospital_data = []
            for r in st.session_state.hospital_results:
                hospital_data.append({
                    '医院代码': r.hospital_code,
                    '医院名称': r.hospital_name,
                    '医院等级': r.hospital_level,
                    '基本系数': f"{float(r.basic_coefficient):.4f}",
                    '加成系数': f"{float(r.bonus_coefficient):.4f}",
                    '最终系数': f"{float(r.final_coefficient):.4f}"
                })
            
            st.dataframe(pd.DataFrame(hospital_data), use_container_width=True, height=400)
        else:
            st.info("暂无医院系数数据")
    
    with tab3:
        st.subheader("辅助目录结果")
        
        if st.session_state.auxiliary_results:
            # 构建病例信息映射
            record_map = {}
            for r in st.session_state.records:
                record_map[r.record_id] = r
            
            # 构建分值映射
            value_map = {}
            for v in st.session_state.value_results:
                value_map[v.dip_code] = v
            
            # 构建分组结果映射
            grouping_map = {}
            for g in st.session_state.grouping_results:
                grouping_map[g.disease_code] = g
            
            aux_data = []
            for r in st.session_state.auxiliary_results:
                record = record_map.get(r.record_id)
                group_info = grouping_map.get(r.dip_code)
                
                aux_data.append({
                    '病例ID': r.record_id,
                    '主要诊断编码': group_info.main_diag_code if group_info else (record.main_diag_code if record else ''),
                    '主要诊断名称': group_info.main_diag_name if group_info else (record.main_diag_name if record else ''),
                    '主要手术操作编码': group_info.main_oprn_code if group_info and group_info.main_oprn_code else '',
                    '主要手术操作名称': group_info.main_oprn_name if group_info and group_info.main_oprn_name else '',
                    '相关手术操作编码': group_info.related_oprn_code if group_info and group_info.related_oprn_code else '',
                    '相关手术操作名称': group_info.related_oprn_name if group_info and group_info.related_oprn_name else '',
                    '辅助分型系数': f"{float(r.max_coefficient):.4f}",
                    'CCI类型': r.cci_type,
                    '疾病严重程度': r.severity_type,
                    '年龄特征': r.age_type,
                    'ICU类型': r.icu_type
                })
            
            st.dataframe(pd.DataFrame(aux_data), use_container_width=True, height=400)
        else:
            st.info("暂无辅助目录数据")
    
    with tab4:
        st.subheader("统计汇总")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### 病种分组统计")
            
            # 按病例数排序
            sorted_results = sorted(st.session_state.value_results, key=lambda x: x.case_count, reverse=True)
            
            for r in sorted_results[:10]:
                st.markdown(f"**{r.dip_code}**: {r.case_count}例, 分值{float(r.disease_value):.2f}")
        
        with col2:
            st.markdown("### 医院统计")
            
            for r in st.session_state.hospital_results:
                st.markdown(f"**{r.hospital_name}** ({r.hospital_level}): 系数{float(r.final_coefficient):.4f}")


def page_dictionary():
    """字典查看页面"""
    st.header("📚 字典查看")
    
    # 字典选择
    dict_name = st.selectbox(
        "选择字典",
        ["DIP3.0国家目录库", "低标目录", "ICD-10编码", "ICD-9-CM-3编码", "CCI合并症并发症", "疾病严重程度辅助目录"]
    )
    
    # 加载数据
    dict_file_map = {
        "DIP3.0国家目录库": str(get_data_dir() / "DIP3.0国家目录库.xlsx"),
        "低标目录": str(get_data_dir() / "低标目录(1).xlsx"),
        "ICD-10编码": str(get_data_dir() / "ICD10国临版2.0对照医保版2.0_0125.xlsx"),
        "ICD-9-CM-3编码": str(get_data_dir() / "ICD9国临版3.0对照医保版2.0_0125.xlsx"),
        "CCI合并症并发症": str(get_data_dir() / "CCI.xlsx"),
        "疾病严重程度辅助目录": str(get_data_dir() / "中重度分型诊断.xlsx")
    }
    
    try:
        df = pd.read_excel(dict_file_map[dict_name])
        
        col1, col2 = st.columns([3, 1])
        
        with col1:
            st.subheader(f"{dict_name} ({len(df)} 条记录)")
            
            # 搜索功能
            search_term = st.text_input("搜索", "")
            
            if search_term:
                # 在所有列中搜索
                mask = df.apply(lambda row: row.astype(str).str.contains(search_term, case=False).any(), axis=1)
                display_df = df[mask]
            else:
                display_df = df
            
            # 分页
            page_size = st.selectbox("每页显示", [100, 200, 500, 1000], index=0)
            total_pages = (len(display_df) + page_size - 1) // page_size
            
            if total_pages > 0:
                page = st.number_input("页码", 1, total_pages, 1)
                start_idx = (page - 1) * page_size
                end_idx = min(start_idx + page_size, len(display_df))
                
                st.dataframe(display_df.iloc[start_idx:end_idx], use_container_width=True, height=500)
                st.info(f"显示 {start_idx+1}-{end_idx} / 共 {len(display_df)} 条")
        
        with col2:
            st.subheader("统计信息")
            st.metric("总记录数", len(df))
            st.metric("列数", len(df.columns))
            
            st.markdown("**列名：**")
            for col in df.columns:
                st.markdown(f"- {col}")
    
    except Exception as e:
        st.error(f"加载字典失败: {e}")


def page_quality_control():
    """质量控制页面"""
    st.header("🔍 质量控制")
    
    if not st.session_state.records:
        st.warning("⚠️ 请先导入数据")
        return
    
    if st.button("运行质量检查", type="primary"):
        with st.spinner("正在进行质量检查..."):
            # 创建病种分组数据
            grouping_engine = DIPGroupingEngine()
            disease_groups = {}
            for record in st.session_state.records:
                group = grouping_engine.group_single_record(record)
                key = group.disease_code
                if key not in disease_groups:
                    disease_groups[key] = {
                        'disease_code': key,
                        'case_count': 0,
                        'avg_cost': 0,
                        'std_cost': 0
                    }
                disease_groups[key]['case_count'] += 1
                disease_groups[key]['avg_cost'] += float(record.total_cost)
            
            # 计算平均费用
            for key in disease_groups:
                if disease_groups[key]['case_count'] > 0:
                    disease_groups[key]['avg_cost'] /= disease_groups[key]['case_count']
            
            disease_groups_df = pd.DataFrame(disease_groups.values())
            
            # 转换records为DataFrame
            records_data = []
            for r in st.session_state.records:
                records_data.append({
                    'record_id': r.record_id,
                    'dip_disease_code': r.dip_disease_code,
                    'total_cost': float(r.total_cost),
                    'main_diag_code': r.main_diag_code,
                    'main_oprn_code': r.main_oprn_code,
                })
            records_df = pd.DataFrame(records_data)
            
            # 运行质量检查
            qc = QualityController()
            report = qc.run_all_checks(records_df, disease_groups_df)
        
        # 显示结果
        st.subheader("质量检查报告")
        st.markdown(f"**报告时间**: {report.report_time}")
        st.markdown(f"**总记录数**: {report.total_records}")
        st.markdown(f"**整体风险等级**: {report.overall_risk_level}")
        
        for result in report.check_results:
            with st.expander(f"{'✅' if result.is_passed else '❌'} {result.check_name}"):
                st.markdown(f"**风险等级**: {result.risk_level}")
                st.markdown(f"**风险病例数**: {result.risk_count}")
                st.markdown(f"**风险比例**: {result.risk_rate:.2%}")
                st.markdown(f"**详细信息**: {result.detail_info}")
                st.markdown(f"**处理建议**: {result.suggestion}")


def main():
    """主函数"""
    # 初始化
    init_session_state()
    
    # 侧边栏
    with st.sidebar:
        st.image("https://img.icons8.com/color/96/hospital.png", width=80)
        st.title("DIP3.0测算系统")
        st.markdown("---")
        
        # 导航
        page = st.radio(
            "导航菜单",
            ["📊 数据导入", "🔬 分组测算", "📈 测算结果", "📚 字典查看", "🔍 质量控制"],
            index=0
        )
        
        st.markdown("---")
        st.markdown("### 系统信息")
        st.markdown("- 版本: v2.0")
        st.markdown("- 规范: DIP3.0")
    
    # 主内容区
    if page == "📊 数据导入":
        page_data_import()
    elif page == "🔬 分组测算":
        page_grouping()
    elif page == "📈 测算结果":
        page_results()
    elif page == "📚 字典查看":
        page_dictionary()
    elif page == "🔍 质量控制":
        page_quality_control()


if __name__ == "__main__":
    main()
