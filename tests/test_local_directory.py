"""
DIP本地目录库生成 - 测试脚本（真实断言版）
演示如何根据医保清单数据生成本地DIP目录库
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from pathlib import Path

from src import DIPGroupingTool, LocalDirectoryGenerator
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
    """综合病种四子组：内科/诊断性/治疗性/相关手术组，op_category 正确，默认不剔除。

    构造 5 个低频(各 3 例，低于阈值 10)病种，分属四种手术属性，验证：
      1) 综合病种含全部四种子组（介入治疗并入相关手术组）；
      2) 各组的 手术操作类别(op_category) 与子组一致；
      3) 默认 exclude_below_threshold=False 时，低频综合病种保留（不被质控剔除）。
    """
    from src.models.models import GroupType

    # 各子组的代表手术码（取自国临版3.0手术分类字典的「类别」列）
    rows = []
    specs = [
        # (诊断码, 诊断名, 手术码, 手术名, 期望子组, 期望类别)
        ("A01.0", "测试内科病",   "",        "",            "内科诊疗组",   ""),
        ("B01.0", "测试诊断操作", "00.2100", "诊断性操作A", "诊断性操作组", "诊断性操作"),
        ("C01.0", "测试治疗操作", "00.0100", "治疗性操作A", "治疗性操作组", "治疗性操作"),
        ("D01.0", "测试手术",     "00.7000", "手术A",       "相关手术组",   "手术"),
        ("E01.0", "测试介入",     "00.5500", "介入治疗A",   "相关手术组",   "介入治疗"),
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
    assert len(mixed) >= 4, f"综合病种数量应 >=4，实际 {len(mixed)}"

    subtypes = {g.mixed_subtype for g in mixed}
    for expected in ("内科诊疗组", "诊断性操作组", "治疗性操作组", "相关手术组"):
        assert expected in subtypes, f"缺少综合病种子组: {expected}"

    # 子组 <-> 类别 一致性校验
    by_sub = {g.mixed_subtype: g for g in mixed}
    assert by_sub["内科诊疗组"].op_category == "", "内科诊疗组 op_category 应为空"
    assert by_sub["诊断性操作组"].op_category == "诊断性操作"
    assert by_sub["治疗性操作组"].op_category == "治疗性操作"
    # 手术 / 介入治疗 均并入相关手术组，类别分别为 手术 / 介入治疗
    related = [g for g in mixed if g.mixed_subtype == "相关手术组"]
    cats = {g.op_category for g in related}
    assert "手术" in cats and "介入治疗" in cats, f"相关手术组应含手术与介入治疗类别，实际 {cats}"

    # 默认不剔除低频综合病种
    assert all(not g.excluded for g in mixed), "默认 exclude_below_threshold=False 不应剔除综合病种"


def test_core_disease_priority_and_merge():
    """核心病种前三层（先期分组 / 并项规则）成组键校验。

    构造样例验证：
      ① 先期分组：低出生体重(不足1周岁+出生体重<2500g，不看诊断) /
         器官移植(55.6901肾移植) / 呼吸循环支持(96.7101呼吸机)
         各自形成 PRI| 前缀的独立组，且不误伤组织移植(角膜11.6000)/
         冠脉旁路(36.1200)；对照：足月正常体重新生儿不进先期；
      ② 并项规则：D18.0 多术式整体并项、I20.0/I20.1 诊断并项(3位码)、
         I70.1 肾动脉支架+球囊联合手术并项，均合并为单一组；
      ③ 普通病种仍走基本规则键。
    """
    rows = []
    def add(dx, op="", n=3, cost=10000, **extra):
        for i in range(n):
            row = {
                "主要诊断代码": dx, "主要诊断名称": dx,
                "主要手术操作代码": op, "主要手术操作名称": op or "",
                "医疗总费用": cost + i * 10,
            }
            row.update(extra)
            rows.append(row)
    # ① 低出生体重：天龄10天 + 出生体重1400g（极低体重）→ PRI|LBW
    add("P07.0", "", **{"天龄": 10, "出生体重": 1400})
    # 对照: 新生儿但体重正常(3200g) → 不进先期
    add("P59.9", "", **{"天龄": 5, "出生体重": 3200})
    add("N18.5", "55.6901")                 # ① 器官移植(肾)
    add("A41.9", "96.7101")                 # ① 呼吸循环支持(呼吸机)
    add("H16.0", "11.6000", n=3)            # 对照: 角膜移植(组织移植, 非先期)
    add("I25.1", "36.1200", n=3)            # 对照: 冠脉旁路(非先期, 非并项族)
    # ② 并项
    add("D18.0", "21.0300x003", n=3)        # D18.0 血管瘤术式1
    add("D18.0", "21.3104", n=3)            # D18.0 血管瘤术式2 -> 应与上并项
    add("I20.0", "36.0600", n=3)            # I20.0 心绞痛
    add("I20.1", "36.0600", n=3)            # I20.1 心绞痛 -> 应与 I20.0 并项
    add("I70.1", "39.9016", n=3)            # 肾动脉支架
    add("I70.1", "39.5002", n=3)            # 肾动脉球囊 -> 应与支架并项
    add("K35.9", "47.0100", n=3)            # 对照: 基本规则
    df = pd.DataFrame(rows)

    gen = LocalDirectoryGenerator(threshold=2)
    groups = gen.cluster_records_to_groups(df)
    keys = list(groups.keys())

    # ① 先期：三类各一组
    pri = [k for k in keys if k.startswith("PRI|")]
    assert len(pri) == 3, f"先期组应恰好 3 个(PRI|)，实际 {pri}"
    lbw = [k for k in pri if k.startswith("PRI|LBW|")]
    assert len(lbw) == 1, f"低出生体重应 1 组, 实际 {lbw}"
    assert "新生儿期" in lbw[0] and "极低" in lbw[0], \
        f"天龄10+1400g 应为 新生儿期|极低出生体重档, 实际 {lbw[0]}"
    assert any(k.startswith("PRI|TRANSPLANT|") for k in pri)
    assert any(k.startswith("PRI|LIFESUPPORT|") for k in pri)
    # 角膜移植 / 冠脉旁路 不应进入先期
    assert not any(k.startswith("H16|") and "PRI" in k for k in keys)
    assert not any(k.startswith("I25|36.1200") and "PRI" in k for k in keys)
    # 正常体重新生儿(P59.9, 3200g) 不应进先期，应走基本规则
    assert any(k.startswith("P59|") for k in keys), "正常体重新生儿应走基本规则键"

    # ② 并项：D18.0 两术式 -> 1 组
    d18 = [k for k in keys if k.startswith("D18|")]
    assert len(d18) == 1 and d18[0] == "D18|OPMERGE", f"D18.0 应并项为 1 组, 实际 {d18}"

    # I20.0 / I20.1 -> 1 组(3位码 I20)
    i20 = [k for k in keys if k.startswith("I20|")]
    assert len(i20) == 1 and i20[0] == "I20|36.0600|", f"心绞痛应 3 位码并项 1 组, 实际 {i20}"

    # I70.1 肾动脉支架/球囊 -> 1 组(REN_STENT_BALLOON)
    i70 = [k for k in keys if "REN_STENT_BALLOON" in k]
    assert len(i70) == 1, f"肾动脉联合手术应并项 1 组, 实际 {i70}"

    # ①+② 不应影响普通基本规则病种
    assert "K35|47.0100|" in keys, "普通病种应保留基本规则键"
    assert "H16|11.6000|" in keys, "角膜移植应走基本规则(非先期)"


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
    assert sev.classify_non_malignant(rec(related_diag_code="J96.0", los=6))["level"] == "重度"
    # 中度：重要器官病损/感染 + 住院≥3天
    assert sev.classify_non_malignant(rec(related_diag_code="I63.9", los=6))["level"] == "中度"
    # 住院<3天不升级
    assert sev.classify_non_malignant(rec(related_diag_code="J96.0", los=2))["level"] == "轻度"
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
    add("K35.9", "急性阑尾炎", 40000, 10, related="J96.0", los=10)
    # Y 对照组：20 例费用均匀 → 无 CV 改善，不触发
    add("I10", "原发性高血压", 5000, 20)
    # Z 门控组：12 例双峰，但 < min_total_cases(15) → 不触发
    add("E11.9", "2型糖尿病", 6000, 6)
    add("E11.9", "2型糖尿病", 30000, 6, related="J96.0", los=10)

    df = pd.DataFrame(rows)
    gen = LocalDirectoryGenerator(threshold=10)
    groups = gen.cluster_records_to_groups(df)
    typed = gen.apply_auxiliary_typing(
        groups, min_total_cases=15, min_type_cases=5, cv_improvement_pct=0.20
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
    # 触发评估报告应有记录
    x_report = [r for r in gen.auxiliary_trigger_report
                if r['dimension'] == '严重程度' and r['triggered'] == '是'
                and 'K35' in r['disease_code']]
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


def test_diagnostic_auxiliary_subdivision():
    """核心病种第三层·诊断辅助细分（③成组层）：与第三步辅助分型(触发式)严格区分。

    验证 ③ 在聚类阶段即产出独立核心病种成组键（各自 RW），与第三步
    「触发式辅助分型」(严重程度/年龄/ICU/CCI，不产成组键、仅加元数据) 机制不同：
      (A) 肿瘤放化疗靶向免疫：主诊断 Z51.1/Z51.8 + 其他诊断(C00-C95)
          + 主要/相关手术操作(化疗99.2503/靶向99.2800x006/免疫99.2800x005 组合)
          → AUX|TUMOR|<肿瘤3位>|<治疗方式>
      (B) 结核耐药：A15-A19 + (主诊断含耐药拓展码 或 其他诊断含 U84.300)
          → AUX|TB|<A15-A16/A17/A18/A19>|<耐药/非耐药>
      (C) 烧伤类：先区分年龄(儿童<14/成人)，再按 深度(主诊断 T29/T30 深度码)
          + 面积(次要诊断 T31/T32) → AUX|BURN|<年龄>|<深度>|<面积>
    非肿瘤非结核非烧伤病种不进入 ③，保留基本规则键（不与辅助分型混淆）。
    肿瘤其他诊断范围收窄为 C00-C75/C76-C80/C81-C86/C88/C90/C91-C95，
    C87/C89/C96/C97/D 类不再触发肿瘤细分。
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

    # (A) 肿瘤放化疗靶向免疫
    add("Z51.1", relop="99.2503", reldx="C80")                              # 化疗
    add("Z51.1", relop="99.2800x006", reldx="C81")                          # 靶向
    add("Z51.8", relop="99.2800x005", reldx="C90")                          # 免疫
    add("Z51.1", relop="99.2503+99.2800x006", reldx="C88")                  # 化疗+靶向
    add("Z51.1", relop="99.2503+99.2800x006+99.2800x005", reldx="C91")       # 三联
    add("Z51.1", reldx="C80")                                               # 无手术 → 其他
    # (A-负例) 肿瘤范围收窄：C97 / D18 不再触发肿瘤细分 → 走基本规则
    add("Z51.1", relop="99.2503", reldx="C97")
    add("Z51.1", relop="99.2503", reldx="D18.0")
    # (B) 结核耐药
    add("A15.1", reldx="")                                                  # 非耐药
    add("A16", reldx="U84.300")                                             # 耐药(U84.300)
    add("A17", reldx="U84.300;A15.0")                                       # 耐药(U84.300)
    add("A15.000x010", reldx="")                                            # 耐药(主诊断拓展码)
    # (C) 烧伤类
    add("T30.2", reldx="T31.1", **{"年龄": 35})    # 成人 Ⅱ度 10-19%
    add("T30.2", reldx="T31.1", **{"年龄": 5})     # 儿童 Ⅱ度 10-19%
    add("T30.5", reldx="T31.4", **{"年龄": 40})    # 成人 深Ⅱ度 40-49%
    add("T30.3", reldx="", **{"年龄": 50})          # 成人 Ⅲ度 未特指面积
    # (C-负例) T31 主诊断(仅面积无深度) 不触发烧伤细分
    add("T31.1", reldx="", **{"年龄": 35})
    # 对照：普通基本规则病种
    add("K35.9", op="47.0100", n=2)                                         # 不应进入 ③

    df = pd.DataFrame(rows)
    gen = LocalDirectoryGenerator(threshold=1)
    groups = gen.cluster_records_to_groups(df)
    keys = list(groups.keys())

    # (A) 肿瘤：5 种治疗方式 + 其他
    assert "AUX|TUMOR|C80|化疗" in keys
    assert "AUX|TUMOR|C81|靶向" in keys
    assert "AUX|TUMOR|C90|免疫" in keys
    assert "AUX|TUMOR|C88|化疗+靶向" in keys
    assert "AUX|TUMOR|C91|化疗+靶向+免疫" in keys
    assert "AUX|TUMOR|C80|其他" in keys
    # (A-负例) C97 / D18 已收窄出肿瘤范围 → 走基本规则(Z51 开头)
    assert not any(k.startswith("AUX|TUMOR|C97") for k in keys)
    assert not any(k.startswith("AUX|TUMOR|D18") for k in keys)
    assert any(k.startswith("Z51|") for k in keys), "收窄后 Z51.1+C97/D18 应走基本规则"
    # (B) 结核（A15.000x010 主诊断耐药拓展码 与 A16+U84.300 同并入 A15-A16|耐药）
    assert "AUX|TB|A15-A16|非耐药" in keys
    assert "AUX|TB|A15-A16|耐药" in keys
    assert "AUX|TB|A17|耐药" in keys
    tb_resistant = groups["AUX|TB|A15-A16|耐药"]
    assert tb_resistant.case_count == 2, \
        f"U84.300 与主诊断拓展码两条路径应并入同组(2例)，实际 {tb_resistant.case_count}"
    # (C) 烧伤：年龄 × 深度 × 面积
    assert "AUX|BURN|成人|Ⅱ度|10-19%" in keys
    assert "AUX|BURN|儿童(小儿)|Ⅱ度|10-19%" in keys
    assert "AUX|BURN|成人|深Ⅱ度|40-49%" in keys
    assert "AUX|BURN|成人|Ⅲ度|未特指面积" in keys
    # (C-负例) T31 主诊断(仅面积无深度) 不触发烧伤细分
    assert not any(k.startswith("AUX|BURN") and "T31" in k for k in keys)
    assert any(k.startswith("T31|") for k in keys), "T31 主诊断应走基本规则"

    # ③ 与基本规则互不干扰：对照组 K35 走基本规则，不在 ③
    assert "K35|47.0100|" in keys
    assert not any(k.startswith("AUX|K35") for k in keys)
    # 所有 ③ 键均以 AUX| 开头（成组层标记），与辅助分型(不产键、仅加元数据)区分
    aux_keys = [k for k in keys if k.startswith("AUX|")]
    assert len(aux_keys) == 13, f"③ 应恰好 13 个 AUX 组，实际 {aux_keys}"


def test_national_dip_alignment():
    """①/③ 严格对齐国家目录库（DIP3.0版分组征求地方意见的函）。

    加载 DIP3.0国家目录库.xlsx 后：
      ① 低出生体重(函4969-4973)：天龄≤28天 + 出生体重 → 直接产出国家 DIP 编码
         P07-01(<750g)/P07-02(750-999)/P07-03(1000-1499)/P07-04(1500-1999)/P07-05(2000-2499)
      ③ 肿瘤(函4974-5015)：Z51.1/Z51.8 × C范围(6档) × 治疗组合(7种) → Z51.x-NN
      ③ 结核(函5040-5061)：A15-A16/A17/A18/A19 × 术式组 × 耐药 → A15-A16-NN 等
      ③ 烧伤(函5016-5039)：xlsx 导出截断缺失该段 → 保持 AUX|BURN 降级键
    未加载国家目录库时仍走描述性键（由前两个用例覆盖，向后兼容）。
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
    add("P07.0", **{"天龄": 10, "出生体重": 1400})   # 极低 → P07-03
    add("P07.0", **{"天龄": 3, "出生体重": 800})     # 超低 → P07-02
    add("P07.1", **{"天龄": 20, "出生体重": 2300})   # 低 → P07-05
    # ①-负例：天龄>28天 不进先期 → 基本规则
    add("P07.0", **{"天龄": 40, "出生体重": 1400})
    # ③ 肿瘤：DIP 编码 = 主诊断 × C范围 × 治疗组合
    add("Z51.1", relop="99.2503", reldx="C80")                              # → Z51.1-23
    add("Z51.1", relop="99.2503+99.2800x006+99.2800x005", reldx="C91")      # → Z51.1-42
    add("Z51.8", relop="99.2800x005", reldx="C90")                          # → Z51.8-40
    add("Z51.8", relop="99.2800x006+99.2800x005", reldx="C81")              # → Z51.8-36
    # ③-肿瘤降级：无治疗操作 → 国家库无对应行，保持描述性键
    add("Z51.1", reldx="C80")
    # ③ 结核：耐药标志 × 术式组
    add("A15.1")                                    # 非耐药无术式 → A15-A16-00
    add("A16", reldx="U84.300")                     # 耐药(U84.300) → A15-A16-02
    add("A15.000x010")                              # 耐药(主诊断拓展码) → A15-A16-02
    add("A17", reldx="U84.300")                     # → A17-02
    add("A15.1", op="34.0401")                      # 非耐药+胸廓成形术 → A15-A16-12
    # ③ 烧伤：xlsx 缺函5016-5039 段 → 应保持 AUX|BURN 降级键
    add("T30.2", reldx="T31.1", **{"年龄": 35})
    # 对照：普通病种走基本规则
    add("K35.9", op="47.0100", n=2)

    df = pd.DataFrame(rows)
    gen = LocalDirectoryGenerator(threshold=1)
    gen.load_national_directory("F:/DIP/data/DIP3.0国家目录库.xlsx")
    groups = gen.cluster_records_to_groups(df)
    keys = list(groups.keys())

    # ① 低出生体重 → 国家 DIP 编码直出
    for dip in ("P07-02", "P07-03", "P07-05"):
        assert dip in keys, f"低出生体重应产出国家编码 {dip}，实际 {sorted(keys)}"
        assert getattr(groups[dip], "national_matched", False) is True, \
            f"{dip} 应标记 national_matched"
        assert getattr(groups[dip], "national_dip_code", None) == dip
    assert not any(k.startswith("PRI|LBW|") for k in keys), \
        "加载国家目录库后不应再出现描述性 LBW 键"
    # ①-负例：天龄40天 → 基本规则(P07 开头)
    assert any(k.startswith("P07|") for k in keys), "超28天新生儿应走基本规则"

    # ③ 肿瘤 → 国家 DIP 编码直出
    for dip in ("Z51.1-23", "Z51.1-42", "Z51.8-40", "Z51.8-36"):
        assert dip in keys, f"肿瘤细分应产出国家编码 {dip}，实际 {sorted(keys)}"
        assert getattr(groups[dip], "national_matched", False) is True
    # ③-肿瘤降级：无治疗操作组合在国家库无行 → 描述性键
    assert "AUX|TUMOR|C80|其他" in keys, "无治疗操作应降级为描述性键"

    # ③ 结核 → 国家 DIP 编码直出
    assert "A15-A16-00" in keys
    assert "A15-A16-02" in keys
    assert groups["A15-A16-02"].case_count == 2, \
        f"U84.300 与主诊断拓展码应并入 A15-A16-02(2例)，实际 {groups['A15-A16-02'].case_count}"
    assert "A17-02" in keys
    assert "A15-A16-12" in keys, f"胸廓成形术应命中 A15-A16-12，实际 {sorted(keys)}"
    assert not any(k.startswith("AUX|TB|") for k in keys), \
        "加载国家目录库后结核不应再出现描述性键"

    # ③ 烧伤：xlsx 无函5016-5039 → 保持降级键
    assert "AUX|BURN|成人|Ⅱ度|10-19%" in keys

    # 对照：基本规则不受影响
    assert "K35|47.0100|" in keys


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

    # ① 先期分组：低出生体重（天龄10天，出生体重1400g）
    add("P07.1", n=3, **{"day_age": 10, "birth_weight": 1400})
    # ① 先期分组：器官移植（肾移植 55.6）
    add("N18.5", op="55.6", n=3)
    # ② 并项规则：诊断并项（心绞痛 I20.x → 3 位码归并）
    add("I20.0", n=3)
    # ③ 诊断辅助细分：肿瘤放化疗（未加载国家目录→描述性键，但层次仍为诊断辅助细分）
    add("Z51.1", relop="99.2503", reldx="C80", n=3)
    # ④ 基本规则：普通手术（阑尾炎 + 阑尾切除）
    add("K35.8", op="47.0", n=3)
    # 综合病种：未达阈值的低频病种（1 例）
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


if __name__ == "__main__":
    test_local_directory_generation()
    test_extreme_case_trimming()
    test_comprehensive_disease_subtypes()
    test_core_disease_priority_and_merge()
    test_auxiliary_typing()
    test_diagnostic_auxiliary_subdivision()
    test_national_dip_alignment()
    test_grouping_layer_order()
    print("test_local_directory.py 全部 8 个用例通过")


