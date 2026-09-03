import sys
sys.path.insert(0, 'F:/DIP')
import pandas as pd
from collections import Counter
from src.interfaces.settlement_importer import SettlementDataImporter
from src.core.local_directory_generator import LocalDirectoryGenerator

df = pd.read_excel('F:/DIP/output/qk_merged_settlement.xlsx')
imp = SettlementDataImporter()
res = imp.import_from_dataframe(df)
recs = res.records
print('records:', len(recs))
r = recs[0]
for a in ['main_diag_code', 'main_oprn_code', 'related_oprn_code', 'related_diag_code',
          'day_age', 'birth_weight', 'age', 'main_diag_name']:
    print('  ', a, '=', repr(getattr(r, a, None)))

gen = LocalDirectoryGenerator(15)
gen.load_national_directory('F:/DIP/data/DIP3.0国家目录库.xlsx')
c = Counter()
for r in recs:
    ck, l = gen._refine_core_group_key(
        r.main_diag_code, r.main_oprn_code, r.related_oprn_code, r.related_diag_code,
        day_age=getattr(r, 'day_age', None), birth_weight=getattr(r, 'birth_weight', None),
        age=getattr(r, 'age', None))
    c[ck] += 1
print('distinct cluster keys:', len(c))
for k, v in c.most_common(8):
    print('   ', v, k)
