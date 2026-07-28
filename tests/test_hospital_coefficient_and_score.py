"""
测试医疗机构等级系数测算和本地目录库分值测算（真实断言版）
"""
import sys
sys.path.insert(0, 'F:/DIP')

from decimal import Decimal
from src.core.hospital_coefficient import HospitalCoefficientCalculator, HospitalLevelClassifier
from src.core.local_directory_score import LocalDirectoryScoreCalculator
from src.models.models import MedicalRecord


def generate_test_records():
    """生成测试病例数据（2 个病种：I21-1×20, K35-1×15）"""
    records = []

    for i in range(20):  # 三级甲等 - 心内科 急性心肌梗死
        records.append(MedicalRecord(
            record_id=f"REC{i+1:04d}", settlement_id=f"SET{i+1:04d}", patient_id=f"P{i+1:04d}",
            visit_id=f"V{i+1:04d}", hospital_code="H001", hospital_name="市人民医院",
            hospital_level="三级甲等", main_diag_code="I21.0", main_diag_name="急性心肌梗死",
            related_diag_code="E11.9,I10", main_oprn_code="36.07",
            total_cost=Decimal(str(15000 + i * 500)), drug_cost=Decimal(str(6000 + i * 200)),
            material_cost=Decimal(str(4000 + i * 150)), admission_date="2024-01-15",
            discharge_date="2024-01-27", los=12, discharge_status="治愈", dip_disease_code="I21-1",
        ))

    for i in range(15):  # 二级甲等 - 普外科 急性阑尾炎
        records.append(MedicalRecord(
            record_id=f"REC{i+21:04d}", settlement_id=f"SET{i+21:04d}", patient_id=f"P{i+21:04d}",
            visit_id=f"V{i+21:04d}", hospital_code="H002", hospital_name="区中心医院",
            hospital_level="二级甲等", main_diag_code="K35.9", main_diag_name="急性阑尾炎",
            main_oprn_code="47.0", total_cost=Decimal(str(10000 + i * 400)),
            drug_cost=Decimal(str(3000 + i * 150)), material_cost=Decimal(str(2500 + i * 100)),
            admission_date="2024-02-10", discharge_date="2024-02-18", los=8,
            discharge_status="治愈", dip_disease_code="K35-1",
        ))

    return records


def test_hospital_level_classifier():
    """医院等级分类器：基础分值 > 0；专科输入应识别专科。"""
    classifier = HospitalLevelClassifier()

    cases = [
        ("三级甲等", ""),
        ("二级甲等", "儿童"),
        ("三级乙等", "肿瘤"),
        ("一级", ""),
        ("未定级", "精神"),
    ]
    specialty_cases = {("二级甲等", "儿童"), ("三级乙等", "肿瘤"), ("未定级", "精神")}

    for level, specialty in cases:
        result = classifier.classify_hospital(level, specialty)
        assert isinstance(result, dict), "classify_hospital 应返回 dict"
        for key in ("level", "level_name", "type", "base_score"):
            assert key in result, f"返回缺少键: {key}"
        assert result['base_score'] > 0, f"{level}{specialty} 基础分值应 > 0"
        if (level, specialty) in specialty_cases:
            assert result['specialty'] is not None, f"{level}{specialty} 应识别出专科"
        else:
            assert result['specialty'] is None, f"{level}{specialty} 不应有专科"


def test_hospital_coefficient_calculator():
    """医院调节系数：基本/总系数 > 0；批量计算 3 家医院。"""
    calculator = HospitalCoefficientCalculator()

    hospital_data = {
        'hospital_code': 'H001', 'hospital_name': '市人民医院', 'hospital_level': '三级甲等',
        'avg_cost': 18000, 'medical_level': 0.85, 'specialty_score': 0.75,
        'cmi': 1.2, 'performance_score': 0.9, 'agreement_score': 0.85,
    }
    city_avg_cost = Decimal("15000")

    result = calculator.calculate_hospital_coefficient(hospital_data, city_avg_cost)
    assert result.hospital_name == '市人民医院'
    assert isinstance(result.basic_coefficient, Decimal) and result.basic_coefficient > 0
    assert isinstance(result.total_coefficient, Decimal) and result.total_coefficient > 0

    hospital_data_list = [
        dict(hospital_data),
        {'hospital_code': 'H002', 'hospital_name': '区中心医院', 'hospital_level': '二级甲等',
         'avg_cost': 12000, 'medical_level': 0.7, 'specialty_score': 0.65,
         'cmi': 0.9, 'performance_score': 0.8, 'agreement_score': 0.8},
        {'hospital_code': 'H003', 'hospital_name': '社区卫生服务中心', 'hospital_level': '一级',
         'avg_cost': 6000, 'medical_level': 0.5, 'specialty_score': 0.4,
         'cmi': 0.6, 'performance_score': 0.7, 'agreement_score': 0.75},
    ]
    results = calculator.batch_calculate(hospital_data_list, city_avg_cost)
    assert len(results) == 3, f"批量计算应返回 3 家医院，实际 {len(results)}"
    codes = {r.hospital_code for r in results}
    assert codes == {"H001", "H002", "H003"}
    for r in results:
        assert r.total_coefficient > 0, f"{r.hospital_code} 总调节系数应 > 0"


def test_local_directory_score_calculator():
    """本地目录库分值测算：单病种/批量/全市统计均健全。"""
    calculator = LocalDirectoryScoreCalculator()
    records = generate_test_records()

    # 单病种
    for dip_code in ("I21-1", "K35-1"):
        result = calculator.calculate_local_directory_score(records, dip_code)
        assert result.total_cases > 0, f"{dip_code} 病例数应 > 0"
        assert result.value_per_point > 0, f"{dip_code} 分值应 > 0"
        assert result.average_cost > 0, f"{dip_code} 平均费用应 > 0"

    # 批量
    batch_results = calculator.batch_calculate_local_directory(records)
    assert set(batch_results.keys()) == {"I21-1", "K35-1"}
    assert batch_results["I21-1"].total_cases == 20
    assert batch_results["K35-1"].total_cases == 15

    # 全市统计
    city_stats = calculator.calculate_city_wide_statistics(records)
    assert city_stats['total_cases'] == 35, f"全市病例数应为 35，实际 {city_stats['total_cases']}"
    assert city_stats['dip_codes'] == 2, "全市 DIP 分组数应为 2"
    assert city_stats['total_cost'] > 0, "全市总费用应 > 0"
    assert city_stats['average_cost'] > 0, "全市平均费用应 > 0"
    assert city_stats['average_los'] > 0, "全市平均住院天数应 > 0"


if __name__ == "__main__":
    test_hospital_level_classifier()
    test_hospital_coefficient_calculator()
    test_local_directory_score_calculator()
    print("test_hospital_coefficient_and_score 全部通过")
