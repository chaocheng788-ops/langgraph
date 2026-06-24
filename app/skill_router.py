"""
技能发现模块 — Skill-as-Tool 模式

将技能转换为 OpenAI Function Calling 工具，
让主 LLM 通过原生 tool_calls 自行选择需要的技能。

技能来源（两套，合并使用）：
  1. skills/ 目录 — 文件定义的技能（prompt.md + YAML Front Matter）
  2. data/skills.json — 前端 API 创建的技能

流程:
  1. 合并两套技能数据，每个技能生成一个 meta-tool（name=use_skill__xxx）
  2. 用 system_prompt（原样，不拼接）+ user_input + meta_tools 调用 LLM
  3. 解析 tool_calls 提取选中的技能名
  4. 返回技能名列表，由调用方注入 prompt 和加载真实工具
"""
import json
from typing import Dict, List
from pathlib import Path

from app.skill_loader import load_skills_from_dir
from app.execution_log import add_log

DATA_DIR = Path(__file__).parent.parent / "data"
SKILLS_FILE = DATA_DIR / "skills.json"


def _read_json(filepath: Path) -> dict:
    """读取 JSON 文件"""
    if filepath.exists():
        try:
            return json.loads(filepath.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def get_all_skills() -> dict:
    """
    合并两套技能来源：文件目录 + API 创建的 JSON。
    文件目录定义的技能优先级更高（同名覆盖）。

    Returns:
        {skill_name: skill_data}
    """
    # 1. 从 skills/ 目录加载
    skills = load_skills_from_dir()

    # 2. 从 data/skills.json 加载（API 创建的技能）
    json_skills = _read_json(SKILLS_FILE)
    for name, data in json_skills.items():
        if name not in skills:
            skills[name] = data

    return skills


def build_skill_meta_tools(all_skills: dict) -> list:
    """
    将技能列表转换为 OpenAI Function Calling 工具定义。

    每个技能生成一个 function，name 为 "use_skill__技能名"，
    description 包含技能描述和所含工具摘要，无需参数。

    Args:
        all_skills: skills.json 的全部内容，key 为技能名

    Returns:
        OpenAI tools 数组，可直接传给 LLM

    示例输出:
        [{
            "type": "function",
            "function": {
                "name": "use_skill__weather_skill",
                "description": "天气查询技能。包含工具: get_weather",
                "parameters": {"type": "object", "properties": {}, "required": []}
            }
        }]
    """
    meta_tools = []
    for skill_name, skill in all_skills.items():
        tool_names = [t["name"] for t in skill.get("tools", [])]
        tool_summary = ", ".join(tool_names) if tool_names else "无"

        meta_tools.append({
            "type": "function",
            "function": {
                "name": f"use_skill__{skill_name}",
                "description": f"{skill.get('description', '')}。包含工具: {tool_summary}",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        })
    return meta_tools


def discover_skills(
    user_input: str,
    system_prompt: str,
    all_skills: dict,
    api_key: str,
    base_url: str,
    model_name: str
) -> tuple:
    """
    使用 Function Calling 让 LLM 自行选择需要的技能。

    system_prompt 原样传入，不做任何拼接。
    LLM 通过 tool_calls 返回选中的技能，无需额外 JSON 解析。

    Args:
        user_input: 用户输入文本
        system_prompt: 系统提示词（来自 prompt.json，原样使用）
        all_skills: 所有技能数据
        api_key: API 密钥
        base_url: API 地址
        model_name: 模型名称

    Returns:
        (selected_skills, discovery_detail)
        - selected_skills: 选中的技能名列表
        - discovery_detail: 发现过程的请求和响应详情，供 SSE 日志输出
    """
    if not all_skills:
        return [], None

    meta_tools = build_skill_meta_tools(all_skills)
    tool_names = [t["function"]["name"] for t in meta_tools]

    try:
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url=base_url,
            temperature=0,
        )
        llm_with_tools = llm.bind_tools(meta_tools)

        response = llm_with_tools.invoke([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input}
        ])

        tool_calls = getattr(response, "tool_calls", None) or []
        response_content = getattr(response, "content", "") or ""

        selected_skills = []
        for tc in tool_calls:
            func_name = tc.get("name", tc.get("function", {}).get("name", ""))
            if func_name.startswith("use_skill__"):
                skill_name = func_name[len("use_skill__"):]
                if skill_name in all_skills:
                    selected_skills.append(skill_name)

        add_log("🧠 技能发现", json.dumps({
            "query": user_input[:50],
            "available": list(all_skills.keys()),
            "selected": selected_skills,
            "mode": "Function Calling"
        }, ensure_ascii=False))

        # 构建发现详情供 SSE 输出
        detail = {
            "request": {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": system_prompt[:80]},
                    {"role": "user", "content": user_input[:80]}
                ],
                "tools": meta_tools
            },
            "response": {
                "content": response_content[:100] if response_content else None,
                "tool_calls": [tc.get("name", tc.get("function", {}).get("name", "")) for tc in tool_calls] if tool_calls else []
            }
        }

        return selected_skills[:3], detail

    except Exception as e:
        add_log("⚠️ 技能发现失败", f"{e}，回退到关键词匹配", "warning")
        return keyword_based_routing(user_input, all_skills), None


def keyword_based_routing(user_query: str, all_skills: dict) -> List[str]:
    """
    基于关键词的 Fallback 路由。
    当 LLM 调用不可用时使用。
    """
    if not all_skills:
        return []

    if len(all_skills) == 1:
        return list(all_skills.keys())

    skill_keywords = {}
    for name, skill in all_skills.items():
        skill_keywords[name] = skill.get("keywords", [])

    scores = {}
    for skill_name, keywords in skill_keywords.items():
        score = sum(1 for kw in keywords if kw in user_query)
        if score > 0:
            scores[skill_name] = score

    sorted_skills = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    selected = [s[0] for s in sorted_skills[:3]]

    if selected:
        add_log("🔑 关键词路由", f"匹配关键词，选择技能: {selected}")

    return selected if selected else list(all_skills.keys())[:5]


def select_relevant_skills(
    user_query: str,
    all_skills: dict,
    api_key: str = "",
    base_url: str = "https://api.deepseek.com/v1",
    model_name: str = "deepseek-chat",
    system_prompt: str = "",
    use_llm: bool = True
) -> tuple:
    """
    主入口函数: 选择相关技能。

    策略:
      1. 如果 use_llm=True，使用 Function Calling 让 LLM 自行选择
      2. 如果 LLM 调用失败，回退到关键词路由
      3. 如果都没有匹配，返回空列表

    Args:
        user_query: 用户查询
        all_skills: 所有技能数据
        api_key: API 密钥
        base_url: API 地址
        model_name: 模型名称
        system_prompt: 系统提示词（原样传入，不做拼接）
        use_llm: 是否使用 LLM 路由

    Returns:
        (selected_skills, discovery_detail)
    """
    if not all_skills or not user_query:
        return [], None

    if not use_llm or not api_key:
        return keyword_based_routing(user_query, all_skills), None

    try:
        return discover_skills(
            user_query, system_prompt, all_skills,
            api_key, base_url, model_name
        )
    except Exception:
        return keyword_based_routing(user_query, all_skills), None