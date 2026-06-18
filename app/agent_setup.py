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
# ── 类型导入 ──
from typing import Annotated, Optional, Sequence
from typing import List, Dict

# ── LangChain / LangGraph 核心依赖 ──
from langchain_core.messages import BaseMessage  # 消息基类
from langgraph.prebuilt import create_react_agent  # 官方 ReAct Agent 工厂函数
from langgraph.graph.message import add_messages  # 消息累积 Reducer（追加而非覆盖）
from langgraph.graph.state import CompiledStateGraph  # 编译后的图类型
from typing_extensions import TypedDict  # TypedDict 定义 AgentState 类型

# ── 内部模块 ──
from app.checkpointer import get_checkpointer  # Checkpointer 单例
from app.execution_log import add_log  # 全局日志
from app.tool_factory import get_tools_from_config  # 工具工厂


# ═══════════════════════════════════════════════════════════════
# AgentState — ReAct Agent 的状态结构
# ═══════════════════════════════════════════════════════════════

class AgentState(TypedDict):
    """
    ReAct Agent 的状态定义。
    兼容 LangGraph 官方 create_react_agent 的 State Schema。
    """
    # messages 使用 add_messages Reducer，新消息追加到列表末尾而非替换
    messages: Annotated[Sequence[BaseMessage], add_messages]
    remaining_steps: int  # 剩余可用步数，防止无限循环


# ═══════════════════════════════════════════════════════════════
# create_agent_graph — 核心函数，构建完整的 ReAct Agent
# ═══════════════════════════════════════════════════════════════

async def create_agent_graph(
    system_prompt: str = "你是一个有用的AI助手。",
    tools_config: Optional[List[Dict[str, str]]] = None,
    max_iterations: int = 10,
    api_key: Optional[str] = None,
    model_name: str = "deepseek-chat",
    base_url: str = "https://api.deepseek.com/v1",
) -> CompiledStateGraph:
    """
    创建 ReAct Agent 图 —— 这是系统核心，整合了 LLM + 工具 + Checkpointer。

    流程:
      1. 校验 api_key
      2. 从 tools_config 获取工具函数列表
      3. 初始化 ChatOpenAI 并绑定工具
      4. 调用 LangGraph 官方 create_react_agent 生成图
      5. 返回已编译的 CompiledStateGraph

    Args:
        system_prompt: 系统提示词，定义 Agent 行为和角色
        tools_config: 工具配置列表，来自前端 tools.json
        max_iterations: 最大推理轮数（LLM↔Tool 循环次数）
        api_key: API 密钥（必填）
        model_name: 模型名称，如 "deepseek-chat" / "deepseek-reasoner"
        base_url: OpenAI 兼容 API 端点地址

    Returns:
        CompiledStateGraph: 已编译的 LangGraph 状态图，可直接调用 invoke/astream

    Raises:
        ValueError: api_key 为空时抛出
        ImportError: langchain-openai 未安装时抛出
    """
    if not api_key:
        raise ValueError("必须提供 api_key 才能使用远程模型")

    # ── 第 1 步: 获取工具函数列表 ──
    tools = get_tools_from_config(tools_config or [])

    # ── 第 2 步: 初始化远程 LLM ──
    add_log("模型选择", f"使用远程模型: {model_name}, API Key: {api_key[:8]}...")
    try:
        from langchain_openai import ChatOpenAI  # OpenAI 兼容客户端
        model = ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url=base_url,
            temperature=0.7,  # 生成随机性，0-2
        )
        if tools:
            # 如果配置了工具，通过 bind_tools 让 LLM 知道可用工具
            tool_names = [t.__name__ for t in tools]
            add_log("工具绑定", f"绑定 {len(tools)} 个工具: {tool_names}")
            model = model.bind_tools(tools)  # 绑定后 LLM 可在响应中返回 tool_calls
        add_log("准备就绪", "远程模型初始化完成, 等待用户输入")
    except ImportError:
        add_log("依赖错误", "缺少 langchain-openai 包", "error")
        raise ImportError("请先安装 langchain-openai: pip install langchain-openai")

    # ── 第 3 步: 构建 ReAct Agent 图 ──
    graph = create_react_agent(
        model,                          # 已绑定工具的 LLM
        tools=tools,                    # 可用工具列表
        prompt=system_prompt,           # 系统提示词（直接作为 prompt 参数）
        state_schema=AgentState,        # 状态结构（messages + remaining_steps）
        checkpointer=await get_checkpointer(),  # SQLite 持久化，跨请求保持上下文
        version="v2",                   # 使用 v2 版本的 ReAct 实现
    )
    return graph  # 返回编译后的图，调用方通过 invoke/astream 执行