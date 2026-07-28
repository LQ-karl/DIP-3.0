"""
DIP3.0本地目录测算系统 - 可视化模块
使用Matplotlib生成各种图表
"""
import pandas as pd
import numpy as np
from typing import List, Optional, Dict, Any
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# 尝试导入matplotlib
try:
    import matplotlib.pyplot as plt
    import matplotlib
    matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
    matplotlib.rcParams['axes.unicode_minus'] = False
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    logger.warning("matplotlib未安装，可视化功能不可用")


class DIPVisualizer:
    """DIP可视化器"""
    
    def __init__(self, output_dir: str = None):
        """
        初始化可视化器
        
        Args:
            output_dir: 图表输出目录
        """
        if output_dir is None:
            output_dir = str(Path(__file__).parent.parent.parent / "output" / "charts")
        
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def _check_matplotlib(self) -> bool:
        """检查matplotlib是否可用"""
        if not MATPLOTLIB_AVAILABLE:
            logger.error("matplotlib未安装，请运行: pip install matplotlib")
            return False
        return True
    
    def plot_cost_distribution(self, records: pd.DataFrame, save_path: str = None) -> str:
        """
        绘制费用分布图
        
        Args:
            records: 病例数据
            save_path: 保存路径
            
        Returns:
            保存的文件路径
        """
        if not self._check_matplotlib():
            return ""
        
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        
        # 1. 总费用分布
        ax1 = axes[0, 0]
        total_cost = records['total_cost'].dropna()
        ax1.hist(total_cost, bins=50, color='steelblue', edgecolor='white', alpha=0.7)
        ax1.set_xlabel('总费用')
        ax1.set_ylabel('病例数')
        ax1.set_title('总费用分布')
        ax1.axvline(total_cost.mean(), color='red', linestyle='--', label=f'均值: {total_cost.mean():.2f}')
        ax1.axvline(total_cost.median(), color='green', linestyle='--', label=f'中位数: {total_cost.median():.2f}')
        ax1.legend()
        
        # 2. 药品费用分布
        ax2 = axes[0, 1]
        if 'drug_cost' in records.columns:
            drug_cost = records['drug_cost'].dropna()
            ax2.hist(drug_cost, bins=50, color='orange', edgecolor='white', alpha=0.7)
            ax2.set_xlabel('药品费用')
            ax2.set_ylabel('病例数')
            ax2.set_title('药品费用分布')
        
        # 3. 耗材费用分布
        ax3 = axes[1, 0]
        if 'consumable_cost' in records.columns:
            consumable_cost = records['consumable_cost'].dropna()
            ax3.hist(consumable_cost, bins=50, color='green', edgecolor='white', alpha=0.7)
            ax3.set_xlabel('耗材费用')
            ax3.set_ylabel('病例数')
            ax3.set_title('耗材费用分布')
        
        # 4. 住院天数分布
        ax4 = axes[1, 1]
        if 'los' in records.columns:
            los = records['los'].dropna()
            ax4.hist(los, bins=30, color='purple', edgecolor='white', alpha=0.7)
            ax4.set_xlabel('住院天数')
            ax4.set_ylabel('病例数')
            ax4.set_title('住院天数分布')
        
        plt.tight_layout()
        
        if save_path is None:
            save_path = str(self.output_dir / "cost_distribution.png")
        
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        logger.info(f"费用分布图已保存: {save_path}")
        return save_path
    
    def plot_disease_distribution(self, disease_groups: pd.DataFrame, top_n: int = 20, save_path: str = None) -> str:
        """
        绘制病种分布图
        
        Args:
            disease_groups: 病种分组数据
            top_n: 显示前N个病种
            save_path: 保存路径
            
        Returns:
            保存的文件路径
        """
        if not self._check_matplotlib():
            return ""
        
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))
        
        # 1. 病种病例数分布（前N个）
        ax1 = axes[0]
        top_diseases = disease_groups.nlargest(top_n, 'case_count')
        ax1.barh(range(len(top_diseases)), top_diseases['case_count'], color='steelblue')
        ax1.set_yticks(range(len(top_diseases)))
        ax1.set_yticklabels(top_diseases['disease_code'])
        ax1.set_xlabel('病例数')
        ax1.set_title(f'病种病例数分布 (前{top_n})')
        ax1.invert_yaxis()
        
        # 2. 分组类型分布
        ax2 = axes[1]
        if 'group_type' in disease_groups.columns:
            group_counts = disease_groups['group_type'].value_counts()
            ax2.pie(group_counts.values, labels=group_counts.index, autopct='%1.1f%%', startangle=90)
            ax2.set_title('分组类型分布')
        
        plt.tight_layout()
        
        if save_path is None:
            save_path = str(self.output_dir / "disease_distribution.png")
        
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        logger.info(f"病种分布图已保存: {save_path}")
        return save_path
    
    def plot_value_comparison(self, disease_groups: pd.DataFrame, save_path: str = None) -> str:
        """
        绘制分值对比图
        
        Args:
            disease_groups: 病种分组数据
            save_path: 保存路径
            
        Returns:
            保存的文件路径
        """
        if not self._check_matplotlib():
            return ""
        
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))
        
        # 1. 病种分值 vs 平均费用
        ax1 = axes[0]
        if 'disease_value' in disease_groups.columns and 'avg_cost' in disease_groups.columns:
            ax1.scatter(disease_groups['disease_value'], disease_groups['avg_cost'], 
                       alpha=0.6, s=50, c='steelblue')
            ax1.set_xlabel('病种分值')
            ax1.set_ylabel('平均费用')
            ax1.set_title('病种分值 vs 平均费用')
            
            # 添加趋势线
            z = np.polyfit(disease_groups['disease_value'], disease_groups['avg_cost'], 1)
            p = np.poly1d(z)
            ax1.plot(disease_groups['disease_value'], p(disease_groups['disease_value']), 
                    "r--", alpha=0.8, label='趋势线')
            ax1.legend()
        
        # 2. 药品分值 vs 耗材分值
        ax2 = axes[1]
        if 'drug_value' in disease_groups.columns and 'consumable_value' in disease_groups.columns:
            ax2.scatter(disease_groups['drug_value'], disease_groups['consumable_value'], 
                       alpha=0.6, s=50, c='orange')
            ax2.set_xlabel('药品分值')
            ax2.set_ylabel('耗材分值')
            ax2.set_title('药品分值 vs 耗材分值')
        
        plt.tight_layout()
        
        if save_path is None:
            save_path = str(self.output_dir / "value_comparison.png")
        
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        logger.info(f"分值对比图已保存: {save_path}")
        return save_path
    
    def plot_anomaly_scatter(self, records: pd.DataFrame, disease_groups: pd.DataFrame, save_path: str = None) -> str:
        """
        绘制异常病例散点图
        
        Args:
            records: 病例数据
            disease_groups: 病种分组数据
            save_path: 保存路径
            
        Returns:
            保存的文件路径
        """
        if not self._check_matplotlib():
            return ""
        
        fig, ax = plt.subplots(figsize=(12, 8))
        
        # 构建病种平均费用查找表
        avg_cost_map = {}
        for _, group in disease_groups.iterrows():
            disease_code = group.get('disease_code', '')
            avg_cost = group.get('avg_cost', 0)
            avg_cost_map[disease_code] = avg_cost
        
        # 计算每个病例的倍率
        rate_ratios = []
        colors = []
        
        for _, record in records.iterrows():
            disease_code = record.get('dip_disease_code', '')
            total_cost = record.get('total_cost', 0)
            avg_cost = avg_cost_map.get(disease_code, 0)
            
            if avg_cost > 0:
                rate_ratio = total_cost / avg_cost
                rate_ratios.append(rate_ratio)
                
                # 根据倍率设置颜色
                if rate_ratio >= 3.0:
                    colors.append('red')  # 极端高倍率
                elif rate_ratio >= 2.0:
                    colors.append('orange')  # 高倍率
                elif rate_ratio <= 0.3:
                    colors.append('purple')  # 极端低倍率
                elif rate_ratio <= 0.5:
                    colors.append('blue')  # 低倍率
                else:
                    colors.append('green')  # 正常
        
        # 绘制散点图
        if rate_ratios:
            ax.scatter(range(len(rate_ratios)), rate_ratios, c=colors, alpha=0.6, s=30)
            ax.axhline(y=2.0, color='orange', linestyle='--', label='高倍率阈值 (2.0)')
            ax.axhline(y=0.5, color='blue', linestyle='--', label='低倍率阈值 (0.5)')
            ax.axhline(y=3.0, color='red', linestyle='--', label='极端高倍率阈值 (3.0)')
            ax.axhline(y=0.3, color='purple', linestyle='--', label='极端低倍率阈值 (0.3)')
            ax.axhline(y=1.0, color='green', linestyle='-', alpha=0.5, label='正常 (1.0)')
        
        ax.set_xlabel('病例序号')
        ax.set_ylabel('费用倍率')
        ax.set_title('异常病例散点图')
        ax.legend()
        ax.set_ylim(0, 5)  # 限制Y轴范围
        
        plt.tight_layout()
        
        if save_path is None:
            save_path = str(self.output_dir / "anomaly_scatter.png")
        
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        logger.info(f"异常病例散点图已保存: {save_path}")
        return save_path
    
    def plot_hospital_comparison(self, records: pd.DataFrame, save_path: str = None) -> str:
        """
        绘制医院对比图
        
        Args:
            records: 病例数据
            save_path: 保存路径
            
        Returns:
            保存的文件路径
        """
        if not self._check_matplotlib():
            return ""
        
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))
        
        # 1. 各医院病例数
        ax1 = axes[0]
        if 'hospital_code' in records.columns:
            hospital_counts = records['hospital_code'].value_counts().head(20)
            ax1.barh(range(len(hospital_counts)), hospital_counts.values, color='steelblue')
            ax1.set_yticks(range(len(hospital_counts)))
            ax1.set_yticklabels(hospital_counts.index)
            ax1.set_xlabel('病例数')
            ax1.set_title('各医院病例数 (前20)')
            ax1.invert_yaxis()
        
        # 2. 各医院平均费用
        ax2 = axes[1]
        if 'hospital_code' in records.columns and 'total_cost' in records.columns:
            hospital_avg_cost = records.groupby('hospital_code')['total_cost'].mean().sort_values(ascending=False).head(20)
            ax2.barh(range(len(hospital_avg_cost)), hospital_avg_cost.values, color='orange')
            ax2.set_yticks(range(len(hospital_avg_cost)))
            ax2.set_yticklabels(hospital_avg_cost.index)
            ax2.set_xlabel('平均费用')
            ax2.set_title('各医院平均费用 (前20)')
            ax2.invert_yaxis()
        
        plt.tight_layout()
        
        if save_path is None:
            save_path = str(self.output_dir / "hospital_comparison.png")
        
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        logger.info(f"医院对比图已保存: {save_path}")
        return save_path
    
    def generate_all_charts(self, records: pd.DataFrame, disease_groups: pd.DataFrame) -> List[str]:
        """
        生成所有图表
        
        Args:
            records: 病例数据
            disease_groups: 病种分组数据
            
        Returns:
            保存的文件路径列表
        """
        saved_paths = []
        
        # 1. 费用分布图
        path = self.plot_cost_distribution(records)
        if path:
            saved_paths.append(path)
        
        # 2. 病种分布图
        path = self.plot_disease_distribution(disease_groups)
        if path:
            saved_paths.append(path)
        
        # 3. 分值对比图
        path = self.plot_value_comparison(disease_groups)
        if path:
            saved_paths.append(path)
        
        # 4. 异常病例散点图
        path = self.plot_anomaly_scatter(records, disease_groups)
        if path:
            saved_paths.append(path)
        
        # 5. 医院对比图
        path = self.plot_hospital_comparison(records)
        if path:
            saved_paths.append(path)
        
        logger.info(f"共生成 {len(saved_paths)} 个图表")
        return saved_paths
