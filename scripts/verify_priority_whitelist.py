import sys, os
sys.path.insert(0, r'F:/DIP'); os.chdir(r'F:/DIP')
from src.core.local_directory_generator import LocalDirectoryGenerator

gen = LocalDirectoryGenerator(threshold=15)
gen.load_national_directory(r'F:/DIP/data/DIP3.0国家目录库.xlsx')

def web_resolve(main_diag, op):
    ck, layer = gen._refine_core_group_key(main_diag, op, "", "")
    ndip = ""
    if layer == "先期分组" and (ck.startswith("PRI|LIFESUPPORT") or ck.startswith("PRI|TRANSPLANT")):
        o = ck.split("|")[2]
        ndip = gen._nat_dip_for_diag_oprn(main_diag[:4], o)
    return ck, layer, ndip

# 主诊断统一用 N18.5（慢性肾衰5期），验证"判定不看诊断"且血液透析不进先期
cases = [
    ("39.9500", "血液透析(应排除)"),
    ("39.9500x007", "CRRT(应纳入)"),
    ("96.7101", "ECMO-xlsx(应纳入)"),
    ("39.6500", "ECMO-函(应纳入)"),
    ("55.6100", "肾移植(应纳入)"),
    ("55.6100x001", "肾移植带扩展(应纳入)"),
    ("37.5100", "心脏移植(应纳入)"),
    ("37.6101", "IABP(应排除)"),
    ("93.9000", "无创通气(应排除)"),
    ("96.7201", "有创呼吸机(应纳入)"),
    ("50.9200x001", "人工肝(应纳入)"),
    ("33.5000", "肺移植(应纳入)"),
    ("41.0200", "造血干细胞移植(应纳入)"),
    ("46.97", "小肠移植(旧清单,应排除)"),
]
print(f"{'手术码':14} {'名称':22} {'layer':10} {'类别':12} {'回填DIP':12} key")
print("-" * 90)
for op, name in cases:
    ck, layer, ndip = web_resolve("N18.5", op)
    cat = ck.split("|")[1] if ck.startswith("PRI|") else "-"
    flag = "OK" if (("排除" in name) == (layer != "先期分组")) else "!!FAIL!!"
    print(f"{op:14} {name:22} {layer:10} {cat:12} {ndip or '-':12} {ck}  [{flag}]")
