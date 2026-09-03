# -*- coding: utf-8 -*-
"""DIP 3.0 版分组方案 · 国家目录引擎（以《按病种分值（DIP）付费 3.0 版分组方案》为准）。

与旧实现（基于征求意见稿《函》）的关键差异：
  1. 四层不再靠「3 位类目码推断」，而是直接按方案自带的分类分段查表：
       ① 先期分组  XQ 1-19      → 按手术操作码 / 低出生体重儿 匹配
       ② 并项规则  BX 20-1744   → 按 (主要诊断, 主要手术操作) 查 BX 名录
       ③ 诊断辅助细分 FZ 1745-1857 → 烧伤 25 / 肿瘤 42 / 结核 46
       ④ 基本规则  JC 1858-5125 → 按 (主要诊断, 主要手术操作) 查 JC 名录（忽略相关手术操作）
  2. 新增「不纳入分组的主要诊断 / 主要手术操作」前置处理。
  3. 新增「基层病种」标记（可不设医疗机构调节系数）。

⚠️ 用户确认的三条匹配口径（2026-09-03）——方案原文与目录库存在编码粒度冲突，
   此处以用户裁决为准，不得擅自改为"外推/前缀"判定：
   · 不纳入分组的【主要诊断】：**仅完全相等**才剔除（名单是全码 A09.900；
     目录库用亚目 A09.9，两者精确交集为 0）。病例填 A09.900x001 ≠ A09.900，不剔除。
   · 不纳入分组的【主要手术操作】：**精确匹配**（名单有基码 99.2800，但肿瘤组用
     99.2800x005/x006；若外推到扩展码，42 个肿瘤组与 499 个目录行将全部作废）。
   · 被判不纳入的码出现在【相关手术操作】时，按规则类型分别处理：
     「按保守治疗入组」→ 相关操作中也剔除；
     「不可作为主要手术操作」「限范围可作主要手术操作」→ 保留（只是不能当主角）。

编码语义（与方案原文一致）：
  - '|' 表示 **或(OR)**：单元格内 A|B = A 或 B
  - '+' 表示 **且(AND)**：单元格内 A+B = A 与 B 须同时出现
  - 主要手术操作编码为空 → 「保守治疗」组

DIP 编码规则（用户确认）：
  {主要诊断编码}-{主要手术操作编码}-{相关手术操作编码}[-{差异维度}]
  主手术操作为空记「保守治疗」；多值原样保留；三段不唯一时追补第 4 段。
  ⚠️ 解析请直接用结构化列，不要反解 DIP 编码字符串：主诊断 A15-A16 自带 '-'，
     与分隔符冲突（本模块内部一律用结构化字段建索引，不解析编码串）。
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

import pandas as pd

LAYER_XQ = "先期分组"
LAYER_BX = "并项规则"
LAYER_FZ = "诊断辅助细分"
LAYER_JC = "基本规则"

CONSERVATIVE = "保守治疗"

# 结核主诊断归类：A15/A16 合并为 A15-A16
TB_CAT_MAP = {"A15": "A15-A16", "A16": "A15-A16", "A17": "A17", "A18": "A18", "A19": "A19"}

# 肿瘤其他诊断范围（方案原文 6 个区间）
NEO_RANGES: List[Tuple[str, int, int]] = [
    ("C00-C75", 0, 75), ("C76-C80", 76, 80), ("C81-C86", 81, 86),
    ("C88", 88, 88), ("C90", 90, 90), ("C91-C95", 91, 95),
]


def _clean(v) -> str:
    """把 NaN/None/空统一成空串。"""
    if v is None:
        return ""
    try:
        if v != v:  # NaN
            return ""
    except TypeError:
        pass
    s = str(v).strip()
    return "" if s.lower() in ("nan", "none", "null", "") else s


def _icd4(code: str) -> str:
    """ICD-10 亚目级（含 1 位小数），如 T20.200 -> T20.2、A09.001 -> A09.0、A40 -> A40。"""
    c = _clean(code).upper().replace(" ", "")
    if not c:
        return ""
    if "." in c:
        head, tail = c.split(".", 1)
        return f"{head}.{tail[:1]}" if tail else head
    return c


def _icd3(code: str) -> str:
    """ICD-10 类目级（字母 + 2 位数字），如 A09.0 -> A09、T20.2 -> T20、C88 -> C88。"""
    c = _clean(code).upper().replace(" ", "")
    if not c:
        return ""
    return c.split(".")[0][:3]


def _diag_candidates(full_code: str) -> List[str]:
    """病例主诊断的查表候选键，按精确度从高到低：完整码 → 亚目(4位) → 类目(3位)。"""
    c = _clean(full_code).upper().replace(" ", "")
    if not c:
        return []
    out = []
    for k in (c, _icd4(c), _icd3(c)):
        if k and k not in out:
            out.append(k)
    return out


def _op_norm(code: str) -> str:
    """手术操作码归一化：去 x 扩展后缀，用于比对（保留 '.'）。"""
    c = _clean(code).upper().replace(" ", "")
    if not c:
        return ""
    return re.sub(r"X\d+$", "", c)


def _op_tokens(cell: str) -> List[str]:
    """把目录单元格拆成『用于建索引的单个码』列表（| 与 + 都拆开）。"""
    return [t for t in re.split(r"[|+]+", _clean(cell)) if t]


def _cell_or_groups(cell: str) -> List[List[str]]:
    """把目录单元格解析为 OR-AND 范式：外层 | 是 OR，内层 + 是 AND。

    例：'25.5905+40.3x00x005|40.5900x011' -> [['25.5905','40.3x00x005'], ['40.5900x011']]
    """
    groups = []
    for alt in _clean(cell).split("|"):
        need = [t for t in (x.strip() for x in alt.split("+")) if t]
        if need:
            groups.append(need)
    return groups


def _cell_matches(cell: str, case_codes: Set[str], case_norms: Set[str]) -> bool:
    """目录单元格(OR-AND 表达式) 是否被病例的编码集合满足。

    case_codes: 病例原始码集合（含 x 扩展）
    case_norms: 病例归一化码集合（去 x 扩展）
    """
    groups = _cell_or_groups(cell)
    if not groups:
        return True  # 空单元格 = 无约束
    for need in groups:
        if all(_token_hit(n, case_codes, case_norms) for n in need):
            return True
    return False


def _token_hit(token: str, case_codes: Set[str], case_norms: Set[str]) -> bool:
    """目录单元格里的单个码 是否被病例的编码集合满足。

    三条铁律（x 扩展码不可互相混淆，否则 99.2800x005 免疫 与 99.2800x006 靶向 会变成同一个码）：
      1. 完全相等 → 命中。
      2. 目录侧带 x 扩展（如 99.2800x005）：只接受病例侧完全相同的扩展码，
         或病例侧填报为其基码（99.2800，填得粗）时的宽松匹配；
         病例侧是**另一个**扩展码（99.2800x006）→ 不命中。
      3. 目录侧为基码（如 93.9000）：病例侧基码相同或为其任意扩展 → 命中。
    """
    tok = token.upper().replace(" ", "")
    if not tok:
        return True
    if tok in case_codes:                       # ① 完全相等
        return True
    tok_norm = _op_norm(tok)
    if tok != tok_norm:                         # ② 目录侧带 x 扩展
        return tok_norm in case_codes           #    仅接受相同扩展码 / 病例侧填报为基码
    if tok in case_norms:                       # ③ 目录侧为基码
        return True
    return any(c.startswith(tok) for c in case_codes if len(tok) >= 5)


def _specificity(cell: str, case_codes: Set[str], case_norms: Set[str]) -> int:
    """单元格被满足的『最高特异性』：0=不满足，n=命中的 AND 组内的码个数。

    用于「多码 AND 组合组 优先于 单码组」：Z51.1 同时做了化疗+免疫(99.2503+99.2800x005)
    应进 FZ-1771，而不是先出现的 FZ-1770（只要求 99.2503）。
    """
    best = 0
    for need in _cell_or_groups(cell):
        if all(_token_hit(n, case_codes, case_norms) for n in need):
            best = max(best, len(need))
    return best


def _pick_by_operation(rows: List[dict], case_op_codes: Set[str],
                       case_op_norms: Set[str]) -> List[dict]:
    """回验候选行的手术操作单元格，并按特异性降序（AND 组合组优先于单码组）。

    索引按「去 x 扩展」的归一化码粗召回，必须用原始单元格再验一次，
    否则 99.2800x006（靶向）会被 99.2800x005（免疫）的行误召回。
    空操作单元格（保守治疗行）视为特异性 0，作兜底保留。
    """
    scored: List[Tuple[int, dict]] = []
    for r in rows:
        cell = _clean(r.get("主要手术操作编码", ""))
        if cell:
            sp = _specificity(cell, case_op_codes, case_op_norms)
            if sp > 0:
                scored.append((sp, r))
        else:
            scored.append((0, r))
    scored.sort(key=lambda x: (-x[0], x[1].get("方案序号", "")))
    return [r for _, r in scored]


@dataclass
class CaseOps:
    """病例手术操作经「不纳入分组」规则清洗后的结果。"""
    main_oprn: str = ""          # 生效的主要手术操作（可能已被顺延或置空）
    related_oprn: str = ""
    conservative: bool = False   # True = 按保守治疗入组（无生效手术操作）
    notes: List[str] = field(default_factory=list)


@dataclass
class NationalMatch:
    """国家目录匹配结果（一条病例最多命中一个组）。"""
    seq: str            # 方案序号，如 BX-20（全局唯一）
    dip_code: str       # DIP 编码（组合键，见模块 docstring）
    layer: str          # 先期分组 / 并项规则 / 诊断辅助细分 / 基本规则
    group_name: str     # 分组名称（用于展示）
    main_diag: str = ""
    main_oprn: str = ""
    related_oprn: str = ""
    aux_kind: str = ""       # 烧伤类 / 肿瘤类 / 结核类
    is_grassroot: bool = False
    conservative: bool = False

    def group_key(self) -> str:
        """本地成组键：以方案序号为权威，保证与目录一一对应。"""
        return f"NAT|{self.seq}"


class NationalDirectoryV30:
    """《DIP 3.0 版分组方案》国家目录引擎。"""

    SHEET_CORE = "核心病种"
    SHEET_EXCL_DIAG = "不纳入分组_主要诊断"
    SHEET_EXCL_OPRN = "不纳入分组_主要手术操作"
    SHEET_GRASSROOT = "基层病种"
    SHEET_TB_DR = "结核耐药诊断列表"

    def __init__(self, path: str):
        self.path = str(path)
        self.rows: List[dict] = []
        self.by_seq: Dict[str, dict] = {}
        self._load()

    # ------------------------------------------------------------------
    # 载入与建索引
    # ------------------------------------------------------------------
    def _read(self, sheet: str) -> pd.DataFrame:
        return pd.read_excel(self.path, sheet_name=sheet, dtype=str, keep_default_na=False)

    def _load(self) -> None:
        core = self._read(self.SHEET_CORE)
        for _, r in core.iterrows():
            row = {k: _clean(v) for k, v in r.to_dict().items()}
            if not row.get("方案序号"):
                continue
            self.rows.append(row)
            self.by_seq[row["方案序号"]] = row

        # ---- 不纳入分组·主要诊断 ----
        self.excl_diag: Set[str] = set()
        try:
            for code in self._read(self.SHEET_EXCL_DIAG)["主要诊断编码"]:
                c = _clean(code).upper()
                if c:
                    self.excl_diag.add(c)
        except Exception:
            self.excl_diag = set()

        # ---- 不纳入分组·主要手术操作 ----
        self.excl_oprn: Dict[str, Tuple[str, Set[str]]] = {}
        try:
            df = self._read(self.SHEET_EXCL_OPRN)
            for _, r in df.iterrows():
                code = _clean(r.get("主要手术操作编码")).upper()
                if not code:
                    continue
                rule = _clean(r.get("处理规则")) or "按保守治疗入组"
                scope = {x.strip().upper() for x in _clean(r.get("限定主诊断范围")).split("|") if x.strip()}
                self.excl_oprn[code] = (rule, scope)
        except Exception:
            self.excl_oprn = {}

        # ---- 基层病种 ----
        self.grassroot_pairs: Set[Tuple[str, str]] = set()   # (诊断键, 手术操作码)
        self.grassroot_conservative: Set[str] = set()        # 仅保守治疗组的诊断键
        try:
            df = self._read(self.SHEET_GRASSROOT)
            for _, r in df.iterrows():
                d = _clean(r.get("主要诊断编码")).upper()
                if not d:
                    continue
                for op in _op_tokens(_clean(r.get("主要手术操作编码"))):
                    self.grassroot_pairs.add((d, op.upper()))
                    self.grassroot_pairs.add((d, _op_norm(op).upper()))
                if not _clean(r.get("主要手术操作编码")):
                    self.grassroot_conservative.add(d)
        except Exception:
            pass

        # ---- 结核耐药诊断列表 ----
        self.tb_dr_codes: Set[str] = set()
        try:
            for code in self._read(self.SHEET_TB_DR)["主要诊断编码"]:
                c = _clean(code).upper()
                if c:
                    self.tb_dr_codes.add(c)
        except Exception:
            self.tb_dr_codes = set()

        self._build_indexes()

    def _build_indexes(self) -> None:
        # ① 先期分组
        self._xq_op_rows: List[dict] = []     # XQ 1-15：按手术操作码匹配，按序号顺序优先
        self._xq_lbw_rows: List[dict] = []    # XQ 16-19：P07 + 天龄 + 体重
        # ② 并项规则
        self._bx_index: Dict[Tuple[str, str], List[dict]] = {}
        # ③ 诊断辅助细分
        self._fz_onco: List[dict] = []
        self._fz_burn: List[dict] = []
        self._fz_tb: List[dict] = []
        # ④ 基本规则
        self._jc_index: Dict[Tuple[str, str], List[dict]] = {}

        for row in self.rows:
            layer = row.get("成组层次", "")
            if layer == LAYER_XQ:
                if row.get("主要诊断编码") == "P07":
                    lo, hi = self._parse_weight_band(row.get("出生体重", ""))
                    days = self._parse_day_limit(row.get("天龄", ""))
                    self._xq_lbw_rows.append(
                        {"row": row, "lo": lo, "hi": hi, "days": days})
                else:
                    self._xq_op_rows.append(row)
            elif layer == LAYER_BX:
                self._index_by_diag_op(self._bx_index, row, row.get("主要手术操作编码", ""))
            elif layer == LAYER_FZ:
                kind = row.get("辅助细分类别", "")
                if kind == "肿瘤类":
                    self._fz_onco.append(row)
                elif kind == "烧伤类":
                    self._fz_burn.append(row)
                elif kind == "结核类":
                    self._fz_tb.append(row)
            elif layer == LAYER_JC:
                self._index_by_diag_op(self._jc_index, row, row.get("主要手术操作编码", ""))

        # XQ 手术操作组按序号升序（保证 XQ-13 组合组先于 XQ-14 单独组判定）
        self._xq_op_rows.sort(key=lambda r: int(re.sub(r"\D", "", r.get("方案序号", "0")) or 0))
        self._xq_lbw_rows.sort(key=lambda d: d["row"].get("方案序号", ""))

    def _index_by_diag_op(self, index: Dict[Tuple[str, str], List[dict]],
                          row: dict, oprn_cell: str):
        diag = _clean(row.get("主要诊断编码")).upper()
        tokens = _op_tokens(oprn_cell)
        if not tokens:
            index.setdefault((diag, ""), []).append(row)
            return
        for t in tokens:
            index.setdefault((diag, t.upper()), []).append(row)
            index.setdefault((diag, _op_norm(t).upper()), []).append(row)

    @staticmethod
    def _parse_weight_band(text: str) -> Tuple[int, int]:
        """解析 '出生体重0-999克' / '出生体重1000-1499克' → (下界, 上界开区间)。"""
        s = _clean(text)
        m = re.search(r"(\d+)\s*[-~至]\s*(\d+)", s)
        if m:
            return int(m.group(1)), int(m.group(2)) + 1
        m = re.search(r"(\d+)", s)
        if m:
            return 0, int(m.group(1))
        return 0, 0

    @staticmethod
    def _parse_day_limit(text: str) -> Optional[int]:
        """解析 '<29天' → 29（天龄上界，开区间）。"""
        m = re.search(r"<\s*(\d+)\s*天", _clean(text))
        return int(m.group(1)) if m else None

    # ------------------------------------------------------------------
    # 前置处理：不纳入分组
    # ------------------------------------------------------------------
    def is_excluded_diag(self, main_diag: str) -> bool:
        """主要诊断命中「不纳入分组的主要诊断列表」→ 剔除，不参与分组测算。

        ⚠️ 用户确认：**仅完全相等**才剔除。名单是全码（A09.900、A16.000、Z51.100），
        目录库用亚目/合并码（A09.9、A15-A16），两者精确交集为 0，故不会误伤目录行。
        病例填 A09.900x001 ≠ A09.900 → 不剔除（不做前缀/类目外推）。
        """
        c = _clean(main_diag).upper().replace(" ", "")
        return bool(c) and c in self.excl_diag

    def clean_operations(self, main_oprn: str, related_oprn: str,
                         main_diag: str) -> CaseOps:
        """按「不纳入分组的主要手术操作列表」三类规则清洗病例手术操作。

        1. 不可作为主要手术操作      → 该码不能当主要手术操作，顺延取下一个手术操作
        2. 按保守治疗入组            → 整条病例按保守治疗（无术式组）成组
        3. 限范围可作主要手术操作    → 主诊断在限定范围内可作主要手术操作，
                                       否则按保守治疗入组（用户确认）

        相关手术操作（用户确认按规则类型分别处理）：
          「按保守治疗入组」的码 → 相关操作中也剔除；
          「不可作为主要手术操作」「限范围可作主要手术操作」→ 保留（只是不能当主角）。
        """
        notes: List[str] = []
        diag_cands = {_icd4(main_diag), _icd3(main_diag)}
        diag_cands.discard("")

        split = lambda s: [c.strip() for c in re.split(r"[|;,、]+", _clean(s)) if c.strip()]
        seq, rel = split(main_oprn), split(related_oprn)

        effective: List[str] = []
        conservative = False
        for code in seq:
            rule, scope = self._lookup_excl_oprn(code.upper().replace(" ", ""))
            if rule is None:
                effective.append(code)
            elif rule == "不可作为主要手术操作":
                notes.append(f"{code} 不可作为主要手术操作→顺延取下一个")
            elif rule == "限范围可作主要手术操作":
                if scope and any(_in_scope(d, scope) for d in diag_cands):
                    effective.append(code)
                    notes.append(f"{code} 主诊断在限定范围内→可作主要手术操作")
                else:
                    conservative = True
                    notes.append(f"{code} 主诊断不在限定范围→按保守治疗入组")
            else:  # 按保守治疗入组
                conservative = True
                notes.append(f"{code} 按保守治疗入组→不计入术式")

        rel_keep: List[str] = []
        for code in rel:
            rule, _ = self._lookup_excl_oprn(code.upper().replace(" ", ""))
            if rule == "按保守治疗入组":
                notes.append(f"{code}(相关) 按保守治疗入组→不计入相关手术操作")
                continue
            rel_keep.append(code)

        # 「按保守治疗入组」的语义是整条病例按无术式成组，故清空生效术式
        if conservative:
            effective = []

        main = effective[0] if effective else ""
        rest = effective[1:]
        tail = [c for c in rel_keep if c not in rest]
        return CaseOps(
            main_oprn=main,
            related_oprn="|".join(rest + tail),
            conservative=(not effective),
            notes=notes,
        )

    def _lookup_excl_oprn(self, code_up: str) -> Tuple[Optional[str], Set[str]]:
        """⚠️ 用户确认：**精确匹配**，不做基码外推（否则 42 个肿瘤组会被 99.2800 误伤）。"""
        return self.excl_oprn.get(code_up, (None, set()))

    # ------------------------------------------------------------------
    # 主匹配入口
    # ------------------------------------------------------------------
    def match(self, main_diag: str, main_oprn: str = "", related_oprn: str = "",
              related_diag: str = "", day_age: int = 0,
              birth_weight: Decimal = Decimal("0"), age: int = 0,
              birth_date: str = "", admission_date: str = "") -> Optional[NationalMatch]:
        """四层顺序匹配：① 先期 → ② 并项 → ③ 诊断辅助细分 → ④ 基本规则。"""
        if self.is_excluded_diag(main_diag):
            return None

        ops = self.clean_operations(main_oprn, related_oprn, main_diag)
        # 用「清洗后」的生效操作集做匹配：不纳入分组的码已被剔除/顺延
        # 病例侧 '+' 表示同时实施（对应目录侧 AND 组），需拆开逐码匹配
        case_op_codes = {c.upper() for c in re.split(r"[|;,、+]+", ops.main_oprn) if c.strip()}
        case_op_codes |= {c.upper() for c in re.split(r"[|;,、+]+", ops.related_oprn) if c.strip()}
        case_op_norms = {_op_norm(c) for c in case_op_codes}
        case_op_norms.discard("")

        m = self._match_xq(main_diag, ops, case_op_codes, case_op_norms,
                           day_age, birth_weight, birth_date, admission_date)
        if m:
            return self._finish(m, ops)
        m = self._match_bx(main_diag, ops, case_op_codes, case_op_norms)
        if m:
            return self._finish(m, ops)
        m = self._match_fz(main_diag, related_diag, ops, case_op_codes, case_op_norms)
        if m:
            return self._finish(m, ops)
        m = self._match_jc(main_diag, ops, case_op_codes, case_op_norms)
        if m:
            return self._finish(m, ops)
        return None

    def _finish(self, row: dict, ops: CaseOps) -> NationalMatch:
        m = NationalMatch(
            seq=row.get("方案序号", ""),
            dip_code=row.get("DIP编码", ""),
            layer=row.get("成组层次", ""),
            group_name=(row.get("分组名称") or row.get("主要诊断名称")
                        or row.get("主要手术操作名称") or ""),
            main_diag=row.get("主要诊断编码", ""),
            main_oprn=row.get("主要手术操作编码", ""),
            related_oprn=row.get("相关手术操作编码", ""),
            aux_kind=row.get("辅助细分类别", ""),
            conservative=ops.conservative,
        )
        m.is_grassroot = self.is_grassroot(row.get("主要诊断编码", ""), ops.main_oprn)
        return m

    # ① 先期分组
    def _match_xq(self, main_diag, ops, case_op_codes, case_op_norms,
                  day_age, birth_weight, birth_date, admission_date) -> Optional[dict]:
        # 手术操作驱动的先期分组（XQ 1-15），不限定为主要手术操作
        for row in self._xq_op_rows:
            if _cell_matches(row.get("主要手术操作编码", ""), case_op_codes, case_op_norms):
                return row

        # 低出生体重儿（XQ 16-19）：主诊断 P07 + 天龄 <29天 + 体重分档
        if _icd3(main_diag) != "P07":
            return None
        days = self._age_in_days(day_age, birth_date, admission_date)
        if days is None:
            return None
        try:
            w = float(birth_weight)
        except Exception:
            return None
        if w <= 0:
            return None
        for item in self._xq_lbw_rows:
            limit = item["days"]
            if limit is not None and days >= limit:
                continue
            if item["lo"] <= w < item["hi"]:
                return item["row"]
        return None

    @staticmethod
    def _age_in_days(day_age, birth_date, admission_date) -> Optional[int]:
        """优先用 出生日期+入院时间 推算天数；否则用天龄字段。"""
        import datetime
        bd = _clean(birth_date)[:10]
        ad = _clean(admission_date)[:10]
        if bd and ad:
            try:
                b = datetime.datetime.strptime(bd, "%Y-%m-%d")
                a = datetime.datetime.strptime(ad, "%Y-%m-%d")
                d = (a - b).days
                if d >= 0:
                    return d
            except Exception:
                pass
        try:
            v = int(day_age or 0)
            return v if v > 0 else None
        except Exception:
            return None

    # ② 并项规则
    def _match_bx(self, main_diag, ops, case_op_codes, case_op_norms) -> Optional[dict]:
        return self._lookup_diag_op(self._bx_index, main_diag, ops, case_op_codes,
                                    case_op_norms, use_related=True)

    # ④ 基本规则
    def _match_jc(self, main_diag, ops, case_op_codes, case_op_norms) -> Optional[dict]:
        # 用户确认：JC 段无相关手术操作列 → 忽略病例的相关手术操作
        return self._lookup_diag_op(self._jc_index, main_diag, ops, case_op_codes,
                                    case_op_norms, use_related=False)

    def _lookup_diag_op(self, index, main_diag, ops: CaseOps,
                        case_op_codes, case_op_norms,
                        use_related: bool) -> Optional[dict]:
        """按 (主要诊断候选键, 生效主要手术操作) 查表；多行时按相关手术操作细分。"""
        candidates: List[dict] = []
        for dk in _diag_candidates(main_diag):
            if ops.main_oprn:
                for ok in (ops.main_oprn.upper(), _op_norm(ops.main_oprn).upper()):
                    candidates.extend(index.get((dk, ok), []))
            else:
                candidates.extend(index.get((dk, ""), []))
            if candidates:
                break
        if not candidates:
            return None

        # 去重（同一行可能被多个 token 索引到）
        seen, uniq = set(), []
        for r in candidates:
            k = r.get("方案序号")
            if k not in seen:
                seen.add(k)
                uniq.append(r)

        uniq = _pick_by_operation(uniq, case_op_codes, case_op_norms)
        if not uniq:
            return None

        if not use_related:
            return uniq[0]

        # 相关手术操作细分：相关码命中细分行；病例无相关码或未命中时回落「相关为空」的行；
        # 无「相关为空」行则未命中（用户确认口径：BX 相关手术=有则细分，不匹配回落空相关行；
        # 不应误落要求特定相关手术的行，否则 K35-47.0100 无相关手术会误入 BX-918）
        rel_codes = {c.upper() for c in re.split(r"[|;,、]+", ops.related_oprn) if c.strip()}
        rel_norms = {_op_norm(c) for c in rel_codes}
        rel_norms.discard("")
        fallback = None
        for r in uniq:
            cell = r.get("相关手术操作编码", "")
            if not _clean(cell):
                if fallback is None:
                    fallback = r
                continue
            if rel_codes and _cell_matches(cell, rel_codes, rel_norms):
                return r
        return fallback

    # ③ 诊断辅助细分
    def _match_fz(self, main_diag, related_diag, ops, case_op_codes,
                  case_op_norms) -> Optional[dict]:
        m = self._match_onco(main_diag, related_diag, ops, case_op_codes, case_op_norms)
        if m:
            return m
        m = self._match_burn(main_diag, related_diag, ops, case_op_codes, case_op_norms)
        if m:
            return m
        return self._match_tb(main_diag, related_diag, ops, case_op_codes, case_op_norms)

    def _match_onco(self, main_diag, related_diag, ops, case_op_codes,
                    case_op_norms) -> Optional[dict]:
        d4 = _icd4(main_diag)
        if d4 not in ("Z51.1", "Z51.8"):
            return None
        # 其他诊断的肿瘤范围
        ranges = set()
        for c in re.split(r"[|;,、]+", _clean(related_diag)):
            c3 = _icd3(c)
            if len(c3) == 3 and c3[0] == "C" and c3[1:3].isdigit():
                n = int(c3[1:3])
                for label, lo, hi in NEO_RANGES:
                    if lo <= n <= hi:
                        ranges.add(label)
        if not ranges:
            return None

        # 肿瘤操作列 '+' 表示 AND，按特异性优先：化疗+免疫(FZ-1771) 应胜过单化疗(FZ-1770)
        best, best_sp = None, 0
        for row in self._fz_onco:
            if _clean(row.get("主要诊断编码")).upper() != d4:
                continue
            if _clean(row.get("其他诊断编码")).upper() not in ranges:
                continue
            cell = _clean(row.get("主要手术操作编码", ""))
            if not cell:
                continue  # 肿瘤 42 组均带操作码，无保守兜底
            sp = _specificity(cell, case_op_codes, case_op_norms)
            if sp > best_sp:
                best_sp, best = sp, row
        return best

    def _match_burn(self, main_diag, related_diag, ops, case_op_codes,
                    case_op_norms) -> Optional[dict]:
        """烧伤：主诊断 3 位亚目码判程度（T20.2/.6 二度、T20.3/.7 三度，仅 T20–T25）
        + 其他诊断 T31/T32 亚目码判面积档 + 手术操作细分。不含年龄维度（方案无）。"""
        d4 = _icd4(main_diag)
        if not re.fullmatch(r"T2[0-5]\.[2367]", d4):
            return None
        rel4 = {_icd4(c) for c in re.split(r"[|;,、]+", _clean(related_diag)) if c.strip()}
        rel4.discard("")
        if not any(c.startswith(("T31", "T32")) for c in rel4):
            return None

        best, best_sp = None, 0
        for row in self._fz_burn:
            diag_codes = {x.upper() for x in _op_tokens(row.get("主要诊断编码", ""))}
            if d4 not in diag_codes:
                continue
            area_codes = {x.upper() for x in _op_tokens(row.get("其他诊断编码", ""))}
            if not (rel4 & area_codes):
                continue
            cell = _clean(row.get("主要手术操作编码", ""))
            if not cell:
                if best is None:
                    best = row  # 保守治疗兜底（特异性 0）
                continue
            sp = _specificity(cell, case_op_codes, case_op_norms)
            if sp > best_sp:
                best_sp, best = sp, row
        return best

    def _match_tb(self, main_diag, related_diag, ops, case_op_codes,
                  case_op_norms) -> Optional[dict]:
        cat = TB_CAT_MAP.get(_icd3(main_diag))
        if not cat:
            return None
        resistant = self._is_tb_resistant(main_diag, related_diag)

        fallback = None
        for row in self._fz_tb:
            if _clean(row.get("主要诊断编码")).upper() != cat:
                continue
            if (_clean(row.get("是否耐药")) == "是") != resistant:
                continue
            cell = row.get("主要手术操作编码", "")
            if not _clean(cell):
                if fallback is None:
                    fallback = row
                continue
            if _cell_matches(cell, case_op_codes, case_op_norms):
                return row
        return fallback

    def _is_tb_resistant(self, main_diag: str, related_diag: str) -> bool:
        """耐药判定：主要诊断含耐药拓展码（附表 48 条）或其他诊断含 U84.300。"""
        md = _clean(main_diag).upper().replace(" ", "")
        for code in self.tb_dr_codes:
            if md.startswith(code):
                return True
        for c in re.split(r"[|;,、]+", _clean(related_diag)):
            cu = c.upper().replace(" ", "")
            if cu.startswith("U84.3"):
                return True
        return False

    # ------------------------------------------------------------------
    # 基层病种
    # ------------------------------------------------------------------
    def is_grassroot(self, diag_key: str, main_oprn: str) -> bool:
        """基层病种判定。

        名单中「主要手术操作为空」= 仅保守治疗组（用户确认）：
        只有该诊断且无生效手术操作的病例才算；带手术操作的行按 (诊断, 术式) 匹配。
        """
        if not self.grassroot_pairs and not self.grassroot_conservative:
            return False
        op = _clean(main_oprn).upper()
        for dk in (diag_key.upper(), _icd4(diag_key), _icd3(diag_key)):
            if not dk:
                continue
            if op:
                if (dk, op) in self.grassroot_pairs:
                    return True
                if (dk, _op_norm(op).upper()) in self.grassroot_pairs:
                    return True
            elif dk in self.grassroot_conservative:
                return True
        return False


_ENGINE_CACHE: Dict[str, "NationalDirectoryV30"] = {}


def get_national_engine(path: str) -> "NationalDirectoryV30":
    """获取（并缓存）国家目录引擎实例。

    引擎为只读（仅在构造时载入目录并建索引，match/is_excluded 等均不改状态），
    跨调用安全复用，避免重复读 5-sheet xlsx + 建索引（约数秒/次）。
    """
    key = os.path.abspath(path)
    eng = _ENGINE_CACHE.get(key)
    if eng is None:
        eng = NationalDirectoryV30(path)
        _ENGINE_CACHE[key] = eng
    return eng


def _in_scope(diag_cand: str, scope: Set[str]) -> bool:
    """判断诊断候选键（类目/亚目）是否落在限定范围集合内。"""
    for s in scope:
        if not s:
            continue
        if "-" in s:  # 区间，形如 C00-C75 / K20-K93
            lo, hi = s.split("-", 1)
            if len(lo) == len(diag_cand) == len(hi) and lo <= diag_cand <= hi:
                return True
            if diag_cand.startswith(lo[:3]):
                n_lo = re.sub(r"\D", "", lo)
                n_hi = re.sub(r"\D", "", hi)
                n_d = re.sub(r"\D", "", diag_cand)
                if n_lo and n_hi and n_d and n_lo.isdigit() and n_hi.isdigit() and n_d.isdigit():
                    if int(n_lo) <= int(n_d) <= int(n_hi):
                        return True
            continue
        if diag_cand.startswith(s):
            return True
    return False
