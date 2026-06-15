"""
LangGraph Agent 构建与工具管理核心模块。
职责:
  1. Checkpointer 单例管理（AsyncSqliteSaver 持久化会话）
  2. 执行日志系统（全局日志累积器，供前端实时查看）
  3. LoggingCallbackHandler（监听 LLM/工具调用的完整链路）
  4. 内置工具定义（weather/search/calculator 等模拟工具）
  5. 动态工具工厂（HTTP 工具 / Echo 回退工具）
  6. create_agent_graph（组装 ReAct Agent 并返回 CompiledStateGraph）
"""
# ── 类型导入 ──
from typing import Any, Dict, List, Optional, Sequence
import json  # JSON 序列化（工具参数、日志详情）

# ── LangChain / LangGraph 核心依赖 ──
from langchain_core.messages import BaseMessage  # 消息基类
from langchain_core.callbacks import BaseCallbackHandler  # 回调处理器基类
from langgraph.prebuilt import create_react_agent  # 官方 ReAct Agent 工厂函数
from langgraph.graph.message import add_messages  # 消息累积 Reducer（追加而非覆盖）
from langgraph.graph.state import CompiledStateGraph  # 编译后的图类型
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver  # 异步 SQLite 持久化
from typing_extensions import TypedDict  # TypedDict 定义 AgentState 类型
from typing import Annotated  # Annotated 配合 add_messages 定义 Reducer

# ═══════════════════════════════════════════════════════════════
# Checkpointer 单例 — 全局唯一，避免重复创建数据库连接
# ═══════════════════════════════════════════════════════════════

_checkpointer: Optional[AsyncSqliteSaver] = None  # 模块级全局变量，缓存单例


async def get_checkpointer(db_path: str = "") -> AsyncSqliteSaver:
    """
    获取全局唯一的 AsyncSqliteSaver 实例（线程安全惰性初始化）。

    Args:
        db_path: SQLite 数据库路径，为空时默认使用 data/checkpoints.db

    Returns:
        AsyncSqliteSaver: 异步 SQLite Checkpointer，用于持久化 Agent 状态
    """
    global _checkpointer  # 声明修改模块级变量
    if _checkpointer is None:  # 只有首次调用时初始化
        import aiosqlite  # 延迟导入，减少启动开销
        if not db_path:  # 未指定路径时使用默认路径
            from pathlib import Path
            Path(Path(__file__).parent.parent / "data").mkdir(exist_ok=True)  # 确保 data 目录存在
            db_path = str(Path(__file__).parent.parent / "data" / "checkpoints.db")
        conn = await aiosqlite.connect(db_path)  # 创建异步 SQLite 连接
        _checkpointer = AsyncSqliteSaver(conn)  # 用连接初始化 Saver
        add_log("Checkpointer", f"AsyncSQLite 已连接: {db_path}")
    return _checkpointer


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

            # 记录到全局日志（截断到 5000 字符避免日志膨胀）
            add_log(f"🔵 模型请求 #{pi+1}",
                json.dumps(request_body, ensure_ascii=False, indent=2, default=str)[:5000])

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
                add_log(f"🟢 模型响应 #{i+1}.{j+1}", f"原始返回:\n{raw_str[:3000]}")

                # ── 思考链展示（DeepSeek-R1 / 深度推理模型） ──
                add_kw = raw.get("additional_kwargs", {})
                reasoning = add_kw.get("reasoning_content", "")
                if reasoning:  # 如果有思维链内容，单独展示
                    add_log("💭 思考链 (R1)", str(reasoning)[:2000])

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
        add_log(f"🔧 工具调用", f"工具: {tool_name}\n入参: {input_str[:500]}")

    def on_tool_end(self, output: str, **kwargs: Any) -> None:
        """工具执行完毕时触发。"""
        add_log(f"🔧 工具返回", str(output)[:2000])

    def on_tool_error(self, error: Any, **kwargs: Any) -> None:
        """工具执行出错时触发。"""
        add_log("🔧 工具错误", str(error)[:1000], "error")


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
# 内置工具定义 — 模拟工具，不依赖外部 API
# ═══════════════════════════════════════════════════════════════

def search_web(query: str) -> str:
    """模拟网页搜索工具。LangChain 根据 docstring 生成工具 Schema。"""
    return f"[搜索] 关于「{query}」的查询结果:\n- 找到了 3 条相关结果\n- 主要信息: {query} 是一个重要的话题，涉及到多个领域。\n- 更多详情请参考相关文档。"


def calculator(expr: str) -> str:
    """安全地计算数学表达式。仅允许数字和基本运算符。"""
    try:
        # ── 安全校验：只允许数字、运算符、括号、空格和小数点 ──
        allowed = set("0123456789+-*/.() ")
        if not all(c in allowed for c in expr):
            return f"[计算] 表达式包含不支持的字符: {expr}"
        # 在受限命名空间中执行 eval，屏蔽危险函数
        result = eval(expr, {"__builtins__": {}}, {})
        return f"[计算] {expr} = {result}"
    except Exception as e:
        return f"[计算] 表达式错误: {e}"


def summarize(text: str) -> str:
    """模拟文本摘要工具。"""
    max_len = min(len(text), 200)  # 最多展示 200 个字符
    return f"[总结] 原文({len(text)}字)核心要点:\n- {text[:max_len]}...\n- (模拟摘要输出)"


def translate(text: str, target_lang: str = "中文") -> str:
    """
    模拟翻译工具。

    Args:
        text: 待翻译文本
        target_lang: 目标语言，默认为中文
    """
    return f"[翻译] 已将「{text[:30]}...」翻译为{target_lang}: (模拟翻译结果)"


def analyze_sentiment(text: str) -> str:
    """模拟情感分析工具。"""
    return f"[情感分析] 文本: {text[:40]}...\n情感倾向: 积极 (模拟分析)"


def get_weather(city: str) -> str:
    """
    天气查询工具。支持主流城市真实数据 + 随机模拟数据。

    内置城市: 北京、上海、广州、深圳、杭州、成都、武汉、西安
    其他城市返回随机模拟数据。
    """
    import random  # 用于非内置城市的随机模拟
    # ── 内置城市真实数据 ──
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
    city_key = city.strip()  # 去除首尾空格
    if city_key in cities:
        w = cities[city_key]
        return (
            f"[天气] {city_key} 当前天气:\n"
            f"- 温度: {w['temp']}°C\n"
            f"- 湿度: {w['humidity']}%\n"
            f"- 风力: {w['wind']}\n"
            f"- 天气: {w['desc']}\n"
            f"- 建议: {'带伞' if '雨' in w['desc'] else '适宜出行'}"  # 根据天气给建议
        )
    else:
        # ── 非内置城市：随机生成模拟数据 ──
        temp = random.randint(15, 35)  # 温度 15-35°C
        humidity = random.randint(30, 90)  # 湿度 30-90%
        descs = ["晴", "多云", "阴", "小雨", "阵雨"]  # 天气池
        return (
            f"[天气] {city_key} 当前天气:\n"
            f"- 温度: {temp}°C\n"
            f"- 湿度: {humidity}%\n"
            f"- 风力: 微风 2级\n"
            f"- 天气: {random.choice(descs)}\n"
            f"- 提示: 该城市为模拟数据"
        )


# ═══════════════════════════════════════════════════════════════
# 内置工具注册表 — 名称 → 函数映射
# ═══════════════════════════════════════════════════════════════

BUILTIN_TOOLS = {
    "search": search_web,       # 网页搜索
    "calculator": calculator,   # 数学计算
    "summarize": summarize,     # 文本摘要
    "translate": translate,     # 翻译
    "sentiment": analyze_sentiment,  # 情感分析
    "weather": get_weather,     # 天气查询
}


# ═══════════════════════════════════════════════════════════════
# 工具工厂函数 — 将前端配置转为可调用的工具对象
# ═══════════════════════════════════════════════════════════════

def get_tools_from_config(tools_config: List[Dict[str, Any]]) -> list:
    """
    将前端传来的工具配置列表转为 LangChain 可调用的工具函数列表。

    支持三类工具:
      1. 内置工具（名称在 BUILTIN_TOOLS 中）→ 直接返回模块级函数
      2. HTTP 工具（有 url 字段）→ 创建闭包，通过 urllib 调用外部 API
      3. Echo 回退工具（其他情况）→ 创建闭包，原样返回参数

    Args:
        tools_config: 工具配置列表，每项含 name/description/url/method/parameters 等

    Returns:
        list[Callable]: 可调用工具函数列表
    """
    tools = []  # 结果列表
    for tc in tools_config:
        # ── 解析配置字段 ──
        name = tc.get("name", "")
        url = tc.get("url", "")
        method = tc.get("method", "GET")
        headers = tc.get("headers", {})

        if name in BUILTIN_TOOLS and not url:
            # 情况 1: 内置工具 — 直接取模块级函数
            tools.append(BUILTIN_TOOLS[name])
            add_log("工具注册", f"内置工具: {name}")

        elif url:
            # 情况 2: HTTP 工具 — 创建闭包调用外部 API
            desc = tc.get("description", "")
            params = tc.get("parameters", {})
            add_log("工具注册", f"HTTP工具: {name} → {method} {url}")
            headers_config = headers  # 闭包捕获变量

            def make_http_tool(
                _name=name,       # 使用默认参数冻结当前值，避免闭包延迟绑定问题
                _url=url,
                _method=method,
                _headers=headers_config,
                _desc=desc,
                _params=params,
            ):
                def http_tool(**kwargs) -> str:
                    """实际的 HTTP 工具调用函数。LangChain 传入参数名=参数值。"""
                    import urllib.request, urllib.parse, json

                    add_log(f"工具调用 [{_name}]", f"请求: {_method} {_url}\n参数: {json.dumps(kwargs, ensure_ascii=False)}")

                    try:
                        if _method.upper() == "GET":
                            # GET 请求：参数拼接到 URL 查询字符串
                            query_string = urllib.parse.urlencode(kwargs)
                            full_url = f"{_url}?{query_string}" if query_string else _url
                            req = urllib.request.Request(full_url, headers=_headers)
                        else:
                            # POST/PUT/DELETE 请求：参数编码为 JSON 请求体
                            data = json.dumps(kwargs).encode("utf-8")
                            req = urllib.request.Request(_url, data=data, headers=_headers)
                            req.method = _method.upper()

                        # 发送请求，30 秒超时
                        with urllib.request.urlopen(req, timeout=30) as resp:
                            body = resp.read().decode("utf-8")

                        add_log(f"工具响应 [{_name}]", f"状态码: {resp.status}\n返回: {body[:300]}")
                        return f"[{_name}] 响应 ({resp.status}): {body[:500]}"
                    except Exception as e:
                        err_msg = f"[{_name}] 请求失败: {e}"
                        add_log(f"工具错误 [{_name}]", str(e), "error")
                        return err_msg

                # 设置函数元数据，LangChain 据此生成工具 Schema
                http_tool.__name__ = _name
                http_tool.__doc__ = _desc or f"HTTP tool: {_method} {_url}"
                return http_tool

            tools.append(make_http_tool())

        else:
            # 情况 3: Echo 回退工具 — 原样返回参数
            desc = tc.get("description", "")
            def make_dynamic(name=name, desc=desc):
                def dynamic_tool(**kwargs) -> str:
                    """回退工具：接收任意参数，原样返回。"""
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