"""验证辅助目录结果系数口径：
- 年龄特征 = mj/M（数据驱动）；CCI = 自身查表法（不变）
"""
import sys
sys.path.insert(0, "F:/DIP")
from decimal import Decimal
from collections import defaultdict
from src.models.models import MedicalRecord
from src.core.auxiliary_directory_exporter import AuxiliaryDirectoryExporter

# 同一核心病种 N18.5-01，三个年龄段、费用差异明显：
# 1-6岁 10例 各 5000；70-79岁 8例 各 15000；80岁以上 6例 各 30000
# M = 350000/24 ≈ 14583
# 期望 age_coefficient: 1-6岁≈0.343；70-79岁≈1.029；80岁以上≈2.057
recs = []
i = 0
for n, cost, age in [(10, 5000.0, 3), (8, 15000.0, 70), (6, 30000.0, 85)]:
    for _ in range(n):
        recs.append(MedicalRecord(
            record_id=f"R{i}", settlement_id=f"R{i}", patient_id=f"R{i}", visit_id=f"R{i}",
            hospital_code="H001", hospital_name="t",
            dip_disease_code="N18.5-01", main_diag_code="N18.5", main_diag_name="慢性肾脏病5期",
            total_cost=Decimal(str(cost)), age=age,
        ))
        i += 1

exp = AuxiliaryDirectoryExporter()
out = exp.classify_records(recs)

agg = defaultdict(set)
for c in out:
    agg[c.age_type].add(round(float(c.age_coefficient), 4))
print("M(病种均费)≈14583  期望 age_coefficient: 1-6岁≈0.343 / 70-79岁≈1.029 / 80岁以上≈2.057")
for lvl, vals in sorted(agg.items()):
    print(f"  age_type={lvl!r}: age_coefficient={vals}")

cci_set = {c.cci_type for c in out}
cci_coeff = {round(float(c.cci_coefficient), 4) for c in out}
print("CCI type:", cci_set, " CCI 系数(应=查表,本例无合并症=1.0):", cci_coeff)
