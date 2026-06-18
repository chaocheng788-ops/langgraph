"""
OpenAI ↔ LangChain 消息格式转换。
职责:
  1. _openai_messages_to_langchain — 将 OpenAI 格式的消息数组转为 LangChain 消息列表
  2. 处理 tool_calls / tool_call_id / name / reasoning_content 等字段
"""
from typing import List

from langchain_core.messages import (
    AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage,
)

from app.execution_log import add_log


# 角色名 → LangChain 消息类映射
ROLE_TO_LC = {
    "system": SystemMessage,     # 系统提示
    "user": HumanMessage,        # 用户输入
    "assistant": AIMessage,      # AI 回复
    "tool": ToolMessage,         # 工具返回
}


def _openai_messages_to_langchain(messages: List) -> List[BaseMessage]:
    """
    将 OpenAI 格式的消息数组转换为 LangChain 消息列表。

    处理字段:
      - tool_calls（assistant 消息的工具调用）
      - tool_call_id（tool 消息的工具调用关联 ID）
      - name（消息发送者名称）
      - reasoning_content（DeepSeek-R1 思维链）

    Args:
        messages: 前端传来的 Message 对象列表（来自 schemas.py 的 Message 模型）

    Returns:
        List[BaseMessage]: LangChain 兼容的消息对象列表
    """
    lc_messages = []  # 结果列表
    for msg in messages:
        # 根据 role 找到对应的 LangChain 消息类
        msg_cls = ROLE_TO_LC.get(msg.role)
        if msg_cls is None:
            add_log("消息转换", f"未知角色 '{msg.role}'，跳过", "warning")
            continue

        # ── 构建消息构造参数 ──
        kwargs = {"content": msg.content}

        if msg.role == "tool":
            # ToolMessage 需要 tool_call_id 关联到 assistant 的 tool_calls
            kwargs["tool_call_id"] = msg.tool_call_id or ""
            if msg.name:
                kwargs["name"] = msg.name
        elif msg.role == "assistant" and msg.tool_calls:
            # AIMessage 有 tool_calls 时携带工具调用信息
            kwargs["tool_calls"] = msg.tool_calls
            if msg.reasoning_content:
                kwargs["reasoning_content"] = msg.reasoning_content
        elif msg.name:
            kwargs["name"] = msg.name

        # 传递 reasoning_content（DeepSeek-R1 思维链），避免多次设置
        if msg.reasoning_content and "reasoning_content" not in kwargs:
            kwargs["reasoning_content"] = msg.reasoning_content

        lc_messages.append(msg_cls(**kwargs))

    return lc_messages