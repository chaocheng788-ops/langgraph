"""
持久化存储模块。
职责:
  1. JSON 文件安全读写（_read_json / _write_json）
  2. 路径常量（DATA_DIR / MODELS_FILE / TOOLS_FILE / PROMPT_FILE）
"""
import json
from typing import Any
from pathlib import Path


# ═══════════════════════════════════════════════════════════════
# 持久化存储路径常量
# ═══════════════════════════════════════════════════════════════

DATA_DIR = Path(__file__).parent.parent / "data"  # 数据目录: langgraph/data/
DATA_DIR.mkdir(exist_ok=True)                     # 确保目录存在
MODELS_FILE = DATA_DIR / "models.json"            # 模型配置文件
TOOLS_FILE = DATA_DIR / "tools.json"              # 工具配置文件
PROMPT_FILE = DATA_DIR / "prompt.json"            # 提示词配置文件


def _read_json(filepath: Path) -> Any:
    """
    安全读取 JSON 文件，文件不存在或解析失败时返回空字典。

    Args:
        filepath: JSON 文件路径

    Returns:
        dict | list: 解析后的 JSON 数据，失败时返回 {}
    """
    if filepath.exists():
        try:
            return json.loads(filepath.read_text(encoding="utf-8"))
        except Exception:
            pass  # 文件损坏时静默返回 {}
    return {}


def _write_json(filepath: Path, data: Any) -> None:
    """
    将数据写入 JSON 文件，ensure_ascii=False 保留中文。

    Args:
        filepath: 目标文件路径
        data: 待写入的数据
    """
    filepath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")