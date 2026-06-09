"""
LangGraph Workflow Builder — Agent mode only.
Uses LangGraph's official create_react_agent for ReAct loop.
"""
from app.agent_setup import create_agent_graph


def build_workflow(config: dict):
    """
    Build an agent workflow from configuration.

    Args:
        config: dict with keys:
            - model_name: str ("fake" or "deepseek-chat"/"deepseek-reasoner")
            - api_key: str (required for real models)
            - system_prompt: str
            - tools: list of {name, description, parameters}
            - max_iterations: int

    Returns:
        A compiled LangGraph StateGraph.
    """
    system_prompt = config.get("system_prompt", "你是一个有用的AI助手。")
    model_name = config.get("model_name", "fake")
    api_key = config.get("api_key", "")
    tools = config.get("tools", [])
    max_iterations = config.get("max_iterations", 10)

    return create_agent_graph(
        system_prompt=system_prompt,
        tools_config=tools,
        max_iterations=max_iterations,
        api_key=api_key,
        model_name=model_name,
    )
