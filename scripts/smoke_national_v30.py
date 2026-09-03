# -*- coding: utf-8 -*-
"""DIP 3.0 国家目录引擎冒烟测试：四层匹配 + 不纳入分组 + 基层病种。

运行：
  C:\\Users\\Dell\\.workbuddy\\binaries\\python\\envs\\default\\Scripts\\python.exe \\
      F:\\DIP\\scripts\\smoke_national_v30.py
"""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.core.national_directory_v30 import NationalDirectoryV30  # noqa: E402

XLSX = ROOT / "data" / "DIP3.0国家目录库.xlsx"

W = Decimal


# (说明, kwargs, 期望方案序号)  期望为 None 表示只观察输出
CASES = [
    # ---------------- ① 先期分组：手术操作驱动 ----------------
    ("XQ-1 心肺移植 33.6x00", dict(main_diag="I50.900", main_oprn="33.6x00"), "XQ-1"),
    ("XQ-6 肾移植 55.6100", dict(main_diag="N18.000", main_oprn="55.6100"), "XQ-6"),
    ("XQ-9 同胞全相合 41.0300", dict(main_diag="C92.100", main_oprn="41.0300"), "XQ-9"),
    ("XQ-11 ECMO 39.6500", dict(main_diag="J96.001", main_oprn="39.6500"), "XQ-11"),
    ("XQ-12 全人工心脏 37.5200x001", dict(main_diag="I50.900", main_oprn="37.5200x001"), "XQ-12"),
    ("XQ-13 呼吸机≥96h+CRRT", dict(main_diag="J96.001", main_oprn="96.7201",
                                related_oprn="39.9500x007"), "XQ-13"),
    ("XQ-14 呼吸机≥96h(无CRRT)", dict(main_diag="J96.001", main_oprn="96.7201"), "XQ-14"),
    ("XQ-15 人工肝 50.9200x001", dict(main_diag="K72.003", main_oprn="50.9200x001"), "XQ-15"),

    # ---------------- ① 先期分组：低出生体重儿 ----------------
    ("XQ-16 超低出生体重 800g", dict(main_diag="P07.000", main_oprn="",
                                 day_age=10, birth_weight=W("800")), "XQ-16"),
    ("XQ-17 极低出生体重 1200g", dict(main_diag="P07.100", main_oprn="",
                                   day_age=10, birth_weight=W("1200")), "XQ-17"),
    ("XQ-18 较低出生体重 1800g", dict(main_diag="P07.100", main_oprn="",
                                   day_age=10, birth_weight=W("1800")), "XQ-18"),
    ("XQ-19 低出生体重 2300g", dict(main_diag="P07.200", main_oprn="",
                                  day_age=10, birth_weight=W("2300")), "XQ-19"),
    ("LBW 体重超档 3000g(应回落)", dict(main_diag="P07.200", main_oprn="",
                                   day_age=10, birth_weight=W("3000")), None),
    ("LBW 天龄≥29天(应回落)", dict(main_diag="P07.000", main_oprn="",
                                day_age=40, birth_weight=W("800")), None),

    # ---------------- ② 并项规则 ----------------
    ("BX-20 A09.0+内镜44.1300x001", dict(main_diag="A09.001", main_oprn="44.1300x001"), "BX-20"),
    ("BX-26 A40+胸腔闭式引流", dict(main_diag="A40.900", main_oprn="34.0401"), "BX-26"),
    ("BX-27 A40+93.9001", dict(main_diag="A40.900", main_oprn="93.9001"), "BX-27"),

    # ---------------- ③ 诊断辅助细分：烧伤 ----------------
    ("FZ-1745 二度 T20.2+面积<10%", dict(main_diag="T20.200", main_oprn="",
                                     related_diag="T31.000"), "FZ-1745"),
    ("FZ-1748 二度 面积10-29%", dict(main_diag="T20.200", main_oprn="",
                                  related_diag="T31.100"), "FZ-1748"),
    ("FZ-1751 二度 面积30-49%", dict(main_diag="T20.200", main_oprn="",
                                  related_diag="T31.300"), "FZ-1751"),
    ("FZ-1754 二度 面积≥50%", dict(main_diag="T20.200", main_oprn="",
                                 related_diag="T31.900"), "FZ-1754"),
    ("FZ-1746 二度+清创86.2201", dict(main_diag="T20.200", main_oprn="86.2201",
                                   related_diag="T31.000"), "FZ-1746"),
    ("FZ-1755 三度 T20.3+面积<10%", dict(main_diag="T20.300", main_oprn="",
                                     related_diag="T31.000"), "FZ-1755"),
    ("FZ-1760 三度 面积10-29%", dict(main_diag="T20.300", main_oprn="",
                                  related_diag="T31.200"), "FZ-1760"),
    ("FZ-1767 三度 面积≥50%", dict(main_diag="T20.300", main_oprn="",
                                 related_diag="T32.900"), "FZ-1767"),

    # ---------------- ③ 诊断辅助细分：肿瘤 ----------------
    ("FZ-1770 Z51.1+化疗99.2503+C34.9", dict(main_diag="Z51.101", main_oprn="99.2503",
                                          related_diag="C34.901"), "FZ-1770"),
    ("FZ-1771 Z51.1+化疗+免疫(+AND)", dict(main_diag="Z51.101", main_oprn="99.2503",
                                        related_oprn="99.2800x005",
                                        related_diag="C34.901"), "FZ-1771"),
    ("FZ-1772 Z51.1+化疗+靶向(+AND)", dict(main_diag="Z51.101", main_oprn="99.2503",
                                        related_oprn="99.2800x006",
                                        related_diag="C34.901"), "FZ-1772"),
    ("FZ-1790 Z51.1+C91-C95", dict(main_diag="Z51.101", main_oprn="99.2503",
                                 related_diag="C92.100"), "FZ-1790"),
    ("FZ-1794 Z51.8+免疫99.2800x005", dict(main_diag="Z51.800", main_oprn="99.2800x005",
                                        related_diag="C34.901"), "FZ-1794"),
    ("FZ-1795 Z51.8+靶向99.2800x006", dict(main_diag="Z51.800", main_oprn="99.2800x006",
                                        related_diag="C34.901"), "FZ-1795"),
    ("FZ-1796 Z51.8+靶向+免疫(+AND)", dict(main_diag="Z51.800", main_oprn="99.2800x006",
                                        related_oprn="99.2800x005",
                                        related_diag="C34.901"), "FZ-1796"),
    ("肿瘤 免疫/靶向不得混淆(x005≠x006)", dict(main_diag="Z51.800", main_oprn="99.2800x006",
                                       related_diag="C34.901"), "FZ-1795"),

    # ---------------- ③ 诊断辅助细分：结核 ----------------
    ("FZ-1841 A17 非耐药 保守", dict(main_diag="A17.000", main_oprn=""), "FZ-1841"),
    ("FZ-1840 A17 耐药 保守(+U84.300)", dict(main_diag="A17.000", main_oprn="",
                                         related_diag="U84.300"), "FZ-1840"),
    ("FZ-1839 A17 非耐药+03.3101", dict(main_diag="A17.000", main_oprn="03.3101"), "FZ-1839"),
    ("FZ-1857 A19 非耐药 保守", dict(main_diag="A19.900", main_oprn=""), "FZ-1857"),
    ("FZ-1855 A19 非耐药+支气管镜", dict(main_diag="A19.900", main_oprn="33.2402"), "FZ-1855"),
    ("FZ-1854 A19 耐药+支气管镜(+U84.300)", dict(main_diag="A19.900", main_oprn="33.2402",
                                            related_diag="U84.300"), "FZ-1854"),
    ("FZ-1836 A15-A16 耐药 保守", dict(main_diag="A16.001", main_oprn="",
                                    related_diag="U84.300"), "FZ-1836"),

    # ---------------- ④ 基本规则 ----------------
    ("JC-1858 A01.0 保守治疗", dict(main_diag="A01.000", main_oprn=""), "JC-1858"),
    ("JC A01.0 保守(内镜按保守清洗)", dict(main_diag="A01.000",
                                     main_oprn="00.2900x001"), "JC-1858"),

    # ---------------- 不纳入分组：主要诊断（仅完全相等才剔除） ----------------
    ("不纳入诊断 Z51.100 残码 → None", dict(main_diag="Z51.100", main_oprn="99.2503",
                                      related_diag="C34.901"), None),
    ("不纳入诊断 A16.000 残码 → None", dict(main_diag="A16.000", main_oprn=""), None),
    ("不纳入诊断 Z99.100 → None", dict(main_diag="Z99.100", main_oprn=""), None),
    ("残码 Z51.100x001 ≠ Z51.100 → 不剔除", dict(main_diag="Z51.100x001", main_oprn="99.2503",
                                          related_diag="C34.901"), "FZ-1770"),

    # ---------------- 不纳入分组：主要手术操作（精确匹配，不外推） ----------------
    ("手术 99.2800 按保守治疗入组", dict(main_diag="Z51.800", main_oprn="99.2800",
                                  related_diag="C34.901"), None),
    ("手术 x005 不得被基码 99.2800 误伤", dict(main_diag="Z51.800", main_oprn="99.2800x005",
                                       related_diag="C34.901"), "FZ-1794"),
    ("手术 00.3101 不可作主要→顺延", dict(main_diag="A01.000", main_oprn="00.3101"), "JC-1858"),
    ("限范围 44.1300x001 主诊断在范围", dict(main_diag="K29.500", main_oprn="44.1300x001"), None),
    ("限范围 44.1300x001 主诊断超范围", dict(main_diag="J18.900", main_oprn="44.1300x001"), None),
    ("按保守治疗入组 00.2900x001", dict(main_diag="A01.000", main_oprn="00.2900x001"), "JC-1858"),

    # ---------------- 基层病种 ----------------
    ("基层 D24+85.2300x001", dict(main_diag="D24", main_oprn="85.2300x001"), None),
    ("基层 D64.900 保守治疗组", dict(main_diag="D64.900", main_oprn=""), None),
]


def main() -> int:
    nd = NationalDirectoryV30(str(XLSX))
    print(f"载入：核心 {len(nd.rows)} 行 / 不纳入诊断 {len(nd.excl_diag)} / "
          f"不纳入手术 {len(nd.excl_oprn)} / 基层对 {len(nd.grassroot_pairs)} / "
          f"基层保守诊断 {len(nd.grassroot_conservative)} / 结核耐药 {len(nd.tb_dr_codes)}")
    print(f"索引：XQ手术 {len(nd._xq_op_rows)} / XQ-LBW {len(nd._xq_lbw_rows)} / "
          f"BX {len(nd._bx_index)} / JC {len(nd._jc_index)} / "
          f"FZ 烧伤{len(nd._fz_burn)} 肿瘤{len(nd._fz_onco)} 结核{len(nd._fz_tb)}")
    print("-" * 118)
    passed = failed = 0
    for desc, kw, expect in CASES:
        try:
            m = nd.match(**kw)
        except Exception as exc:  # noqa: BLE001
            print(f"[异常] {desc:34s} {type(exc).__name__}: {exc}")
            failed += 1
            continue
        got = m.seq if m else "None"
        ok = (m is not None and got == expect) if expect else (m is None)
        mark = "√" if (ok if expect else (m is None)) else "×"
        if expect:
            passed += ok
            failed += (not ok)
            mark = "√" if ok else "×"
        else:
            mark = "·"
        if m is None:
            print(f"[{mark}] {desc:34s} -> None   (未命中)")
        else:
            flag = "基层" if m.is_grassroot else "    "
            cons = "保守" if m.conservative else "    "
            print(f"[{mark}] {desc:34s} -> {got:>8s} | {m.layer:6s} | {flag} | {cons} | "
                  f"{m.dip_code[:52]:52s}")
    print("-" * 118)
    print(f"断言用例 {passed + failed} 条：通过 {passed}，失败 {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
