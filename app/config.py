"""
Configuration utilities for the LangGraph Platform.
"""
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


CONFIG_DIR = Path(__file__).parent.parent / "configs"
CONFIG_DIR.mkdir(exist_ok=True)


def save_config(name: str, config: Dict[str, Any]) -> str:
    """Save a workflow configuration to disk."""
    filepath = CONFIG_DIR / f"{name}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    return str(filepath)


def load_config(name: str) -> Optional[Dict[str, Any]]:
    """Load a workflow configuration from disk."""
    filepath = CONFIG_DIR / f"{name}.json"
    if filepath.exists():
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def list_configs() -> list:
    """List all saved workflow configurations."""
    configs = []
    for f in CONFIG_DIR.glob("*.json"):
        configs.append(f.stem)
    return configs


def export_to_yaml(config: Dict[str, Any]) -> str:
    """Export workflow configuration to YAML format."""
    try:
        import yaml
        return yaml.dump(config, default_flow_style=False, allow_unicode=True)
    except ImportError:
        return json.dumps(config, ensure_ascii=False, indent=2)
