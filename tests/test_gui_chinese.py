"""
DIP测算工具 - 中文图形化测试界面（完整版）
包含：医保结算清单导入、分值测算、医院系数、辅助目录、费用异常处理、特例单议
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import sys
sys.path.insert(0, 'F:/DIP')

from decimal import Decimal
from pathlib import Path
from src.core.calculation_config import (
    DIPCalculationConfig, CostType, CostCalculationConfig, StatisticalConfig,
    create_default_config, create_full_config, create_drug_material_config
)
from src.core.local_directory_score_configurable import LocalDirectoryScoreCalculator
from src.core.value_calculator_selectable import (
    DIPValueCalculator, ValueCalculationConfig, ValueCalculationMethod,
    create_average_cost_config, create_reference_disease_config, create_standard_quota_config,
    create_drug_value_config, create_consumable_value_config
)
from src.core.hospital_coefficient_selector import (
    HospitalCoefficientSelector, CoefficientCalculationConfig, CoefficientCalculationMethod,
    create_basic_only_config, create_bonus_only_config, create_basic_bonus_config,
    create_disease_level_config, create_comprehensive_config
)
from src.core.auxiliary_directory_exporter import AuxiliaryDirectoryExporter
from src.core.grouping_engine import DIPGroupingEngine
from src.interfaces.settlement_importer import SettlementDataImporter, ImportConfig
from src.models.models import MedicalRecord


def generate_test_records():
    """生成测试病例数据"""
    records = []
    for i in range(20):
        records.append(MedicalRecord(
            record_id=f"R{i+1:04d}", settlement_id=f"S{i+1:04d}",
            patient_id=f"P{i+1:04d}", visit_id=f"V{i+1:04d}",
            hospital_code="H001", hospital_name="市人民医院", hospital_level="三级甲等",
            main_diag_code="I21.0", main_diag_name="前壁急性透壁性心肌梗死",
            total_cost=Decimal(str(15000 + i * 500)),
            drug_cost=Decimal(str(6000 + i * 200)),
            material_cost=Decimal(str(4000 + i * 150)),
            admission_date="2024-01-15", discharge_date="2024-01-27", los=12,
            discharge_status="治愈"
        ))
    for i in range(15):
        records.append(MedicalRecord(
            record_id=f"R{i+21:04d}", settlement_id=f"S{i+21:04d}",
            patient_id=f"P{i+21:04d}", visit_id=f"V{i+21:04d}",
            hospital_code="H002", hospital_name="区中心医院", hospital_level="二级甲等",
            main_diag_code="K35", main_diag_name="急性阑尾炎",
            total_cost=Decimal(str(10000 + i * 400)),
            drug_cost=Decimal(str(3000 + i * 150)),
            material_cost=Decimal(str(2500 + i * 100)),
            admission_date="2024-02-10", discharge_date="2024-02-18", los=8,
            discharge_status="治愈"
        ))
    return records


class DIPCalculationApp:
    def __init__(self, root):
        self.root = root
        self.root.title("DIP按病种分值分组测算工具 v2.0（DIP3.0规范完整版）")
        self.root.geometry("1400x900")
        
        # 数据
        self.records = []
        self.config = create_default_config()
        self.calculator = LocalDirectoryScoreCalculator(self.config)
        self.results = {}
        
        # 初始化各模块
        self.grouping_engine = DIPGroupingEngine()
        self.importer = SettlementDataImporter()
        self.value_config = create_average_cost_config()
        self.value_calculator = DIPValueCalculator(self.value_config)
        
        self.hospital_config = create_basic_bonus_config()
        self.hospital_selector = HospitalCoefficientSelector(self.hospital_config)
        
        self.auxiliary_exporter = AuxiliaryDirectoryExporter()

        self.setup_ui()
    
    def setup_ui(self):
        """设置UI界面"""
        # 主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        
        # ===== 左侧：配置面板 =====
        left_frame = ttk.LabelFrame(main_frame, text="数据与配置", padding="10")
        left_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 5))
        
        # 数据导入区域
        ttk.Label(left_frame, text="【医保结算清单导入】", font=("", 10, "bold")).grid(
            row=0, column=0, sticky=tk.W, pady=(0, 5)
        )
        
        ttk.Button(left_frame, text="导入Excel/CSV文件", command=self.import_data).grid(
            row=1, column=0, sticky=tk.W, padx=(20, 0), pady=5
        )
        ttk.Button(left_frame, text="使用测试数据", command=self.load_test_data).grid(
            row=2, column=0, sticky=tk.W, padx=(20, 0), pady=5
        )
        
        self.data_label = ttk.Label(left_frame, text="未加载数据")
        self.data_label.grid(row=3, column=0, sticky=tk.W, padx=(20, 0), pady=5)
        
        # 分值计算方法选择
        ttk.Label(left_frame, text="【分值计算方法】", font=("", 10, "bold")).grid(
            row=4, column=0, sticky=tk.W, pady=(15, 5)
        )
        
        self.value_method_var = tk.StringVar(value="平均费用法")
        value_methods = ["平均费用法", "基准病种费用法", "标准定额法", "药品分值法", "耗材分值法"]
        
        for i, method in enumerate(value_methods):
            ttk.Radiobutton(left_frame, text=method, variable=self.value_method_var, 
                           value=method, command=self.update_value_config).grid(
                row=i+5, column=0, sticky=tk.W, padx=(20, 0), pady=2
            )
        
        # 医院系数计算方法选择
        ttk.Label(left_frame, text="【医院系数计算方法】", font=("", 10, "bold")).grid(
            row=11, column=0, sticky=tk.W, pady=(15, 5)
        )
        
        self.hospital_method_var = tk.StringVar(value="基本+加成系数法")
        hospital_methods = ["基本系数法", "加成系数法", "基本+加成系数法", "病种级别系数法", "综合系数法"]
        
        for i, method in enumerate(hospital_methods):
            ttk.Radiobutton(left_frame, text=method, variable=self.hospital_method_var,
                           value=method, command=self.update_hospital_config).grid(
                row=i+12, column=0, sticky=tk.W, padx=(20, 0), pady=2
            )
        
        # 执行按钮
        ttk.Button(left_frame, text="执行完整测算", command=self.calculate).grid(
            row=18, column=0, sticky=tk.W, padx=(20, 0), pady=(20, 0)
        )
        ttk.Button(left_frame, text="导出完整报告", command=self.export_report).grid(
            row=19, column=0, sticky=tk.W, padx=(20, 0), pady=5
        )
        
        # ===== 右侧：结果面板 =====
        right_frame = ttk.LabelFrame(main_frame, text="测算结果", padding="10")
        right_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(5, 0))
        
        # 选项卡
        notebook = ttk.Notebook(right_frame)
        notebook.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 选项卡1：分组测算结果
        tab1 = ttk.Frame(notebook, padding="10")
        notebook.add(tab1, text="分组测算结果")
        
        columns1 = ('序号', '主要诊断编码', '主要诊断名称', '主要手术操作编码', '主要手术操作名称', '相关手术操作编码', '相关手术操作名称', '病例数', '病种类型', '病种分值', '药品分值', '耗材分值', '平均费用')
        
        # 创建滚动条容器
        tree_frame1 = ttk.Frame(tab1)
        tree_frame1.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.tree1 = ttk.Treeview(tree_frame1, columns=columns1, show='headings', height=20)
        for col in columns1:
            self.tree1.heading(col, text=col)
            self.tree1.column(col, width=120)
        
        # 垂直滚动条
        v_scrollbar1 = ttk.Scrollbar(tree_frame1, orient=tk.VERTICAL, command=self.tree1.yview)
        self.tree1.configure(yscrollcommand=v_scrollbar1.set)
        
        # 横向滚动条
        h_scrollbar1 = ttk.Scrollbar(tree_frame1, orient=tk.HORIZONTAL, command=self.tree1.xview)
        self.tree1.configure(xscrollcommand=h_scrollbar1.set)
        
        # 布局
        self.tree1.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        v_scrollbar1.grid(row=0, column=1, sticky=(tk.N, tk.S))
        h_scrollbar1.grid(row=1, column=0, sticky=(tk.W, tk.E))
        
        # 配置权重使树视图可扩展
        tree_frame1.columnconfigure(0, weight=1)
        tree_frame1.rowconfigure(0, weight=1)
        
        # 选项卡2：医院系数结果
        tab2 = ttk.Frame(notebook, padding="10")
        notebook.add(tab2, text="医院系数结果")
        
        columns2 = ('医院代码', '医院名称', '医院等级', '基本系数', '加成系数', '最终系数')
        
        tree_frame2 = ttk.Frame(tab2)
        tree_frame2.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.tree2 = ttk.Treeview(tree_frame2, columns=columns2, show='headings', height=20)
        for col in columns2:
            self.tree2.heading(col, text=col)
            self.tree2.column(col, width=120)
        
        v_scrollbar2 = ttk.Scrollbar(tree_frame2, orient=tk.VERTICAL, command=self.tree2.yview)
        self.tree2.configure(yscrollcommand=v_scrollbar2.set)
        h_scrollbar2 = ttk.Scrollbar(tree_frame2, orient=tk.HORIZONTAL, command=self.tree2.xview)
        self.tree2.configure(xscrollcommand=h_scrollbar2.set)
        
        self.tree2.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        v_scrollbar2.grid(row=0, column=1, sticky=(tk.N, tk.S))
        h_scrollbar2.grid(row=1, column=0, sticky=(tk.W, tk.E))
        
        tree_frame2.columnconfigure(0, weight=1)
        tree_frame2.rowconfigure(0, weight=1)
        
        # 选项卡3：辅助目录结果
        tab3 = ttk.Frame(notebook, padding="10")
        notebook.add(tab3, text="辅助目录结果")
        
        columns3 = ('病例ID', 'DIP编码', 'CCI类型', '疾病严重程度', '年龄特征', 'ICU类型')
        
        tree_frame3 = ttk.Frame(tab3)
        tree_frame3.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.tree3 = ttk.Treeview(tree_frame3, columns=columns3, show='headings', height=20)
        for col in columns3:
            self.tree3.heading(col, text=col)
            self.tree3.column(col, width=120)
        
        v_scrollbar3 = ttk.Scrollbar(tree_frame3, orient=tk.VERTICAL, command=self.tree3.yview)
        self.tree3.configure(yscrollcommand=v_scrollbar3.set)
        h_scrollbar3 = ttk.Scrollbar(tree_frame3, orient=tk.HORIZONTAL, command=self.tree3.xview)
        self.tree3.configure(xscrollcommand=h_scrollbar3.set)
        
        self.tree3.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        v_scrollbar3.grid(row=0, column=1, sticky=(tk.N, tk.S))
        h_scrollbar3.grid(row=1, column=0, sticky=(tk.W, tk.E))
        
        tree_frame3.columnconfigure(0, weight=1)
        tree_frame3.rowconfigure(0, weight=1)
        
        # 选项卡4：统计汇总
        tab4 = ttk.Frame(notebook, padding="10")
        notebook.add(tab4, text="统计汇总")
        
        self.summary_text = tk.Text(tab4, height=20, width=80, font=("", 10))
        self.summary_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        scrollbar4 = ttk.Scrollbar(tab4, orient=tk.VERTICAL, command=self.summary_text.yview)
        self.summary_text.configure(yscrollcommand=scrollbar4.set)
        scrollbar4.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        # 选项卡5：字典查看
        tab5 = ttk.Frame(notebook, padding="10")
        notebook.add(tab5, text="字典查看")
        
        # 字典选择区域
        dict_frame = ttk.LabelFrame(tab5, text="选择字典", padding="5")
        dict_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        
        self.dict_var = tk.StringVar(value="低标目录")
        dict_options = ["DIP3.0国家目录库", "低标目录", "ICD-10编码", "ICD-9-CM-3编码", "CCI合并症并发症", "疾病严重程度辅助目录"]
        
        for i, dict_name in enumerate(dict_options):
            ttk.Radiobutton(dict_frame, text=dict_name, variable=self.dict_var, 
                           value=dict_name, command=self.load_dictionary).grid(
                row=0, column=i, padx=10
            )
        
        # 搜索区域
        search_frame = ttk.Frame(tab5)
        search_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        
        ttk.Label(search_frame, text="搜索:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=30)
        self.search_entry.pack(side=tk.LEFT, padx=(5, 10))
        ttk.Button(search_frame, text="搜索", command=self.search_dictionary).pack(side=tk.LEFT)
        ttk.Button(search_frame, text="刷新", command=self.load_dictionary).pack(side=tk.LEFT, padx=5)
        
        # 字典内容显示
        self.dict_tree = ttk.Treeview(tab5, show='headings', height=15)
        self.dict_tree.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        dict_scrollbar = ttk.Scrollbar(tab5, orient=tk.VERTICAL, command=self.dict_tree.yview)
        self.dict_tree.configure(yscrollcommand=dict_scrollbar.set)
        dict_scrollbar.grid(row=2, column=1, sticky=(tk.N, tk.S))
        
        # 分页控制
        page_frame = ttk.Frame(tab5)
        page_frame.grid(row=3, column=0, sticky=(tk.W, tk.E), pady=(5, 0))
        
        self.page_size = 500  # 每页显示500条
        self.current_page = 0
        self.total_pages = 0
        self.all_dict_data = []  # 存储全部数据
        self.all_dict_data_filtered = []  # 存储筛选后数据
        
        ttk.Button(page_frame, text="上一页", command=self.prev_page).pack(side=tk.LEFT)
        self.page_label = ttk.Label(page_frame, text="第 0/0 页")
        self.page_label.pack(side=tk.LEFT, padx=10)
        ttk.Button(page_frame, text="下一页", command=self.next_page).pack(side=tk.LEFT)
        
        ttk.Label(page_frame, text="每页:").pack(side=tk.LEFT, padx=(20, 5))
        self.page_size_var = tk.StringVar(value="500")
        page_size_combo = ttk.Combobox(page_frame, textvariable=self.page_size_var, 
                                       values=["100", "200", "500", "1000"], width=5)
        page_size_combo.pack(side=tk.LEFT)
        page_size_combo.bind('<<ComboboxSelected>>', self.change_page_size)
        page_size_combo.bind('<FocusOut>', self.change_page_size)
        
        # 状态栏
        self.dict_status = ttk.Label(tab5, text="共 0 条记录")
        self.dict_status.grid(row=4, column=0, sticky=tk.W, pady=(5, 0))
        
        # 配置权重
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(0, weight=1)
        for tab in [tab1, tab2, tab3, tab4, tab5]:
            tab.columnconfigure(0, weight=1)
            tab.rowconfigure(0, weight=1)
        tab5.rowconfigure(2, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(0, weight=1)
    
    def import_data(self):
        """导入医保结算清单数据"""
        file_path = filedialog.askopenfilename(
            title="选择医保结算清单文件",
            filetypes=[
                ("Excel文件", "*.xlsx *.xls"),
                ("CSV文件", "*.csv"),
                ("所有文件", "*.*")
            ]
        )
        
        if file_path:
            try:
                # 创建导入器
                importer = SettlementDataImporter()
                
                # 导入文件
                result = importer.import_file(file_path)
                
                if result.imported_rows > 0:
                    self.records = result.records
                    
                    # 对导入的数据进行DIP分组
                    self.group_records()
                    
                    # 更新数据标签
                    self.data_label.config(
                        text=f"已导入: {result.imported_rows}条记录 (来自 {Path(file_path).name})"
                    )
                    
                    messagebox.showinfo("导入成功", 
                        f"成功导入 {result.imported_rows} 条记录\n"
                        f"失败 {result.failed_rows} 条记录")
                else:
                    messagebox.showerror("导入失败", 
                        f"导入失败:\n" + "\n".join(result.import_log))
                    
            except Exception as e:
                messagebox.showerror("错误", f"导入失败: {str(e)}")
    
    def load_test_data(self):
        """加载测试数据"""
        self.records = generate_test_records()
        
        # 对测试数据进行DIP分组
        self.group_records()
        
        self.data_label.config(text=f"已加载: {len(self.records)}条测试记录")
        messagebox.showinfo("成功", f"已加载 {len(self.records)} 条测试记录")
    
    def group_records(self):
        """对病例记录进行DIP分组"""
        if not self.records:
            return
        
        # 使用分组引擎对每条记录进行分组
        for record in self.records:
            disease_group = self.grouping_engine.group_single_record(record)
            record.dip_disease_code = disease_group.disease_code
            record.dip_disease_name = disease_group.disease_name
    
    def update_value_config(self):
        """更新分值计算配置"""
        method = self.value_method_var.get()
        if method == "平均费用法":
            self.value_config = create_average_cost_config()
        elif method == "基准病种费用法":
            self.value_config = create_reference_disease_config()
        elif method == "标准定额法":
            self.value_config = create_standard_quota_config()
        elif method == "药品分值法":
            self.value_config = create_drug_value_config()
        elif method == "耗材分值法":
            self.value_config = create_consumable_value_config()
        
        self.value_calculator = DIPValueCalculator(self.value_config)
    
    def update_hospital_config(self):
        """更新医院系数配置"""
        method = self.hospital_method_var.get()
        if method == "基本系数法":
            self.hospital_config = create_basic_only_config()
        elif method == "加成系数法":
            self.hospital_config = create_bonus_only_config()
        elif method == "基本+加成系数法":
            self.hospital_config = create_basic_bonus_config()
        elif method == "病种级别系数法":
            self.hospital_config = create_disease_level_config()
        elif method == "综合系数法":
            self.hospital_config = create_comprehensive_config()
        
        self.hospital_selector = HospitalCoefficientSelector(self.hospital_config)
    
    def calculate(self):
        """执行完整测算"""
        if not self.records:
            messagebox.showwarning("警告", "请先导入或加载数据！")
            return
        
        try:
            # 更新配置
            self.update_value_config()
            self.update_hospital_config()
            
            # 1. 本地目录库测算
            cost_configs = [CostCalculationConfig(cost_type=CostType.TOTAL, enabled=True)]
            
            self.config = DIPCalculationConfig(
                cost_configs=cost_configs,
                statistical_config=StatisticalConfig(
                    calculate_mean=True,
                    calculate_median=True,
                    calculate_std=True,
                    calculate_cv=True,
                    calculate_percentiles=True,
                    remove_outliers=True
                )
            )
            self.calculator = LocalDirectoryScoreCalculator(self.config)
            self.results = self.calculator.batch_calculate_local_directory(self.records)
            
            # 2. 分值测算
            self.value_results = self.value_calculator.calculate_all_values(self.records)
            
            # 3. 医院系数测算
            hospital_data = self._prepare_hospital_data()
            self.hospital_results = self.hospital_selector.batch_calculate(
                hospital_data, self.records
            )
            
            # 4. 辅助目录测算
            self.auxiliary_results = self.auxiliary_exporter.classify_records(self.records)

            # 更新界面
            self.update_all_results()
            
        except Exception as e:
            messagebox.showerror("错误", f"测算失败: {str(e)}")
    
    def _prepare_hospital_data(self):
        """准备医院数据"""
        hospital_stats = {}
        
        for record in self.records:
            code = record.hospital_code
            if code not in hospital_stats:
                hospital_stats[code] = {
                    'hospital_code': code,
                    'hospital_name': record.hospital_name,
                    'hospital_level': record.hospital_level,
                    'total_cost': Decimal("0"),
                    'count': 0
                }
            hospital_stats[code]['total_cost'] += record.total_cost
            hospital_stats[code]['count'] += 1
        
        # 计算平均费用
        for code, stats in hospital_stats.items():
            if stats['count'] > 0:
                stats['avg_cost'] = stats['total_cost'] / stats['count']
            else:
                stats['avg_cost'] = Decimal("0")
        
        return list(hospital_stats.values())
    
    def update_all_results(self):
        """更新所有结果"""
        self.update_value_results()
        self.update_hospital_results()
        self.update_auxiliary_results()
        self.update_summary()
    
    def update_value_results(self):
        """更新分组测算结果 - 显示本地历史数据形成的病种分组"""
        for item in self.tree1.get_children():
            self.tree1.delete(item)
        
        # 构建DIP目录查找表（按DIP编码匹配）
        dip_info_map = {}
        try:
            import pandas as pd
            dip_dir = pd.read_excel("F:/DIP/data/DIP3.0国家目录库.xlsx")
            for _, row in dip_dir.iterrows():
                dip_code = str(row.get('DIP编码', ''))
                diag_code = str(row.get('主要诊断编码', '')) if pd.notna(row.get('主要诊断编码')) else ''
                diag_name = str(row.get('主要诊断名称', '')) if pd.notna(row.get('主要诊断名称')) else ''
                proc_code = str(row.get('主要手术操作编码', '')) if pd.notna(row.get('主要手术操作编码')) else ''
                proc_name = str(row.get('主要手术操作名称', '')) if pd.notna(row.get('主要手术操作名称')) else ''
                rel_proc_code = str(row.get('相关手术操作编码', '')) if pd.notna(row.get('相关手术操作编码')) else ''
                rel_proc_name = str(row.get('相关手术操作名称', '')) if pd.notna(row.get('相关手术操作名称')) else ''
                # 以DIP编码为key存储
                dip_info_map[dip_code] = {
                    'dip_code': dip_code,
                    'diag_code': diag_code,
                    'diag_name': diag_name,
                    'proc_code': proc_code,
                    'proc_name': proc_name,
                    'rel_proc_code': rel_proc_code,
                    'rel_proc_name': rel_proc_name
                }
                # 也存储不带后缀的诊断编码映射（用于匹配分组结果）
                if diag_code not in dip_info_map:
                    dip_info_map[diag_code] = []
                if isinstance(dip_info_map.get(diag_code), list):
                    dip_info_map[diag_code].append({
                        'dip_code': dip_code,
                        'diag_code': diag_code,
                        'diag_name': diag_name,
                        'proc_code': proc_code,
                        'proc_name': proc_name,
                        'rel_proc_code': rel_proc_code,
                        'rel_proc_name': rel_proc_name
                    })
        except Exception as e:
            print(f"加载DIP目录失败: {e}")
        
        # 只显示有历史数据的病种分组
        for idx, result in enumerate(self.value_results, 1):
            # 直接用dip_code匹配DIP3.0目录
            best_match = dip_info_map.get(result.dip_code)
            
            # 如果直接匹配失败，尝试用诊断编码匹配
            if not best_match or not isinstance(best_match, dict):
                diag_entries = dip_info_map.get(result.dip_code, [])
                if isinstance(diag_entries, list) and diag_entries:
                    # 优先查找无手术的内科病种
                    for entry in diag_entries:
                        if not entry['proc_code']:
                            best_match = entry
                            break
                    if not best_match:
                        best_match = diag_entries[0]
            
            if best_match and isinstance(best_match, dict):
                diag_code = best_match['diag_code']
                diag_name = best_match['diag_name']
                proc_code = best_match['proc_code']
                proc_name = best_match['proc_name']
                rel_proc_code = best_match['rel_proc_code']
                rel_proc_name = best_match['rel_proc_name']
            else:
                # 如果没找到匹配，使用结果中的信息
                diag_code = result.dip_code.replace('-00', '').replace('-01', '')
                diag_name = result.disease_name
                proc_code = ''
                proc_name = ''
                rel_proc_code = ''
                rel_proc_name = ''
            
            # 判断病种类型：根据病例数是否达到阈值（15例为默认阈值）
            threshold = 15
            group_type = "核心病种" if result.case_count >= threshold else "综合病种"
            
            self.tree1.insert('', 'end', values=(
                idx,
                diag_code,
                diag_name,
                proc_code,
                proc_name,
                rel_proc_code,
                rel_proc_name,
                result.case_count,
                group_type,
                f"{float(result.disease_value):.2f}",
                f"{float(result.drug_value):.2f}",
                f"{float(result.consumable_value):.2f}",
                f"{float(result.avg_cost):.2f}"
            ))
    
    def update_hospital_results(self):
        """更新医院系数结果"""
        for item in self.tree2.get_children():
            self.tree2.delete(item)
        
        for result in self.hospital_results:
            self.tree2.insert('', 'end', values=(
                result.hospital_code,
                result.hospital_name,
                result.hospital_level,
                f"{float(result.basic_coefficient):.4f}",
                f"{float(result.bonus_coefficient):.4f}",
                f"{float(result.final_coefficient):.4f}"
            ))
    
    def update_auxiliary_results(self):
        """更新辅助目录结果"""
        for item in self.tree3.get_children():
            self.tree3.delete(item)
        
        for result in self.auxiliary_results:
            self.tree3.insert('', 'end', values=(
                result.record_id,
                result.dip_code,
                result.cci_type,
                result.severity_type,
                result.age_type,
                result.icu_type
            ))
    
    def update_summary(self):
        """更新统计汇总"""
        self.summary_text.delete(1.0, tk.END)
        
        # 基本统计
        self.summary_text.insert(tk.END, "【DIP3.0规范完整版测算统计】\n")
        self.summary_text.insert(tk.END, "="*50 + "\n")
        self.summary_text.insert(tk.END, f"总病例数: {len(self.records)}\n")
        
        total_cost = sum(r.total_cost for r in self.records)
        self.summary_text.insert(tk.END, f"总费用: {float(total_cost):.2f}元\n")
        
        avg_cost = total_cost / len(self.records) if self.records else Decimal("0")
        self.summary_text.insert(tk.END, f"平均费用: {float(avg_cost):.2f}元\n")
        
        # DIP分组统计
        dip_counts = {}
        for record in self.records:
            dip_code = record.dip_disease_code
            if dip_code not in dip_counts:
                dip_counts[dip_code] = {'count': 0, 'name': record.dip_disease_name}
            dip_counts[dip_code]['count'] += 1
        
        self.summary_text.insert(tk.END, f"\n【DIP分组统计】\n")
        self.summary_text.insert(tk.END, "-"*50 + "\n")
        self.summary_text.insert(tk.END, f"DIP分组数: {len(dip_counts)}\n")
        for dip_code, info in sorted(dip_counts.items(), key=lambda x: -x[1]['count']):
            self.summary_text.insert(tk.END, f"  {dip_code} ({info['name']}): {info['count']}例\n")
        
        # 分组测算统计
        self.summary_text.insert(tk.END, "\n【分组测算统计】\n")
        self.summary_text.insert(tk.END, "-"*50 + "\n")
        self.summary_text.insert(tk.END, f"计算方法: {self.value_config.calculation_method.value}\n")
        self.summary_text.insert(tk.END, f"本地病种数: {len(dip_counts)}\n")
        self.summary_text.insert(tk.END, f"有分值病种数: {len(self.value_results)}\n")
        
        # 医院系数统计
        self.summary_text.insert(tk.END, "\n【医院系数统计】\n")
        self.summary_text.insert(tk.END, "-"*50 + "\n")
        self.summary_text.insert(tk.END, f"计算方法: {self.hospital_config.calculation_method.value}\n")
        self.summary_text.insert(tk.END, f"计算医院数量: {len(self.hospital_results)}\n")
        
        # 辅助目录统计
        self.summary_text.insert(tk.END, "\n【辅助目录统计】\n")
        self.summary_text.insert(tk.END, "-"*50 + "\n")
        cci_types = {}
        severity_types = {}
        for result in self.auxiliary_results:
            cci_types[result.cci_type] = cci_types.get(result.cci_type, 0) + 1
            severity_types[result.severity_type] = severity_types.get(result.severity_type, 0) + 1
        
        self.summary_text.insert(tk.END, "CCI分类:\n")
        for cci_type, count in cci_types.items():
            self.summary_text.insert(tk.END, f"  {cci_type}: {count}例\n")
        
        self.summary_text.insert(tk.END, "疾病严重程度:\n")
        for severity, count in severity_types.items():
            self.summary_text.insert(tk.END, f"  {severity}: {count}例\n")
        
        # 配置信息
        self.summary_text.insert(tk.END, "\n【测算配置】\n")
        self.summary_text.insert(tk.END, "-"*50 + "\n")
        self.summary_text.insert(tk.END, f"分组分值计算方法: {self.value_config.calculation_method.value}\n")
        self.summary_text.insert(tk.END, f"医院系数方法: {self.hospital_config.calculation_method.value}\n")
    
    def export_report(self):
        """导出完整报告"""
        if not self.records:
            messagebox.showwarning("警告", "没有数据可导出！")
            return
        
        file_path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel文件", "*.xlsx")],
            initialfile="DIP完整测算报告.xlsx"
        )
        if file_path:
            try:
                # 导出分组测算结果
                self.value_calculator.export_results(self.value_results, file_path)
                
                # 导出医院系数结果
                hospital_path = file_path.replace('.xlsx', '_医院系数.xlsx')
                self.hospital_selector.export_coefficients(self.hospital_results, hospital_path)
                
                # 导出辅助目录结果
                auxiliary_path = file_path.replace('.xlsx', '_辅助目录.xlsx')
                self.auxiliary_exporter.export_to_excel(self.auxiliary_results, auxiliary_path)
                
                messagebox.showinfo("成功", f"完整报告已导出到:\n{file_path}\n"
                                   f"医院系数: {hospital_path}\n"
                                   f"辅助目录: {auxiliary_path}")
            except Exception as e:
                messagebox.showerror("错误", f"导出失败: {str(e)}")
    
    def load_dictionary(self):
        """加载字典数据"""
        dict_name = self.dict_var.get()
        
        # 清空现有数据
        for item in self.dict_tree.get_children():
            self.dict_tree.delete(item)
        
        # 根据选择的字典类型加载数据
        dict_file = None
        
        if dict_name == "DIP3.0国家目录库":
            dict_file = "F:/DIP/data/DIP3.0国家目录库.xlsx"
        elif dict_name == "低标目录":
            dict_file = "F:/DIP/data/低标目录(1).xlsx"
        elif dict_name == "ICD-10编码":
            dict_file = "F:/DIP/data/ICD10国临版2.0对照医保版2.0_0125.xlsx"
        elif dict_name == "ICD-9-CM-3编码":
            dict_file = "F:/DIP/data/ICD9国临版3.0对照医保版2.0_0125.xlsx"
        elif dict_name == "CCI合并症并发症":
            dict_file = "F:/DIP/data/CCI.xlsx"
        elif dict_name == "疾病严重程度辅助目录":
            dict_file = "F:/DIP/data/中重度分型诊断.xlsx"
        
        try:
            if dict_file and Path(dict_file).exists():
                import pandas as pd
                df = pd.read_excel(dict_file)
                
                # 保存全部数据
                self.all_dict_data = []
                for idx, row in df.iterrows():
                    values = [str(v) if pd.notna(v) else '' for v in row]
                    self.all_dict_data.append(values)
                
                # 初始化筛选数据为全部数据
                self.all_dict_data_filtered = self.all_dict_data
                
                # 设置表格列
                self.dict_tree['columns'] = list(df.columns)
                for col in df.columns:
                    self.dict_tree.heading(col, text=col)
                    self.dict_tree.column(col, width=150)
                
                # 计算总页数
                self.total_pages = (len(self.all_dict_data) + self.page_size - 1) // self.page_size
                self.current_page = 0
                
                # 显示第一页
                self.show_current_page()
                
                self.dict_status.config(text=f"共 {len(df)} 条记录")
            else:
                self.dict_status.config(text=f"未找到字典文件: {dict_name}")
        except Exception as e:
            self.dict_status.config(text=f"加载字典失败: {str(e)}")
    
    def search_dictionary(self):
        """搜索字典数据（在全部数据中搜索）"""
        keyword = self.search_var.get().strip()
        if not keyword:
            # 如果搜索框为空，显示全部数据
            self.show_current_page()
            self.dict_status.config(text=f"共 {len(self.all_dict_data)} 条记录")
            return
        
        # 在全部数据中搜索
        search_results = []
        for row in self.all_dict_data:
            if any(keyword.lower() in str(v).lower() for v in row):
                search_results.append(row)
        
        # 更新显示数据为搜索结果
        self.all_dict_data_filtered = search_results
        self.total_pages = (len(search_results) + self.page_size - 1) // self.page_size
        self.current_page = 0
        
        # 显示第一页搜索结果
        self.show_filtered_page()
        
        self.dict_status.config(text=f"搜索 '{keyword}' - 找到 {len(search_results)} 条记录")
    
    def show_filtered_page(self):
        """显示筛选后的当前页数据"""
        # 清空现有数据
        for item in self.dict_tree.get_children():
            self.dict_tree.delete(item)
        
        # 获取当前显示的数据（可能是搜索结果或全部数据）
        data = self.all_dict_data_filtered if self.all_dict_data_filtered else self.all_dict_data
        
        # 计算当前页的数据范围
        start_idx = self.current_page * self.page_size
        end_idx = min(start_idx + self.page_size, len(data))
        
        # 插入当前页数据
        for i in range(start_idx, end_idx):
            self.dict_tree.insert('', 'end', values=data[i])
        
        # 更新页码标签
        self.page_label.config(text=f"第 {self.current_page + 1}/{self.total_pages} 页")
    
    def show_current_page(self):
        """显示当前页数据"""
        # 清空现有数据
        for item in self.dict_tree.get_children():
            self.dict_tree.delete(item)
        
        # 获取当前显示的数据（可能是搜索结果或全部数据）
        data = self.all_dict_data_filtered if self.all_dict_data_filtered else self.all_dict_data
        
        # 计算当前页的数据范围
        start_idx = self.current_page * self.page_size
        end_idx = min(start_idx + self.page_size, len(data))
        
        # 插入当前页数据
        for i in range(start_idx, end_idx):
            self.dict_tree.insert('', 'end', values=data[i])
        
        # 更新页码标签
        self.page_label.config(text=f"第 {self.current_page + 1}/{self.total_pages} 页")
    
    def prev_page(self):
        """上一页"""
        if self.current_page > 0:
            self.current_page -= 1
            self.show_current_page()
    
    def next_page(self):
        """下一页"""
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.show_current_page()
    
    def change_page_size(self, event=None):
        """更改每页显示数量"""
        try:
            new_size = int(self.page_size_var.get())
            if new_size > 0 and new_size != self.page_size:
                self.page_size = new_size
                data = self.all_dict_data_filtered if self.all_dict_data_filtered else self.all_dict_data
                self.total_pages = max(1, (len(data) + self.page_size - 1) // self.page_size)
                self.current_page = 0
                self.show_current_page()
                self.dict_status.config(text=f"共 {len(data)} 条记录 | 每页 {self.page_size} 条 | 共 {self.total_pages} 页")
        except (ValueError, tk.TclError):
            pass


def main():
    root = tk.Tk()
    app = DIPCalculationApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
