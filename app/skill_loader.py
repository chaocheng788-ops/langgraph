"""
技能文件加载器

从 skills/ 目录读取以 prompt.md 定义的技能。
每个技能是一个子目录，包含 prompt.md 文件，
其 YAML Front Matter 定义技能元数据，正文为 prompt 内容。

目录结构:
  skills/
    architect/
      prompt.md     ← YAML Front Matter + prompt 正文
    weather/
      prompt.md
      tools.json    ← 可选：工具定义
"""
import yaml
import json
from pathlib import Path
from typing import Dict, Tuple, Optional

from app.execution_log import add_log

SKILLS_DIR = Path(__file__).parent.parent / "skills"


def parse_front_matter(content: str) -> Tuple[dict, str]:
    """
    解析 YAML Front Matter。

    格式:
      ---
      name: architect
      version: 1.0.0
      description: 架构图生成
      ---
      正文内容...

    Returns:
        (metadata_dict, body_content)
    """
    content = content.lstrip()
    if not content.startswith("---"):
        return {}, content

    # 找到第二个 ---
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content

    yaml_str = parts[1].strip()
    body = parts[2].strip()

    try:
        metadata = yaml.safe_load(yaml_str) or {}
    except yaml.YAMLError:
        metadata = {}

    return metadata, body


def load_skill_from_dir(skill_name: str) -> Optional[dict]:
    """
    从 skills/目录加载单个技能。

    Args:
        skill_name: 技能目录名，如 "architect"

    Returns:
        技能数据字典，包含 name/description/prompt/tools 等字段
        如果目录或 prompt.md 不存在，返回 None
    """
    skill_dir = SKILLS_DIR / skill_name
    if not skill_dir.is_dir():
        return None

    prompt_file = skill_dir / "prompt.md"
    if not prompt_file.exists():
        return None

    try:
        content = prompt_file.read_text(encoding="utf-8")
    except Exception:
        return None

    metadata, body = parse_front_matter(content)

    # 构建技能数据
    skill_data = {
        "name": metadata.get("name", skill_name),
        "description": metadata.get("description", ""),
        "version": metadata.get("version", "1.0.0"),
        "prompt": body,
        "tools": [],
        "_source": "file",  # 标记来源为文件目录
    }

    # 读取可选的 tools.json
    tools_file = skill_dir / "tools.json"
    if tools_file.exists():
        try:
            tools_data = json.loads(tools_file.read_text(encoding="utf-8"))
            if isinstance(tools_data, list):
                skill_data["tools"] = tools_data
            elif isinstance(tools_data, dict):
                skill_data["tools"] = list(tools_data.values())
        except Exception:
            pass

    return skill_data


def load_skills_from_dir() -> dict:
    """
    扫描 skills/ 目录，加载所有技能。

    Returns:
        {skill_name: skill_data}，与 skills.json 格式兼容
    """
    if not SKILLS_DIR.is_dir():
        return {}

    skills = {}
    for item in SKILLS_DIR.iterdir():
        if not item.is_dir():
            continue
        skill_data = load_skill_from_dir(item.name)
        if skill_data:
            skills[skill_data["name"]] = skill_data

    if skills:
        add_log("📁 技能目录", f"从 skills/ 加载 {len(skills)} 个技能: {list(skills.keys())}")

    return skills