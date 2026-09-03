"""
DIP测算工具 - 图形化测试界面
"""
import pytest
tk = pytest.importorskip("tkinter")
from tkinter import ttk, messagebox, filedialog
import sys, os
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decimal import Decimal
from src.core.calculation_config import (
    DIPCalculationConfig, CostType, CalculationType,
    CostCalculationConfig, StatisticalConfig,
    create_default_config, create_full_config,
    create_drug_material_config, create_simple_config
)
from src.core.local_directory_score_configurable import LocalDirectoryScoreCalculator
from src.models.models import MedicalRecord, HospitalCoefficient


def make_test_records():
    """生成测试病例数据（模块级，供无界面测试直接调用）"""
    records = []

    # 三级甲等医院 - 心内科
    for i in range(20):
        records.append(MedicalRecord(
            record_id=f"REC{i+1:04d}",
            settlement_id=f"SET{i+1:04d}",
            patient_id=f"P{i+1:04d}",
            visit_id=f"V{i+1:04d}",
            hospital_code="H001",
            hospital_name="市人民医院",
            hospital_level="三级甲等",
            main_diag_code="I21.0",
            main_diag_name="急性心肌梗死",
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
            discharge_status="治愈",
            dip_disease_code="I21-1"
        ))

    # 二级甲等医院 - 普外科
    for i in range(15):
        records.append(MedicalRecord(
            record_id=f"REC{i+21:04d}",
            settlement_id=f"SET{i+21:04d}",
            patient_id=f"P{i+21:04d}",
            visit_id=f"V{i+21:04d}",
            hospital_code="H002",
            hospital_name="区中心医院",
            hospital_level="二级甲等",
            main_diag_code="K35.9",
            main_diag_name="急性阑尾炎",
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
            discharge_status="治愈",
            dip_disease_code="K35-1"
        ))

    return records


class DIPCalculationGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("DIP按病种分值分组测算工具 - 测试界面")
        self.root.geometry("1000x700")
        
        # 创建配置
        self.config = create_default_config()
        self.calculator = LocalDirectoryScoreCalculator(self.config)
        self.records = self.generate_test_records()
        
        self.setup_ui()
    
    def generate_test_records(self):
        """生成测试病例数据"""
        return make_test_records()


    def setup_ui(self):
        """设置UI界面"""
        # 创建主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 配置权重
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        
        # 左侧：配置区域
        config_frame = ttk.LabelFrame(main_frame, text="测算配置", padding="10")
        config_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 5))
        
        # 费用类型配置
        ttk.Label(config_frame, text="费用类型配置:").grid(row=0, column=0, sticky=tk.W, pady=(0, 5))
        
        self.cost_vars = {}
        cost_types = [
            ("总费用", CostType.TOTAL),
            ("药品费用", CostType.DRUG),
            ("材料费用", CostType.MATERIAL),
            ("耗材费用", CostType.CONSUMABLE),
            ("检查费用", CostType.EXAM),
            ("治疗费用", CostType.TREATMENT),
            ("护理费用", CostType.NURSING)
        ]
        
        for i, (name, cost_type) in enumerate(cost_types):
            var = tk.BooleanVar(value=(cost_type == CostType.TOTAL))
            self.cost_vars[cost_type] = var
            ttk.Checkbutton(config_frame, text=name, variable=var).grid(
                row=i+1, column=0, sticky=tk.W, padx=(20, 0)
            )
        
        # 统计配置
        ttk.Label(config_frame, text="统计计算配置:").grid(row=9, column=0, sticky=tk.W, pady=(10, 5))
        
        self.stat_vars = {
            'mean': tk.BooleanVar(value=True),
            'median': tk.BooleanVar(value=True),
            'std': tk.BooleanVar(value=True),
            'cv': tk.BooleanVar(value=True),
            'percentiles': tk.BooleanVar(value=True),
            'remove_outliers': tk.BooleanVar(value=True)
        }
        
        stat_items = [
            ("平均值", 'mean'),
            ("中位数", 'median'),
            ("标准差", 'std'),
            ("变异系数", 'cv'),
            ("分位数", 'percentiles'),
            ("异常值剔除", 'remove_outliers')
        ]
        
        for i, (name, key) in enumerate(stat_items):
            ttk.Checkbutton(config_frame, text=name, variable=self.stat_vars[key]).grid(
                row=i+10, column=0, sticky=tk.W, padx=(20, 0)
            )
        
        # 预设配置按钮
        ttk.Label(config_frame, text="预设配置:").grid(row=17, column=0, sticky=tk.W, pady=(10, 5))
        
        ttk.Button(config_frame, text="默认配置", command=self.apply_default_config).grid(
            row=18, column=0, sticky=tk.W, padx=(20, 0), pady=2
        )
        ttk.Button(config_frame, text="完整配置", command=self.apply_full_config).grid(
            row=19, column=0, sticky=tk.W, padx=(20, 0), pady=2
        )
        ttk.Button(config_frame, text="药品+材料配置", command=self.apply_drug_material_config).grid(
            row=20, column=0, sticky=tk.W, padx=(20, 0), pady=2
        )
        ttk.Button(config_frame, text="简单配置", command=self.apply_simple_config).grid(
            row=21, column=0, sticky=tk.W, padx=(20, 0), pady=2
        )
        
        # 应用配置按钮
        ttk.Button(config_frame, text="应用配置并计算", command=self.apply_config).grid(
            row=22, column=0, sticky=tk.W, padx=(20, 0), pady=(10, 0)
        )
        
        # 右侧：结果展示区域
        result_frame = ttk.LabelFrame(main_frame, text="计算结果", padding="10")
        result_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(5, 0))
        
        # 结果表格
        columns = ('DIP编码', '病例数', '最终分值', '医院调节系数')
        self.result_tree = ttk.Treeview(result_frame, columns=columns, show='headings', height=10)
        
        for col in columns:
            self.result_tree.heading(col, text=col)
            self.result_tree.column(col, width=100)
        
        self.result_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 滚动条
        scrollbar = ttk.Scrollbar(result_frame, orient=tk.VERTICAL, command=self.result_tree.yview)
        self.result_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        # 详细信息文本框
        ttk.Label(result_frame, text="详细统计信息:").grid(row=1, column=0, sticky=tk.W, pady=(10, 5))
        
        self.detail_text = tk.Text(result_frame, height=15, width=60)
        self.detail_text.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        detail_scrollbar = ttk.Scrollbar(result_frame, orient=tk.VERTICAL, command=self.detail_text.yview)
        self.detail_text.configure(yscrollcommand=detail_scrollbar.set)
        detail_scrollbar.grid(row=2, column=1, sticky=(tk.N, tk.S))
        
        # 配置权重
        result_frame.columnconfigure(0, weight=1)
        result_frame.rowconfigure(2, weight=1)
        
        # 初始计算
        self.run_calculation()
    
    def apply_default_config(self):
        """应用默认配置"""
        self.config = create_default_config()
        self.update_ui_from_config()
        self.apply_config()
    
    def apply_full_config(self):
        """应用完整配置"""
        self.config = create_full_config()
        self.update_ui_from_config()
        self.apply_config()
    
    def apply_drug_material_config(self):
        """应用药品+材料配置"""
        self.config = create_drug_material_config()
        self.update_ui_from_config()
        self.apply_config()
    
    def apply_simple_config(self):
        """应用简单配置"""
        self.config = create_simple_config()
        self.update_ui_from_config()
        self.apply_config()
    
    def update_ui_from_config(self):
        """根据配置更新UI"""
        # 更新费用类型复选框
        for cost_type, var in self.cost_vars.items():
            enabled = any(c.cost_type == cost_type and c.enabled for c in self.config.cost_configs)
            var.set(enabled)
        
        # 更新统计配置复选框
        self.stat_vars['mean'].set(self.config.statistical_config.calculate_mean)
        self.stat_vars['median'].set(self.config.statistical_config.calculate_median)
        self.stat_vars['std'].set(self.config.statistical_config.calculate_std)
        self.stat_vars['cv'].set(self.config.statistical_config.calculate_cv)
        self.stat_vars['percentiles'].set(self.config.statistical_config.calculate_percentiles)
        self.stat_vars['remove_outliers'].set(self.config.statistical_config.remove_outliers)
    
    def apply_config(self):
        """应用配置并计算"""
        # 从UI获取配置
        cost_configs = []
        for cost_type, var in self.cost_vars.items():
            if var.get():
                cost_configs.append(CostCalculationConfig(
                    cost_type=cost_type,
                    enabled=True
                ))
        
        # 如果没有选择任何费用类型，使用默认
        if not cost_configs:
            cost_configs = [CostCalculationConfig(cost_type=CostType.TOTAL, enabled=True)]
        
        # 创建统计配置
        statistical_config = StatisticalConfig(
            calculate_mean=self.stat_vars['mean'].get(),
            calculate_median=self.stat_vars['median'].get(),
            calculate_std=self.stat_vars['std'].get(),
            calculate_cv=self.stat_vars['cv'].get(),
            calculate_percentiles=self.stat_vars['percentiles'].get(),
            remove_outliers=self.stat_vars['remove_outliers'].get()
        )
        
        # 创建完整配置
        self.config = DIPCalculationConfig(
            cost_configs=cost_configs,
            statistical_config=statistical_config
        )
        
        # 更新计算器
        self.calculator = LocalDirectoryScoreCalculator(self.config)
        
        # 运行计算
        self.run_calculation()
    
    def run_calculation(self):
        """运行计算"""
        results = self.calculator.batch_calculate_local_directory(self.records)
        
        # 清空结果表格
        for item in self.result_tree.get_children():
            self.result_tree.delete(item)
        
        # 清空详细信息
        self.detail_text.delete(1.0, tk.END)
        
        # 添加结果到表格
        for dip_code, result in sorted(results.items()):
            self.result_tree.insert('', 'end', values=(
                dip_code,
                result['total_cases'],
                f"{float(result['final_score']):.2f}",
                f"{float(result['hospital_coefficient']):.4f}"
            ))
            
            # 添加详细信息
            self.detail_text.insert(tk.END, f"\n{'='*50}\n")
            self.detail_text.insert(tk.END, f"DIP编码: {dip_code}\n")
            self.detail_text.insert(tk.END, f"病例数: {result['total_cases']}\n")
            self.detail_text.insert(tk.END, f"最终分值: {float(result['final_score']):.2f}\n")
            self.detail_text.insert(tk.END, f"医院调节系数: {float(result['hospital_coefficient']):.4f}\n")
            self.detail_text.insert(tk.END, f"\n费用统计:\n")
            
            for cost_type, stats in result.get('cost_statistics', {}).items():
                self.detail_text.insert(tk.END, f"\n  {cost_type}:\n")
                for key, value in stats.items():
                    if key != 'score':
                        self.detail_text.insert(tk.END, f"    {key}: {value}\n")


def test_gui_batch_calculation():
    recs = make_test_records()
    assert len(recs) == 35
    calc = LocalDirectoryScoreCalculator(create_default_config())
    results = calc.batch_calculate_local_directory(recs)
    assert set(results.keys()) == {"I21-1", "K35-1"}
    assert sum(v["total_cases"] for v in results.values()) == 35
    for v in results.values():
        assert float(v["final_score"]) > 0
        assert float(v["hospital_coefficient"]) > 0


def test_gui_tree_populated():
    pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except Exception:
        pytest.skip("no display available")
    try:
        app = DIPCalculationGUI(root)
        children = app.result_tree.get_children()
        assert len(children) == 2
        for c in children:
            vals = app.result_tree.item(c, "values")
            assert float(vals[2]) > 0  # 最终分值
    finally:
        root.destroy()


def main():
    root = tk.Tk()
    app = DIPCalculationGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
