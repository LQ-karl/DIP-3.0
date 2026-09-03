"""
DIP按病种分值分组测算工具 - 辅助目录分型表格模块
基于《国家医疗保障按病种分值(DIP)付费3.0版技术规范》
功能：辅助目录分型单独形成表格输出
"""
import pandas as pd
from typing import List, Dict, Optional
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from ..models.models import MedicalRecord
from .auxiliary_directory import AuxiliaryDirectoryCalculator, AuxiliarySubgroup


class AuxiliaryDirectoryExporter:
    """辅助目录分型导出器"""
    
    # 注：CCI / 严重程度 / 年龄 / ICU 的分级与系数不再在此硬编码，统一委托主引擎
    # （auxiliary_directory.py 的 CCICalculator / DiseaseSeverityClassifier /
    # AgeFeatureClassifier / ICUStayClassifier），保证与 CLI 主流程（apply_auxiliary_typing）
    # 使用同一套规则、命名与系数，消除双实现结论打架（B4）。

    def __init__(self):
        # 统一委托主引擎
        self.calculator = AuxiliaryDirectoryCalculator()

    # ------------------------------------------------------------------
    # 辅助分型测算门控阈值（严格贴合 DIP3.0 §5.2 触发条件三条）。
    # 该门控与地方「核心病种成组阈值」完全解耦：无论核心病种成组阈值怎么设，
    # 辅助分型只有在「病种病例数 > AUX_MIN_CORE_CASES」且「某分型评估病例数 >
    # AUX_MIN_SUBTYPE_CASES」且「组内费用 CV 偏大(cv_before >= 阈值) 且 分型后
    # 组内费用 CV 下降 >= AUX_CV_IMPROVEMENT_THRESHOLD」时才测算；否则该维度
    # 不拆分。维度竞争取「触发系数(mj/M)最高」者胜出。
    # ------------------------------------------------------------------
    AUX_MIN_CORE_CASES: int = 10       # 触发条件(1)：病种病例数须 > 10
    AUX_MIN_SUBTYPE_CASES: int = 5     # 触发条件(2)：某分型评估病例数须 > 5
    AUX_CV_BEFORE_THRESHOLD: float = 0.7      # 触发条件(3)-组内CV偏大门槛（遴选CV>0.7引入辅助分型）
    AUX_CV_IMPROVEMENT_THRESHOLD: float = 0.2  # 触发条件(3)-分型后CV下降≥20%
    AUX_ICU_RELAX_FACTOR: float = 0.5          # 监护病房触发条件适当放宽

    @staticmethod
    def _compute_cv(values) -> float:
        """变异系数 CV = 标准差 / 均值（费用波动程度）。空/均值为 0 时返回 0。"""
        n = len(values)
        if n == 0:
            return 0.0
        mean = sum(values) / n
        if mean == 0:
            return 0.0
        var = sum((v - mean) ** 2 for v in values) / n
        return (var ** 0.5) / mean


    def classify_records(
        self,
        records: List[MedicalRecord],
        aux_min_core_cases: int = AUX_MIN_CORE_CASES,
        aux_min_subtype_cases: int = AUX_MIN_SUBTYPE_CASES,
        aux_cv_before_threshold: float = AUX_CV_BEFORE_THRESHOLD,
        aux_cv_improvement_threshold: float = AUX_CV_IMPROVEMENT_THRESHOLD,
        aux_icu_relax_factor: float = AUX_ICU_RELAX_FACTOR,
        core_disease_codes: Optional[set] = None,
    ) -> List[AuxiliarySubgroup]:
        """对核心病种记录做**子组级**辅助分型聚类（委托统一引擎，贴合 DIP3.0 §5.2）。

        行为（与 DIP3.0 规范及用户口径一致）：
          - 辅助分型发生在「核心病种聚类成组之后」，针对组内费用偏高的病例，
            结合 CCI / 疾病严重程度 / 年龄 / 监护病房 等多维度「再次聚类」成子型组，
            返回子组级列表（每条 = 核心病种 x 维度 x 子型），而非逐病例一条。
          - 仅对核心病种（达地方阈值）测算：传 core_disease_codes 时过滤，
            综合病种（未达阈值折叠）不出现在辅助目录中。
          - 触发条件（闸门）：病种病例数 > 阈值 且 某分型评估病例数 > 阈值 且
            【组内费用 CV 偏大(cv_before >= 阈值) 且 分型后组内费用 CV 下降 ≥ 20%】
            才测算；否则该维度不拆；所有维度均未达标则该病种不产生任何辅助子组。
          - 维度竞争：多个达标维度中取「触发系数(mj/M)最高」者作为实际应用维度。
          - 子型系数：CCI 查表固定系数（不纳入 mj/M）；其余维度 = mj / M。
        """
        return self.calculator.build_auxiliary_subgroups(
            records,
            core_disease_codes=core_disease_codes,
            min_core_cases=aux_min_core_cases,
            min_subtype_cases=aux_min_subtype_cases,
            cv_before_threshold=aux_cv_before_threshold,
            cv_improvement_threshold=aux_cv_improvement_threshold,
            icu_relax_factor=aux_icu_relax_factor,
        )
    
    def export_to_excel(
        self,
        subgroups: List[AuxiliarySubgroup],
        output_path: str
    ) -> str:
        """导出辅助分型子组到 Excel（子组级，与测算口径一致）。

        Args:
            subgroups: AuxiliarySubgroup 列表（来自 classify_records）。
            output_path: 输出文件路径。
        Returns:
            输出文件路径。
        """
        cols = ["核心病种编码","核心病种名称","分型维度","亚型","病例数",
                "子组均费","辅助分型系数","触发系数(mj/M)","组内CV(分型前)",
                "组内CV(分型后)","CV下降幅度","竞争胜出维度","低频合并"]
        rows = [s.to_dict() for s in subgroups]
        df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=cols)

        stats = []
        if subgroups:
            from collections import Counter
            dim_counter = Counter(s.dimension for s in subgroups)
            for dim, cnt in sorted(dim_counter.items()):
                stats.append({"统计项": f"分型维度-{dim}", "子组数": cnt})
            stats.append({"统计项": "子组总数", "子组数": len(subgroups)})
        stats_df = (pd.DataFrame(stats)
                    if stats else pd.DataFrame(columns=["统计项", "子组数"]))

        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="辅助分型子组", index=False)
            stats_df.to_excel(writer, sheet_name="统计汇总", index=False)
        return output_path

def create_auxiliary_exporter() -> AuxiliaryDirectoryExporter:
    """创建辅助目录导出器"""
    return AuxiliaryDirectoryExporter()
