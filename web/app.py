"""
DIP3.0本地目录测算系统 - Web界面
基于Streamlit构建
"""
import streamlit as st
import pandas as pd
import sys
import os
import importlib
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from decimal import Decimal, ROUND_HALF_UP
from src.models.models import MedicalRecord, DiseaseGroup, GroupType
from src.core.grouping_engine import DIPGroupingEngine
from src.utils.paths import get_data_dir
from src.core.value_calculator_selectable import (
    DIPValueCalculator, ValueCalculationConfig, ValueCalculationMethod, ValueCalculationResult,
    create_average_cost_config, create_reference_disease_config, create_standard_quota_config
)
from src.core.hospital_coefficient_selector import (
    HospitalCoefficientSelector, CoefficientCalculationConfig, CoefficientCalculationMethod,
    create_basic_bonus_config
)
from src.core.auxiliary_directory_exporter import AuxiliaryDirectoryExporter
from src.core.quality_control import QualityController
from src.core.high_low_rate_handler import HighLowRateHandler
from src.core.local_directory_generator import LocalDirectoryGenerator

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


# ============================================================
# 结算清单 → MedicalRecord 转换（兼容多套列名别名）
# ============================================================
def _resolve_col(row, *candidates):
    """按候选列名（忽略大小写与首尾空白）取首个存在的非空值；否则返回 None。"""
    cols = {str(c).strip().lower(): c for c in row.index}
    for cand in candidates:
        key = str(cand).strip().lower()
        if key in cols:
            val = row[cols[key]]
            if val is None or (isinstance(val, float) and pd.isna(val)):
                continue
            if str(val).strip() == "":
                continue
            return val
    return None


def _to_str(val):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    return str(val).strip()


def _to_decimal(val):
    s = _to_str(val)
    if s == "":
        return Decimal("0")
    try:
        return Decimal(s)
    except Exception:
        return Decimal("0")


def _to_int(val):
    s = _to_str(val)
    if s == "":
        return 0
    try:
        return int(float(s))
    except Exception:
        return 0


def _import_df_to_records(df: "pd.DataFrame"):
    """把结算清单 DataFrame 转换为 MedicalRecord 列表。

    列名识别同时支持：
      - 标准中文表头（清单流水号/医院代码/总费用/主要诊断编码…）
      - 测试数据与导出的英文/混合表头（record_id/hospital_code/医疗总费用/相关诊断编码…）
    并补读其他诊断、其他手术、年龄、ICU、出院状态等字段，供辅助分型(CCI)使用。
    """
    records = []
    for _, row in df.iterrows():
        records.append(MedicalRecord(
            record_id=_to_str(_resolve_col(row, "病案号", "清单流水号", "record_id", "结算清单流水号", "结算ID")),
            settlement_id=_to_str(_resolve_col(row, "结算ID", "settlement_id")),
            patient_id=_to_str(_resolve_col(row, "人员编号", "patient_id")),
            visit_id=_to_str(_resolve_col(row, "就诊ID", "visit_id")),
            hospital_code=_to_str(_resolve_col(row, "医院代码", "hospital_code", "定点医药机构代码")),
            hospital_name=_to_str(_resolve_col(row, "医院名称", "hospital_name")),
            hospital_level=_to_str(_resolve_col(row, "医院等级", "hospital_level")),
            gender=_to_str(_resolve_col(row, "性别", "gender")),
            birth_date=_to_str(_resolve_col(row, "出生日期", "birth_date")),
            age=_to_int(_resolve_col(row, "年龄", "age")),
            day_age=_to_int(_resolve_col(row, "年龄(天)", "天龄", "day_age")),
            birth_weight=_to_decimal(_resolve_col(row, "出生体重", "birth_weight", "新生儿出生体重")),
            main_diag_code=_to_str(_resolve_col(row, "主要诊断编码", "main_diag_code", "主要诊断代码")),
            main_diag_name=_to_str(_resolve_col(row, "主要诊断名称", "main_diag_name", "主要诊断")),
            main_oprn_code=_to_str(_resolve_col(row, "主要手术操作代码", "主要手术编码", "main_oprn_code", "主要手术操作编码")),
            main_oprn_name=_to_str(_resolve_col(row, "主要手术名称", "main_oprn_name", "主要手术操作名称")),
            related_diag_code=_to_str(_resolve_col(row, "相关诊断代码", "相关诊断编码", "related_diag_code", "其他诊断编码")),
            related_diag_name=_to_str(_resolve_col(row, "相关诊断名称", "related_diag_name", "其他诊断名称")),
            related_oprn_code=_to_str(_resolve_col(row, "相关手术操作代码", "相关手术编码", "相关手术操作编码", "related_oprn_code", "其他手术编码")),
            related_oprn_name=_to_str(_resolve_col(row, "相关手术名称", "相关手术操作名称", "related_oprn_name", "其他手术名称")),
            admission_date=_to_str(_resolve_col(row, "入院日期", "admission_date", "入院时间")),
            discharge_date=_to_str(_resolve_col(row, "出院日期", "discharge_date", "出院时间")),
            los=_to_int(_resolve_col(row, "住院天数", "los", "实际住院天数")),
            discharge_status=_to_str(_resolve_col(row, "出院状态", "discharge_status", "离院方式")),
            icu_type=_to_str(_resolve_col(row, "重症监护病房类型", "icu_type")),
            icu_hours=_to_int(_resolve_col(row, "进出重症监护室时间", "icu_hours")),
            ventilator_hours=_to_int(_resolve_col(row, "呼吸机使用时间", "ventilator_hours")),
            coma_hours=_to_int(_resolve_col(row, "昏迷时间", "coma_hours")),
            total_cost=_to_decimal(_resolve_col(row, "医疗费用总额(元)", "总费用", "医疗总费用", "total_cost", "金额合计")),
            drug_cost=_to_decimal(_resolve_col(row, "药品费用", "drug_cost")),
            material_cost=_to_decimal(_resolve_col(row, "材料费用", "material_cost")),
            consumable_cost=_to_decimal(_resolve_col(row, "耗材费用", "consumable_cost")),
            fund_pay=_to_decimal(_resolve_col(row, "基金支付总额(元)", "医保统筹基金支付", "fund_pay", "统筹支付")),
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
                    
                    # 转换为MedicalRecord对象（兼容多套列名别名，并补读其他诊断/手术）
                    st.session_state.records = _import_df_to_records(df)
                
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


def _calc_find_dip_code(dip_dir, diag_code, oprn_code):
    """从DIP3.0目录库查找匹配的DIP编码（与原闭包逻辑一致）。"""
    if dip_dir is None or getattr(dip_dir, "empty", True) or '主要诊断编码' not in dip_dir.columns:
        return (None, None, None, None, None)
    matching = dip_dir[dip_dir['主要诊断编码'] == diag_code]
    for _, row in matching.iterrows():
        dip_proc = str(row.get('主要手术操作编码', '')) if pd.notna(row.get('主要手术操作编码')) else ''
        # 内科病种（无手术操作）
        if not oprn_code and not dip_proc:
            return (str(row.get('DIP编码', '')), str(row.get('主要诊断编码', '')),
                    str(row.get('主要诊断名称', '')), dip_proc,
                    str(row.get('主要手术操作名称', '') if pd.notna(row.get('主要手术操作名称')) else ''))
        # 手术病种（有手术操作，精确匹配）
        if oprn_code and dip_proc and oprn_code == dip_proc:
            return (str(row.get('DIP编码', '')), str(row.get('主要诊断编码', '')),
                    str(row.get('主要诊断名称', '')), dip_proc,
                    str(row.get('主要手术操作名称', '') if pd.notna(row.get('主要手术操作名称')) else ''))
    return (None, None, None, None, None)


# 缓存核心引擎实例（构造约 7s，加载字典/手术类别映射），供 Web 判定综合病种子组复用，
# 保证与本地目录库导出（LocalDirectoryGenerator）口径一致。
_GEN_CACHE = None
_GEN_CACHE_MTIME = None


def _get_shared_gen() -> "LocalDirectoryGenerator":
    """懒加载并缓存核心引擎实例（含手术类别映射，用于判定综合病种子组）。

    mtime 守卫：比对 local_directory_generator.py 源文件修改时间，编辑后下次调用
    会 reload 该模块并重建实例，避免 Streamlit 热重载下持有旧 class 实例导致
    'object has no attribute' 类错误。
    """
    global _GEN_CACHE, _GEN_CACHE_MTIME
    mod = sys.modules.get(LocalDirectoryGenerator.__module__)
    src_path = getattr(mod, "__file__", None) if mod else None
    mtime = os.path.getmtime(src_path) if src_path else None

    def _build():
        g = LocalDirectoryGenerator(threshold=15)
        # 加载国家目录库：使 ①/③ 特殊组(低体重出生儿/肿瘤/结核)直出国家标准 DIP 码，
        # Web「按国家目录分组、国家格式显示」的前提。
        try:
            nd = get_data_dir() / "DIP3.0国家目录库.xlsx"
            if nd.exists():
                g.load_national_directory(str(nd))
        except Exception:
            pass
        return g

    if _GEN_CACHE is None:
        _GEN_CACHE = _build()
        _GEN_CACHE_MTIME = mtime
    elif mtime is not None and _GEN_CACHE_MTIME is not None and mtime > _GEN_CACHE_MTIME:
        # 源文件已变更：强制 reload 模块以加载最新代码，再重建实例
        reloaded = importlib.reload(mod)
        new_cls = getattr(reloaded, "LocalDirectoryGenerator")
        _GEN_CACHE = new_cls(threshold=15)
        try:
            nd = get_data_dir() / "DIP3.0国家目录库.xlsx"
            if nd.exists():
                _GEN_CACHE.load_national_directory(str(nd))
        except Exception:
            pass
        _GEN_CACHE_MTIME = mtime
    return _GEN_CACHE


def _build_core_mixed(temp_groups: dict, threshold: int, records=None):
    """按核心病种阈值拆分并归集（DIP3.0 规范）。

    达临界值(threshold)的组 -> 核心病种(CORE)，保留原成组键；
    未达临界值的组 -> 进入综合病种池，按「手术属性子组 + 主诊断 3 位类目码」折叠为
    综合病种(MIXED)，避免 1 例组各自成组（此前 Web 仅打标签却不折叠，导致阈值失效）。

    综合病种命名格式：类目名称 + 子组类型
      （保守治疗组 / 诊断性操作组 / 治疗性操作组 / 相关手术组），
      与 LocalDirectoryGenerator 导出口径一致。

    返回 (core_groups, mixed_spec, code_to_mixed)：
      core_groups   : 达阈值的 DiseaseGroup 列表（group_type 已置 CORE）
      mixed_spec    : {mixed_key: {'case_count','cost_sum','name','diag3','subtype','cat_name'}}
      code_to_mixed : {原 disease_code: mixed_key}（仅含未达阈值的码，供 value_results 一致合并）
    """
    gen = _get_shared_gen()
    # 预构建 3 位类目 -> 候选(编码,名称)，用于推导综合病种「类目名称」
    cat_candidates: dict = {}
    if records:
        for r in records:
            d3 = (r.main_diag_code or "")[:3]
            if d3:
                cat_candidates.setdefault(d3, []).append((r.main_diag_code, r.main_diag_name))

    core_groups = []
    mixed_spec: dict = {}
    code_to_mixed: dict = {}
    for g in temp_groups.values():
        # 四层（先期分组/并项规则/诊断辅助细分/基本规则）统一按地方阈值判定：
        # 达阈值 -> 核心病种；未达阈值 -> 折叠进综合病种池。
        # （不再对 ①②③ 做"恒为核心"豁免，与 LocalDirectoryGenerator.cluster_records_to_groups 口径一致。）
        if g.case_count >= threshold:
            g.group_type = GroupType.CORE
            core_groups.append(g)
        else:
            diag3 = (g.main_diag_code or "")[:3]
            subtype = gen._get_op_subtype(g.main_oprn_code)
            mk = f"MIX_{subtype}_{diag3}"
            code_to_mixed[g.disease_code] = mk
            cat_name = gen._resolve_category_name(
                diag3, cat_candidates.get(diag3, [(g.main_diag_code, g.main_diag_name)])
            )
            spec = mixed_spec.setdefault(mk, {
                "case_count": 0,
                "cost_sum": Decimal("0"),
                "name": f"{cat_name}{subtype}",
                "diag3": diag3,
                "subtype": subtype,
                "cat_name": cat_name,
            })
            spec["case_count"] += g.case_count
            # 此时 g.avg_cost 已是被均摊后的均值，加权求和还原总费用
            spec["cost_sum"] += g.avg_cost * g.case_count
    return core_groups, mixed_spec, code_to_mixed


def _merge_value_results_to_mixed(value_results, temp_groups: dict, threshold: int,
                                  value_calculator, records):
    """将未达阈值的 ValueCalculationResult 折叠为综合病种，使其与 grouping_results 一致。

    返回合并后的 value_results 列表（核心病种保留原样，未达阈值的按主诊断 3 位码归集）。
    """
    _core, mixed_spec, code_to_mixed = _build_core_mixed(temp_groups, threshold, records=records)
    if not code_to_mixed:
        return value_results
    merged: dict = {}
    kept = []
    for v in value_results:
        mk = code_to_mixed.get(v.dip_code)
        if mk is None:
            kept.append(v)
            continue
        s = merged.setdefault(mk, {
            "case_count": 0,
            "total_cost": Decimal("0"),
            "total_drug_cost": Decimal("0"),
            "total_consumable_cost": Decimal("0"),
            "value_sum": Decimal("0"),
            "drug_value_sum": Decimal("0"),
            "consumable_value_sum": Decimal("0"),
        })
        s["case_count"] += v.case_count
        s["total_cost"] += v.total_cost
        s["total_drug_cost"] += v.total_drug_cost
        s["total_consumable_cost"] += v.total_consumable_cost
        s["value_sum"] += v.disease_value * v.case_count
        s["drug_value_sum"] += v.drug_value * v.case_count
        s["consumable_value_sum"] += v.consumable_value * v.case_count
    city_avg_cost = (
        sum((r.total_cost for r in records), Decimal("0")) / len(records)
        if records else Decimal("0")
    )
    for mk, s in merged.items():
        if s["case_count"] > 0:
            s["avg_cost"] = (s["total_cost"] / s["case_count"]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            s["avg_drug_cost"] = (s["total_drug_cost"] / s["case_count"]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            s["avg_consumable_cost"] = (s["total_consumable_cost"] / s["case_count"]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            name = mixed_spec[mk]['name']
            # 病种分值 = 均值费用/全市均值×基数，按病例数加权等价于各成员加权均值
            disease_value = (s["value_sum"] / s["case_count"]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            drug_value = (s["drug_value_sum"] / s["case_count"]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            consumable_value = (s["consumable_value_sum"] / s["case_count"]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            kept.append(ValueCalculationResult(
                dip_code=mk,
                disease_name=name,
                case_count=s["case_count"],
                total_cost=s["total_cost"],
                avg_cost=s["avg_cost"],
                total_drug_cost=s["total_drug_cost"],
                avg_drug_cost=s["avg_drug_cost"],
                total_consumable_cost=s["total_consumable_cost"],
                avg_consumable_cost=s["avg_consumable_cost"],
                disease_value=disease_value,
                drug_value=drug_value,
                consumable_value=consumable_value,
                calculation_method=value_calculator.config.calculation_method.value,
                city_avg_cost=city_avg_cost,
            ))
    return kept


def _calc_run_stage():
    """按 _calc_* 状态分块推进测算（单线程，逐条分组逻辑与原实现完全一致）。"""
    ss = st.session_state
    records = ss.records
    total = len(records)
    threshold = ss.get('_calc_threshold', 15)
    value_method = ss.get('_calc_value_method', '平均费用法')

    if ss.get('_calc_stage') == 'grouping':
        temp_groups = ss.get('_calc_temp_groups', {})
        processed = ss.get('_calc_processed', 0)
        # 本地目录库四层成组引擎（先期→并项→诊断辅助细分→基本规则），供四层决策复用
        gen = _get_shared_gen()
        # 分块大小：至少 2000，或总量 1/50，保证 rerun 次数有界
        chunk = max(2000, total // 50)
        end = min(processed + chunk, total)
        for idx in range(processed, end):
            record = records[idx]
            # 四层顺序成组（先期→并项→诊断辅助细分→基本规则），得到唯一成组键 + 层次。
            # 先期分组（LBW/器官移植/呼吸循环支持）等核心病种在此即以核心病种身份成组，
            # 不再被"国家目录查表 + 主诊断-手术兜底"绕过，确保先期分组在结果中可见。
            cluster_key, layer = gen._refine_core_group_key(
                record.main_diag_code, record.main_oprn_code, record.related_oprn_code,
                record.related_diag_code,
                day_age=record.day_age, birth_weight=record.birth_weight, age=record.age,
                birth_date=record.birth_date, admission_date=record.admission_date,
            )
            # 先期分组·器官移植/呼吸循环支持：按 (主诊断 + 手术) 查国家目录，
            # 将同一手术码下混有的多种主诊断拆成多个成组键（显示行），
            # 使每行国家DIP码的类目与其真实主诊断前3位一致。
            # 注意：layer 保持"先期分组"不变（排序需要）。
            if layer == "先期分组" and (
                cluster_key.startswith("PRI|LIFESUPPORT")
                or cluster_key.startswith("PRI|TRANSPLANT")
                or cluster_key.startswith("PRI|COMBINED")
            ):
                _parts = cluster_key.split("|")
                _op = _parts[2] if len(_parts) > 2 else ""
                _diag4 = gen._extract_icd4(record.main_diag_code or "")
                if _op and _diag4:
                    if cluster_key.startswith("PRI|COMBINED"):
                        # 4966 组合组：呼吸机[≥96h] + CRRT，按 (诊断 + 双手术) 查国家目录
                        _ndip = gen._nat_dip_for_combined(
                            _diag4, gen._priority_combined_966_vent, gen._priority_combined_966_crrt)
                    else:
                        _ndip = gen._nat_dip_for_diag_oprn(_diag4, _op)
                    if _ndip:
                        cluster_key = _ndip  # 按(诊断+手术)查到的国家DIP码成组→同一手术按诊断拆多行
            disease_code = cluster_key
            disease_name = record.main_diag_name
            main_diag_code = record.main_diag_code
            main_oprn_code = record.main_oprn_code
            main_oprn_name = record.main_oprn_name
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
                    avg_cost=record.total_cost,
                    grouping_layer=layer,
                )
            record.dip_disease_code = disease_code
            record.dip_disease_name = disease_name
        ss._calc_temp_groups = temp_groups
        ss._calc_processed = end
        if end >= total:
            for group in temp_groups.values():
                if group.case_count > 0:
                    group.avg_cost = group.avg_cost / group.case_count
            # ===== 按国家目录库对齐 DIP 编码 =====
            # ①/③ 特殊组在生成器已加载国家目录后直出国家标准 DIP 码(如 P07-01/T21.200→5025/
            #   Z51.1-19/A15-A16-00)，直接采用；②/④ 按 主要诊断+主要手术 查国家目录；
            # 先期分组·器官移植/呼吸循环支持 国家 DIP 以手术码为键，单独按手术反查。
            gen = _get_shared_gen()
            cluster_to_national = {}
            group_display = {}
            for g in temp_groups.values():
                orig = g.disease_code
                ndip = ""
                matched = False
                if orig in getattr(gen, '_nat_dip_codes', set()):
                    ndip = orig          # ①/③ 已直出国家标准 DIP 码
                    matched = True
                elif (orig.startswith("PRI|TRANSPLANT") or orig.startswith("PRI|LIFESUPPORT")
                      or orig.startswith("PRI|COMBINED")):
                    # 先期分组已在成组循环中按 (主诊断+手术) 查国家目录并拆行；
                    # 残留未匹配到的 PRI| 键保持原样（诚实标记未匹配），
                    # 不再按手术反查注入错误类目(如 A41.9)。
                    ndip = ""
                    matched = False
                else:
                    # ②/④ 基本规则/并项规则：按 诊断(4位)+手术 查国家目录
                    diag4 = gen._extract_icd4(g.main_diag_code)
                    ndip = gen._nat_dip_for_diag_oprn(diag4, g.main_oprn_code)
                    matched = bool(ndip)
                if not ndip:
                    ndip = orig  # 国家目录未命中，回退本地成组键（保证不丢组）
                g.disease_code = ndip
                cluster_to_national[orig] = ndip
                nat_row = gen._nat_rows_by_dip.get(ndip, {})
                if matched and nat_row:
                    disp = (
                        str(nat_row.get('主要诊断编码', g.main_diag_code)),
                        str(nat_row.get('主要诊断名称', g.main_diag_name)),
                        str(nat_row.get('主要手术操作编码', g.main_oprn_code) or ''),
                        str(nat_row.get('主要手术操作名称', g.main_oprn_name) or ''),
                        str(nat_row.get('相关手术操作编码', g.related_oprn_code) or ''),
                        str(nat_row.get('相关手术操作名称', g.related_oprn_name) or ''),
                    )
                else:
                    disp = (g.main_diag_code, g.main_diag_name, g.main_oprn_code or '',
                            g.main_oprn_name or '', g.related_oprn_code or '', g.related_oprn_name or '')
                group_display[ndip] = (disp, g.grouping_layer, matched)
            # 成员记录按国家 DIP 码归集（下游 value/hospital/aux 以 record.dip_disease_code 为键，保持一致）
            for r in records:
                if r.dip_disease_code in cluster_to_national:
                    r.dip_disease_code = cluster_to_national[r.dip_disease_code]
            # 按阈值拆分核心/综合病种：未达阈值的组折叠为综合病种（单独成区显示，见 tab1）
            core_groups, mixed_spec, _ = _build_core_mixed(temp_groups, threshold, records=records)
            # ===== 基层病种遴选（名录+本地校验，与 CLI 主流程 select_grassroot_groups 同口径）=====
            # ① 名录初判：命中《分组方案》基层病种 sheet 的核心组为候选（引擎按 诊断+手术 判定，
            #    手术为空=仅保守治疗组）；② 成员重建：Web 批量成组不落 member_records，
            #    按国家 DIP 编码归集 hospital_level/total_cost（供基层占比与组内 CV 计算）；
            # ③ 统一走生成器 select_grassroot_groups：核心病种 + 基层占比≥50% + 组内 CV≤0.7。
            _members_by_code = {}
            for _r in records:
                _members_by_code.setdefault(_r.dip_disease_code, []).append({
                    'hospital_level': _r.hospital_level or '',
                    'total_cost': _r.total_cost,
                })
            _core_dict = {}
            for _g in core_groups:
                _mems = _members_by_code.get(_g.disease_code, [])
                _prev = _core_dict.get(_g.disease_code)
                if _prev is not None:
                    # 不同本地成组键映射到同一国家 DIP 编码（罕见）：合并成员，避免成员丢失
                    _prev.member_records = (_prev.member_records or []) + _mems
                    continue
                _g.member_records = _mems
                _eng = getattr(gen, '_nat_engine', None)
                _g.is_grassroot = bool(
                    _eng and _eng.is_grassroot(_g.main_diag_code, _g.main_oprn_code)
                )
                _core_dict[_g.disease_code] = _g
            if getattr(gen, 'enable_grassroot', True):
                try:
                    gen.select_grassroot_groups(_core_dict)
                except Exception as _ge:  # noqa: BLE001
                    print(f"警告: 基层病种遴选失败: {_ge}")
                # 同编码被合并的重复组，遴选结果同步回原对象
                for _g in core_groups:
                    _kept = _core_dict.get(_g.disease_code)
                    if _kept is not None and _kept is not _g:
                        _g.is_grassroot = _kept.is_grassroot
            grouping_results = list(core_groups)
            for mk, spec in mixed_spec.items():
                avg = (spec["cost_sum"] / spec["case_count"]) if spec["case_count"] else Decimal("0")
                grouping_results.append(DiseaseGroup(
                    disease_code=mk,
                    disease_name=spec["name"],
                    main_diag_code=spec["diag3"],
                    main_diag_name=spec["name"],
                    main_oprn_code="",
                    main_oprn_name="",
                    related_oprn_code="",
                    related_oprn_name="",
                    group_type=GroupType.MIXED,
                    case_count=spec["case_count"],
                    avg_cost=avg,
                    mixed_subtype=spec["subtype"],
                    grouping_layer="综合病种",
                ))
            # 按四层顺序排序：先期分组→并项规则→诊断辅助细分→基本规则→综合病种
            grouping_results.sort(key=LocalDirectoryGenerator._layer_sort_key)
            ss.grouping_results = grouping_results
            ss._calc_group_display = group_display
            ss._calc_stage = 'done_batch'
        return

    if ss.get('_calc_stage') == 'done_batch':
        with st.spinner("正在计算病种分值、医院系数与辅助目录…"):
            if value_method == "平均费用法":
                value_config = create_average_cost_config()
            elif value_method == "基准病种费用法":
                value_config = create_reference_disease_config()
            else:
                value_config = create_standard_quota_config()
            value_calculator = DIPValueCalculator(value_config)
            ss.value_results = value_calculator.calculate_all_values(records)

            # 与 grouping_results 保持一致：将未达阈值的病种折叠为综合病种，
            # 否则「病种分组数」统计与 tab1 表格会出现 1 例组（阈值失效）。
            ss.value_results = _merge_value_results_to_mixed(
                ss.value_results, ss._calc_temp_groups, threshold, value_calculator, records
            )

            hospital_config = create_basic_bonus_config()
            hospital_selector = HospitalCoefficientSelector(hospital_config)
            hospital_set = {}
            for r in records:
                if r.hospital_code not in hospital_set:
                    hospital_set[r.hospital_code] = {
                        'hospital_code': r.hospital_code,
                        'hospital_name': r.hospital_name,
                        'hospital_level': r.hospital_level
                    }
            hospital_data_list = list(hospital_set.values())
            ss.hospital_results = hospital_selector.batch_calculate(hospital_data_list, records)

            # 兜底：强制重新加载磁盘最新版 exporter 模块，避免 Streamlit 自动重载只 rerun
            # 入口脚本、未重新 import 子模块，导致进程缓存旧版（无 core_disease_codes 参数）而崩溃。
            import src.core.auxiliary_directory as _auxdir_mod
            importlib.reload(_auxdir_mod)
            import src.core.auxiliary_directory_exporter as _aux_mod
            importlib.reload(_aux_mod)
            from src.core.auxiliary_directory_exporter import AuxiliaryDirectoryExporter

            auxiliary_exporter = AuxiliaryDirectoryExporter()
            # 辅助分型仅对核心病种（达地方阈值）测算：先把本地未达阈值的
            # 综合病种记录剔除，避免"核心病种阈值=15 但辅助目录里仍有 2 例病种"的不合理现象。
            core_disease_codes = {
                r.disease_code for r in st.session_state.grouping_results
                if getattr(r, "group_type", None) == GroupType.CORE
            }
            ss.auxiliary_results = auxiliary_exporter.classify_records(
                records, core_disease_codes=core_disease_codes)
        for k in ('_calc_stage', '_calc_temp_groups', '_calc_dip_dir', '_calc_processed',
                  '_calc_threshold', '_calc_value_method', '_calc_hospital_method',
                  '_calc_group_display'):
            ss.pop(k, None)
        ss._calc_running = False
        return


def _render_calc_progress():
    """测算进行中：渲染进度条并推进一阶段。"""
    ss = st.session_state
    total = len(ss.records)
    processed = ss.get('_calc_processed', 0)
    stage = ss.get('_calc_stage')
    if stage == 'grouping':
        pct = (processed / total) if total else 1.0
        st.info(f"⏳ ① 成组聚类中：{processed}/{total} 条（{int(pct * 100)}%）")
    else:
        processed = total
        st.info("⏳ ② 计算病种分值 / 医院系数 / 辅助目录中…")
    st.progress((processed / total) if total else 1.0)
    try:
        _calc_run_stage()
    except Exception as e:
        for k in ('_calc_running', '_calc_stage', '_calc_temp_groups', '_calc_dip_dir', '_calc_processed',
                  '_calc_group_display'):
            ss.pop(k, None)
        st.error(f"测算过程中发生错误: {str(e)}")
        return
    if not ss.get('_calc_running'):
        st.success("✅ 测算完成！")
        st.balloons()
        _render_grouping_stats()
    else:
        st.rerun()


def _render_grouping_stats():
    """测算结果统计卡片（与原页面一致）。"""
    if st.session_state.value_results:
        st.subheader("📊 测算结果统计")
        grp = st.session_state.get("grouping_results", [])
        core_n = sum(1 for g in grp if g.group_type == GroupType.CORE)
        mixed_n = sum(1 for g in grp if g.group_type == GroupType.MIXED)
        grassroot_n = sum(1 for g in grp if getattr(g, 'is_grassroot', False))
        grassroot_cases = sum(
            g.case_count for g in grp if getattr(g, 'is_grassroot', False))
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("核心病种数", core_n)
        with col2:
            st.metric("综合病种数", mixed_n)
        with col3:
            st.metric("基层病种数", grassroot_n)
        with col4:
            total_cases = sum(r.case_count for r in st.session_state.value_results)
            st.metric("总病例数", total_cases)
        with col5:
            st.metric("医院数量", len(st.session_state.hospital_results))
        st.caption(
            f"阈值={st.session_state.get('_calc_threshold', 15)}：达阈值形成核心病种，"
            f"未达阈值按主诊断 3 位码折叠为综合病种（共 {core_n + mixed_n} 个病种组）。"
            + (f"基层病种 {grassroot_n} 个（覆盖 {grassroot_cases} 例，名录候选+基层占比≥50%+CV≤0.7 遴选，不设医疗机构调节系数）。"
               if grassroot_n else "")
        )


def page_grouping():
    """分组测算页面"""
    st.header("🔬 分组测算")
    
    if not st.session_state.records:
        st.warning("⚠️ 请先导入数据")
        return

    # 测算进行中：显示进度条并分块推进（单线程，保证测算逻辑与结果不变）
    if st.session_state.get('_calc_running'):
        _render_calc_progress()
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
            ss = st.session_state
            # 预热核心引擎（含手术类别映射，约 7s，仅首次；用于判定综合病种子组）
            with st.spinner("正在加载分组引擎…"):
                _get_shared_gen()
            ss._calc_running = True
            ss._calc_processed = 0
            ss._calc_temp_groups = {}
            ss._calc_threshold = threshold
            ss._calc_value_method = value_method
            ss._calc_hospital_method = hospital_method
            try:
                ss._calc_dip_dir = pd.read_excel(str(get_data_dir() / "DIP3.0国家目录库.xlsx"))
            except Exception:
                ss._calc_dip_dir = pd.DataFrame()
            ss._calc_stage = 'grouping'
            st.rerun()
    
    # 显示测算结果统计
    _render_grouping_stats()


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
        group_display = st.session_state.get('_calc_group_display', {})
        # 病种分值/药品分值/耗材分值由 value_results 计算（按成组键 dip_code 关联）
        value_map = {v.dip_code: v for v in st.session_state.value_results}

        core_rows, mixed_rows = [], []
        for idx, r in enumerate(st.session_state.grouping_results, 1):
            vrec = value_map.get(r.disease_code)
            disease_value = float(vrec.disease_value) if vrec else 0.0
            drug_value = float(vrec.drug_value) if vrec else 0.0
            consumable_value = float(vrec.consumable_value) if vrec else 0.0
            layer = getattr(r, "grouping_layer", "") or (
                "综合病种" if r.group_type == GroupType.MIXED else "")

            if layer == "综合病种":
                # 综合病种单独成区（本地未达阈值折叠，非国家目录核心病种）
                mixed_rows.append({
                    '序号': idx,
                    '分组类型': '综合病种',
                    '主要诊断编码': r.main_diag_code,
                    '主要诊断名称': r.main_diag_name,
                    '病例数': r.case_count,
                    '病种分值': f"{disease_value:.2f}",
                    '药品分值': f"{drug_value:.2f}",
                    '耗材分值': f"{consumable_value:.2f}",
                    '平均费用': f"¥{float(r.avg_cost):,.2f}"
                })
                continue

            # 核心病种：按国家目录库四层成组，国家格式显示（国家DIP编码 + 标准诊断/手术）
            disp = group_display.get(r.disease_code)
            if disp:
                (diag_code, diag_name, oprn_code, oprn_name,
                 rel_oprn_code, rel_oprn_name), dlayer, matched = disp
            else:
                diag_code, diag_name = r.main_diag_code, r.main_diag_name
                oprn_code, oprn_name = r.main_oprn_code or '', r.main_oprn_name or ''
                rel_oprn_code, rel_oprn_name = r.related_oprn_code or '', r.related_oprn_name or ''
                dlayer = layer
            core_rows.append({
                '序号': idx,
                '国家DIP编码': r.disease_code,
                '分组层次': dlayer,
                '基层病种': '是' if getattr(r, 'is_grassroot', False) else '',
                '主要诊断编码': diag_code,
                '主要诊断名称': diag_name,
                '主要手术操作编码': oprn_code,
                '主要手术操作名称': oprn_name,
                '相关手术操作编码': rel_oprn_code,
                '相关手术操作名称': rel_oprn_name,
                '病例数': r.case_count,
                '病种分值': f"{disease_value:.2f}",
                '药品分值': f"{drug_value:.2f}",
                '耗材分值': f"{consumable_value:.2f}",
                '平均费用': f"¥{float(r.avg_cost):,.2f}"
            })

        if core_rows:
            st.markdown("**核心病种（按国家目录库四层成组）**")
            st.dataframe(pd.DataFrame(core_rows), use_container_width=True, height=400)
        if mixed_rows:
            st.markdown("**综合病种（本地未达阈值折叠，单独成区）**")
            st.dataframe(pd.DataFrame(mixed_rows), use_container_width=True, height=200)
    
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

        aux_subs = st.session_state.auxiliary_results  # List[AuxiliarySubgroup] 子组级
        if aux_subs:
            st.info(
                "辅助分型发生在【核心病种聚类成组之后】，对组内费用偏高的病例，结合 CCI / 疾病严重程度 / "
                "年龄 / 监护病房 等多维度『再次聚类』成子型组（子组级，不再逐病例）。\n"
                "触发条件（DIP3.0 §5.2 三条）：①病种病例数充分；②某分型评估病例数充分；"
                "③组内费用变异系数偏大（CV≥0.7）且经某维度分型后组内费用 CV 下降≥20%（明显差异）才测算；"
                "所有维度均未达标则该病种不产生任何子组（视为同质）。\n"
                "维度竞争：多个达标维度中取『触发系数(mj/M)最高』者作为实际应用的聚类维度（标记为『竞争胜出维度』）。\n"
                "子型系数：CCI 查表固定系数；其余维度 = 子组均费 / 病种均费 (mj/M)。"
            )

            # 按分型维度筛选展示
            dim_options = ["全部维度"] + sorted({s.dimension for s in aux_subs})
            chosen_dim = st.radio(
                "按分型维度筛选：", dim_options, index=0, horizontal=True, key="aux_dim_filter"
            )
            rows = [
                s.to_dict() for s in aux_subs
                if chosen_dim == "全部维度" or s.dimension == chosen_dim
            ]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, height=400)
            st.caption(
                f"共 {len(aux_subs)} 个辅助分型子组"
                + (f"，当前筛选显示 {len(rows)} 个。" if chosen_dim != "全部维度" else "。")
            )
        else:
            st.info("暂无辅助目录数据（无核心病种达到『明显差异』闸门，或尚未测算）。")
    
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
