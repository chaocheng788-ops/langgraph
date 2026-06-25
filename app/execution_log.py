"""
全局执行日志系统 + LoggingCallbackHandler。
职责:
  1. 全局日志累积器（_execution_logs），供前端通过 /logs API 实时查看
  2. LoggingCallbackHandler（监听 LLM/工具调用的完整链路）
"""
# ── 类型导入 ──
from typing import Any, Dict, List
import json  # JSON 序列化（工具参数、日志详情）

# ── LangChain 核心依赖 ──
from langchain_core.callbacks import BaseCallbackHandler  # 回调处理器基类


# ═══════════════════════════════════════════════════════════════
# 全局执行日志系统 — 每次 Agent 调用前清空，前端通过 /logs API 获取
# ═══════════════════════════════════════════════════════════════

_execution_logs: List[dict] = []  # 日志列表，每个元素为 {step, detail, level, timestamp}


def get_logs() -> List[dict]:
    """返回当前累积的日志副本（避免外部修改内部列表）。"""
    return list(_execution_logs)


def clear_logs():
    """清空日志列表（每次新执行前调用）。"""
    _execution_logs.clear()


def add_log(step: str, detail: str, level: str = "info"):
    """
    添加一条执行日志。

    Args:
        step: 步骤名称（如 "🔵 模型请求 #1"）
        detail: 详细内容（JSON 字符串或纯文本）
        level: 日志级别（info / warning / error）
    """
    _execution_logs.append({
        "step": step,
        "detail": detail,
        "level": level,
        # 毫秒精度的时间戳，如 "14:32:05.123"
        "timestamp": __import__("datetime").datetime.now().strftime("%H:%M:%S.%f")[:-3],
    })


# ═══════════════════════════════════════════════════════════════
# LoggingCallbackHandler — 监听 LLM 和工具调用的完整生命周期
# ═══════════════════════════════════════════════════════════════

class LoggingCallbackHandler(BaseCallbackHandler):
    """
    LangChain 回调处理器，在 Agent 执行过程中记录:
      - LLM 请求入参（模型名、温度、消息、工具列表）
      - LLM 响应输出（content + tool_calls + reasoning_content）
      - 工具调用开始 / 完成 / 错误
    """

    def on_chat_model_start(
        self, serialized: dict, messages: list, **kwargs: Any
    ) -> None:
        """
        LLM 调用开始时触发。记录完整的 API 请求参数。

        Args:
            serialized: 序列化的模型配置
            messages: 待发送的消息列表 List[List[BaseMessage]]
            kwargs: 包含 invocation_params（含有 model/temperature/tools 等）
        """
        # 提取 API 级别的调用参数
        inv_params = kwargs.get("invocation_params", {})
        model = inv_params.get("model", inv_params.get("model_name", "?"))  # 优先取 model，回退取 model_name

        # messages 是 List[List[BaseMessage]]，每个内层列表是一个对话提示
        for pi, msg_list in enumerate(messages):
            # ── 把 LangChain 消息对象转成 JSON 可序列化的字典 ──
            msgs_json = []
            for msg in msg_list:
                entry = {}  # 每条消息的结构
                role = getattr(msg, "type", "?")  # human / ai / system / tool
                entry["role"] = role
                entry["content"] = getattr(msg, "content", "")
                # 保留工具调用相关字段
                for attr in ("tool_calls", "tool_call_id", "name"):
                    val = getattr(msg, attr, None)
                    if val is not None:
                        entry[attr] = val
                # 保留 additional_kwargs（如 reasoning_content）
                add_kw = getattr(msg, "additional_kwargs", {})
                if add_kw:
                    entry["additional_kwargs"] = add_kw
                msgs_json.append(entry)

            # ── 构造完整的 HTTP 请求体（模拟 OpenAI API 格式） ──
            request_body = {
                "model": model,
                "temperature": inv_params.get("temperature", 0.7),
                "messages": msgs_json,
                "tools": inv_params.get("tools", None),
                "tool_choice": inv_params.get("tool_choice", None),
            }
            # 移除值为 None 的键，保持输出整洁
            request_body = {k: v for k, v in request_body.items() if v is not None}

            # 记录到全局日志
            add_log(f"🔵 模型请求 #{pi+1}",
                json.dumps(request_body, ensure_ascii=False, indent=2, default=str))

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        """
        LLM 调用完成时触发。记录模型原始返回。

        Args:
            response: LLMResult 对象，包含 generations 列表
        """
        for i, gen_list in enumerate(response.generations):
            for j, gen in enumerate(gen_list):
                msg = gen.message if hasattr(gen, "message") else str(gen)  # 取 AIMessage
                # 序列化 AIMessage 为可读字典
                raw = {
                    "content": getattr(msg, "content", ""),
                    "tool_calls": getattr(msg, "tool_calls", None),
                    "additional_kwargs": getattr(msg, "additional_kwargs", {}),
                }
                raw_str = json.dumps(raw, ensure_ascii=False, indent=2, default=str)
                add_log(f"🟢 模型响应 #{i+1}.{j+1}", f"原始返回:\n{raw_str}")

                # ── 思考链展示（DeepSeek-R1 / 深度推理模型） ──
                add_kw = raw.get("additional_kwargs", {})
                reasoning = add_kw.get("reasoning_content", "")
                if reasoning:  # 如果有思维链内容，单独展示
                    add_log("💭 思考链 (R1)", str(reasoning))

                # ── 模型决策分析 ──
                tool_calls = raw.get("tool_calls")
                if tool_calls:  # 模型决定调用工具
                    for tc in tool_calls:
                        tc_name = tc.get("name", "?")
                        tc_args = tc.get("args", {})
                        add_log("💭 模型决策", f"调用工具: {tc_name}\n参数: {json.dumps(tc_args, ensure_ascii=False)}")
                elif raw.get("content"):  # 模型直接给出文本回答
                    add_log("💭 模型决策", "直接回答，不调用工具")

    def on_llm_error(self, error: Any, **kwargs: Any) -> None:
        """LLM 调用出错时触发。"""
        add_log("🔴 模型错误", str(error)[:1000], "error")

    def on_tool_start(
        self, serialized: dict, input_str: str, **kwargs: Any
    ) -> None:
        """工具开始执行时触发。"""
        tool_name = serialized.get("name", "?")
        add_log(f"🔧 工具调用", f"工具: {tool_name}\n入参: {input_str}")

    def on_tool_end(self, output: str, **kwargs: Any) -> None:
        """工具执行完毕时触发。"""
        add_log(f"🔧 工具返回", str(output))

    def on_tool_error(self, error: Any, **kwargs: Any) -> None:
        """工具执行出错时触发。"""
        add_log("🔧 工具错误", str(error)[:1000], "error")