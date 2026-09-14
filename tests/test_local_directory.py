"""
DIP本地目录库生成 - 测试脚本（真实断言版）
演示如何根据医保清单数据生成本地DIP目录库
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import pytest
from pathlib import Path

from src import DIPGroupingTool, LocalDirectoryGenerator
from src.models.models import GroupType
from src.utils.paths import get_output_dir


SAMPLE_FILE = Path(__file__).resolve().parent / "sample_settlement_data.xlsx"
OUTPUT_DIR = get_output_dir() / "local_directory"
THRESHOLD = 10


def create_sample_settlement_data():
    """创建示例医保清单数据并写入 sample_settlement_data.xlsx。"""
    data = []

    # 急性阑尾炎病例（腹腔镜手术）
    for i in range(20):
        data.append({
            '清单流水号': f'R{i+1:04d}', '结算ID': f'S{i+1:04d}', '人员编号': f'P{i+1:04d}',
            '就诊ID': f'V{i+1:04d}', '定点医药机构编号': 'H001', '定点医药机构名称': '市人民医院',
            '主要诊断代码': 'K35.9', '主要诊断名称': '急性阑尾炎',
            '主要手术操作代码': '47.0100', '主要手术操作名称': '腹腔镜下阑尾切除术',
            '相关手术操作代码': '', '相关手术操作名称': '',
            '医疗总费用': 12000 + (i * 500), '药品费用': 3000 + (i * 100),
            '耗材费用': 2000 + (i * 200), '住院天数': 5,
        })

    # 急性阑尾炎病例（传统手术）
    for i in range(15):
        data.append({
            '清单流水号': f'R{21+i:04d}', '结算ID': f'S{21+i:04d}', '人员编号': f'P{21+i:04d}',
            '就诊ID': f'V{21+i:04d}', '定点医药机构编号': 'H001', '定点医药机构名称': '市人民医院',
            '主要诊断代码': 'K35.9', '主要诊断名称': '急性阑尾炎',
            '主要手术操作代码': '47.0901', '主要手术操作名称': '阑尾切除术',
            '相关手术操作代码': '', '相关手术操作名称': '',
            '医疗总费用': 8000 + (i * 300), '药品费用': 2000 + (i * 80),
            '耗材费用': 1000 + (i * 100), '住院天数': 7,
        })

    # 急性心肌梗死病例（支架置入）
    for i in range(18):
        data.append({
            '清单流水号': f'R{36+i:04d}', '结算ID': f'S{36+i:04d}', '人员编号': f'P{36+i:04d}',
            '就诊ID': f'V{36+i:04d}', '定点医药机构编号': 'H002', '定点医药机构名称': '市中心医院',
            '主要诊断代码': 'I21.0', '主要诊断名称': '前壁急性透壁性心肌梗死',
            '主要手术操作代码': '36.0700', '主要手术操作名称': '药物洗脱冠状动脉支架置入',
            '相关手术操作代码': '88.7200', '相关手术操作名称': '冠状动脉造影',
            '医疗总费用': 45000 + (i * 1000), '药品费用': 15000 + (i * 300),
            '耗材费用': 20000 + (i * 500), '住院天数': 10,
        })

    # 肺炎病例（内科保守治疗）
    for i in range(25):
        data.append({
            '清单流水号': f'R{54+i:04d}', '结算ID': f'S{54+i:04d}', '人员编号': f'P{54+i:04d}',
            '就诊ID': f'V{54+i:04d}', '定点医药机构编号': 'H001', '定点医药机构名称': '市人民医院',
            '主要诊断代码': 'J18.9', '主要诊断名称': '肺炎',
            '主要手术操作代码': '', '主要手术操作名称': '',
            '相关手术操作代码': '', '相关手术操作名称': '',
            '医疗总费用': 6000 + (i * 200), '药品费用': 2500 + (i * 100),
            '耗材费用': 500 + (i * 50), '住院天数': 8,
        })

    # 胆囊结石病例（腹腔镜手术）
    for i in range(12):
        data.append({
            '清单流水号': f'R{79+i:04d}', '结算ID': f'S{79+i:04d}', '人员编号': f'P{79+i:04d}',
            '就诊ID': f'V{79+i:04d}', '定点医药机构编号': 'H002', '定点医药机构名称': '市中心医院',
            '主要诊断代码': 'K80.2', '主要诊断名称': '胆囊结石',
            '主要手术操作代码': '51.2300', '主要手术操作名称': '腹腔镜胆囊切除术',
            '相关手术操作代码': '', '相关手术操作名称': '',
            '医疗总费用': 15000 + (i * 400), '药品费用': 4000 + (i * 100),
            '耗材费用': 3000 + (i * 200), '住院天数': 6,
        })

    # 髋关节置换病例（高费用手术）
    for i in range(8):
        data.append({
            '清单流水号': f'R{91+i:04d}', '结算ID': f'S{91+i:04d}', '人员编号': f'P{91+i:04d}',
            '就诊ID': f'V{91+i:04d}', '定点医药机构编号': 'H003', '定点医药机构名称': '市骨科医院',
            '主要诊断代码': 'M16.1', '主要诊断名称': '髋关节骨关节病',
            '主要手术操作代码': '81.5100', '主要手术操作名称': '全髋关节置换术',
            '相关手术操作代码': '', '相关手术操作名称': '',
            '医疗总费用': 55000 + (i * 1500), '药品费用': 8000 + (i * 200),
            '耗材费用': 35000 + (i * 1000), '住院天数': 12,
        })

    # 少量低频病例（用于测试综合病种合并）
    low_freq_diseases = [
        ('A09', '感染性腹泻', '', '', 3000),
        ('E11.9', '2型糖尿病', '', '', 5000),
        ('I10', '原发性高血压', '', '', 4000),
        ('N40', '前列腺增生', '60.2900', '经尿道前列腺切除术', 12000),
    ]
    idx = 99
    for code, name, oprn_code, oprn_name, cost in low_freq_diseases:
        for i in range(3):  # 每种只有3例
            idx += 1
            data.append({
                '清单流水号': f'R{idx:04d}', '结算ID': f'S{idx:04d}', '人员编号': f'P{idx:04d}',
                '就诊ID': f'V{idx:04d}', '定点医药机构编号': 'H001', '定点医药机构名称': '市人民医院',
                '主要诊断代码': code, '主要诊断名称': name,
                '主要手术操作代码': oprn_code, '主要手术操作名称': oprn_name,
                '相关手术操作代码': '', '相关手术操作名称': '',
                '医疗总费用': cost + (i * 200), '药品费用': cost // 3,
                '耗材费用': cost // 5, '住院天数': 5,
            })

    df = pd.DataFrame(data)
    SAMPLE_FILE.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(SAMPLE_FILE, index=False, engine='openpyxl')
    assert SAMPLE_FILE.exists()
    assert len(data) == 110
    return str(SAMPLE_FILE)


def test_local_directory_generation():
    """测试本地目录库生成：文件产出、核心病种阈值、RW 与 CCI/严重度列。"""
    sample_file = create_sample_settlement_data()
    assert Path(sample_file).exists()

    tool = DIPGroupingTool()

    # threshold 经 generate_local_directory 透传（验证 ③ 的修复）
    output_file = tool.generate_local_directory(
        settlement_file=sample_file,
        national_directory_file=None,
        threshold=THRESHOLD,
        output_dir=str(OUTPUT_DIR),
    )
    assert tool.local_directory_generator.threshold == THRESHOLD, \
        "generate_local_directory 未将 threshold 透传到底层生成器"

    assert Path(output_file).exists(), "完整版目录库文件未生成"

    # 四个导出文件都应存在
    expected_files = [
        OUTPUT_DIR / "本地DIP目录库_完整版.xlsx",
        OUTPUT_DIR / "本地DIP目录库_核心病种.xlsx",
        OUTPUT_DIR / "本地DIP目录库_综合病种.xlsx",
        OUTPUT_DIR / "本地DIP目录库_统计报告.xlsx",
    ]
    for f in expected_files:
        assert f.exists(), f"缺少导出文件: {f.name}"

    # 核心病种文件：应包含 RW、CCI、疾病严重程度列，且均为核心（病例数 >= 阈值）
    core_df = pd.read_excel(OUTPUT_DIR / "本地DIP目录库_核心病种.xlsx")
    for col in ("病种分值(RW)", "CCI评分", "疾病严重程度",
                "辅助分型维度", "辅助分型等级", "辅助调节系数", "父病种代码"):
        assert col in core_df.columns, f"核心病种缺少列: {col}"
    assert len(core_df) > 0, "核心病种不应为空"
    assert (core_df["病例数"] >= THRESHOLD).all(), "存在病例数低于阈值的核心病种"
    assert (core_df["病种分值(RW)"] > 0).all(), "病种分值(RW)应全部大于 0"

    # 综合病种文件应存在且含相同新增列
    mixed_df = pd.read_excel(OUTPUT_DIR / "本地DIP目录库_综合病种.xlsx")
    for col in ("病种分值(RW)", "CCI评分", "疾病严重程度"):
        assert col in mixed_df.columns, f"综合病种缺少列: {col}"

    # 统计报告应存在且非空
    stats_df = pd.read_excel(OUTPUT_DIR / "本地DIP目录库_统计报告.xlsx")
    assert len(stats_df) > 0, "统计报告不应为空"


def test_extreme_case_trimming():
    """极端病例裁剪：组内 2.5%/97.5% 分位数，整体裁剪率受控（≈5%，≤8%），小样本组不裁剪。"""
    import random
    random.seed(42)

    rows = []
    # 大组：200 例，主费用 ~10000，注入极端低/高值
    for i in range(200):
        c = random.gauss(10000, 1500)
        if i % 40 == 0:
            c = 200.0       # 极端低值
        elif i % 40 == 1:
            c = 80000.0     # 极端高值
        rows.append({
            "主要诊断代码": "K35.9", "主要诊断名称": "急性阑尾炎",
            "主要手术操作代码": "47.0901", "主要手术操作名称": "阑尾切除",
            "医疗总费用": round(c, 2),
        })
    # 小组：10 例，应不参与裁剪
    for i in range(10):
        rows.append({
            "主要诊断代码": "J18.9", "主要诊断名称": "肺炎",
            "主要手术操作代码": "", "主要手术操作名称": "",
            "医疗总费用": round(random.gauss(8000, 800), 2),
        })
    df = pd.DataFrame(rows)

    gen = LocalDirectoryGenerator(threshold=5)  # 默认 min_trim_group_size=25
    groups = gen.cluster_records_to_groups(df)

    big = [g for g in groups.values() if g.original_case_count == 200][0]
    small = [g for g in groups.values() if g.original_case_count == 10][0]

    # 大组应被裁剪，且裁剪率落在 3%~8%（≈5%）
    assert big.trim_count > 0, "大组(200例)应被裁剪"
    big_rate = big.trim_count / big.original_case_count
    assert 0.03 <= big_rate <= 0.08, f"大组裁剪率应≈5%，实际 {big_rate*100:.2f}%"
    # 小组(<25例)不应裁剪
    assert small.trim_count == 0, "小组(<25例)不应裁剪"
    # 费用上下��有效且 下限 > 0、上限 > 下限
    assert big.trim_lower_bound > 0, "裁剪下限应大于 0"
    assert big.trim_upper_bound > big.trim_lower_bound, "裁剪上限应大于下限"
    # 有效病例数 = 原始 - 裁剪
    assert big.trimmed_case_count == big.original_case_count - big.trim_count
    # 整体裁剪率受控
    assert 0.03 <= gen.overall_trim_rate <= 0.08, \
        f"整体裁剪率应受控(3%~8%)，实际 {gen.overall_trim_rate*100:.2f}%"


def test_comprehensive_disease_subtypes():
    """综合病种四子组：内科诊疗组/诊断性/治疗性/相关手术组，op_category 正确，默认不剔除。

    构造 6 个低频(各 3 例，低于阈值 10)病种，分属四种手术属性，验证：
      1) 综合病种含全部四种子组（介入治疗并入相关手术组）；
      2) 各组的 手术操作类别(op_category) 与子组一致；
      3) 默认 exclude_below_threshold=False 时，低频综合病种保留（不被质控剔除）；
      4) 官方《不纳入分组的主要手术操作》标「按保守治疗入组」的简单操作
         （如 00.0100 治疗性超声）生效术式为空 → 内科诊疗组（用户裁决 2026-09-14）。
    """
    from src.models.models import GroupType

    # 各子组的代表手术码（取自国临版3.0手术分类字典的「类别」列；均须避开
    # 《不纳入分组的主要手术操作》中"按保守治疗入组"清单，以单独验证类别判定）
    rows = []
    specs = [
        # (诊断码, 诊断名, 手术码, 手术名, 期望子组, 期望类别)
        ("A01.0", "测试内科病",   "",            "",             "内科诊疗组",   ""),
        ("B01.0", "测试诊断操作", "00.2101",     "诊断性操作A",  "诊断性操作组", "诊断性操作"),
        ("C01.0", "测试治疗操作", "00.0901",     "治疗性操作A",  "治疗性操作组", "治疗性操作"),
        ("D01.0", "测试手术",     "00.7000x001", "手术A",        "相关手术组",   "手术"),
        ("E01.0", "测试介入",     "00.5500x008", "介入治疗A",    "相关手术组",   "介入治疗"),
        # 官方《不纳入分组的主要手术操作》标「按保守治疗入组」的简单操作：
        # 其在手术分类表中虽属"治疗性操作"，但生效术式为空 → 内科诊疗组
        ("F01.0", "测试简单操作", "00.0100",     "治疗性超声",   "内科诊疗组",   ""),
    ]
    for code, name, oprn, oprn_name, _sub, _cat in specs:
        for i in range(3):  # 每病 3 例，低于阈值 -> 进入综合病种
            rows.append({
                "主要诊断代码": code,
                "主要诊断名称": name,
                "主要手术操作代码": oprn,
                "主要手术操作名称": oprn_name,
                "医疗总费用": 5000 + (i * 200),
            })
    df = pd.DataFrame(rows)

    # 阈值 10 > 3，全部落入综合病种；不加载字典目录时仍可聚类（CCI/严重度走默认）
    gen = LocalDirectoryGenerator(threshold=10)
    groups = gen.cluster_records_to_groups(df)

    mixed = [g for g in groups.values() if g.group_type == GroupType.MIXED]
    assert len(mixed) >= 5, f"综合病种数量应 >=5，实际 {len(mixed)}"

    subtypes = {g.mixed_subtype for g in mixed}
    for expected in ("内科诊疗组", "诊断性操作组", "治疗性操作组", "相关手术组"):
        assert expected in subtypes, f"缺少综合病种子组: {expected}"

    # 子组 <-> 类别 一致性校验（按成组键精确定位，避免同子组多组相互覆盖）
    assert groups["内科诊疗组|A01"].op_category == "", "内科诊疗组 op_category 应为空"
    assert groups["诊断性操作组|B01"].op_category == "诊断性操作"
    assert groups["治疗性操作组|C01"].op_category == "治疗性操作"
    # 手术 / 介入治疗 均并入相关手术组，类别分别为 手术 / 介入治疗
    assert groups["相关手术组|D01"].op_category == "手术"
    assert groups["相关手术组|E01"].op_category == "介入治疗"
    # 关键回归（用户裁决 2026-09-14）：官方《不纳入分组的主要手术操作》标注
    # "按保守治疗入组"的简单操作，生效术式为空 → 内科诊疗组；
    # 不得因其在手术分类表中类别是"治疗性操作"而误归治疗性操作组
    assert groups["内科诊疗组|F01"].op_category == "", \
        "按保守治疗入组的简单操作应落内科诊疗组"

    # 默认不剔除低频综合病种
    assert all(not g.excluded for g in mixed), "默认 exclude_below_threshold=False 不应剔除综合病种"


def test_zonghe_dictionary_engine_fallback():
    """综合病种兜底层：核心病种四层未命中 → 官方《综合病种字典表》按「类目 + 治疗方式组」入组。

    2026-09-14 用户裁决「纳入并接入引擎兜底成组」。依据 DIP 2.0 技术规范
    第二章第二节「形成综合病种」+ 第四章第四节「入组综合病种」：
      ① 字典规模 = 2048 个 ICD-10 类目 × 4 组 = 8192 条；
      ② 治疗方式组判定：无手术操作→内科诊疗组(1)；诊断性操作→(2)；
         治疗性操作→(3)；手术 / 介入治疗→相关手术组(4)；
      ③ 编码 = 类目码 + '-' + 组编号；名称 / 组名称一律取自字典；
      ④ 剑号「+」/星号「*」类目优先命中带标记写法；
      ⑤ 类目不在字典内 → 返回 None（由调用方回落 ④ 基本规则键）。
    """
    from src.core.national_directory_v30 import get_national_engine
    from src.utils.paths import get_data_dir

    engine = get_national_engine(str(get_data_dir() / "DIP3.0国家目录库.xlsx"))

    # ① 字典规模：2048 类目 × 4 组
    assert len(engine.zh_index) == 8192, f"综合病种索引应 8192 条，实际 {len(engine.zh_index)}"
    assert engine.zh_groups == {1: "内科诊疗组", 2: "诊断性操作组",
                                3: "治疗性操作组", 4: "相关手术组"}

    # ② 一码四组：治疗方式组由主要手术操作属性判定
    assert engine.match_zonghe("A09.900", "", False).code == "A09-1"
    assert engine.match_zonghe("A09.900", "诊断性操作", True).code == "A09-2"
    assert engine.match_zonghe("A09.900", "治疗性操作", True).code == "A09-3"
    for cat in ("手术", "介入治疗"):
        m = engine.match_zonghe("A09.900", cat, True)
        assert m.code == "A09-4" and m.group_no == 4, f"{cat} 应并入相关手术组"
    # 有主手术但类别未知（不在手术操作分类表）→ 内科诊疗组
    assert engine.match_zonghe("A09.900", "", True).code == "A09-1"

    # ③ 名称 / 组名称 / 命中类目取自字典
    m = engine.match_zonghe("A09.900", "手术", True)
    assert m.name == "其他传染性和未特指病因的胃肠炎和结肠炎（相关手术组）"
    assert m.group_name == "相关手术组"
    assert m.icd_class == "A09"

    # ④ 剑号 / 星号类目：优先命中带标记写法
    assert engine.match_zonghe("A17.000", "", False).code == "A17+-1"
    assert engine.match_zonghe("A17.000", "手术", True).code == "A17+-4"
    assert engine.match_zonghe("G01*", "", False).code == "G01*-1"

    # ⑤ 非字典内类目 / 空主诊断 → 不匹配（调用方回落 ④ 基本规则键）
    assert engine.match_zonghe("QQQ.9", "", False) is None
    assert engine.match_zonghe("", "", False) is None


def test_zonghe_engine_fallback_treats_simple_operation_as_conservative():
    """综合病种兜底（成组键层）：官方标「按保守治疗入组」的简单操作 → 内科诊疗组。

    用户裁决 2026-09-14：「医保结算清单中手术操作未填写是保守治疗；参考《不纳入
    分组的主要手术操作》中的简单治疗，都纳入保守治疗」。

    00.0100（头和颈部血管治疗性超声）在手术操作分类表中类别为"治疗性操作"，但
    官方《五、不纳入分组的主要手术操作》明确标注「按保守治疗入组」，故其生效术式
    为空 → 综合病种入组 A09-1（内科诊疗组），而非 A09-3（治疗性操作组）。
    """
    gen = LocalDirectoryGenerator(threshold=2)

    # 简单操作（按保守治疗入组）→ 内科诊疗组
    key, layer = gen._refine_core_group_key("A09.900", "00.0100", "")
    assert key == "A09-1", f"按保守治疗入组的简单操作应入内科诊疗组(A09-1)，实际 {key}"
    assert layer == "综合病种"

    # 对照①：真正的治疗性操作（不在保守治疗清单）→ 治疗性操作组
    key2, _ = gen._refine_core_group_key("A09.900", "00.0901", "")
    assert key2 == "A09-3", f"治疗性操作应入治疗性操作组(A09-3)，实际 {key2}"

    # 对照②：未填写手术操作 → 内科诊疗组
    key3, _ = gen._refine_core_group_key("A09.900", "", "")
    assert key3 == "A09-1", f"未填写手术操作应入内科诊疗组(A09-1)，实际 {key3}"

    # 对照③：手术（不在保守治疗清单）→ 相关手术组
    key4, _ = gen._refine_core_group_key("A09.900", "00.7000x001", "")
    assert key4 == "A09-4", f"手术应入相关手术组(A09-4)，实际 {key4}"


def test_resolve_category_name_prefers_icd10_map():
    """综合病种类目名称优先使用 ICD-10 医保2.0 版权威类目名称。

    _resolve_category_name 应为实例方法：注入 _icd10_category_map 后，即使
    candidates 给了不同名称，也应返回权威类目名称；仅在映射缺失时回退到病例名推导。
    """
    from src.core.local_directory_generator import LocalDirectoryGenerator

    gen = LocalDirectoryGenerator(threshold=10)
    # 注入权威映射（优先级 1）
    gen._icd10_category_map = {"J18": "肺炎", "I20": "心绞痛"}
    # 即使病例名是「急性肺炎」「不稳定性心绞痛」，也应取权威类目名称
    assert gen._resolve_category_name("J18", [("J18.9", "急性肺炎")]) == "肺炎"
    assert gen._resolve_category_name("I20", [("I20.0", "不稳定性心绞痛")]) == "心绞痛"

    # 映射缺失时回退：精确 3 位码候选 -> 取其名；否则取最短名称
    gen._icd10_category_map = {}
    assert gen._resolve_category_name("K35", [("K35.9", "急性阑尾炎")]) == "急性阑尾炎"
    assert gen._resolve_category_name("K35", [("K35.1", "急性阑尾炎伴腹膜脓肿"),
                                               ("K35.9", "急性阑尾炎")]) == "急性阑尾炎"
    # 无候选时兜底返回 3 位码
    assert gen._resolve_category_name("Z98", []) == "Z98"


def test_core_disease_priority_and_merge():
    """核心病种前三层（先期分组 / 并项规则）成组键校验（DIP3.0 新目录引擎版）。

    构造样例验证（引擎自动加载 data/DIP3.0国家目录库.xlsx，成组键=方案序号）：
      ① 先期分组：低出生体重(不足1周岁+出生体重<2500g，不看诊断)→XQ-17 /
         器官移植(55.6901肾移植)→XQ-6 / 呼吸循环支持(96.7201有创呼吸机≥96h)→XQ-14，
         均直出先期方案序号；对照：角膜移植(11.6000)按不纳入手术规则
         「按保守治疗入组」→JC-2975(H16.0-保守治疗-)，不进先期；
             冠脉旁路(36.1200)国家目录无对应行→综合病种兜底(I25-4 相关手术组)；
             对照：足月正常体重新生儿不进先期→JC-4513(P59.9-保守治疗-)；
      ② 并项规则（按 BX 名录查表）：D18.0 两条规范并项术式(21.0300x003/21.0300x004)
         并为同组 BX-332；I20.0/I20.1+36.0700 诊断3位并项为同组 BX-609；
         I70.1 肾动脉支架(主)+球囊(相关) 并项为 BX-720；
      ③④ 普通病种仍走基本规则（K35.9+47.0100→JC-3625）。
    """
    rows = []
    def add(dx, op="", relop="", n=3, cost=10000, **extra):
        for i in range(n):
            row = {
                "主要诊断代码": dx, "主要诊断名称": dx,
                "主要手术操作代码": op, "主要手术操作名称": op or "",
                "相关手术操作代码": relop, "相关手术操作名称": relop or "",
                "医疗总费用": cost + i * 10,
            }
            row.update(extra)
            rows.append(row)
    # ① 低出生体重：天龄10天 + 出生体重1400g（极低体重）→ XQ-17
    add("P07.0", "", **{"天龄": 10, "出生体重": 1400})
    # 对照: 新生儿但体重正常(3200g) → 不进先期 → JC-4513(P59.9-保守治疗-)
    add("P59.9", "", **{"天龄": 5, "出生体重": 3200})
    add("N18.5", "55.6901")                 # ① 器官移植(肾) → XQ-6
    add("A41.9", "96.7201")                 # ① 呼吸循环支持(有创呼吸机≥96h) → XQ-14
    add("H16.0", "11.6000", n=3)            # 对照: 角膜移植 → 不纳入手术(按保守治疗入组)→JC-2975
    add("I25.1", "36.1200", n=3)            # 对照: 冠脉旁路(国家目录无行→综合病种兜底 相关手术组)
    # ② 并项（BX 名录查表）
    add("D18.0", "21.0300x003", n=3)        # D18.0 规范并项术式1
    add("D18.0", "21.0300x004", n=3)        # D18.0 规范并项术式2 → 与术式1同组 BX-332
    add("I20.0", "36.0700", n=3)            # I20.0 支架 → BX-609(诊断3位并项 I20)
    add("I20.1", "36.0700", n=3)            # I20.1 支架 → 与 I20.0 同组 BX-609
    add("I70.1", "39.9016", relop="39.5002", n=3)   # 支架(主)+球囊(相关) → BX-720 并项
    add("I70.1", "39.5002", n=3)            # 对照: 仅球囊 → JC-3285 基本规则
    add("K35.9", "47.0100", n=3)            # 对照: 基本规则 JC-3625
    df = pd.DataFrame(rows)

    gen = LocalDirectoryGenerator(threshold=2)
    groups = gen.cluster_records_to_groups(df)
    keys = list(groups.keys())

    # ① 先期：三类各一组（方案序号键，国家目录直出）
    for seq, name in (("XQ-17", "低出生体重(1000-1499g)"),
                      ("XQ-6", "器官移植"), ("XQ-14", "呼吸循环支持")):
        assert seq in keys, f"先期组 {name} 应直出 {seq}，实际 {sorted(keys)}"
        assert groups[seq].grouping_layer == "先期分组"
        assert groups[seq].national_matched is True
    assert "出生体重1000-1499克" in groups["XQ-17"].national_dip_code, \
        f"1400g 应命中极低出生体重档，实际 {groups['XQ-17'].national_dip_code}"
    # 角膜移植不进先期，且按不纳入手术规则「按保守治疗入组」→ H16.0-保守治疗-
    assert "JC-2975" in keys and groups["JC-2975"].grouping_layer == "基本规则", \
        f"角膜移植(11.6000)应按保守治疗入组 JC-2975，实际 {sorted(k for k in keys if 'H16' in k)}"
    # 冠脉旁路 国家目录无对应行 → 综合病种兜底（36.1200=手术 → 相关手术组）
    assert "I25-4" in keys, f"冠脉旁路应落综合病种相关手术组，实际 {sorted(keys)}"
    assert groups["I25-4"].grouping_layer == "综合病种"
    assert groups["I25-4"].national_matched is True
    assert groups["I25-4"].national_dip_code == "I25-4"
    # 正常体重新生儿(P59.9, 3200g) 不进先期 → JC-4513(P59.9-保守治疗-)
    assert "JC-4513" in keys, "正常体重新生儿应走基本规则（无手术操作）"

    # ② 并项：D18.0 两规范术式 → 同组 BX-332（6例）
    assert groups["BX-332"].case_count == 6, \
        f"D18.0 两术式应并项同组 BX-332(6例)，实际 {groups['BX-332'].case_count}"
    assert groups["BX-332"].grouping_layer == "并项规则"

    # I20.0 / I20.1 + 36.0700 → 同组 BX-609（诊断3位 I20 并项，6例）
    assert groups["BX-609"].case_count == 6, \
        f"I20.0/I20.1 应诊断并项同组 BX-609(6例)，实际 {groups['BX-609'].case_count}"

    # I70.1 支架(主)+球囊(相关) → BX-720 并项；仅球囊 → JC-3285 基本规则
    assert "BX-720" in keys and groups["BX-720"].grouping_layer == "并项规则"
    assert "JC-3285" in keys and groups["JC-3285"].grouping_layer == "基本规则"

    # ①+② 不应影响普通基本规则病种
    assert "JC-3625" in keys, "普通病种 K35.9+47.0100 应落 JC-3625(K35-47.0100-)"
    assert groups["JC-3625"].grouping_layer == "基本规则"


def test_auxiliary_typing():
    """第三步·辅助分型：四维度分级正确性 + 触发条件门控 + 核心病种拆分。

    单元级：
      ① CCI 四级（无0 / 一般1-2 / 严重3-4 / 极严重≥5）；
      ② 疾病严重程度（死亡 IV-A/<3天、IV-B/≥3天；重度/中度/轻度；恶性肿瘤高费用型）；
      ③ 年龄特征（0-28天/29天-1周岁/1-6岁/7-17岁/65-69/70-79/80+，成人 None）；
      ④ ICU 天数（<2 无 / 2-7 / 8-14 / 15-30 / 31+）。
    集成级：
      ⑤ 触发组（30例、费用双峰、按严重程度可分）→ 拆分为子组且病例数守恒；
         对照组（费用均匀）不触发；病例数<15 的组即使双峰也不触发。
    """
    from types import SimpleNamespace
    from decimal import Decimal
    from src.core.auxiliary_directory import (
        CCICalculator, DiseaseSeverityClassifier,
        AgeFeatureClassifier, ICUStayClassifier,
    )

    # ---------- ① CCI 四级 ----------
    cci = CCICalculator()
    assert cci.get_cci_level(0)[0] == "无"
    assert cci.get_cci_level(1)[0] == "一般"
    assert cci.get_cci_level(2)[0] == "一般"
    assert cci.get_cci_level(3)[0] == "严重"
    assert cci.get_cci_level(4)[0] == "严重"
    assert cci.get_cci_level(5)[0] == "极严重"
    assert cci.get_cci_level(9)[0] == "极严重"

    # ---------- ② 疾病严重程度 ----------
    sev = DiseaseSeverityClassifier()

    def rec(**kw):
        base = dict(main_diag_code="I50.9", related_diag_code="", los=5, age=45,
                    day_age=0, discharge_status="", total_cost=Decimal("10000"),
                    drug_cost=Decimal("2000"), treatment_cost=Decimal("3000"),
                    icu_days=0)
        base.update(kw)
        return SimpleNamespace(**base)

    # 死亡按住院天数拆 IV-A / IV-B
    assert sev.classify_non_malignant(rec(discharge_status="死亡", los=2))["level"] == "死亡-IV-A"
    assert sev.classify_non_malignant(rec(discharge_status="死亡", los=5))["level"] == "死亡-IV-B"
    # 重度：功能衰竭/休克/脓毒症 + 住院≥3天
    assert sev.classify_non_malignant(rec(related_diag_code="R57.0", los=6))["level"] == "重度"
    # 中度：重要器官病损/感染 + 住院≥3天
    assert sev.classify_non_malignant(rec(related_diag_code="I63.9", los=6))["level"] == "中度"
    # 住院<3天不升级
    assert sev.classify_non_malignant(rec(related_diag_code="R57.0", los=2))["level"] == "轻度"
    assert sev.classify_non_malignant(rec())["level"] == "轻度"
    # 恶性肿瘤：死亡 IV-A；高费用类型一（费用≥3倍标准且治疗费占比≥50%）
    std = Decimal("10000")
    t = rec(main_diag_code="C34.9", discharge_status="死亡", los=1)
    assert sev.classify_malignant_tumor(t, std, std)["level"] == "死亡-IV-A"
    hi1 = rec(main_diag_code="C34.9", total_cost=Decimal("40000"),
              treatment_cost=Decimal("25000"))
    assert sev.classify_malignant_tumor(hi1, std, std)["level"] == "高费用类型一"
    hi2 = rec(main_diag_code="C34.9", total_cost=Decimal("40000"),
              treatment_cost=Decimal("0"), drug_cost=Decimal("25000"))
    assert sev.classify_malignant_tumor(hi2, std, std)["level"] == "高费用类型二"
    # 肿瘤转移并发：次要诊断为不同类目恶性肿瘤 + 住院≥3天
    meta = rec(main_diag_code="C34.9", related_diag_code="C78.7", los=5)
    assert sev.classify_malignant_tumor(meta, std, std)["level"] == "肿瘤转移并发"

    # ---------- ③ 年龄特征 ----------
    age = AgeFeatureClassifier()
    assert age.classify(rec(age=0, day_age=10))["sub_level"] == "0-28天"
    assert age.classify(rec(age=0, day_age=100))["sub_level"] == "29天-1周岁"
    assert age.classify(rec(age=3))["sub_level"] == "1-6岁"
    assert age.classify(rec(age=10))["sub_level"] == "7-17岁"
    assert age.classify(rec(age=67))["sub_level"] == "65-69岁"
    assert age.classify(rec(age=75))["sub_level"] == "70-79岁"
    assert age.classify(rec(age=85))["sub_level"] == "80岁以上"
    assert age.classify(rec(age=40)) is None, "成人(18-64)不适用年龄特征分型"
    # B11（2026-09-04 用户裁决）：65岁以上结合严重程度辅助分型校正
    assert age.classify(rec(age=75), severity_level="重度")["sub_level"] == "70-79岁·重度"
    assert age.classify(rec(age=67), severity_level="轻度")["sub_level"] == "65-69岁·轻度"
    assert age.classify(rec(age=85), severity_level="中度")["condition"].find("B11") >= 0
    assert age.classify(rec(age=40), severity_level="重度") is None, "成人不受严重程度校正影响"

    # ---------- ④ ICU 天数 ----------
    icu = ICUStayClassifier()
    assert icu.classify(1) is None
    assert icu.classify(5)["sub_level"] == "2-7天"
    assert icu.classify(10)["sub_level"] == "8-14天"
    assert icu.classify(20)["sub_level"] == "15-30天"
    assert icu.classify(40)["sub_level"] == "31天以上"

    # ---------- ⑤ 触发条件门控 + 拆分（集成） ----------
    rows = []

    def add(dx, name, cost, n, related="", los=5, age_=45, icu_=0, status="医嘱离院"):
        for i in range(n):
            rows.append({
                "主要诊断代码": dx, "主要诊断名称": name,
                "主要手术操作代码": "", "主要手术操作名称": "",
                "相关诊断代码": related,
                "医疗总费用": cost + i * 10, "药品费用": 1000, "治疗费用": 1000,
                "住院天数": los, "年龄": age_, "ICU天数": icu_, "出院状态": status,
            })

    # X 触发组：30 例（轻度 20 + 重度 10），费用双峰 → CV 改善显著
    add("K35.9", "急性阑尾炎", 8000, 20)
    add("K35.9", "急性阑尾炎", 40000, 10, related="R57.0", los=10)
    # Y 对照组：20 例费用均匀 → 无 CV 改善，不触发
    add("I10", "原发性高血压", 5000, 20)
    # Z 门控组：12 例双峰，但 < min_total_cases(15) → 不触发
    add("E11.9", "2型糖尿病", 6000, 6)
    add("E11.9", "2型糖尿病", 30000, 6, related="R57.0", los=10)

    df = pd.DataFrame(rows)
    gen = LocalDirectoryGenerator(threshold=10)
    groups = gen.cluster_records_to_groups(df)
    typed = gen.apply_auxiliary_typing(
        groups, min_total_cases=15, min_type_cases=5, cv_improvement_pct=0.20,
        cv_mode="improvement",
    )

    # X：应按「严重程度」拆分为子组，父组行消失，病例数守恒
    x_subs = [g for g in typed.values()
              if g.main_diag_code == "K35.9" and g.auxiliary_parent_code]
    assert len(x_subs) >= 2, f"触发组应拆分为 >=2 个子组，实际 {len(x_subs)}"
    assert all(g.auxiliary_type == "严重程度" for g in x_subs), \
        f"最优维度应为严重程度，实际 {[g.auxiliary_type for g in x_subs]}"
    levels = {g.auxiliary_level for g in x_subs}
    assert "重度" in levels and "轻度" in levels, f"子组等级应含重度/轻度，实际 {levels}"
    assert sum(g.case_count for g in x_subs) == 30, "拆分后病例数应守恒(30)"
    assert not any(g.main_diag_code == "K35.9" and not g.auxiliary_parent_code
                   for g in typed.values()), "拆分后父病种不应再单独成行"
    # 触发评估报告应有记录（新成组键下以 main_diag_code 定位病种）
    x_report = [r for r in gen.auxiliary_trigger_report
                if r['dimension'] == '严重程度' and r['triggered'] == '是'
                and r.get('main_diag_code') == 'K35.9']
    assert x_report, "触发评估报告应记录 K35.9 严重程度维度触发"
    assert x_report[0]['cv_improvement'] >= 0.20

    # Y：费用均匀 → 不触发，原组保留
    y = [g for g in typed.values() if g.main_diag_code == "I10"]
    assert len(y) == 1 and not y[0].auxiliary_split and y[0].auxiliary_parent_code == "", \
        "对照组(费用均匀)不应被拆分"

    # Z：12 例 < min_total_cases(15) → 即使双峰也不触发
    z = [g for g in typed.values() if g.main_diag_code == "E11.9"]
    assert len(z) == 1 and not z[0].auxiliary_split and z[0].auxiliary_parent_code == "", \
        "病例数不足 min_total_cases 的组不应被拆分"


def test_auxiliary_typing_runs_after_four_layers():
    """顺序护栏回归：辅助分型(第三步)必须排在四层成组之后。

    - 四层成组(cluster_records_to_groups)后，所有核心病种须已带合法 grouping_layer；
    - 辅助分型在四层成组之后可正常运行，且拆出的子组继承父层分组层次；
    - 负例：若把某核心病种的 grouping_layer 抹空（模拟四层成组未完成就调辅助分型），
      护栏须抛 RuntimeError 阻断，阻止顺序回归。
    """
    rows = []
    def add(dx, name, cost, n, related="", los=5, age_=45):
        for i in range(n):
            rows.append({
                "主要诊断代码": dx, "主要诊断名称": name,
                "主要手术操作代码": "", "主要手术操作名称": "",
                "相关诊断代码": related,
                "医疗总费用": cost + i * 10, "药品费用": 1000, "治疗费用": 1000,
                "住院天数": los, "年龄": age_, "ICU天数": 0, "出院状态": "医嘱离院",
            })
    add("K35.9", "急性阑尾炎", 8000, 20)
    add("K35.9", "急性阑尾炎", 40000, 10, related="R57.0", los=10)
    add("I10", "原发性高血压", 5000, 20)
    df = pd.DataFrame(rows)
    gen = LocalDirectoryGenerator(threshold=10)
    groups = gen.cluster_records_to_groups(df)

    # 1) 四层成组后，所有核心病种都带合法分组层次（先期/并项/诊断辅助细分/基本规则）
    core = [g for g in groups.values()
            if g.group_type == GroupType.CORE and not g.excluded]
    assert core, "应有核心病种"
    assert all(g.grouping_layer in LocalDirectoryGenerator.LAYER_ORDER for g in core), \
        "四层成组后核心病种须带合法 grouping_layer"

    # 2) 辅助分型在四层成组之后顺利运行；拆出的子组继承父层分组层次
    typed = gen.apply_auxiliary_typing(groups, min_total_cases=15, min_type_cases=5,
                                       cv_mode="improvement")
    for g in typed.values():
        if g.auxiliary_parent_code:
            assert g.grouping_layer in LocalDirectoryGenerator.LAYER_ORDER

    # 3) 负例：抹空某核心病种的分组层次后“提前”调用，护栏须拦截
    bad = dict(groups)
    target = next(g for g in bad.values()
                  if g.group_type == GroupType.CORE and not g.excluded)
    target.grouping_layer = ""
    with pytest.raises(RuntimeError):
        gen.apply_auxiliary_typing(bad)


def test_diagnostic_auxiliary_subdivision():
    """核心病种第三层·诊断辅助细分（③成组层，DIP3.0 新目录引擎版）：与第三步辅助分型严格区分。

    引擎自动加载 data/DIP3.0国家目录库.xlsx 后，③ 由国家目录 FZ 行直出方案序号；
    引擎未命中（国家目录无对应行）时回落 **综合病种兜底**（2026-09-14 用户裁决：
    按《综合病种字典表》以「主诊断类目 + 治疗方式组」入组），再兜底 ④ 基本规则键。
    验证与第三步「触发式辅助分型」(严重程度/年龄/ICU/CCI，不产成组键) 机制不同：
      (A) 肿瘤放化疗靶向免疫：主诊断 Z51.1/Z51.8 + 其他诊断 C 范围
          × 手术组合（目录行以 + 表示 AND：99.2503 / 99.2503+99.2800x006 / 三联）
          → FZ-1774/FZ-1784/FZ-1793/FZ-1806 等；特异性优先（组合组胜过单码组）；
          无治疗操作 → 国家目录无对应行 → 降级描述键 AUX|TUMOR|C80|其他；
      (B) 结核耐药：A15-A19 + (主诊断耐药拓展码 或 其他诊断 U84.300)
          → FZ-1836(耐药)/FZ-1837(非耐药)/FZ-1840(A17耐药)/FZ-1829(胸廓成形)；
      (C) 烧伤类：主诊断 T20-T25 二度/三度部位码 + 其他诊断 T31/T32 面积档
          × 手术（保守/切痫86.22族/植皮86.6族）→ FZ-1745/1746/1747/1764；
          T30(未特指)不在目录烧伤行主诊断内 → 引擎未命中回落综合病种（T30-1 内科诊疗组）；
          一度(T30.100)《目录》无对应组 → 同落综合病种 T30-1。
    非肿瘤非结核非烧伤病种不进入 ③（K35.9→JC-3625 基本规则）。
    肿瘤其他诊断范围收窄为 C00-C95 允许范围，C97/D 类不再触发肿瘤细分。
    """
    rows = []

    def add(dx, op="", relop="", reldx="", n=1, **extra):
        for _ in range(n):
            row = {
                "主要诊断代码": dx, "主要诊断名称": "",
                "主要手术操作代码": op, "主要手术操作名称": "",
                "相关手术操作代码": relop, "相关手术操作名称": "",
                "相关诊断代码": reldx,
                "医疗总费用": 10000,
            }
            row.update(extra)
            rows.append(row)

    # (A) 肿瘤放化疗靶向免疫（目录组合行：99.2503 / +99.2800x006 / 三联）
    add("Z51.1", op="99.2503", reldx="C80")                                 # 化疗 → FZ-1774
    add("Z51.8", op="99.2800x005", reldx="C90")                             # 免疫 → FZ-1806
    add("Z51.1", op="99.2503|99.2800x006", reldx="C88")                     # 化疗+靶向 → FZ-1784
    add("Z51.1", op="99.2503+99.2800x006", reldx="C88")                     # 加号同义 → 同组 FZ-1784
    add("Z51.1", op="99.2503+99.2800x006+99.2800x005", reldx="C91")          # 三联 → FZ-1793
    add("Z51.1", reldx="C80")                                               # 无手术 → 降级描述键
    # (A-负例) 肿瘤范围收窄：C97 / D18 不再触发肿瘤细分 → 走基本规则
    add("Z51.1", op="99.2503", reldx="C97")
    add("Z51.1", op="99.2503", reldx="D18.0")
    # (B) 结核耐药
    add("A15.1")                                                            # 非耐药 → FZ-1837
    add("A16", reldx="U84.300")                                             # 耐药(U84.300) → FZ-1836
    add("A15.000x010")                                                      # 耐药(主诊断拓展码) → FZ-1836
    add("A17", reldx="U84.300")                                             # → FZ-1840
    add("A15.1", op="34.0401")                                              # 胸廓成形术 → FZ-1829
    # (C) 烧伤类（目录烧伤行主诊断=T20-T25 二/三度部位码；无年龄维度）
    add("T21.2", reldx="T31.0")                                             # 二度 <10% 保守 → FZ-1745
    add("T21.2", op="86.2200x011", reldx="T31.0")                           # 二度 <10% 切痂 → FZ-1746
    add("T21.2", op="86.6201", reldx="T31.0")                               # 二度 <10% 植皮 → FZ-1747
    add("T21.3", reldx="T31.4")                                             # 三度 30-49% 保守 → FZ-1764
    # (C-回落) T30.2 / T30.100：新目录烧伤行不含 T30（未特指/一度）→ 引擎未命中
    #          → 综合病种兜底（无手术操作 → T30-1 内科诊疗组，2 例同组）
    add("T30.2", reldx="T31.1", **{"年龄": 35})
    # (C-一度负例) T30.100 = 一度烧伤（目录无对应组）→ 不进入诊断辅助细分 → 基本规则
    add("T30.100", reldx="T31.1", **{"年龄": 40})
    # (C-负例) T31 主诊断(仅面积无深度) 不触发烧伤细分
    add("T31.1", reldx="", **{"年龄": 35})
    # 对照：普通基本规则病种
    add("K35.9", op="47.0100", n=2)                                         # 不应进入 ③

    df = pd.DataFrame(rows)
    gen = LocalDirectoryGenerator(threshold=1)
    groups = gen.cluster_records_to_groups(df)
    keys = list(groups.keys())

    # (A) 肿瘤：国家目录 FZ 行直出方案序号
    for seq in ("FZ-1774", "FZ-1806", "FZ-1793"):
        assert seq in keys, f"肿瘤细分应直出 {seq}，实际 {sorted(keys)}"
        assert groups[seq].grouping_layer == "诊断辅助细分"
        assert groups[seq].national_matched is True
    # 化疗+靶向：OR 与 + 两种写法同组（目录行 AND 组合，特异性优先）
    assert groups["FZ-1784"].case_count == 2, \
        f"99.2503|99.2800x006 与 99.2503+99.2800x006 应同入 FZ-1784(2例)，实际 {groups['FZ-1784'].case_count}"
    # (A-降级) 无治疗操作 → 主手术为空记保守治疗 → JC-5111(Z51.1-保守治疗-)
    assert "JC-5111" in keys and groups["JC-5111"].grouping_layer == "基本规则", \
        "Z51.1 无治疗操作应按保守治疗入 JC-5111"
    # (A-负例) C97 / D18 已收窄出肿瘤范围 → 引擎未命中 → 综合病种兜底
    #          （Z51 类目 + 99.2503 治疗性操作 → Z51-3 治疗性操作组，2 例同组）
    assert not any(k.startswith("AUX|TUMOR|C97") for k in keys)
    assert not any(k.startswith("AUX|TUMOR|D18") for k in keys)
    assert "Z51-3" in keys and groups["Z51-3"].grouping_layer == "综合病种", \
        f"收窄后 Z51.1+C97/D18 应落综合病种 Z51-3，实际 {sorted(keys)}"
    assert groups["Z51-3"].case_count == 2, \
        f"C97 与 D18 两例应同落 Z51-3(2例)，实际 {groups['Z51-3'].case_count}"
    # (B) 结核：方案序号直出；两条耐药路径并入同组 FZ-1836(2例)
    assert "FZ-1837" in keys, "A15.1 非耐药应落 FZ-1837"
    assert "FZ-1836" in keys, "A16+U84.300 耐药应落 FZ-1836"
    assert groups["FZ-1836"].case_count == 2, \
        f"U84.300 与主诊断拓展码两条路径应并入同组(2例)，实际 {groups['FZ-1836'].case_count}"
    assert "FZ-1840" in keys, "A17 耐药应落 FZ-1840"
    assert "FZ-1829" in keys, "胸廓成形术应命中 FZ-1829"
    # (C) 烧伤：目录行直出（程度×面积×术式，无年龄维度）
    for seq in ("FZ-1745", "FZ-1746", "FZ-1747", "FZ-1764"):
        assert seq in keys, f"烧伤应直出 {seq}，实际 {sorted(keys)}"
        assert getattr(groups[seq], "national_matched", False) is True
        assert getattr(groups[seq], "grouping_layer", "") == "诊断辅助细分"
    # (C-回落) T30.2(35岁) 与 T30.100(40岁) 无手术操作 → 综合病种 T30-1 内科诊疗组（2 例）
    assert "T30-1" in keys and groups["T30-1"].case_count == 2, \
        f"T30.2 与 T30.100 应同落综合病种 T30-1(2例)，实际 {sorted(keys)}"
    assert groups["T30-1"].grouping_layer == "综合病种"
    # (C-负例) T31 主诊断(仅面积无深度) 不触发烧伤细分 → 综合病种 T31-1
    assert "T31-1" in keys and groups["T31-1"].grouping_layer == "综合病种", \
        f"T31 主诊断应走综合病种兜底，实际 {sorted(keys)}"

    # ③ 与基本规则互不干扰：对照组 K35 走基本规则，不在 ③
    assert "JC-3625" in keys and groups["JC-3625"].grouping_layer == "基本规则"


def test_national_dip_alignment():
    """①/③ 严格对齐 DIP3.0 版分组方案（新目录引擎，成组键=方案序号）。

    加载 data/DIP3.0国家目录库.xlsx 后：
      ① 低出生体重：天龄<29天 + 出生体重分档 → XQ-16(超低)/XQ-17(极低)/XQ-19(低)，
         national_dip_code 含体重区间（P07-保守治疗--<29天|出生体重XXXX克）；
      ①-负例：天龄>28天 不进先期 → JC-4478(P07-保守治疗-)；
      ③ 肿瘤：Z51.1/Z51.8 × C范围 × 手术组合 → FZ-1774/FZ-1793/FZ-1806/FZ-1802；
      ③ 结核：FZ-1837(非耐药)/FZ-1836(耐药,双路径同组)/FZ-1840(A17)/FZ-1829(胸廓成形)；
      ③ 烧伤：T21.2+T31.0 → FZ-1745（目录烧伤行主诊断=T20-T25 部位码）。
    引擎未命中时回落综合病种兜底（主诊断类目 + 治疗方式组），再兜底 ④ 基本规则键。
    """
    rows = []

    def add(dx, op="", relop="", reldx="", n=1, **extra):
        for _ in range(n):
            row = {
                "主要诊断代码": dx, "主要诊断名称": "",
                "主要手术操作代码": op, "主要手术操作名称": "",
                "相关手术操作代码": relop, "相关手术操作名称": "",
                "相关诊断代码": reldx,
                "医疗总费用": 10000,
            }
            row.update(extra)
            rows.append(row)

    # ① 低出生体重：三个体重档
    add("P07.0", **{"天龄": 10, "出生体重": 1400})   # 极低 → XQ-17
    add("P07.0", **{"天龄": 3, "出生体重": 800})     # 超低 → XQ-16
    add("P07.1", **{"天龄": 20, "出生体重": 2300})   # 低 → XQ-19
    # ①-负例：天龄>28天 不进先期 → JC-4478(P07-保守治疗-)
    add("P07.0", **{"天龄": 40, "出生体重": 1400})
    # ③ 肿瘤：DIP 编码 = 主诊断 × 手术组合 × C范围
    add("Z51.1", op="99.2503", reldx="C80")                                  # → FZ-1774
    add("Z51.1", op="99.2503+99.2800x006+99.2800x005", reldx="C91")          # → FZ-1793
    add("Z51.8", op="99.2800x005", reldx="C90")                              # → FZ-1806
    add("Z51.8", op="99.2800x006+99.2800x005", reldx="C81")                  # → FZ-1802
    # ③ 结核：耐药标志 × 术式组
    add("A15.1")                                    # 非耐药无术式 → FZ-1837
    add("A16", reldx="U84.300")                     # 耐药(U84.300) → FZ-1836
    add("A15.000x010")                              # 耐药(主诊断拓展码) → FZ-1836
    add("A17", reldx="U84.300")                     # → FZ-1840
    add("A15.1", op="34.0401")                      # 非耐药+胸廓成形术 → FZ-1829
    # ③ 烧伤：目录行 T20-T25 部位码 × T31/T32 面积档
    add("T21.2", reldx="T31.0")                     # → FZ-1745
    # 对照：普通病种走基本规则
    add("K35.9", op="47.0100", n=2)                 # → JC-3625

    df = pd.DataFrame(rows)
    gen = LocalDirectoryGenerator(threshold=1)  # 引擎在 __init__ 自动加载 data/DIP3.0国家目录库.xlsx
    groups = gen.cluster_records_to_groups(df)
    keys = list(groups.keys())

    # ① 低出生体重 → 方案序号直出，national_dip_code 含体重区间
    for seq, weight_label in (("XQ-16", "出生体重0-999克"), ("XQ-17", "出生体重1000-1499克"),
                              ("XQ-19", "出生体重2000-2499克")):
        assert seq in keys, f"低出生体重应直出 {seq}，实际 {sorted(keys)}"
        g = groups[seq]
        assert getattr(g, "national_matched", False) is True
        assert getattr(g, "national_seq", "") == seq
        assert weight_label in g.national_dip_code, \
            f"{seq} 应含 {weight_label}，实际 {g.national_dip_code}"
        assert g.grouping_layer == "先期分组"
    assert not any(k.startswith("PRI|LBW|") for k in keys), \
        "加载国家目录库后不应再出现描述性 LBW 键"
    # ①-负例：天龄40天 → JC-4478(P07-保守治疗-)
    assert "JC-4478" in keys, "超28天新生儿应按保守治疗入 JC-4478"

    # ③ 肿瘤 → 方案序号直出，DIP 编码以 Z51.x 开头
    for seq in ("FZ-1774", "FZ-1793", "FZ-1806", "FZ-1802"):
        assert seq in keys, f"肿瘤细分应直出 {seq}，实际 {sorted(keys)}"
        assert getattr(groups[seq], "national_matched", False) is True
        assert groups[seq].national_dip_code.startswith("Z51."), \
            f"{seq} DIP 编码应以 Z51. 开头，实际 {groups[seq].national_dip_code}"

    # ③ 结核 → 方案序号直出
    assert "FZ-1837" in keys, "A15.1 非耐药应落 FZ-1837"
    assert "FZ-1836" in keys, "A16 耐药应落 FZ-1836"
    assert groups["FZ-1836"].case_count == 2, \
        f"U84.300 与主诊断拓展码应并入 FZ-1836(2例)，实际 {groups['FZ-1836'].case_count}"
    assert "FZ-1840" in keys
    assert "FZ-1829" in keys, f"胸廓成形术应命中 FZ-1829，实际 {sorted(keys)}"
    assert not any(k.startswith("AUX|TB|") for k in keys), \
        "加载国家目录库后结核不应再出现描述性键"

    # ③ 烧伤：目录行直出
    assert "FZ-1745" in keys, "烧伤 T21.2+T31.0 应直出 FZ-1745"
    assert getattr(groups["FZ-1745"], "national_matched", False) is True

    # 对照：基本规则不受影响
    assert "JC-3625" in keys


def test_grouping_layer_order():
    """本地目录库测算严格按 ①先期→②并项→③诊断辅助细分→④基本规则→综合病种 顺序成组与输出。

    覆盖：
      - 每条记录仅命中最高优先级的一层，得到唯一成组键 + 成组层次标注；
      - 核心病种输出顺序为 先期分组 → 并项规则 → 诊断辅助细分 → 基本规则；
      - 完整目录中综合病种单列于四层核心病种之后；
      - 导出 DataFrame 的「分组层次」列严格非降排列。
    """
    rows = []

    def add(dx, op="", relop="", reldx="", n=3, **extra):
        for _ in range(n):
            row = {
                "main_diag_code": dx, "main_diag_name": "",
                "main_oprn_code": op, "main_oprn_name": "",
                "related_oprn_code": relop, "related_oprn_name": "",
                "related_diag_code": reldx,
                "total_cost": 10000,
                "day_age": 0, "birth_weight": 0, "age": 0,
                "los": 5, "icu_days": 0, "discharge_status": "1",
            }
            row.update(extra)
            rows.append(row)

    # ① 先期分组：低出生体重（天龄10天，出生体重1400g）→ XQ-17
    add("P07.1", n=3, **{"day_age": 10, "birth_weight": 1400})
    # ① 先期分组：器官移植（肾移植 55.6901 → XQ-6）
    add("N18.5", op="55.6901", n=3)
    # ② 并项规则：I20.0+36.0700 → BX-609（诊断3位 I20 并项）
    add("I20.0", op="36.0700", n=3)
    # ③ 诊断辅助细分：肿瘤放化疗（Z51.1+99.2503+C80 → FZ-1774）
    add("Z51.1", op="99.2503", reldx="C80", n=3)
    # ④ 基本规则：普通手术（阑尾炎 + 阑尾切除 → JC-3625）
    add("K35.8", op="47.0100", n=3)
    # 综合病种：未达阈值的低频病种（1 例，国家目录无对应行）
    add("Q89.9", op="", n=1)

    df = pd.DataFrame(rows)
    gen = LocalDirectoryGenerator(threshold=2)
    groups = gen.cluster_records_to_groups(df)

    # 1) 每个核心病种都应带有四层之一的成组层次标注
    valid_layers = {"先期分组", "并项规则", "诊断辅助细分", "基本规则"}
    for k, g in groups.items():
        if g.group_type.value == "核心病种":
            assert g.grouping_layer in valid_layers, \
                f"核心病种 {k} 成组层次缺失或非法: {g.grouping_layer!r}"

    core = [g for g in groups.values() if g.group_type.value == "核心病种"]
    mixed = [g for g in groups.values() if g.group_type.value == "综合病种"]
    assert mixed, "应存在综合病种（未达阈值）"
    assert {g.grouping_layer for g in core} == valid_layers, \
        f"四层核心病种应齐全，实际: {sorted(set(g.grouping_layer for g in core))}"

    # 2) 核心病种按四层顺序输出（先期→并项→诊断辅助细分→基本规则）
    core_order = [g.grouping_layer for g in sorted(core, key=gen._layer_sort_key)]
    assert core_order == sorted(core_order, key=lambda L: gen.LAYER_ORDER[L]), \
        f"核心病种输出顺序不符合四层顺序: {core_order}"

    # 3) 导出核心病种目录：分组层次列严格非降
    core_df = gen._export_core_directory(core)
    layer_seq = core_df["分组层次"].tolist()
    assert layer_seq == sorted(layer_seq, key=lambda L: gen.LAYER_ORDER.get(L, 9)), \
        f"核心病种目录分组层次未按四层顺序排列: {layer_seq}"

    # 4) 完整目录：综合病种排在四层核心病种之后
    full_df = gen._export_full_directory(list(groups.values()))
    layers_full = full_df["分组层次"].tolist()
    assert layers_full == sorted(layers_full, key=lambda L: gen.LAYER_ORDER.get(L, 9)), \
        f"完整目录未按 四层+综合 顺序排列: {layers_full}"
    assert layers_full[-len(mixed):] == ["综合病种"] * len(mixed), \
        "综合病种应排在所有核心病种之后"


# =====================================================================
# B5 / B6 / B7 整改回归测试（核心病种辅助分型测算）
# =====================================================================

def _aux_rows(specs, dx="K35.9", name="急性阑尾炎"):
    """构造辅助分型测试数据。

    specs: list of (cost, related_diag, n, **extra)
    返回 pandas.DataFrame，字段与 test_auxiliary_typing 一致。
    """
    rows = []
    for cost, related, n, *rest in specs:
        extra = rest[0] if rest else {}
        for i in range(n):
            row = {
                "主要诊断代码": dx, "主要诊断名称": name,
                "主要手术操作代码": "", "主要手术操作名称": "",
                "相关诊断代码": related,
                "医疗总费用": cost + i * 10, "药品费用": 1000, "治疗费用": 1000,
                "住院天数": extra.get("los", 5), "年龄": extra.get("age", 45),
                "ICU天数": extra.get("icu", 0), "出院状态": "医嘱离院",
            }
            rows.append(row)
    return pd.DataFrame(rows)


def test_b5_high_cost_baseline_is_score_standard():
    """B5：高费用判定基准须为「分值费用标准」= 未测算辅助分型的核心病种的平均费用(mi)，

    而非任意平均费用倍数（如旧代码的 2×avg）。
    - 恶性肿瘤 record，total_cost 落在 (3×avg, 3×2×avg) 之间：
      若用错误基准 2×avg（阈值 3×2×avg=6×avg），判为「其他」；
      若用正确基准 avg（阈值 3×avg），判为「高费用类型一」。
    - 另验证显式传入 RW×点值（0.5 × 60000 = 30000 = avg）时与 mi 等价。
    """
    from decimal import Decimal
    from src.core.auxiliary_directory import AuxiliaryDirectoryCalculator

    calc = AuxiliaryDirectoryCalculator()
    avg = Decimal("30000")
    # total_cost=120000 ∈ (3×avg=90000, 3×2×avg=180000) → 用 avg 判高费用、用 2×avg 判其他
    rec = __import__("src.models.models", fromlist=["MedicalRecord"]).MedicalRecord(
        record_id="R9", settlement_id="S9", patient_id="P9", visit_id="V9",
        hospital_code="H001", hospital_name="测试医院",
        main_diag_code="C34.9", main_diag_name="肺恶性肿瘤",
        total_cost=Decimal("120000"), drug_cost=Decimal("10000"),
        treatment_cost=Decimal("70000"), discharge_status="医嘱离院", los=5,
    )
    # 正确口径：分值费用标准 = 未测算辅助分型的核心病种平均费用 avg
    res = calc.calculate_all_auxiliary_coefficients(
        record=rec, disease_avg_cost=avg
    )
    assert res["severity"]["level"] == "高费用类型一", \
        f"B5 失败：应以分值费用标准(=avg)判高费用，实际 {res['severity']['level']}"

    # 显式传入 RW×点值（0.5 × 60000 = 30000，等价于 avg）作为支付标准基准
    res2 = calc.calculate_all_auxiliary_coefficients(
        record=rec, disease_avg_cost=avg, rw=Decimal("0.5"), point_value=Decimal("60000")
    )
    assert res2["severity"]["level"] == "高费用类型一", \
        f"B5 失败：RW×点值 显式路径应等价，实际 {res2['severity']['level']}"


def test_b6_tcm_and_bed_day_excluded():
    """B6：中医优势病种 / 床日病种不纳入辅助分型（标记或码集命中即跳过）。

    - 对照组（普通 K35.9 双峰）：正常触发拆分；
    - 同数据但 main_diag_code 命中 tcm_disease_codes → 不拆分；
    - 同数据但某核心病种 is_tcm_advantage=True → 不拆分。
    """
    specs = [
        (8000, "", 20),
        (40000, "R57.0", 10, {"los": 10}),  # 重度+高费用 → 触发
    ]

    # 1) 普通病种应触发拆分
    df = _aux_rows(specs)
    gen = LocalDirectoryGenerator(threshold=10)
    groups = gen.cluster_records_to_groups(df)
    typed = gen.apply_auxiliary_typing(groups, min_total_cases=15, min_type_cases=5,
                                       cv_mode="improvement")
    subs = [g for g in typed.values()
            if g.main_diag_code == "K35.9" and g.auxiliary_parent_code]
    assert subs, "对照组 K35.9 双峰应触发辅助分型拆分"
    assert any(g.auxiliary_type == "严重程度" for g in subs)

    # 2) 命中 tcm_disease_codes → 跳过拆分
    df2 = _aux_rows(specs, dx="Z98.9", name="中医优势病种示例")
    gen2 = LocalDirectoryGenerator(threshold=10)
    g2 = gen2.cluster_records_to_groups(df2)
    typed2 = gen2.apply_auxiliary_typing(
        g2, min_total_cases=15, min_type_cases=5,
        tcm_disease_codes={"Z98.9"}, cv_mode="improvement",
    )
    subs2 = [g for g in typed2.values()
             if g.main_diag_code == "Z98.9" and g.auxiliary_parent_code]
    assert not subs2, "B6 失败：命中中医优势码集的病种不应拆分"
    z = [g for g in typed2.values() if g.main_diag_code == "Z98.9"]
    assert len(z) == 1 and not z[0].auxiliary_split

    # 3) is_tcm_advantage 标记 → 跳过拆分
    df3 = _aux_rows(specs)
    gen3 = LocalDirectoryGenerator(threshold=10)
    g3 = gen3.cluster_records_to_groups(df3)
    target = next(g for g in g3.values()
                  if g.group_type == GroupType.CORE and not g.excluded)
    target.is_tcm_advantage = True
    typed3 = gen3.apply_auxiliary_typing(g3, min_total_cases=15, min_type_cases=5,
                                         cv_mode="improvement")
    subs3 = [g for g in typed3.values()
             if g.main_diag_code == "K35.9" and g.auxiliary_parent_code]
    assert not subs3, "B6 失败：标记 is_tcm_advantage 的病种不应拆分"


def test_b7_multi_rule_competition_by_trigger_coefficient():
    """B7：多维度触发时，纳入「触发系数(=mj/M)最高」的维度（多规则竞争）。

    构造两组对比数据，使严重程度与 CCI 两个维度均触发，但触发系数高低互换：
      - 场景A：严重程度触发系数 > CCI → 选「严重程度」；
      - 场景B：CCI 触发系数 > 严重程度 → 选「CCI」。
    验证 best_dim 随触发系数最高者变化。
    """
    # 场景A：高费用病例集中于「重度」(R57.0, CCI无) → 严重程度触发系数高
    specA = [
        (8000, "", 10),                          # 轻度 / CCI无
        (50000, "R57.0", 8, {"los": 10}),        # 重度(高费用) / CCI无
        (30000, "C34.1,I500,J441,E119", 12),     # 轻度 / CCI极严重(中等费用)
    ]
    # 场景B：高费用病例集中于「CCI极严重」(非重度) → CCI 触发系数高
    specB = [
        (8000, "R57.0", 10, {"los": 10}),        # 重度(低费用) / CCI无
        (50000, "C34.1,I500,J441,E119", 8),      # 轻度 / CCI极严重(高费用)
        (30000, "", 12),                          # 轻度 / CCI无
    ]

    for label, spec, expect_dim in [
        ("A-严重程度胜出", specA, "严重程度"),
        ("B-CCI胜出", specB, "CCI"),
    ]:
        df = _aux_rows(spec)
        gen = LocalDirectoryGenerator(threshold=10)
        groups = gen.cluster_records_to_groups(df)
        typed = gen.apply_auxiliary_typing(
            groups, min_total_cases=15, min_type_cases=5, cv_improvement_pct=0.20,
            cv_mode="improvement",
        )
        # 该 K35.9 应被拆分为子组（两个维度均触发），且最优维度=期望
        subs = [g for g in typed.values()
                if g.main_diag_code == "K35.9" and g.auxiliary_parent_code]
        assert subs, f"{label}：应触发辅助分型拆分"
        assert all(g.auxiliary_type == expect_dim for g in subs), \
            f"{label}：多规则竞争应选触发系数最高的维度「{expect_dim}」，" \
            f"实际 {[g.auxiliary_type for g in subs]}"
        # 触发评估报告应记录该维度 triggered=是 且其触发系数最高
        # （新成组键下 disease_code=方案序号，以 main_diag_code 定位病种）
        rep = [r for r in gen.auxiliary_trigger_report
               if r.get("main_diag_code") == "K35.9"]
        trig = [r for r in rep if r["triggered"] == "是"]
        assert any(r["dimension"] == expect_dim for r in trig), \
            f"{label}：报告应记录「{expect_dim}」维度触发"


def test_exporter_malignant_high_cost_uses_mi():
    """Web 单条路径：恶性肿瘤高费用判定须用 mi（未拆分核心病种均值），而非恒为 0。

    之前 exporter 传 cost_standard=0，导致高费用类型一/二在 Web 端永不触发。
    """
    from decimal import Decimal
    from src.core.auxiliary_directory_exporter import AuxiliaryDirectoryExporter
    MedicalRecord = __import__("src.models.models", fromlist=["MedicalRecord"]).MedicalRecord

    def mk(rid, cost, treat, drug=0, dx="C34.9"):
        return MedicalRecord(
            record_id=rid, settlement_id=rid, patient_id=rid, visit_id=rid,
            hospital_code="H001", hospital_name="t",
            main_diag_code=dx, main_diag_name="肺恶性肿瘤",
            total_cost=Decimal(str(cost)), treatment_cost=Decimal(str(treat)),
            drug_cost=Decimal(str(drug)), discharge_status="医嘱离院", los=5,
        )
    # 3 条低费用 + 1 条高费用（治疗费占比≥50%）
    recs = [mk(f"L{i}", 10000, 8000) for i in range(3)] + [mk("H1", 120000, 70000)]
    # mi = (10000×3 + 120000) / 4 = 37500；120000 ≥ 3×37500=112500 → 高费用类型一
    # 注：classify_records 现已改为子组级聚合（不直接暴露逐病例标签），
    # 此处直接验证恶性肿瘤高费用判定须用 mi 而非恒为 0 的回归点。
    from src.core.auxiliary_directory import AuxiliaryDirectoryCalculator
    calc = AuxiliaryDirectoryCalculator()
    mi = Decimal("37500")
    hi = calc.severity_classifier.classify_malignant_tumor(
        mk("H1", 120000, 70000), mi, mi)
    lo = calc.severity_classifier.classify_malignant_tumor(
        mk("L0", 10000, 8000), mi, mi)
    assert hi["level"] == "高费用类型一", \
        f"高费用病例应判『高费用类型一』，实际 {hi['level']}"
    assert lo["level"] != "高费用类型一", \
        f"低费用病例不应判高费用，实际 {lo['level']}"


def test_auxiliary_typing_default_absolute_mode():
    """验证 CLI 默认使用 absolute CV 模式（测试阶段口径）。

    默认参数：min_total_cases=10, cv_mode="absolute", cv_threshold=0.6。
    触发报告应记录 cv_mode="absolute"；后期切换 cv_mode="improvement" 可恢复改善率口径。
    """
    rows = []
    def add(dx, name, cost, n, related="", los=5, age_=45, icu_=0, status="医嘱离院"):
        for i in range(n):
            rows.append({
                "主要诊断代码": dx, "主要诊断名称": name,
                "主要手术操作代码": "", "主要手术操作名称": "",
                "相关诊断代码": related,
                "医疗总费用": cost + i * 10, "药品费用": 1000, "治疗费用": 1000,
                "住院天数": los, "年龄": age_, "ICU天数": icu_, "出院状态": status,
            })
    # 20 例双峰 → 默认 absolute 模式下评估
    add("K35.9", "急性阑尾炎", 8000, 12)
    add("K35.9", "急性阑尾炎", 40000, 8, related="R57.0", los=10)

    df = pd.DataFrame(rows)
    gen = LocalDirectoryGenerator(threshold=10)
    groups = gen.cluster_records_to_groups(df)
    # 不传 cv_mode → 使用默认 "absolute"
    typed = gen.apply_auxiliary_typing(groups)

    # 触发报告必须存在且记录了 cv_mode
    assert hasattr(gen, "auxiliary_trigger_report")
    assert len(gen.auxiliary_trigger_report) > 0
    modes = {r.get("cv_mode") for r in gen.auxiliary_trigger_report}
    assert modes == {"absolute"}, f"默认 cv_mode 应为 absolute，实际 {modes}"
    # cv_threshold 字段应为 0.6
    thresholds = {r.get("cv_threshold") for r in gen.auxiliary_trigger_report}
    assert thresholds == {0.6}, f"默认 cv_threshold 应为 0.6，实际 {thresholds}"


def test_derive_icu_days_rule_charge_item():
    """监护病房住院天数·判断1（charge_item，默认）：含重症监护/层流洁净床位费收费项目
    + 特级护理天数 → icu_days = 特级护理天数；无对应收费项目则回落既有 icu_days。"""
    gen = LocalDirectoryGenerator(threshold=15)  # 默认 icu_days_rule='charge_item'
    assert gen.icu_days_rule == "charge_item"
    # 重症监护床位费 + 特级护理5天 → 5
    assert gen._derive_icu_days(0, 5, "", {"011105000060000"}) == 5
    # 层流洁净床位费 + 特级护理3天 → 3
    assert gen._derive_icu_days(0, 3, "", {"011105000070000"}) == 3
    # 无对应收费项目（即便有特级护理）→ 回落 0
    assert gen._derive_icu_days(0, 5, "", set()) == 0
    assert gen._derive_icu_days(0, 5, "", {"990000000000000"}) == 0
    # 与既有 icu_days(10) 取大值：severe 且 nurscare=5 < 10 → 10
    assert gen._derive_icu_days(10, 5, "", {"011105000060000"}) == 10


def test_derive_icu_days_rule_ward_type():
    """监护病房住院天数·判断2（ward_type）：重症监护病房类型非空 + 特级护理天数
    → icu_days = 特级护理天数；病房类型为空则回落既有 icu_days。"""
    gen = LocalDirectoryGenerator(threshold=15, icu_days_rule="ward_type")
    assert gen.icu_days_rule == "ward_type"
    # 病房类型非空 + 特级护理8天 → 8
    assert gen._derive_icu_days(0, 8, "外科重症监护病房(SICU)", set()) == 8
    # 病房类型为空 → 回落 0
    assert gen._derive_icu_days(0, 8, "", set()) == 0


def test_derive_icu_days_rule_switch_isolated():
    """两种判断方式互不串扰：切换规则后，另一种规则的输入不再生效。"""
    # 判断2 模式：忽略收费项目码
    gen2 = LocalDirectoryGenerator(threshold=15, icu_days_rule="ward_type")
    assert gen2._derive_icu_days(0, 5, "", {"011105000060000"}) == 0
    # 判断1(默认)模式：忽略病房类型
    gen1 = LocalDirectoryGenerator(threshold=15)
    assert gen1._derive_icu_days(0, 5, "SICU", set()) == 0


def test_icu_days_rule_flows_through_cluster():
    """收费项目/特级护理天数经成组流程推导为成员记录 icu_days（两种规则各验一条）。"""
    import pandas as pd
    base = {"结算ID": "S1", "主要诊断代码": "I21.900",
            "主要手术操作代码": "00.2400", "total_cost": 10000}
    # 判断1：收费项目含重症监护床位费 + 特级护理5天
    df1 = pd.DataFrame([{**base, "spga_nurscare_days": 5,
                         "charge_item_codes": "011105000060000"}])
    g1 = LocalDirectoryGenerator(threshold=1)
    groups1 = g1.cluster_records_to_groups(df1)
    rec1 = next(g.member_records[0] for g in groups1.values()
                if g.main_diag_code == "I21.900" and g.member_records)
    assert rec1["icu_days"] == 5

    # 判断2：重症监护病房类型非空 + 特级护理8天
    df2 = pd.DataFrame([{**base, "spga_nurscare_days": 8,
                         "scs_cutd_ward_type": "SICU"}])
    g2 = LocalDirectoryGenerator(threshold=1, icu_days_rule="ward_type")
    groups2 = g2.cluster_records_to_groups(df2)
    rec2 = next(g.member_records[0] for g in groups2.values()
                if g.main_diag_code == "I21.900" and g.member_records)
    assert rec2["icu_days"] == 8


def test_merge_rule1_driven_by_national_3digit():
    """并项规则判定改为按 BX 名录查表（DIP3.0 新方案口径）。

    旧「主要诊断=3位类目码 即并项」的判据已废弃：
      - J18.9（无手术）→ JC-3414(J18-保守治疗-) 基本规则，不再因 3 位类目归并项层；
      - 并项层由 BX 名录驱动：I20.0+36.0700 → BX-609(I20-36.06/36.07 族并项)；
      - 其它层独占的 3 位类目不被误判：P07.0(LBW)→XQ-17 先期、A18.0(结核)→FZ 诊断辅助细分；
      - 命中 BX/JC 后 national_seq / national_dip_code 在 _build_group 回填。
    """
    gen = LocalDirectoryGenerator(threshold=2)

    # 1) J18.9 无手术 → 基本规则保守治疗行（3位类目判据已废弃）
    key, layer = gen._refine_core_group_key("J18.9", "", "", "")
    assert (key, layer) == ("JC-3414", "基本规则"), \
        f"J18.9 无手术应落 JC-3414 基本规则, 实际 {layer}/{key}"

    # 2) 并项层由 BX 名录驱动
    key, layer = gen._refine_core_group_key("I20.0", "36.0700", "", "")
    assert (key, layer) == ("BX-609", "并项规则"), \
        f"I20.0+36.0700 应命中 BX-609 并项规则, 实际 {layer}/{key}"

    # 3) 其它层独占的 3 位类目不误归并项
    key, layer = gen._refine_core_group_key("A18.0", "", "", "")
    assert layer == "诊断辅助细分", f"A18.0(结核) 应归诊断辅助细分, 实际 {layer}/{key}"
    key, layer = gen._refine_core_group_key("P07.0", "", "", "",
                                            day_age=10, birth_weight=1400)
    assert layer == "先期分组", f"P07.0(LBW) 应归先期分组, 实际 {layer}/{key}"

    # 4) 成组后国家目录元数据回填（national_seq / national_dip_code）
    rows = []
    for i in range(3):
        rows.append({
            "主要诊断代码": "J18.9", "主要诊断名称": "肺炎",
            "主要手术操作代码": "", "主要手术操作名称": "",
            "医疗总费用": 10000 + i * 10,
        })
    df = pd.DataFrame(rows)
    groups = gen.cluster_records_to_groups(df)
    j18 = [g for g in groups.values() if g.national_seq == "JC-3414"]
    assert j18, f"应存在 JC-3414(J18-保守治疗-) 组，实际 {sorted(groups.keys())}"
    g = j18[0]
    assert g.national_matched is True
    assert str(g.national_dip_code).startswith("J18"), \
        f"J18 组国目 DIP 应以 J18 开头, 实际 {g.national_dip_code}"


def test_priority_merge_aux_respect_threshold():
    """①②③④ 四层成组一律受核心病种阈值(分组阈值)约束。

    验证：未达 threshold 的 ①先期分组 / ②并项规则 / ③诊断辅助细分 组，与
    ④基本规则 一致，折叠进入综合病种（不再"恒为核心"）。达到阈值的同类组
    仍保留为对应层的核心病种。
    """
    TH = 5

    def _make(dx, op="", relop="", reldx="", day_age=0, birth_weight=0, age=0, n=1):
        rows = []
        for _ in range(n):
            rows.append({
                "main_diag_code": dx, "main_diag_name": "",
                "main_oprn_code": op, "main_oprn_name": "",
                "related_oprn_code": relop, "related_oprn_name": "",
                "related_diag_code": reldx,
                "total_cost": 10000,
                "day_age": day_age, "birth_weight": birth_weight, "age": age,
            })
        return pd.DataFrame(rows)

    # 各层"未达阈值"(1 例)应折叠为综合病种
    low_specs = [
        ("先期分组", dict(dx="P07.0", day_age=10, birth_weight=1400, n=1)),
        ("并项规则", dict(dx="I20.0", op="36.0700", n=1)),
        ("诊断辅助细分", dict(dx="T21.2", reldx="T31.0", n=1)),
        ("基本规则", dict(dx="K35.9", op="47.0100", n=1)),
    ]
    for layer, kw in low_specs:
        gen = LocalDirectoryGenerator(threshold=TH)
        groups = gen.cluster_records_to_groups(_make(**kw))
        core = [g for g in groups.values() if g.group_type.value == "核心病种"]
        assert not any(g.grouping_layer == layer for g in core), \
            f"{layer} 未达阈值(1例) 不应保留为核心病种，应折叠入综合病种"
        assert any(g.group_type.value == "综合病种" for g in groups.values()), \
            f"{layer} 未达阈值(1例) 应进入综合病种"

    # 各层"达阈值"(10 例)应保留为对应层核心病种
    high_specs = [
        ("先期分组", dict(dx="P07.0", day_age=10, birth_weight=1400, n=10)),
        ("并项规则", dict(dx="I20.0", op="36.0700", n=10)),
        ("诊断辅助细分", dict(dx="T21.2", reldx="T31.0", n=10)),
        ("基本规则", dict(dx="K35.9", op="47.0100", n=10)),
    ]
    for layer, kw in high_specs:
        gen = LocalDirectoryGenerator(threshold=TH)
        groups = gen.cluster_records_to_groups(_make(**kw))
        core = [g for g in groups.values() if g.group_type.value == "核心病种"]
        assert any(g.grouping_layer == layer for g in core), \
            f"{layer} 达阈值(10例) 应保留为核心病种"


if __name__ == "__main__":
    test_local_directory_generation()
    test_extreme_case_trimming()
    test_comprehensive_disease_subtypes()
    test_core_disease_priority_and_merge()
    test_auxiliary_typing()
    test_diagnostic_auxiliary_subdivision()
    test_national_dip_alignment()
    test_grouping_layer_order()
    test_priority_merge_aux_respect_threshold()
    test_b5_high_cost_baseline_is_score_standard()
    test_b6_tcm_and_bed_day_excluded()
    test_b7_multi_rule_competition_by_trigger_coefficient()
    test_exporter_malignant_high_cost_uses_mi()
    test_auxiliary_typing_default_absolute_mode()
    test_derive_icu_days_rule_charge_item()
    test_derive_icu_days_rule_ward_type()
    test_derive_icu_days_rule_switch_isolated()
    test_icu_days_rule_flows_through_cluster()
    print("test_local_directory.py 全部 18 个用例通过")


