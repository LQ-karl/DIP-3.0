"""
DIP按病种分值分组测算工具 - 数据加载模块
用于加载目录库、字典等数据文件
"""
import pandas as pd
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import os

from ..models.models import DiseaseGroup, GroupType
from .paths import get_data_dir


class DataLoader:
    """数据加载器"""
    
    def __init__(self, data_dir: str = None):
        """
        初始化数据加载器

        Args:
            data_dir: 数据目录路径（默认取项目 data 目录）
        """
        self.data_dir = Path(data_dir) if data_dir else get_data_dir()
        self.loaded_data = {}
    
    def load_excel(self, filename: str, sheet_name: str = 0) -> pd.DataFrame:
        """
        加载Excel文件
        
        Args:
            filename: 文件名
            sheet_name: 工作表名称或索引
            
        Returns:
            DataFrame
        """
        file_path = self.data_dir / filename
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        try:
            df = pd.read_excel(file_path, sheet_name=sheet_name)
            self.loaded_data[filename] = df
            return df
        except Exception as e:
            raise Exception(f"加载文件失败 {filename}: {str(e)}")
    
    def load_icd10_directory(self) -> pd.DataFrame:
        """
        加载ICD-10疾病诊断目录
        
        Returns:
            ICD-10目录DataFrame
        """
        df = self.load_excel("ICD10国临版2.0对照医保版2.0_0125.xlsx")
        rename_map = {
            "国临版编码": "国临版代码",
            "国临版名称": "国临版名称",
            "医保版2.0编码": "医保版代码",
            "医保版2.0名称": "医保版名称",
        }
        df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
        return df
    
    def load_icd9_directory(self) -> pd.DataFrame:
        """
        加载ICD-9-CM-3手术操作目录
        
        Returns:
            ICD-9-CM-3目录DataFrame
        """
        df = self.load_excel("ICD9国临版3.0对照医保版2.0_0125.xlsx")
        rename_map = {
            "国临3.0手术代码": "国临版代码",
            "国临3.0手术名称": "国临版名称",
            "医保2.0手术代码": "医保版代码",
            "医保2.0手术名称": "医保版名称",
        }
        df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
        return df
    
    def load_cci_index(self) -> pd.DataFrame:
        """
        加载CCI（Charlson合并症指数）目录
        
        Returns:
            CCI目录DataFrame
        """
        df = self.load_excel("CCI.xlsx")
        rename_map = {
            "ICD10 code": "ICD10代码",
            "Charlson component": "Charlson组成部分",
        }
        df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
        return df
    
    def load_severity_classification(self) -> pd.DataFrame:
        """
        加载中重度分型诊断目录
        
        Returns:
            严重程度分型目录DataFrame
        """
        df = self.load_excel("中重度分型诊断.xlsx")
        return df
    
    def load_low_standard_directory(self) -> pd.DataFrame:
        """
        加载低标目录
        
        Returns:
            低标目录DataFrame
        """
        df = self.load_excel("低标目录(1).xlsx", sheet_name="dic_low_rw")
        if len(df) > 0 and str(df.iloc[0, 0]).strip() == "序号":
            df = pd.read_excel(
                self.data_dir / "低标目录(1).xlsx",
                sheet_name="dic_low_rw",
                header=1
            )
        rename_map = {
            "序号": "序号",
            "诊断代码": "ICD代码",
            "诊断名称": "疾病名称",
        }
        df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
        return df
    
    def load_new_surgery_codes(self) -> pd.DataFrame:
        """
        加载新增医保手术操作代码
        
        Returns:
            新增手术操作代码DataFrame
        """
        df = self.load_excel("新增医保手术操作代码.xlsx")
        return df
    
    def load_assistant_classification(self) -> pd.DataFrame:
        """
        加载辅助分型参考数据
        
        Returns:
            辅助分型参考DataFrame
        """
        df = self.load_excel("辅助分型AI参考.xlsx", sheet_name="GX_ASSI")
        return df
    
    def get_icd10_mapping(self) -> Dict[str, str]:
        """
        获取ICD-10国临版到医保版的映射
        
        Returns:
            映射字典
        """
        df = self.load_icd10_directory()
        mapping = {}
        for _, row in df.iterrows():
            national_code = str(row["国临版代码"]).strip()
            medical_code = str(row["医保版代码"]).strip()
            if national_code and medical_code:
                mapping[national_code] = medical_code
        return mapping
    
    def get_icd9_mapping(self) -> Dict[str, str]:
        """
        获取ICD-9-CM-3国临版到医保版的映射
        
        Returns:
            映射字典
        """
        df = self.load_icd9_directory()
        mapping = {}
        for _, row in df.iterrows():
            national_code = str(row["国临版代码"]).strip()
            medical_code = str(row["医保版代码"]).strip()
            if national_code and medical_code:
                mapping[national_code] = medical_code
        return mapping
    
    def get_cci_mapping(self) -> Dict[str, int]:
        """
        获取CCI指数映射
        
        Returns:
            ICD-10代码到CCI分数的映射
        """
        df = self.load_cci_index()
        mapping = {}
        for _, row in df.iterrows():
            icd_code = str(row["ICD10代码"]).strip()
            component = str(row["Charlson组成部分"]).strip()
            if icd_code:
                # 根据Charlson组成部分确定分数
                score = self._get_cci_score(component)
                mapping[icd_code] = score
        return mapping
    
    def _get_cci_score(self, component: str) -> int:
        """
        根据Charlson组成部分获取CCI分数
        
        Args:
            component: Charlson组成部分描述
            
        Returns:
            CCI分数
        """
        # 简化的CCI评分规则
        if "心肌梗死" in component or "充血性心力衰竭" in component:
            return 1
        elif "周围血管疾病" in component or "脑血管疾病" in component:
            return 1
        elif "痴呆" in component:
            return 1
        elif "慢性肺部疾病" in component:
            return 1
        elif "结缔组织病" in component or "溃疡病" in component:
            return 1
        elif "轻度肝脏疾病" in component:
            return 1
        elif "糖尿病" in component:
            return 1
        elif "偏瘫" in component:
            return 2
        elif "中度或重度肾脏疾病" in component:
            return 2
        elif "糖尿病合并并发症" in component:
            return 2
        elif "任何肿瘤" in component or "白血病" in component or "淋巴瘤" in component:
            return 2
        elif "中度或重度肝脏疾病" in component:
            return 3
        elif "转移性实体瘤" in component:
            return 6
        elif "AIDS" in component:
            return 6
        else:
            return 0
    
    def load_all_data(self) -> Dict[str, pd.DataFrame]:
        """
        加载所有数据文件
        
        Returns:
            所有数据的字典
        """
        data = {}
        
        try:
            data["icd10"] = self.load_icd10_directory()
        except Exception as e:
            print(f"加载ICD-10目录失败: {e}")
        
        try:
            data["icd9"] = self.load_icd9_directory()
        except Exception as e:
            print(f"加载ICD-9目录失败: {e}")
        
        try:
            data["cci"] = self.load_cci_index()
        except Exception as e:
            print(f"加载CCI指数失败: {e}")
        
        try:
            data["severity"] = self.load_severity_classification()
        except Exception as e:
            print(f"加载严重程度分型失败: {e}")
        
        try:
            data["low_standard"] = self.load_low_standard_directory()
        except Exception as e:
            print(f"加载低标目录失败: {e}")
        
        try:
            data["new_surgery"] = self.load_new_surgery_codes()
        except Exception as e:
            print(f"加载新增手术代码失败: {e}")
        
        return data


class DiseaseGroupLoader:
    """病种组合加载器"""
    
    def __init__(self, data_dir: str = None):
        self.data_dir = Path(data_dir) if data_dir else get_data_dir()
        self.data_loader = DataLoader(data_dir)
    
    def load_disease_groups_from_excel(self, filename: str) -> List[DiseaseGroup]:
        """
        从Excel文件加载病种组合
        
        Args:
            filename: Excel文件名
            
        Returns:
            病种组合列表
        """
        df = self.data_loader.load_excel(filename)
        groups = []
        
        for _, row in df.iterrows():
            try:
                group = DiseaseGroup(
                    disease_code=str(row.get("病种代码", row.get("DIP组合代码", ""))),
                    disease_name=str(row.get("病种名称", row.get("DIP组合名称", ""))),
                    main_diag_code=str(row.get("主要诊断代码", "")),
                    main_diag_name=str(row.get("主要诊断名称", "")),
                    main_oprn_code=str(row.get("主要手术操作代码", row.get("主要操作代码", ""))),
                    main_oprn_name=str(row.get("主要手术操作名称", row.get("主要操作名称", ""))),
                    related_oprn_code=str(row.get("相关手术操作代码", row.get("相关操作代码", ""))),
                    related_oprn_name=str(row.get("相关手术操作名称", row.get("相关操作名称", ""))),
                    case_count=int(row.get("病例数", 0)),
                    avg_cost=float(row.get("次均费用", 0))
                )
                groups.append(group)
            except Exception as e:
                print(f"解析病种组合失败: {e}")
                continue
        
        return groups
    
    def create_disease_group(
        self,
        disease_code: str,
        disease_name: str,
        main_diag_code: str,
        main_diag_name: str,
        main_oprn_code: str = "",
        main_oprn_name: str = "",
        related_oprn_code: str = "",
        related_oprn_name: str = "",
        case_count: int = 0,
        avg_cost: float = 0
    ) -> DiseaseGroup:
        """
        创建病种组合对象
        
        Args:
            病种组合属性
            
        Returns:
            病种组合对象
        """
        return DiseaseGroup(
            disease_code=disease_code,
            disease_name=disease_name,
            main_diag_code=main_diag_code,
            main_diag_name=main_diag_name,
            main_oprn_code=main_oprn_code,
            main_oprn_name=main_oprn_name,
            related_oprn_code=related_oprn_code,
            related_oprn_name=related_oprn_name,
            case_count=case_count,
            avg_cost=avg_cost
        )
