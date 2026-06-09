"""
Official create_react_agent integration.
Uses LangGraph's built-in ReAct agent pattern instead of hand-written loops.
"""
from typing import Any, Dict, List, Optional, Sequence
import json

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.callbacks import CallbackManagerForLLMRun
from langgraph.prebuilt import create_react_agent
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from typing_extensions import TypedDict
from typing import Annotated


# Global execution log accumulator
_execution_logs: List[dict] = []

def get_logs() -> List[dict]:
    return list(_execution_logs)

def clear_logs():
    _execution_logs.clear()

def add_log(step: str, detail: str, level: str = "info"):
    _execution_logs.append({
        "step": step,
        "detail": detail,
        "level": level,
        "timestamp": __import__("datetime").datetime.now().strftime("%H:%M:%S.%f")[:-3],
    })


# ============================================================
# Agent State (compatible with create_react_agent)
# ============================================================

class AgentState(TypedDict):
    """State for the ReAct agent. Compatible with create_react_agent."""
    messages: Annotated[Sequence[BaseMessage], add_messages]
    remaining_steps: int


# ============================================================
# Tool definitions — real Python functions users can configure
# ============================================================

def search_web(query: str) -> str:
    """Search the web for information about a given query."""
    return f"[搜索] 关于「{query}」的查询结果:\n- 找到了 3 条相关结果\n- 主要信息: {query} 是一个重要的话题，涉及到多个领域。\n- 更多详情请参考相关文档。"

def calculator(expr: str) -> str:
    """Evaluate a mathematical expression."""
    try:
        # Safe eval — only allow basic math
        allowed = set("0123456789+-*/.() ")
        if not all(c in allowed for c in expr):
            return f"[计算] 表达式包含不支持的字符: {expr}"
        result = eval(expr, {"__builtins__": {}}, {})
        return f"[计算] {expr} = {result}"
    except Exception as e:
        return f"[计算] 表达式错误: {e}"

def summarize(text: str) -> str:
    """Summarize a piece of text into key points."""
    max_len = min(len(text), 200)
    return f"[总结] 原文({len(text)}字)核心要点:\n- {text[:max_len]}...\n- (模拟摘要输出)"

def translate(text: str, target_lang: str = "中文") -> str:
    """Translate text to the target language."""
    return f"[翻译] 已将「{text[:30]}...」翻译为{target_lang}: (模拟翻译结果)"

def analyze_sentiment(text: str) -> str:
    """Analyze the sentiment of a piece of text."""
    return f"[情感分析] 文本: {text[:40]}...\n情感倾向: 积极 (模拟分析)"


# Registry of built-in tools
BUILTIN_TOOLS = {
    "search": search_web,
    "calculator": calculator,
    "summarize": summarize,
    "translate": translate,
    "sentiment": analyze_sentiment,
}


def get_tools_from_config(tools_config: List[Dict[str, Any]]) -> list:
    """Convert tool config from the frontend into callable tool functions.
    Supports:
      - Built-in tools (name matches BUILTIN_TOOLS)
      - HTTP tools (has 'url' field) that call external APIs
      - Echo tools (fallback, just return the input)
    """
    tools = []
    for tc in tools_config:
        name = tc.get("name", "")
        url = tc.get("url", "")
        method = tc.get("method", "GET")
        headers = tc.get("headers", {})

        if name in BUILTIN_TOOLS and not url:
            # Built-in tool
            tools.append(BUILTIN_TOOLS[name])
            add_log("工具注册", f"内置工具: {name}")
        elif url:
            # HTTP tool — calls external API
            desc = tc.get("description", "")
            params = tc.get("parameters", {})
            add_log("工具注册", f"HTTP工具: {name} → {method} {url}")
            headers_config = headers

            def make_http_tool(
                _name=name,
                _url=url,
                _method=method,
                _headers=headers_config,
                _desc=desc,
                _params=params,
            ):
                def http_tool(**kwargs) -> str:
                    import urllib.request, urllib.parse, json

                    add_log(f"工具调用 [{_name}]", f"请求: {_method} {_url}\n参数: {json.dumps(kwargs, ensure_ascii=False)}")

                    try:
                        if _method.upper() == "GET":
                            query_string = urllib.parse.urlencode(kwargs)
                            full_url = f"{_url}?{query_string}" if query_string else _url
                            req = urllib.request.Request(full_url, headers=_headers)
                        else:
                            # POST / PUT / DELETE with JSON body
                            data = json.dumps(kwargs).encode("utf-8")
                            req = urllib.request.Request(_url, data=data, headers=_headers)
                            req.method = _method.upper()

                        with urllib.request.urlopen(req, timeout=30) as resp:
                            body = resp.read().decode("utf-8")
                        
                        add_log(f"工具响应 [{_name}]", f"状态码: {resp.status}\n返回: {body[:300]}")
                        return f"[{_name}] 响应 ({resp.status}): {body[:500]}"
                    except Exception as e:
                        err_msg = f"[{_name}] 请求失败: {e}"
                        add_log(f"工具错误 [{_name}]", str(e), "error")
                        return err_msg
                http_tool.__name__ = _name
                http_tool.__doc__ = _desc or f"HTTP tool: {_method} {_url}"
                return http_tool
            tools.append(make_http_tool())
        else:
            # Dynamic echo tool
            desc = tc.get("description", "")
            def make_dynamic(name=name, desc=desc):
                def dynamic_tool(**kwargs) -> str:
                    params_str = json.dumps(kwargs, ensure_ascii=False)
                    add_log(f"工具调用 [{name}]", f"参数: {params_str}")
                    result = f"[{name}] 执行结果: {desc}\n参数: {params_str}"
                    add_log(f"工具响应 [{name}]", result[:200])
                    return result
                dynamic_tool.__name__ = name
                dynamic_tool.__doc__ = desc or f"A tool named {name}"
                return dynamic_tool
            tools.append(make_dynamic())
    return tools


# ============================================================
# FakeChatModel — simulates LLM without needing API keys
# ============================================================

class FakeChatModel(BaseChatModel):
    """A simulated ChatModel that works with create_react_agent.
    No API key required. Simulates tool-calling behavior."""
    
    model_name: str = "fake-model"
    system_prompt: str = "你是一个有用的AI助手。"
    tool_names: List[str] = []
    max_rounds: int = 3

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        # Count tool results so far
        tool_result_count = sum(1 for m in messages if isinstance(m, ToolMessage))
        total_tools = len(self.tool_names)
        last_content = messages[-1].content if messages else ""

        # Decide: should we call a tool or give the final answer?
        if tool_result_count < total_tools and tool_result_count < self.max_rounds:
            # Call the next tool in sequence
            tool_idx = tool_result_count
            tool_name = self.tool_names[tool_idx]

            # Determine appropriate argument name based on tool
            tool_args = {"query": last_content[:60]}
            if tool_name in ("summarize", "translate", "sentiment"):
                tool_args = {"text": last_content[:60]}
            elif tool_name == "calculator":
                tool_args = {"expr": "2+2"}

            response = AIMessage(
                content=f"我需要使用{tool_name}工具进行第{tool_idx + 1}/{total_tools}步分析。",
                tool_calls=[{
                    "name": tool_name,
                    "args": tool_args,
                    "id": f"call_{tool_idx + 1}",
                    "type": "tool_call",
                }],
            )
        else:
            # All tools executed or max rounds reached — give final answer
            tool_summary = f"已调用{total_tools}个工具" if total_tools > 0 else "未使用工具"
            response = AIMessage(
                content=(
                    f"[最终回答] ({tool_summary})\n\n"
                    f"用户问题: {messages[0].content[:50] if messages else ''}...\n\n"
                    f"分析结论: 经过{tool_result_count}轮工具调用和综合分析，已完成处理。\n"
                    f"{self.system_prompt}"
                )
            )

        return ChatResult(generations=[ChatGeneration(message=response)])

    @property
    def _llm_type(self) -> str:
        return "fake-chat-model"

    def bind_tools(self, tools: list, **kwargs):
        """Override bind_tools to capture tool names."""
        self.tool_names = [t.name if hasattr(t, '__name__') else str(t) for t in tools]
        # Also try getting name from __name__ attribute
        self.tool_names = []
        for t in tools:
            if hasattr(t, 'name'):
                self.tool_names.append(t.name)
            elif hasattr(t, '__name__'):
                self.tool_names.append(t.__name__)
            else:
                self.tool_names.append(str(t))
        return self


def create_agent_graph(
    system_prompt: str = "你是一个有用的AI助手。",
    tools_config: Optional[List[Dict[str, str]]] = None,
    max_iterations: int = 10,
    api_key: Optional[str] = None,
    model_name: str = "fake",
) -> CompiledStateGraph:
    """
    Create a ReAct agent graph using the official create_react_agent.

    Args:
        system_prompt: The system prompt for the LLM.
        tools_config: List of tool configs from the frontend.
        max_iterations: Maximum number of LLM-tool rounds.
        api_key: API key for remote model (DeepSeek / OpenAI-compatible).
        model_name: "fake" for local simulation, or model name like
                    "deepseek-chat", "deepseek-reasoner" for real API.

    Returns:
        A compiled LangGraph StateGraph.
    """
    tools = get_tools_from_config(tools_config or [])

    if api_key and model_name != "fake":
        # ============================================================
        # REAL REMOTE MODEL (DeepSeek / OpenAI-compatible)
        # ============================================================
        add_log("模型选择", f"使用远程模型: {model_name}, API Key: {api_key[:8]}...")
        try:
            from langchain_openai import ChatOpenAI
            model = ChatOpenAI(
                model=model_name,
                api_key=api_key,
                base_url="https://api.deepseek.com/v1",
                temperature=0.7,
            )
            # Bind tools so the model knows what it can call
            if tools:
                tool_names = [t.__name__ for t in tools]
                add_log("工具绑定", f"绑定 {len(tools)} 个工具: {tool_names}")
                model = model.bind_tools(tools)
            add_log("准备就绪", "远程模型初始化完成, 等待用户输入")
        except ImportError:
            add_log("依赖错误", "缺少 langchain-openai 包", "error")
            raise ImportError("请先安装 langchain-openai: pip install langchain-openai")
    else:
        # ============================================================
        # LOCAL SIMULATED MODEL (no API key needed)
        # ============================================================
        tool_names = [t.__name__ for t in tools]
        add_log("模型选择", f"使用本地模拟模型, 工具: {tool_names}")
        model = FakeChatModel(
            model_name="fake-gpt",
            system_prompt=system_prompt,
            tool_names=tool_names,
            max_rounds=min(max_iterations, 5),
        )

    graph = create_react_agent(
        model,
        tools=tools,
        prompt=system_prompt,
        state_schema=AgentState,
        version="v2",
    )
    return graph
