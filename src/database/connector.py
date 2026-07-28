"""
DIP3.0本地目录测算系统 - 数据库连接器
支持SQLite、MySQL、SQL Server、Oracle
"""
import pandas as pd
from typing import Optional, Dict, Any, List
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class DatabaseConnector:
    """数据库连接器"""
    
    def __init__(self, db_type: str = "sqlite", **kwargs):
        """
        初始化数据库连接器
        
        Args:
            db_type: 数据库类型 (sqlite, mysql, sqlserver, oracle)
            **kwargs: 连接参数
        """
        self.db_type = db_type.lower()
        self.connection = None
        self.engine = None
        
        if self.db_type == "sqlite":
            self.db_path = kwargs.get("db_path", "dip3.db")
        elif self.db_type == "mysql":
            self.host = kwargs.get("host", "localhost")
            self.port = kwargs.get("port", 3306)
            self.user = kwargs.get("user", "root")
            self.password = kwargs.get("password", "")
            self.database = kwargs.get("database", "dip3")
        elif self.db_type == "sqlserver":
            self.host = kwargs.get("host", "localhost")
            self.port = kwargs.get("port", 1433)
            self.user = kwargs.get("user", "sa")
            self.password = kwargs.get("password", "")
            self.database = kwargs.get("database", "dip3")
        elif self.db_type == "oracle":
            self.host = kwargs.get("host", "localhost")
            self.port = kwargs.get("port", 1521)
            self.user = kwargs.get("user", "system")
            self.password = kwargs.get("password", "")
            self.service_name = kwargs.get("service_name", "orcl")
        else:
            raise ValueError(f"不支持的数据库类型: {db_type}")
    
    def get_connection_string(self) -> str:
        """获取数据库连接字符串"""
        if self.db_type == "sqlite":
            return f"sqlite:///{self.db_path}"
        elif self.db_type == "mysql":
            return f"mysql+pymysql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"
        elif self.db_type == "sqlserver":
            return f"mssql+pyodbc://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}?driver=ODBC+Driver+17+for+SQL+Server"
        elif self.db_type == "oracle":
            return f"oracle+cx_oracle://{self.user}:{self.password}@{self.host}:{self.port}/{self.service_name}"
        else:
            raise ValueError(f"不支持的数据库类型: {self.db_type}")
    
    def connect(self):
        """建立数据库连接"""
        try:
            from sqlalchemy import create_engine
            conn_str = self.get_connection_string()
            self.engine = create_engine(conn_str)
            self.connection = self.engine.connect()
            logger.info(f"成功连接到{self.db_type}数据库")
            return True
        except Exception as e:
            logger.error(f"数据库连接失败: {e}")
            return False
    
    def disconnect(self):
        """关闭数据库连接"""
        if self.connection:
            self.connection.close()
        if self.engine:
            self.engine.dispose()
        logger.info("数据库连接已关闭")
    
    def read_table(self, table_name: str, schema: str = None) -> pd.DataFrame:
        """
        读取数据库表
        
        Args:
            table_name: 表名
            schema: Schema名（可选）
            
        Returns:
            DataFrame
        """
        try:
            df = pd.read_sql_table(table_name, self.engine, schema=schema)
            logger.info(f"成功读取表 {table_name}，共 {len(df)} 行")
            return df
        except Exception as e:
            logger.error(f"读取表 {table_name} 失败: {e}")
            return pd.DataFrame()
    
    def read_query(self, query: str) -> pd.DataFrame:
        """
        执行SQL查询
        
        Args:
            query: SQL查询语句
            
        Returns:
            DataFrame
        """
        try:
            df = pd.read_sql_query(query, self.engine)
            logger.info(f"查询成功，共 {len(df)} 行")
            return df
        except Exception as e:
            logger.error(f"查询失败: {e}")
            return pd.DataFrame()
    
    def write_table(self, df: pd.DataFrame, table_name: str, if_exists: str = "append"):
        """
        写入数据到数据库表
        
        Args:
            df: 要写入的DataFrame
            table_name: 目标表名
            if_exists: 表存在时的处理方式 (append, replace, fail)
        """
        try:
            df.to_sql(table_name, self.engine, if_exists=if_exists, index=False)
            logger.info(f"成功写入 {len(df)} 行数据到表 {table_name}")
            return True
        except Exception as e:
            logger.error(f"写入表 {table_name} 失败: {e}")
            return False
    
    def execute_sql(self, sql: str):
        """
        执行SQL语句
        
        Args:
            sql: SQL语句
        """
        try:
            self.connection.execute(sql)
            logger.info("SQL语句执行成功")
            return True
        except Exception as e:
            logger.error(f"SQL语句执行失败: {e}")
            return False


class FileDataReader:
    """文件数据读取器"""
    
    @staticmethod
    def read_csv(file_path: str, encoding: str = "utf-8", **kwargs) -> pd.DataFrame:
        """
        读取CSV文件
        
        Args:
            file_path: 文件路径
            encoding: 编码格式
            
        Returns:
            DataFrame
        """
        try:
            df = pd.read_csv(file_path, encoding=encoding, **kwargs)
            logger.info(f"成功读取CSV文件 {file_path}，共 {len(df)} 行")
            return df
        except Exception as e:
            logger.error(f"读取CSV文件失败: {e}")
            return pd.DataFrame()
    
    @staticmethod
    def read_excel(file_path: str, sheet_name: str = 0, **kwargs) -> pd.DataFrame:
        """
        读取Excel文件
        
        Args:
            file_path: 文件路径
            sheet_name: Sheet名称或索引
            
        Returns:
            DataFrame
        """
        try:
            df = pd.read_excel(file_path, sheet_name=sheet_name, **kwargs)
            logger.info(f"成功读取Excel文件 {file_path}，共 {len(df)} 行")
            return df
        except Exception as e:
            logger.error(f"读取Excel文件失败: {e}")
            return pd.DataFrame()


class UnifiedDataReader:
    """统一数据读取器"""
    
    def __init__(self):
        self.file_reader = FileDataReader()
        self.db_connector = None
    
    def read_data(self, source: str, source_type: str = "auto", **kwargs) -> pd.DataFrame:
        """
        统一数据读取接口
        
        Args:
            source: 数据源（文件路径或数据库表名）
            source_type: 数据源类型 (auto, csv, excel, sqlite, mysql, sqlserver, oracle)
            **kwargs: 额外参数
            
        Returns:
            DataFrame
        """
        if source_type == "auto":
            source_type = self._detect_source_type(source)
        
        if source_type in ["csv"]:
            return self.file_reader.read_csv(source, **kwargs)
        elif source_type in ["excel", "xlsx", "xls"]:
            return self.file_reader.read_excel(source, **kwargs)
        elif source_type in ["sqlite", "mysql", "sqlserver", "oracle"]:
            if self.db_connector is None or self.db_connector.db_type != source_type:
                self.db_connector = DatabaseConnector(source_type, **kwargs)
                self.db_connector.connect()
            return self.db_connector.read_table(source)
        else:
            logger.error(f"不支持的数据源类型: {source_type}")
            return pd.DataFrame()
    
    def _detect_source_type(self, source: str) -> str:
        """自动检测数据源类型"""
        if source.endswith(".csv"):
            return "csv"
        elif source.endswith((".xlsx", ".xls")):
            return "excel"
        elif source.endswith(".db") or source.endswith(".sqlite"):
            return "sqlite"
        else:
            return "unknown"


# 便捷函数
def read_csv(file_path: str, **kwargs) -> pd.DataFrame:
    """读取CSV文件"""
    return FileDataReader.read_csv(file_path, **kwargs)


def read_excel(file_path: str, **kwargs) -> pd.DataFrame:
    """读取Excel文件"""
    return FileDataReader.read_excel(file_path, **kwargs)


def read_database(table_name: str, db_type: str = "sqlite", **kwargs) -> pd.DataFrame:
    """读取数据库表"""
    connector = DatabaseConnector(db_type, **kwargs)
    connector.connect()
    df = connector.read_table(table_name)
    connector.disconnect()
    return df
