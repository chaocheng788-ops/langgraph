"""
Official create_react_agent integration.
Uses LangGraph's built-in ReAct agent pattern instead of hand-written loops.
"""
from typing import Any, Dict, List, Optional, Sequence
import json

from langchain_core.messages import BaseMessage
from langchain_core.callbacks import BaseCallbackHandler
from langgraph.prebuilt import create_react_agent
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from typing_extensions import TypedDict
from typing import Annotated

# ── Checkpointer 单例 ──
_checkpointer: Optional[AsyncSqliteSaver] = None

async def get_checkpointer(db_path: str = "") -> AsyncSqliteSaver:
    """获取全局唯一的 AsyncSqliteSaver 实例。"""
    global _checkpointer
    if _checkpointer is None:
        import aiosqlite
        if not db_path:
            from pathlib import Path
            Path(Path(__file__).parent.parent / "data").mkdir(exist_ok=True)
            db_path = str(Path(__file__).parent.parent / "data" / "checkpoints.db")
        conn = await aiosqlite.connect(db_path)
        _checkpointer = AsyncSqliteSaver(conn)
        add_log("Checkpointer", f"AsyncSQLite 已连接: {db_path}")
    return _checkpointer


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
# LLM 请求/响应日志回调
# ============================================================

class LoggingCallbackHandler(BaseCallbackHandler):
    """记录每次调用 LLM 的原始入参和原始返回。"""

    def on_chat_model_start(
        self, serialized: dict, messages: list, **kwargs: Any
    ) -> None:
        # 提取 tools / tool_choice / temperature 等 API 级参数
        inv_params = kwargs.get("invocation_params", {})
        model = inv_params.get("model", inv_params.get("model_name", "?"))

        # messages 是 List[List[BaseMessage]]，每个内层列表是一个对话
        for pi, msg_list in enumerate(messages):
            msgs_json = []
            for msg in msg_list:
                entry = {}
                role = getattr(msg, "type", "?")
                entry["role"] = role
                entry["content"] = getattr(msg, "content", "")
                for attr in ("tool_calls", "tool_call_id", "name"):
                    val = getattr(msg, attr, None)
                    if val is not None:
                        entry[attr] = val
                add_kw = getattr(msg, "additional_kwargs", {})
                if add_kw:
                    entry["additional_kwargs"] = add_kw
                msgs_json.append(entry)

            # 构造完整 HTTP 请求体
            request_body = {
                "model": model,
                "temperature": inv_params.get("temperature", 0.7),
                "messages": msgs_json,
                "tools": inv_params.get("tools", None),
                "tool_choice": inv_params.get("tool_choice", None),
            }
            request_body = {k: v for k, v in request_body.items() if v is not None}

            add_log(f"🔵 模型请求 #{pi+1}",
                json.dumps(request_body, ensure_ascii=False, indent=2, default=str)[:5000])

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        for i, gen_list in enumerate(response.generations):
            for j, gen in enumerate(gen_list):
                msg = gen.message if hasattr(gen, "message") else str(gen)
                # 序列化 AIMessage 为可读格式
                raw = {
                    "content": getattr(msg, "content", ""),
                    "tool_calls": getattr(msg, "tool_calls", None),
                    "additional_kwargs": getattr(msg, "additional_kwargs", {}),
                }
                raw_str = json.dumps(raw, ensure_ascii=False, indent=2, default=str)
                add_log(f"🟢 模型响应 #{i+1}.{j+1}", f"原始返回:\n{raw_str[:3000]}")

                # ── 思考链展示 ──
                # 1. 如果有 reasoning_content（DeepSeek-R1），单独展示
                add_kw = raw.get("additional_kwargs", {})
                reasoning = add_kw.get("reasoning_content", "")
                if reasoning:
                    add_log("💭 思考链 (R1)", str(reasoning)[:2000])

                # 2. 如果有 tool_calls，展示模型决策
                tool_calls = raw.get("tool_calls")
                if tool_calls:
                    for tc in tool_calls:
                        tc_name = tc.get("name", "?")
                        tc_args = tc.get("args", {})
                        add_log("💭 模型决策", f"调用工具: {tc_name}\n参数: {json.dumps(tc_args, ensure_ascii=False)}")
                elif raw.get("content"):
                    # 有内容无工具调用 = 最终回答
                    add_log("💭 模型决策", "直接回答，不调用工具")

    def on_llm_error(self, error: Any, **kwargs: Any) -> None:
        add_log("🔴 模型错误", str(error)[:1000], "error")

    def on_tool_start(
        self, serialized: dict, input_str: str, **kwargs: Any
    ) -> None:
        """工具开始执行。"""
        tool_name = serialized.get("name", "?")
        add_log(f"🔧 工具调用", f"工具: {tool_name}\n入参: {input_str[:500]}")

    def on_tool_end(self, output: str, **kwargs: Any) -> None:
        """工具执行完毕。"""
        add_log(f"🔧 工具返回", str(output)[:2000])

    def on_tool_error(self, error: Any, **kwargs: Any) -> None:
        add_log("🔧 工具错误", str(error)[:1000], "error")


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

def get_weather(city: str) -> str:
    """传入城市名字可查天气，如北京，传入北京"""
    import random
    cities = {
        "北京": {"temp": 25, "humidity": 45, "wind": "东北风 3级", "desc": "晴"},
        "上海": {"temp": 28, "humidity": 70, "wind": "东南风 4级", "desc": "多云转小雨"},
        "广州": {"temp": 32, "humidity": 80, "wind": "南风 2级", "desc": "雷阵雨"},
        "深圳": {"temp": 30, "humidity": 75, "wind": "西南风 3级", "desc": "多云"},
        "杭州": {"temp": 26, "humidity": 60, "wind": "东风 2级", "desc": "阴"},
        "成都": {"temp": 24, "humidity": 55, "wind": "北风 1级", "desc": "小雨"},
        "武汉": {"temp": 29, "humidity": 65, "wind": "南风 3级", "desc": "晴转多云"},
        "西安": {"temp": 27, "humidity": 40, "wind": "西风 2级", "desc": "晴"},
    }
    city_key = city.strip()
    if city_key in cities:
        w = cities[city_key]
        return (
            f"[天气] {city_key} 当前天气:\n"
            f"- 温度: {w['temp']}°C\n"
            f"- 湿度: {w['humidity']}%\n"
            f"- 风力: {w['wind']}\n"
            f"- 天气: {w['desc']}\n"
            f"- 建议: {'带伞' if '雨' in w['desc'] else '适宜出行'}"
        )
    else:
        temp = random.randint(15, 35)
        humidity = random.randint(30, 90)
        descs = ["晴", "多云", "阴", "小雨", "阵雨"]
        return (
            f"[天气] {city_key} 当前天气:\n"
            f"- 温度: {temp}°C\n"
            f"- 湿度: {humidity}%\n"
            f"- 风力: 微风 2级\n"
            f"- 天气: {random.choice(descs)}\n"
            f"- 提示: 该城市为模拟数据"
        )


# Registry of built-in tools
BUILTIN_TOOLS = {
    "search": search_web,
    "calculator": calculator,
    "summarize": summarize,
    "translate": translate,
    "sentiment": analyze_sentiment,
    "weather": get_weather,
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


async def create_agent_graph(
    system_prompt: str = "你是一个有用的AI助手。",
    tools_config: Optional[List[Dict[str, str]]] = None,
    max_iterations: int = 10,
    api_key: Optional[str] = None,
    model_name: str = "deepseek-chat",
    base_url: str = "https://api.deepseek.com/v1",
) -> CompiledStateGraph:
    """
    Create a ReAct agent graph using a remote LLM (DeepSeek / OpenAI-compatible).

    Args:
        system_prompt: The system prompt for the LLM.
        tools_config: List of tool configs from the frontend.
        max_iterations: Maximum number of LLM-tool rounds.
        api_key: API key for the remote model (required).
        model_name: Model name, e.g. "deepseek-chat", "deepseek-reasoner".
        base_url: API base URL for OpenAI-compatible endpoints.

    Returns:
        A compiled LangGraph StateGraph.

    Raises:
        ValueError: If no api_key is provided.
        ImportError: If langchain-openai is not installed.
    """
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
