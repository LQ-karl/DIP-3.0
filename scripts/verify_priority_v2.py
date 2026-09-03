import sys
sys.path.insert(0, "F:/DIP")
from decimal import Decimal
from src.core.local_directory_generator import LocalDirectoryGenerator

gen = LocalDirectoryGenerator(threshold=15)
gen.load_national_directory("F:/DIP/data/DIP3.0国家目录库.xlsx")

def grp(main_diag, main_op="", rel_op="", rel_diag="", day_age=0, birth_weight=Decimal("0"),
        age=0, birth_date="", admission_date=""):
    k, layer = gen._refine_core_group_key(
        main_diag, main_op, rel_op, rel_diag,
        day_age=day_age, birth_weight=birth_weight, age=age,
        birth_date=birth_date, admission_date=admission_date)
    return k, layer

print("=== 呼吸循环支持 / 组合组 4966（只看手术）===")
cases = [
    ("I21.4", "96.7201", "39.9500x007"),       # 呼吸机≥96h + CRRT 同时 → 4966 组合
    ("I21.4", "39.9500x007", ""),              # 仅 CRRT
    ("I21.4", "96.7201", ""),                  # 仅 呼吸机≥96h
    ("I21.4", "96.7101", ""),                  # 呼吸机<96h → 不应先期
    ("J96.0", "39.6500", ""),                  # ECMO
    ("J96.0", "37.5200x001", ""),             # 全人工心脏
    ("J96.0", "50.9200x001", ""),             # 人工肝
    ("I50.0", "39.9500", ""),                  # 普通血液透析 → 不应先期
    ("G47.3", "93.9000", ""),                  # 无创通气 → 不应先期
    ("I21.4", "37.6101", ""),                  # IABP → 不应先期
]
for md, mo, ro in cases:
    k, layer = grp(md, mo, ro)
    print(f"  {md:6s} op={mo:14s} rel={ro:12s} -> {k:40s} [{layer}]")

print("\n=== 器官移植（只看手术）===")
for md, mo in [("N18.5","55.6100"),("I21.4","37.5100"),("J96.0","33.5000"),("C92.0","41.0200")]:
    k, layer = grp(md, mo)
    print(f"  {md:6s} op={mo:12s} -> {k:40s} [{layer}]")

print("\n=== 低出生体重儿 4969–4973（P07 + 天龄<29 + 体重档）===")
# 主诊断 P07.x，天龄<29天，不同出生体重
for w, expect in [(700, "P07-01"), (800, "P07-02"), (1200, "P07-03"), (1700, "P07-04"), (2200, "P07-05")]:
    k, layer = grp("P07.1", "", "", day_age=10, birth_weight=Decimal(str(w)))
    ok = "OK" if k == expect else "**FAIL**"
    print(f"  P07.1 day=10 w={w:4d} -> {k:10s} expect {expect:8s} {ok} [{layer}]")
# 非 P07 诊断 + 低体重 → 不应归 LBW 先期
k, layer = grp("Q87.0", "", "", day_age=10, birth_weight=Decimal("800"))
print(f"  非P07 Q87.0 day=10 w=800 -> {k:30s} [{layer}]  (期望基本规则/非先期)")
# P07 但天龄≥29 → 不应归 LBW 先期
k, layer = grp("P07.1", "", "", day_age=40, birth_weight=Decimal("800"))
print(f"  P07.1 day=40 w=800 -> {k:30s} [{layer}]  (期望非LBW先期)")
# 正常体重 P07 → 不应归 LBW 先期
k, layer = grp("P07.1", "", "", day_age=10, birth_weight=Decimal("3000"))
print(f"  P07.1 day=10 w=3000 -> {k:30s} [{layer}]  (期望非LBW先期)")

print("\n=== CRRT 真实诊断回填（N18.5 + 39.9500x007 → N18.5-03）===")
k, layer = grp("N18.5", "39.9500x007", "")
print(f"  N18.5 + 39.9500x007 -> {k} [{layer}]")
