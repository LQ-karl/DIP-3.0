"""
DIP3.0 本地目录测算系统 - 路径解析模块

集中管理项目根目录、数据目录、输出目录、模板目录的解析，
消除散落在各处的硬编码绝对路径（如 F:\\DIP\\...），
使程序在任意部署位置（含 Linux CI 环境）均可运行。

优先级：
1. 环境变量 DIP_DATA_DIR / DIP_OUTPUT_DIR / DIP_TEMPLATES_DIR 显式指定
2. 否则基于本文件位置自动推导项目根目录（src/utils/paths.py -> 上溯两级）
3. 数据/输出/模板目录为项目根下的 data / output / templates
"""
import os
from pathlib import Path

# src/utils/paths.py -> parents[0]=src/utils, [1]=src, [2]=项目根(F:/DIP)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def get_project_root() -> Path:
    """返回项目根目录（F:/DIP 或 CI 检出目录）。"""
    env = os.environ.get("DIP_PROJECT_ROOT")
    if env:
        return Path(env)
    return _PROJECT_ROOT


def get_data_dir() -> Path:
    """数据字典目录，可被环境变量 DIP_DATA_DIR 覆盖。"""
    env = os.environ.get("DIP_DATA_DIR")
    if env:
        return Path(env)
    return get_project_root() / "data"


def get_output_dir() -> Path:
    """结果输出目录，可被环境变量 DIP_OUTPUT_DIR 覆盖。"""
    env = os.environ.get("DIP_OUTPUT_DIR")
    if env:
        return Path(env)
    return get_project_root() / "output"


def get_templates_dir() -> Path:
    """模板目录，可被环境变量 DIP_TEMPLATES_DIR 覆盖。"""
    env = os.environ.get("DIP_TEMPLATES_DIR")
    if env:
        return Path(env)
    return get_project_root() / "templates"


def data_file(filename: str) -> Path:
    """返回数据目录下某文件的完整路径。"""
    return get_data_dir() / filename


def output_file(filename: str) -> Path:
    """返回输出目录下某文件的完整路径。"""
    return get_output_dir() / filename


def template_file(filename: str) -> Path:
    """返回模板目录下某文件的完整路径。"""
    return get_templates_dir() / filename
