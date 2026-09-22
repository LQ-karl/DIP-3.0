# DIP3.0 本地目录测算系统

> 医保按病种分值付费（DIP）3.0 本地目录测算引擎 —— 严格对齐国家 DIP3.0 分组方案。

## 一、项目简介

本系统用于医保 DIP3.0 本地目录的测算与分组，覆盖从病例数据到本地病种目录、RW（相对权重）、辅助分型、医院系数、点值及付费标准测算的完整链路。

计算主线：**四层成组 → RW = mi / M × 1000 → 医院系数 → 辅助分型系数 → 点值 → 支付标准**

## 二、核心能力

- **四层成组引擎**：① 先期（XQ）> ② 核心（BX）> ③ 综合（FZ：烧伤 / 肿瘤 / 结核）> ④ 基础（JC）。每条病例仅命中一层；成组键为方案序号，DIP 编码为「主诊断-主手术-相关手术」三段式。
- **RW 测算**：RW = 病种例均费用(mi) / 全部病例例均费用(M) × 1000。
- **辅助分型**：严重程度 / 年龄 / ICU / CCI 四维度；触发条件为病例数 ≥ 15、分型病例 ≥ 5、CV 改善 ≥ 20%。
- **综合病种兜底**：四层均未命中时按官方《综合病种字典表》入组（主诊断类目 + 治疗方式组：内科诊疗组 / 诊断性操作组 / 治疗性操作组 / 相关手术组）。
- **基层病种遴选**：基层机构占比 ≥ 50% 且组内 CV ≤ 0.7，不设医疗机构调节系数。
- **国家目录库权威引擎**：由官方 xlsx 重建（5 个 sheet），逐字段保真，作为唯一分组依据。

## 三、技术栈

- 语言：Python 3.13（推荐使用受管虚拟环境）
- 数据处理：pandas、numpy、sqlalchemy、openpyxl
- 可视化 / 算法：matplotlib、scikit-learn
- Web 界面：Streamlit

## 四、目录结构

```
DIP/
├── src/                # 核心代码
│   ├── core/          # 分组引擎、本地目录生成、辅助分型、点值/支付测算
│   ├── models/        # 数据模型
│   ├── utils/         # 路径、数据加载等工具
│   └── interfaces/    # 医保接口解析（如 4101A）
├── data/              # 数据字典（xlsx）：国家目录库、中重度分型、CCI、综合病种等
├── scripts/           # 字典重建与核验脚本
├── tests/             # pytest 测试套件
├── web/               # Streamlit Web 界面（app.py）
├── docs/              # 说明文档与复核报告
├── output/            # 运行产物（已 gitignore，不入库）
├── requirements.txt
├── pytest.ini
└── 启动Web界面.bat
```

## 五、快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 启动 Web 界面（推荐）

- 方式一：双击项目根目录的 `启动Web界面.bat`
- 方式二：手动启动

  ```bash
  python -m streamlit run web/app.py --server.port 8501
  ```

启动后访问 http://localhost:8501

### 3. 程序化调用（API）

核心能力封装在 `src/dip_tool.py` 的 `DIPGroupingTool` 类中，可直接导入使用：

```python
from src.dip_tool import DIPGroupingTool

tool = DIPGroupingTool()   # 自动加载 data/ 下的字典
tool.load_data()
# 调用分组、RW、辅助分型、点值等接口...
```

## 六、核心引擎说明

| 模块 | 文件 | 职责 |
|------|------|------|
| 国家目录库（权威） | `src/core/national_directory_v30.py` | DIP3.0 唯一分组依据，含 5 个 sheet |
| 本地目录生成 | `src/core/local_directory_generator.py` | 成组键计算、综合病种兜底、基层病种 |
| 辅助分型 | `src/core/auxiliary_directory.py` | CCI / 中重度分型判定 |
| 测算工具入口 | `src/dip_tool.py` | `DIPGroupingTool` 统一 API |

## 七、数据字典与口径

所有字典严格以国家 DIP3.0 官方附件 / 函为准，口径与复核说明详见 `docs/`。

- `data/DIP3.0国家目录库.xlsx`：核心病种 / 不纳入分组诊断 / 不纳入分组手术 / 基层病种 / 结核耐药
- `data/中重度分型诊断.xlsx`：GX_ASSI 表，重度 / 中度两档
- `data/CCI.xlsx`：CCI 合并症并发症权重
- `data/综合病种字典表.xlsx`：综合病种兜底字典

## 八、测试

```bash
pytest
```

- `pytest.ini` 已配置 `pythonpath=.`、`testpaths=tests`。
- 当前套件约 **91 passed / 4 skipped**。
- 引擎冒烟测试：`python scripts/smoke_national_v30.py`

## 九、许可证

内部测算工具，未声明开源许可证。
