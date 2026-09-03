import sys, time, faulthandler
faulthandler.dump_traceback_later(45, exit=True)  # 45s 后若仍卡，打印堆栈并退出
sys.path.insert(0, 'F:/DIP')
import pandas as pd

from src.interfaces.settlement_importer import SettlementDataImporter
from src.core.local_directory_generator import LocalDirectoryGenerator
from src.core.value_calculator_selectable import DIPValueCalculator, create_average_cost_config
from src.core.hospital_coefficient_selector import HospitalCoefficientSelector, create_basic_bonus_config
from src.core.auxiliary_directory_exporter import AuxiliaryDirectoryExporter

PATH = 'F:/DIP/output/qk_merged_settlement.xlsx'
print('reading', PATH, flush=True)
df = pd.read_excel(PATH)
print('rows in xlsx:', len(df), flush=True)

imp = SettlementDataImporter()
res = imp.import_from_dataframe(df)
records = res.records
print('records:', len(records), flush=True)

gen = LocalDirectoryGenerator(15)
t = time.time()
gen.load_national_directory('F:/DIP/data/DIP3.0国家目录库.xlsx')
print('load_national_directory: %.2fs' % (time.time() - t), flush=True)

# ---- grouping 阶段 ----
t = time.time()
temp = {}
for i, r in enumerate(records):
    ck, layer = gen._refine_core_group_key(
        r.main_diag_code, r.main_oprn_code, r.related_oprn_code, r.related_diag_code,
        day_age=getattr(r, 'day_age', None), birth_weight=getattr(r, 'birth_weight', None),
        age=getattr(r, 'age', None), birth_date=getattr(r, 'birth_date', None),
        admission_date=getattr(r, 'admission_date', None))
    r.dip_disease_code = ck  # 复现 Web：grouping 后回填
    temp[ck] = temp.get(ck, 0) + 1
print('grouping: %.2fs  unique_groups=%d' % (time.time() - t, len(temp)), flush=True)

# ---- done_batch: 病种分值 ----
t = time.time()
vc = DIPValueCalculator(create_average_cost_config())
vr = vc.calculate_all_values(records)
print('calculate_all_values: %.2fs  results=%d' % (time.time() - t, len(vr)), flush=True)

# ---- done_batch: 医院系数 ----
t = time.time()
hs = HospitalCoefficientSelector(create_basic_bonus_config())
hs_set = {}
for r in records:
    if r.hospital_code not in hs_set:
        hs_set[r.hospital_code] = {
            'hospital_code': r.hospital_code,
            'hospital_name': getattr(r, 'hospital_name', ''),
            'hospital_level': getattr(r, 'hospital_level', '')}
hr = hs.batch_calculate(list(hs_set.values()), records)
print('hospital batch_calculate: %.2fs  results=%d' % (time.time() - t, len(hr)), flush=True)

# ---- done_batch: 辅助目录 ----
t = time.time()
ax = AuxiliaryDirectoryExporter()
ar = ax.classify_records(records)
print('classify_records: %.2fs  results=%d' % (time.time() - t, len(ar)), flush=True)

print('ALL DONE', flush=True)
