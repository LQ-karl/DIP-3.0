"""
DIP测算工具 - 图形化测试界面（带错误捕获）
"""
import tkinter as tk
from tkinter import ttk, messagebox
import sys
import traceback

sys.path.insert(0, 'F:/DIP')

from decimal import Decimal
from src.core.calculation_config import (
    DIPCalculationConfig, CostType, CalculationType,
    CostCalculationConfig, StatisticalConfig,
    create_default_config, create_full_config,
    create_drug_material_config, create_simple_config
)
from src.core.local_directory_score_configurable import LocalDirectoryScoreCalculator
from src.models.models import MedicalRecord, HospitalCoefficient


# 日志文件
LOG_FILE = "F:/DIP/gui_log.txt"

def log(msg):
    """写日志"""
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")
    print(msg)


def generate_test_records():
    """生成测试病例数据"""
    records = []
    
    for i in range(20):
        records.append(MedicalRecord(
            record_id=f"REC{i+1:04d}",
            settlement_id=f"SET{i+1:04d}",
            patient_id=f"P{i+1:04d}",
            visit_id=f"V{i+1:04d}",
            hospital_code="H001",
            hospital_name="City Hospital",
            hospital_level="Level 3A",
            main_diag_code="I21.0",
            main_diag_name="Acute MI",
            related_diag_code="E11.9,I10",
            main_oprn_code="36.07",
            total_cost=Decimal(str(15000 + i * 500)),
            drug_cost=Decimal(str(6000 + i * 200)),
            material_cost=Decimal(str(4000 + i * 150)),
            consumable_cost=Decimal(str(2000 + i * 100)),
            exam_cost=Decimal(str(1500 + i * 50)),
            treatment_cost=Decimal(str(1000 + i * 30)),
            nursing_cost=Decimal(str(500 + i * 20)),
            admission_date="2024-01-15",
            discharge_date="2024-01-27",
            los=12,
            discharge_status="Cured",
            dip_disease_code="I21-1"
        ))
    
    for i in range(15):
        records.append(MedicalRecord(
            record_id=f"REC{i+21:04d}",
            settlement_id=f"SET{i+21:04d}",
            patient_id=f"P{i+21:04d}",
            visit_id=f"V{i+21:04d}",
            hospital_code="H002",
            hospital_name="District Hospital",
            hospital_level="Level 2A",
            main_diag_code="K35.9",
            main_diag_name="Acute Appendicitis",
            main_oprn_code="47.0",
            total_cost=Decimal(str(10000 + i * 400)),
            drug_cost=Decimal(str(3000 + i * 150)),
            material_cost=Decimal(str(2500 + i * 100)),
            consumable_cost=Decimal(str(1500 + i * 80)),
            exam_cost=Decimal(str(1000 + i * 40)),
            treatment_cost=Decimal(str(800 + i * 25)),
            nursing_cost=Decimal(str(400 + i * 15)),
            admission_date="2024-02-10",
            discharge_date="2024-02-18",
            los=8,
            discharge_status="Cured",
            dip_disease_code="K35-1"
        ))
    
    return records


class DIPCalculationGUI:
    def __init__(self, root):
        log("Initializing GUI...")
        self.root = root
        self.root.title("DIP Calculation Tool")
        self.root.geometry("1000x700")
        
        self.config = create_default_config()
        self.calculator = LocalDirectoryScoreCalculator(self.config)
        self.records = generate_test_records()
        log(f"Generated {len(self.records)} test records")
        
        self.setup_ui()
        self.run_calculation()
        log("GUI initialized successfully")
    
    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        
        # Left panel - Config
        config_frame = ttk.LabelFrame(main_frame, text="Configuration", padding="10")
        config_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 5))
        
        ttk.Label(config_frame, text="Cost Types:").grid(row=0, column=0, sticky=tk.W, pady=(0, 5))
        
        self.cost_vars = {}
        cost_types = [
            ("Total Cost", CostType.TOTAL),
            ("Drug Cost", CostType.DRUG),
            ("Material Cost", CostType.MATERIAL),
            ("Consumable", CostType.CONSUMABLE),
            ("Exam Cost", CostType.EXAM),
            ("Treatment", CostType.TREATMENT),
            ("Nursing", CostType.NURSING)
        ]
        
        for i, (name, cost_type) in enumerate(cost_types):
            var = tk.BooleanVar(value=(cost_type == CostType.TOTAL))
            self.cost_vars[cost_type] = var
            ttk.Checkbutton(config_frame, text=name, variable=var).grid(
                row=i+1, column=0, sticky=tk.W, padx=(20, 0)
            )
        
        ttk.Label(config_frame, text="Statistics:").grid(row=9, column=0, sticky=tk.W, pady=(10, 5))
        
        self.stat_vars = {
            'mean': tk.BooleanVar(value=True),
            'median': tk.BooleanVar(value=True),
            'std': tk.BooleanVar(value=True),
            'cv': tk.BooleanVar(value=True),
            'percentiles': tk.BooleanVar(value=True),
            'remove_outliers': tk.BooleanVar(value=True)
        }
        
        stat_items = [
            ("Mean", 'mean'),
            ("Median", 'median'),
            ("Std Dev", 'std'),
            ("CV", 'cv'),
            ("Percentiles", 'percentiles'),
            ("Remove Outliers", 'remove_outliers')
        ]
        
        for i, (name, key) in enumerate(stat_items):
            ttk.Checkbutton(config_frame, text=name, variable=self.stat_vars[key]).grid(
                row=i+10, column=0, sticky=tk.W, padx=(20, 0)
            )
        
        ttk.Label(config_frame, text="Presets:").grid(row=17, column=0, sticky=tk.W, pady=(10, 5))
        
        ttk.Button(config_frame, text="Default", command=self.apply_default_config).grid(
            row=18, column=0, sticky=tk.W, padx=(20, 0), pady=2
        )
        ttk.Button(config_frame, text="Full", command=self.apply_full_config).grid(
            row=19, column=0, sticky=tk.W, padx=(20, 0), pady=2
        )
        ttk.Button(config_frame, text="Drug+Material", command=self.apply_drug_material_config).grid(
            row=20, column=0, sticky=tk.W, padx=(20, 0), pady=2
        )
        ttk.Button(config_frame, text="Simple", command=self.apply_simple_config).grid(
            row=21, column=0, sticky=tk.W, padx=(20, 0), pady=2
        )
        
        ttk.Button(config_frame, text="Apply & Calculate", command=self.apply_config).grid(
            row=22, column=0, sticky=tk.W, padx=(20, 0), pady=(10, 0)
        )
        
        # Right panel - Results
        result_frame = ttk.LabelFrame(main_frame, text="Results", padding="10")
        result_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(5, 0))
        
        columns = ('DIP Code', 'Cases', 'Score', 'Coeff')
        self.result_tree = ttk.Treeview(result_frame, columns=columns, show='headings', height=10)
        
        for col in columns:
            self.result_tree.heading(col, text=col)
            self.result_tree.column(col, width=100)
        
        self.result_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        scrollbar = ttk.Scrollbar(result_frame, orient=tk.VERTICAL, command=self.result_tree.yview)
        self.result_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        ttk.Label(result_frame, text="Details:").grid(row=1, column=0, sticky=tk.W, pady=(10, 5))
        
        self.detail_text = tk.Text(result_frame, height=15, width=60)
        self.detail_text.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        detail_scrollbar = ttk.Scrollbar(result_frame, orient=tk.VERTICAL, command=self.detail_text.yview)
        self.detail_text.configure(yscrollcommand=detail_scrollbar.set)
        detail_scrollbar.grid(row=2, column=1, sticky=(tk.N, tk.S))
        
        result_frame.columnconfigure(0, weight=1)
        result_frame.rowconfigure(2, weight=1)
    
    def apply_default_config(self):
        self.config = create_default_config()
        self.update_ui_from_config()
        self.apply_config()
    
    def apply_full_config(self):
        self.config = create_full_config()
        self.update_ui_from_config()
        self.apply_config()
    
    def apply_drug_material_config(self):
        self.config = create_drug_material_config()
        self.update_ui_from_config()
        self.apply_config()
    
    def apply_simple_config(self):
        self.config = create_simple_config()
        self.update_ui_from_config()
        self.apply_config()
    
    def update_ui_from_config(self):
        for cost_type, var in self.cost_vars.items():
            enabled = any(c.cost_type == cost_type and c.enabled for c in self.config.cost_configs)
            var.set(enabled)
        
        self.stat_vars['mean'].set(self.config.statistical_config.calculate_mean)
        self.stat_vars['median'].set(self.config.statistical_config.calculate_median)
        self.stat_vars['std'].set(self.config.statistical_config.calculate_std)
        self.stat_vars['cv'].set(self.config.statistical_config.calculate_cv)
        self.stat_vars['percentiles'].set(self.config.statistical_config.calculate_percentiles)
        self.stat_vars['remove_outliers'].set(self.config.statistical_config.remove_outliers)
    
    def apply_config(self):
        log("Applying config...")
        cost_configs = []
        for cost_type, var in self.cost_vars.items():
            if var.get():
                cost_configs.append(CostCalculationConfig(cost_type=cost_type, enabled=True))
        
        if not cost_configs:
            cost_configs = [CostCalculationConfig(cost_type=CostType.TOTAL, enabled=True)]
        
        statistical_config = StatisticalConfig(
            calculate_mean=self.stat_vars['mean'].get(),
            calculate_median=self.stat_vars['median'].get(),
            calculate_std=self.stat_vars['std'].get(),
            calculate_cv=self.stat_vars['cv'].get(),
            calculate_percentiles=self.stat_vars['percentiles'].get(),
            remove_outliers=self.stat_vars['remove_outliers'].get()
        )
        
        self.config = DIPCalculationConfig(
            cost_configs=cost_configs,
            statistical_config=statistical_config
        )
        
        self.calculator = LocalDirectoryScoreCalculator(self.config)
        self.run_calculation()
        log("Config applied successfully")
    
    def run_calculation(self):
        log("Running calculation...")
        results = self.calculator.batch_calculate_local_directory(self.records)
        
        for item in self.result_tree.get_children():
            self.result_tree.delete(item)
        
        self.detail_text.delete(1.0, tk.END)
        
        for dip_code, result in sorted(results.items()):
            self.result_tree.insert('', 'end', values=(
                dip_code,
                result['total_cases'],
                f"{float(result['final_score']):.2f}",
                f"{float(result['hospital_coefficient']):.4f}"
            ))
            
            self.detail_text.insert(tk.END, f"\n{'='*50}\n")
            self.detail_text.insert(tk.END, f"DIP Code: {dip_code}\n")
            self.detail_text.insert(tk.END, f"Cases: {result['total_cases']}\n")
            self.detail_text.insert(tk.END, f"Score: {float(result['final_score']):.2f}\n")
            self.detail_text.insert(tk.END, f"Coefficient: {float(result['hospital_coefficient']):.4f}\n")
            self.detail_text.insert(tk.END, f"\nCost Statistics:\n")
            
            for cost_type, stats in result.get('cost_statistics', {}).items():
                self.detail_text.insert(tk.END, f"\n  {cost_type}:\n")
                for key, value in stats.items():
                    if key != 'score':
                        self.detail_text.insert(tk.END, f"    {key}: {value}\n")
        
        log("Calculation complete")


def main():
    # Clear log file
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write("DIP GUI Log\n" + "="*50 + "\n")
    
    log("Starting application...")
    
    try:
        root = tk.Tk()
        app = DIPCalculationGUI(root)
        log("Entering mainloop...")
        root.mainloop()
    except Exception as e:
        log(f"ERROR: {e}")
        log(traceback.format_exc())
        messagebox.showerror("Error", str(e))
    
    log("Application closed")


if __name__ == "__main__":
    main()
