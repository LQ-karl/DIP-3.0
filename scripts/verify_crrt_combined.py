import sys
sys.path.insert(0, "F:/DIP")
from src.core.local_directory_generator import LocalDirectoryGenerator

gen = LocalDirectoryGenerator(threshold=15)
gen.load_national_directory("F:/DIP/data/DIP3.0国家目录库.xlsx")

cases = [
    # (主诊断, 主手术, 相关手术, 期望层/键描述)
    ("N18.5", "39.9500x007", "", "CRRT单独 → 基本规则(非先期)"),
    ("N18.5", "96.7201", "", "呼吸机≥96h单独 → 先期(4967)"),
    ("N18.5", "96.7201", "39.9500x007", "呼吸机+CRRT → 4966组合先期"),
    ("N18.5", "", "39.9500x007", "CRRT仅作相关手术 → 基本规则(非先期)"),
    ("J96.0", "96.7101", "", "呼吸机<96h → 基本规则(非先期)"),
    ("A41.9", "39.6500", "", "ECMO → 先期(4964)"),
    ("I21.0", "37.5200x001", "", "全人工心脏 → 先期(4965)"),
    ("K72.9", "50.9200x001", "", "人工肝 → 先期(4968)"),
    ("N18.5", "39.9500", "", "普通血液透析 → 基本规则(非先期)"),
    ("I50.9", "55.6100", "", "肾移植 → 先期(4959)"),
]

print(f"{'主诊断':<8}{'主手术':<14}{'相关手术':<14}{'→ 判定结果':<40}期望")
print("-" * 100)
all_ok = True
for diag, mop, rop, expect in cases:
    key = gen._detect_priority(diag, mop, rop)
    if key is None:
        result = "基本规则(None)"
    else:
        result = key
    # 判定是否为先期
    is_pri = key is not None and key.startswith("PRI|")
    # 期望解析（"非先期" 不算先期）
    exp_pri = ("先期" in expect) and ("非先期" not in expect)
    exp_combined = "4966" in expect
    ok = (is_pri == exp_pri) and (("COMBINED" in result) == exp_combined)
    all_ok = all_ok and ok
    mark = "OK " if ok else "FAIL"
    print(f"{mark} {diag:<8}{mop:<14}{rop:<14}{result:<40}{expect}")

# 重点：CRRT 单独必须不是先期，且组合组必须同时出现
crrt_alone = gen._detect_priority("N18.5", "39.9500x007", "")
vent_crrt = gen._detect_priority("N18.5", "96.7201", "39.9500x007")
assert crrt_alone is None, f"CRRT单独不应是先期, got {crrt_alone}"
assert vent_crrt == "PRI|COMBINED|96.7201+39.9500x007", f"组合组错误: {vent_crrt}"
print("\n核心断言通过：CRRT单独→基本规则；呼吸机+CRRT→4966组合先期")
print("全部用例:", "PASS" if all_ok else "FAIL")
