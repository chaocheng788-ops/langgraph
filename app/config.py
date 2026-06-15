"""
配置管理工具模块。
提供工作流配置的持久化存储：保存/加载/列出 JSON 配置，支持导出为 YAML。

注意：此模块用于 LangGraph CLI 工作流配置（configs/ 目录），
     与 data/ 目录下的 models.json/tools.json（Web UI 配置）是独立的两套体系。
"""
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


# 配置文件存储目录（项目根/configs/，自动创建）
CONFIG_DIR = Path(__file__).parent.parent / "configs"
CONFIG_DIR.mkdir(exist_ok=True)


def save_config(name: str, config: Dict[str, Any]) -> str:
    """
    将工作流配置保存为 JSON 文件。

    Args:
        name: 配置名称（不含扩展名，如 "my_workflow"）
        config: 配置字典，包含 model/tools/prompt 等字段

    Returns:
        str: 保存后的文件路径
    """
    filepath = CONFIG_DIR / f"{name}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)  # ensure_ascii=False 保留中文
    return str(filepath)


def load_config(name: str) -> Optional[Dict[str, Any]]:
    """
    从磁盘加载指定名称的工作流配置。

    Args:
        name: 配置名称（不含 .json 扩展名）

    Returns:
        dict | None: 配置字典，文件不存在时返回 None
    """
    filepath = CONFIG_DIR / f"{name}.json"
    if filepath.exists():
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def list_configs() -> list:
    """
    列出所有已保存的工作流配置名称。

    Returns:
        list[str]: 配置名称列表（已去除 .json 扩展名）
    """
    configs = []
    for f in CONFIG_DIR.glob("*.json"):
        configs.append(f.stem)  # Path.stem 返回不含扩展名的文件名
    return configs


def export_to_yaml(config: Dict[str, Any]) -> str:
    """
    将工作流配置导出为 YAML 格式字符串。
    优先使用 PyYAML 库，未安装时回退为 JSON 格式。

    Args:
        config: 配置字典

    Returns:
        str: YAML 格式字符串（或 JSON 作为回退）
    """
    try:
        import yaml
        # default_flow_style=False 输出块风格（多行），allow_unicode=True 保留中文
        return yaml.dump(config, default_flow_style=False, allow_unicode=True)
    except ImportError:
        # PyYAML 未安装时返回格式化的 JSON
        return json.dumps(config, ensure_ascii=False, indent=2)