"""
LangGraph Workflow Builder — Agent mode only。
使用 LangGraph 官方 create_react_agent 实现 ReAct 循环（推理-行动-观察）。
从 server.py 接收运行时配置，委托给 agent_setup.py 构建可执行的 Agent 图。
"""
from app.agent_setup import create_agent_graph  # Agent 图构建函数（异步）


async def build_workflow(config: dict):
    """
    根据配置字典构建一个可执行的 Agent 工作流。

    这是 server.py 调用 Agent 的统一入口。解耦了 API 层和 Agent 构建逻辑，
    支持 LangGraph CLI 等工具直接调用此函数。

    Args:
        config: 运行时配置字典，包含以下键:
            - model_name: str  模型名称，如 "deepseek-v4-pro"
            - api_key: str     API 密钥（必填）
            - base_url: str    OpenAI 兼容 API 地址
            - system_prompt: str  系统提示词
            - tools: list[dict]   工具定义列表，每个含 name/description/parameters
            - max_iterations: int  Agent 最大推理轮数

    Returns:
        CompiledStateGraph: 已编译的 LangGraph 状态图，可直接 invoke/astream
    """
    # 从配置中提取各项参数，未提供时使用默认值
    system_prompt = config.get("system_prompt", "你是一个有用的AI助手。")
    model_name = config.get("model_name", "deepseek-chat")
    api_key = config.get("api_key", "")
    base_url = config.get("base_url", "https://api.deepseek.com/v1")
    tools = config.get("tools", [])
    max_iterations = config.get("max_iterations", 10)

    # 异步委托给 agent_setup 构建完整的 ReAct Agent 图（含 checkpointer 持久化）
    return await create_agent_graph(
        system_prompt=system_prompt,
        tools_config=tools,
        max_iterations=max_iterations,
        api_key=api_key,
        model_name=model_name,
        base_url=base_url,
    )