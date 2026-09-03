"""
DIP测算工具 - 简单测试界面
"""
import pytest
tk = pytest.importorskip("tkinter")
from tkinter import ttk
import sys, os
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decimal import Decimal
from src.core.calculation_config import (
    DIPCalculationConfig, CostType, CostCalculationConfig, StatisticalConfig,
    create_default_config, create_full_config
)
from src.core.local_directory_score_configurable import LocalDirectoryScoreCalculator
from src.models.models import MedicalRecord


def generate_test_records():
    records = []
    for i in range(20):
        records.append(MedicalRecord(
            record_id=f"R{i+1:04d}", settlement_id=f"S{i+1:04d}",
            patient_id=f"P{i+1:04d}", visit_id=f"V{i+1:04d}",
            hospital_code="H001", hospital_name="Hospital A", hospital_level="3A",
            main_diag_code="I21.0", main_diag_name="Acute MI",
            total_cost=Decimal(str(15000 + i * 500)),
            drug_cost=Decimal(str(6000 + i * 200)),
            material_cost=Decimal(str(4000 + i * 150)),
            admission_date="2024-01-15", discharge_date="2024-01-27", los=12,
            discharge_status="Cured", dip_disease_code="I21-1"
        ))
    for i in range(15):
        records.append(MedicalRecord(
            record_id=f"R{i+21:04d}", settlement_id=f"S{i+21:04d}",
            patient_id=f"P{i+21:04d}", visit_id=f"V{i+21:04d}",
            hospital_code="H002", hospital_name="Hospital B", hospital_level="2A",
            main_diag_code="K35.9", main_diag_name="Appendicitis",
            total_cost=Decimal(str(10000 + i * 400)),
            drug_cost=Decimal(str(3000 + i * 150)),
            material_cost=Decimal(str(2500 + i * 100)),
            admission_date="2024-02-10", discharge_date="2024-02-18", los=8,
            discharge_status="Cured", dip_disease_code="K35-1"
        ))
    return records


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("DIP Calculation Tool")
        self.root.geometry("900x600")
        
        self.records = generate_test_records()
        self.config = create_default_config()
        self.calculator = LocalDirectoryScoreCalculator(self.config)
        
        # Top frame - Config
        top = ttk.LabelFrame(root, text="Configuration", padding=10)
        top.pack(fill=tk.X, padx=10, pady=5)
        
        self.cost_vars = {}
        costs = [("Total", CostType.TOTAL), ("Drug", CostType.DRUG), ("Material", CostType.MATERIAL)]
        for i, (name, ct) in enumerate(costs):
            var = tk.BooleanVar(value=(ct == CostType.TOTAL))
            self.cost_vars[ct] = var
            ttk.Checkbutton(top, text=name, variable=var).grid(row=0, column=i, padx=10)
        
        self.stat_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="Remove Outliers", variable=self.stat_var).grid(row=0, column=3, padx=10)
        
        ttk.Button(top, text="Calculate", command=self.calculate).grid(row=0, column=4, padx=20)
        
        # Bottom frame - Results
        bottom = ttk.LabelFrame(root, text="Results", padding=10)
        bottom.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        columns = ('DIP Code', 'Cases', 'Score', 'Drug Avg', 'Material Avg')
        self.tree = ttk.Treeview(bottom, columns=columns, show='headings', height=15)
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=120)
        self.tree.pack(fill=tk.BOTH, expand=True)
        
        self.calculate()
    
    def calculate(self):
        cost_configs = []
        for ct, var in self.cost_vars.items():
            if var.get():
                cost_configs.append(CostCalculationConfig(cost_type=ct, enabled=True))
        
        if not cost_configs:
            cost_configs = [CostCalculationConfig(cost_type=CostType.TOTAL, enabled=True)]
        
        self.config = DIPCalculationConfig(
            cost_configs=cost_configs,
            statistical_config=StatisticalConfig(remove_outliers=self.stat_var.get())
        )
        self.calculator = LocalDirectoryScoreCalculator(self.config)
        
        results = self.calculator.batch_calculate_local_directory(self.records)
        
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        for dip_code, result in sorted(results.items()):
            stats = result.get('cost_statistics', {})
            drug_avg = stats.get('Drug Cost', {}).get('average', 'N/A')
            mat_avg = stats.get('Material Cost', {}).get('average', 'N/A')
            
            self.tree.insert('', 'end', values=(
                dip_code,
                result['total_cases'],
                f"{float(result['final_score']):.2f}",
                f"{float(drug_avg):.2f}" if drug_avg != 'N/A' else 'N/A',
                f"{float(mat_avg):.2f}" if mat_avg != 'N/A' else 'N/A'
            ))


def test_simple_generate_records():
    recs = generate_test_records()
    assert len(recs) == 35
    assert len([r for r in recs if r.main_diag_code == "I21.0"]) == 20
    assert len([r for r in recs if r.main_diag_code == "K35.9"]) == 15
    for r in recs:
        assert r.dip_disease_code


def test_simple_batch_calculation():
    recs = generate_test_records()
    results = LocalDirectoryScoreCalculator(
        create_default_config()
    ).batch_calculate_local_directory(recs)
    assert set(results.keys()) == {"I21-1", "K35-1"}
    assert sum(v["total_cases"] for v in results.values()) == 35
    for v in results.values():
        assert float(v["final_score"]) > 0
        assert float(v["hospital_coefficient"]) > 0


def test_simple_gui_wires_tree():
    pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except Exception:
        pytest.skip("no display available")
    try:
        app = App(root)
        children = app.tree.get_children()
        assert len(children) == 2
        for c in children:
            vals = app.tree.item(c, "values")
            assert float(vals[2]) > 0  # 分值列
    finally:
        root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
