import sys, os
sys.path.insert(0, r'F:/DIP'); os.chdir(r'F:/DIP')
from src.core.local_directory_generator import LocalDirectoryGenerator

gen = LocalDirectoryGenerator(threshold=15)
gen.load_national_directory(r'F:/DIP/data/DIP3.0国家目录库.xlsx')

# 模拟 Web 先期分组回填逻辑
def web_resolve(main_diag, op):
    ck, layer = gen._refine_core_group_key(main_diag, op, "", "")
    ndip = ""
    if layer == "先期分组" and (ck.startswith("PRI|LIFESUPPORT") or ck.startswith("PRI|TRANSPLANT")):
        o = ck.split("|")[2]
        ndip = gen._nat_dip_for_diag_oprn(main_diag[:4], o)
    return ck, layer, ndip

ops = [
    ("39.9500", "血液透析"),
    ("39.2700x001", "为肾透析的动静脉造瘘术"),
    ("39.9500x007", "连续性肾脏替代治疗[CRRT]"),
    ("54.9800", "腹膜透析"),
    ("55.6", "肾移植"),
]
print("=== N18.5 各主要手术 成组层次 vs Web回填 ===")
for op, name in ops:
    ck, layer, ndip = web_resolve("N18.5", op)
    print(f"  主手术 {op} ({name})")
    print(f"     -> 本地键={ck} | 层次={layer} | Web国家DIP码={ndip or '(无/回落基本规则)'}")

print("\n=== 单独验证 _refine_core_group_key('N18.5','39.9500') ===")
ck, layer = gen._refine_core_group_key("N18.5", "39.9500", "", "")
print("  ck=", ck, " layer=", layer)
