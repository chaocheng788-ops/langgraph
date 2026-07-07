"""
LangGraph Workflow Builder — 单图编排：路由节点 + Agent 子图节点。
技能路由和 Agent 执行合并到一个 StateGraph 中，
create_react_agent 作为子图（黑盒节点）嵌入。
"""
from typing import Annotated, Sequence, List
from typing_extensions import TypedDict

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

from app.agent_setup import create_agent_graph
from app.skill_router import get_all_skills, select_relevant_skills, resolve_skills
from app.checkpointer import get_checkpointer
from app.execution_log import add_log

# 路由节点专用的提示词
ROUTER_PROMPT = (
    "你是一个技能路由器。你的唯一任务是分析用户请求，从可用技能中选择最合适的技能来响应用户。\n\n"
    "规则：\n"
    "1. 仔细理解用户描述的真实意图，而非字面意思\n"
    "2. 通过调用对应的 use_skill__* 函数来选择匹配的技能，并且返回content保证有内容\n"
    "3. 如果用户请求涉及多个领域，可以同时选择多个技能\n"
    "4. 选择技能，可以生成回答\n"
    "5. 如果没有任何技能匹配用户请求，不要调用任何函数"
)


class OrchestratorState(TypedDict):
    """编排图的状态：包含 messages、选中的技能、剩余步数。"""
    messages: Annotated[Sequence[BaseMessage], add_messages]
    selected_skills: List[str]
    remaining_steps: int


async def build_workflow(config: dict):
    """
    构建单图编排工作流：START → route → agent → END。

    route 节点：首次对话执行技能发现（LLM Function Calling），后续轮次复用已选技能
    agent 节点：create_react_agent 子图，绑定全部技能的工具
    """
    system_prompt = config.get("system_prompt", "")
    model_name = config.get("model_name", "deepseek-chat")
    api_key = config.get("api_key", "")
    base_url = config.get("base_url", "https://api.deepseek.com/v1")
    max_iterations = config.get("max_iterations", 10)

    all_skills = get_all_skills()

    # 预编译 Agent 子图：绑定所有技能的全部工具
    all_tools = []
    if all_skills:
        all_tools, _ = resolve_skills(list(all_skills.keys()))

    agent_subgraph = await create_agent_graph(
        system_prompt=system_prompt,
        tools_config=all_tools,
        max_iterations=max_iterations,
        api_key=api_key,
        model_name=model_name,
        base_url=base_url,
    )

    # ── 路由节点 ──
    async def route_node(state: OrchestratorState):
        # 已有选中的技能（来自上一轮对话）→ 直接复用，不重新路由，不重复注入 prompt
        existing_skills = state.get("selected_skills", [])
        if existing_skills:
            add_log("🧠 技能复用", f"沿用上一轮选中的技能: {existing_skills}")
            return {"selected_skills": existing_skills}

        # 首次对话：执行路由发现
        messages = state.get("messages", [])
        user_input = ""
        for m in reversed(messages):
            if isinstance(m, HumanMessage):
                user_input = str(m.content)
                break

        if not all_skills or not user_input:
            return {"selected_skills": []}

        routed_skills, discovery_info = select_relevant_skills(
            user_input, all_skills,
            api_key=api_key, base_url=base_url,
            model_name=model_name, system_prompt=ROUTER_PROMPT,
        )

        if not routed_skills:
            return {"selected_skills": []}

        _, skill_prompt = resolve_skills(routed_skills)

        new_msgs = []
        if skill_prompt:
            new_msgs.append(SystemMessage(
                content=f"[已匹配技能: {', '.join(routed_skills)}]\n\n{skill_prompt}"
            ))

        add_log("🧠 技能发现", f"从 {len(all_skills)} 个技能中自动选择: {routed_skills}")

        return {"selected_skills": routed_skills, "messages": new_msgs}

    # ── 组装外层图：START → route → agent → END ──
    graph = StateGraph(OrchestratorState)
    graph.add_node("route", route_node)
    graph.add_node("agent", agent_subgraph)
    graph.add_edge(START, "route")
    graph.add_edge("route", "agent")
    graph.add_edge("agent", END)

    checkpointer = await get_checkpointer()
    return graph.compile(checkpointer=checkpointer)