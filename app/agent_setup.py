"""
LangGraph Agent 核心组装模块。
职责:
  1. AgentState — ReAct Agent 的状态结构定义
  2. create_agent_graph — 组装 ReAct Agent 并返回 CompiledStateGraph

依赖模块：
  - app.checkpointer: Checkpointer 单例
  - app.execution_log: 日志系统
  - app.tool_factory: 动态工具工厂
"""
from typing import Annotated, Optional, Sequence
from typing import List, Dict

from langchain_core.messages import BaseMessage
from langgraph.prebuilt import create_react_agent
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from typing_extensions import TypedDict

from app.checkpointer import get_checkpointer
from app.execution_log import add_log
from app.tool_factory import get_tools_from_config


class AgentState(TypedDict):
    """
    ReAct Agent 的状态定义。
    兼容 LangGraph 官方 create_react_agent 的 State Schema。
    """
    messages: Annotated[Sequence[BaseMessage], add_messages]
    remaining_steps: int
    selected_skills: List[str]  # 选中的技能列表，跨轮次持久化


async def create_agent_graph(
    system_prompt: str = "你是一个有用的AI助手。",
    tools_config: Optional[List[Dict[str, str]]] = None,
    max_iterations: int = 10,
    api_key: Optional[str] = None,
    model_name: str = "deepseek-chat",
    base_url: str = "https://api.deepseek.com/v1",
) -> CompiledStateGraph:
    if not api_key:
        raise ValueError("必须提供 api_key 才能使用远程模型")

    tools = get_tools_from_config(tools_config or [])

    add_log("模型选择", f"使用远程模型: {model_name}, API Key: {api_key[:8]}...")
    try:
        from langchain_openai import ChatOpenAI
        model = ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url=base_url,
            temperature=0.7,
        )
        if tools:
            tool_names = [t.__name__ for t in tools]
            add_log("工具绑定", f"绑定 {len(tools)} 个工具: {tool_names}")
            model = model.bind_tools(tools)
        add_log("准备就绪", "远程模型初始化完成, 等待用户输入")
    except ImportError:
        add_log("依赖错误", "缺少 langchain-openai 包", "error")
        raise ImportError("请先安装 langchain-openai: pip install langchain-openai")

    graph = create_react_agent(
        model,
        tools=tools,
        prompt=system_prompt,
        state_schema=AgentState,
        checkpointer=await get_checkpointer(),
        version="v2",
    )
    return graph