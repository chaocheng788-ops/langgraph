"""
LLM 辅助技能路由模块
使用轻量级 LLM 根据用户意图选择相关技能，减少主 LLM 的 token 消耗。
"""
import json
from typing import Dict, List, Optional
from pathlib import Path

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


def build_skill_catalog(all_skills: dict) -> str:
    """
    构建技能目录文本，用于传给 Router LLM。

    格式示例:
      1. weather_skill
         描述: 提供天气查询相关功能
         包含工具: get_weather (查询城市天气)
      2. search_skill
         描述: 提供网页搜索功能
         包含工具: search_web (搜索网页信息)
    """
    lines = []
    for idx, (skill_name, skill_data) in enumerate(all_skills.items(), 1):
        description = skill_data.get("description", "无描述")
        tools = skill_data.get("tools", [])

        tool_summary = ", ".join([
            f"{t['name']} ({t.get('description', '')[:30]})"
            for t in tools[:3]
        ])

        lines.append(f"{idx}. {skill_name}")
        lines.append(f"   描述: {description}")
        lines.append(f"   包含工具: {tool_summary if tool_summary else '无'}")
        lines.append("")

    return "\n".join(lines)


ROUTER_SYSTEM_PROMPT = """你是一个智能意图分类助手。你的任务是根据用户的问题，从可用技能列表中选择最相关的 1-3 个技能。

选择原则:
1. 仔细分析用户问题的意图和需求
2. 只选择真正需要用到的技能，不要过度选择
3. 如果用户问题涉及多个领域，可以选择多个技能
4. 如果没有匹配的技能，返回空列表 []
5. 必须严格按照 JSON 格式返回

输出格式:
{"selected_skills": ["skill_name1", "skill_name2"]}

示例 1:
用户: 北京今天天气怎么样？
输出: {"selected_skills": ["weather_skill"]}

示例 2:
用户: 帮我查一下苹果公司的最新新闻，然后翻译成中文
输出: {"selected_skills": ["search_skill", "translation_skill"]}

示例 3:
用户: 你好
输出: {"selected_skills": []}"""


def llm_based_routing(
    user_query: str,
    all_skills: dict,
    api_key: str,
    base_url: str = "https://api.deepseek.com/v1",
    model: str = "deepseek-chat"
) -> List[str]:
    """
    使用 LLM 进行技能路由。

    Args:
        user_query: 用户查询文本
        all_skills: 所有技能数据（从 skills.json 读取）
        api_key: API 密钥
        base_url: API 地址
        model: 使用的模型名称

    Returns:
        相关技能名称列表，如 ["weather_skill", "search_skill"]
    """
    if not all_skills:
        return []

    if len(all_skills) == 1:
        return list(all_skills.keys())

    skill_catalog = build_skill_catalog(all_skills)
    user_prompt = f"""可用技能目录:
{skill_catalog}

用户问题: {user_query}

请输出 JSON 格式的选择结果:"""

    try:
        from langchain_openai import ChatOpenAI

        router_llm = ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=0,
            max_tokens=200
        )

        response = router_llm.invoke([
            {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ])

        content = response.content.strip()

        # 提取 JSON（处理 ```json ... ``` 包裹情况）
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        result = json.loads(content)
        selected_skills = result.get("selected_skills", [])

        # 验证技能名称
        valid_skills = [s for s in selected_skills if s in all_skills]

        add_log("🧠 路由决策", json.dumps({
            "query": user_query[:50],
            "available": list(all_skills.keys()),
            "selected": valid_skills,
            "router_model": model
        }, ensure_ascii=False))

        return valid_skills[:3]

    except Exception as e:
        add_log("⚠️ 路由失败", f"Router LLM 调用失败: {e}，回退到全部技能", "warning")
        return list(all_skills.keys())[:5]


def keyword_based_routing(user_query: str, all_skills: dict) -> List[str]:
    """
    基于关键词的 Fallback 路由。
    当 LLM 路由不可用时使用。
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
    use_llm: bool = True
) -> List[str]:
    """
    主入口函数: 选择相关技能。

    策略:
      1. 如果 use_llm=True，先尝试 LLM 路由
      2. 如果 LLM 路由失败，回退到关键词路由
      3. 如果都没有匹配，返回全部技能

    Args:
        user_query: 用户查询
        all_skills: 所有技能数据
        api_key: API 密钥
        base_url: API 地址
        use_llm: 是否使用 LLM 路由

    Returns:
        相关技能名称列表
    """
    if not all_skills or not user_query:
        return list(all_skills.keys()) if all_skills else []

    if not use_llm or not api_key:
        # 没有 API Key 时使用关键词路由
        return keyword_based_routing(user_query, all_skills)

    try:
        return llm_based_routing(user_query, all_skills, api_key, base_url)
    except Exception:
        return keyword_based_routing(user_query, all_skills)