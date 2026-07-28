"""
DIP辅助目录测算 - 测试脚本（真实断言版）
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decimal import Decimal
from src.models.models import MedicalRecord
from src.core.auxiliary_directory import (
    CCICalculator, DiseaseSeverityClassifier, AgeFeatureClassifier,
    ViolationBehaviorClassifier, AuxiliaryDirectoryCalculator
)


def test_cci_calculator():
    """CCI 计算器：分数与分级符合 Charlson 合并症指数逻辑。"""
    calculator = CCICalculator()

    cases = {
        ("I21.0", "E11.9"): 2,   # 心梗(1) + 糖尿病(1)
        ("J44.1", "I50.0"): 2,   # COPD(1) + 心衰(1)
        ("C34.1", "E11.3"): 3,   # 肺癌(2) + 糖尿病并发症
        ("K80.2",): 0,           # 胆囊结石（无 Charlson 组成部分）
        ("I10", "E11.9"): 1,     # 高血压(0) + 糖尿病(1)
    }

    for diagnoses, expected in cases.items():
        score = calculator.calculate_cci(list(diagnoses))
        level, coeff = calculator.get_cci_level(score)
        assert isinstance(score, int) and score >= 0, "CCI 分数应为非负整数"
        assert score == expected, f"诊断 {diagnoses} 的 CCI 应为 {expected}，实际 {score}"
        assert isinstance(level, str) and level, "CCI 分级应为非空字符串"
        assert isinstance(coeff, Decimal) and coeff > 0, "CCI 调节系数应 > 0"


def test_severity_classifier():
    """疾病严重程度分型：非恶性（肾衰竭相关）→ 重度；恶性 → 一般。"""
    classifier = DiseaseSeverityClassifier()

    record1 = MedicalRecord(
        record_id="R001", settlement_id="S001", patient_id="P001",
        visit_id="V001", hospital_code="H001", hospital_name="测试医院",
        main_diag_code="K35.9", main_diag_name="急性阑尾炎",
        related_diag_code="N17.0", discharge_status="医嘱离院", los=5,
    )
    result1 = classifier.classify_non_malignant(record1)
    assert result1['level'] == '重度', f"非恶性(肾衰竭相关)应判重度，实际 {result1['level']}"
    assert result1['coefficient'] == Decimal("1.3")

    record2 = MedicalRecord(
        record_id="R002", settlement_id="S002", patient_id="P002",
        visit_id="V002", hospital_code="H001", hospital_name="测试医院",
        main_diag_code="C34.1", main_diag_name="肺恶性肿瘤",
        total_cost=Decimal("80000"), drug_cost=Decimal("45000"),
        treatment_cost=Decimal("5000"), discharge_status="医嘱离院", los=15,
    )
    avg_cost = Decimal("30000")
    result2 = classifier.classify_malignant_tumor(record2, avg_cost, avg_cost * 2)
    # DIP3.0 规范 7 亚型：未命中死亡/高费用/转移/衰竭/器官病损 → 兜底"其他"
    assert result2['level'] == '其他', f"恶性肿瘤默认应判其他，实际 {result2['level']}"
    assert result2['coefficient'] == Decimal("1.0")
    assert result2['condition'], "恶性肿瘤分型应给出触发条件"


def test_age_classifier():
    """年龄特征分型（DIP3.0）：18岁以下与65岁以上分型，成人不适用。

    儿科段：0-28天 / 29天-1周岁 / 1-6岁 / 7-17岁；
    老年段：65-69岁 / 70-79岁 / 80岁以上。
    """
    classifier = AgeFeatureClassifier()
    # (年龄, 期望 sub_level)
    expectations = [
        (0, '29天-1周岁'),   # 未提供天龄时不足1周岁默认 29天-1周岁
        (3, '1-6岁'),
        (8, '7-17岁'),
        (15, '7-17岁'),
        (67, '65-69岁'),
        (78, '70-79岁'),
        (88, '80岁以上'),
    ]

    for age, expected_sub in expectations:
        record = MedicalRecord(
            record_id="R001", settlement_id="S001", patient_id="P001",
            visit_id="V001", hospital_code="H001", hospital_name="测试医院",
            main_diag_code="J18.9", main_diag_name="肺炎", age=age,
        )
        result = classifier.classify(record)
        assert result is not None, f"年龄 {age} 岁应产生年龄分型"
        assert result['coefficient'] > 0, f"年龄 {age} 岁的调节系数应 > 0"
        assert result['sub_level'] == expected_sub, \
            f"年龄 {age} 岁分型应为 {expected_sub}，实际 {result['sub_level']}"

    # 成人(18-64岁)不适用年龄特征分型
    adult = MedicalRecord(
        record_id="R002", settlement_id="S002", patient_id="P002",
        visit_id="V002", hospital_code="H001", hospital_name="测试医院",
        main_diag_code="J18.9", main_diag_name="肺炎", age=40,
    )
    assert classifier.classify(adult) is None, "成人(18-64岁)不应产生年龄分型"


def test_violation_classifier():
    """违规行为评分：低标入院(25%)与超长住院(4.17倍)均判高风险。"""
    classifier = ViolationBehaviorClassifier()

    record = MedicalRecord(
        record_id="R001", settlement_id="S001", patient_id="P001",
        visit_id="V001", hospital_code="H001", hospital_name="测试医院",
        main_diag_code="K35.9", main_diag_name="急性阑尾炎", total_cost=Decimal("3000"),
    )
    rla = classifier.calculate_rla_score(record, Decimal("12000"))
    assert rla['risk_level'] == '高风险', f"费用 25% 应判高风险，实际 {rla['risk_level']}"
    assert rla['score'] == Decimal("1.0")

    record2 = MedicalRecord(
        record_id="R002", settlement_id="S002", patient_id="P002",
        visit_id="V002", hospital_code="H001", hospital_name="测试医院",
        main_diag_code="K35.9", main_diag_name="急性阑尾炎", los=25,
    )
    ext = classifier.calculate_extended_stay_score(record2, Decimal("6"))
    assert ext['risk_level'] == '高风险', f"超长住院应判高风险，实际 {ext['risk_level']}"


def test_auxiliary_calculator():
    """辅助目录综合计算：CCI/年龄/合计系数均健全。"""
    calculator = AuxiliaryDirectoryCalculator()
    record = MedicalRecord(
        record_id="R001", settlement_id="S001", patient_id="P001",
        visit_id="V001", hospital_code="H001", hospital_name="测试医院",
        main_diag_code="I21.0", main_diag_name="急性心肌梗死",
        main_oprn_code="36.0700", main_oprn_name="冠状动脉支架置入",
        related_diag_code="E11.3", total_cost=Decimal("45000"),
        drug_cost=Decimal("12000"), consumable_cost=Decimal("25000"),
        treatment_cost=Decimal("3000"), discharge_status="医嘱离院", los=12, age=72,
    )
    result = calculator.calculate_all_auxiliary_coefficients(
        record=record, disease_avg_cost=Decimal("35000"),
        disease_avg_los=Decimal("10"), disease_mortality_rate=Decimal("0.03"),
    )

    assert result['cci']['score'] == 2, f"CCI 应为 2，实际 {result['cci']['score']}"
    # DIP3.0 规范 CCI 四级：1-2 分 = 一般，系数 1.1
    assert result['cci']['level'] == '一般'
    assert result['cci']['coefficient'] == Decimal("1.1")
    assert result['severity']['level'] == '轻度'
    assert '老年' in result['age']['level'], f"72 岁应归老年，实际 {result['age']['level']}"
    assert result['age']['sub_level'] == '70-79岁'
    assert result['max_coefficient'] == Decimal("1.1"), \
        f"最高调节系数应为 1.1，实际 {result['max_coefficient']}"
    assert isinstance(result['violation'], dict), "violation 应为 dict"


if __name__ == "__main__":
    test_cci_calculator()
    test_severity_classifier()
    test_age_classifier()
    test_violation_classifier()
    test_auxiliary_calculator()
    print("test_auxiliary 全部通过")
