"""
LangGraph Platform — API 服务器（FastAPI 子应用）。
挂载到 main.py 的 /api 路径下，提供完整的 REST API。

API 模块:
  1. /health                          — 健康检查
  2. /models    GET/POST/DELETE       — 模型配置 CRUD
  3. /tools     GET/POST/DELETE       — 工具配置 CRUD
  4. /prompt    GET/POST              — 系统提示词管理
  5. /run       POST                  — 同步执行 Agent（返回完整结果）
  6. /run-stream POST                 — 流式执行 Agent（SSE 实时推送日志和消息）
  7. /logs      GET                   — 获取最近一次执行的日志
  8. /conversations GET/DELETE/{tid}  — 历史对话管理
"""
# ── 标准库导入 ──
import json  # JSON 序列化/反序列化
import uuid  # 生成唯一会话 ID
from typing import Any, Dict, List, Optional  # 类型注解
from pathlib import Path  # 跨平台路径处理
from contextlib import asynccontextmanager  # FastAPI lifespan 上下文

# ── FastAPI 核心 ──
from fastapi import FastAPI, HTTPException  # Web 框架 + HTTP 异常
from fastapi.middleware.cors import CORSMiddleware  # 跨域中间件
from fastapi.responses import StreamingResponse  # SSE 流式响应
from pydantic import BaseModel  # 请求/响应数据模型

# ── 内部模块 ──
from app.graph import build_workflow  # Agent 图构建入口
from app.agent_setup import get_logs, clear_logs, add_log, LoggingCallbackHandler  # 日志 + 回调

# ── LangChain 消息类型 ──
from langchain_core.messages import (
    AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage,
)


# ═══════════════════════════════════════════════════════════════
# Pydantic 数据模型 — 定义请求/响应的结构和默认值
# ═══════════════════════════════════════════════════════════════

class ModelConfig(BaseModel):
    """模型配置数据模型。"""
    name: str                                                  # 用户自定义名称，如 "deepseek-1"
    model_name: str = "deepseek-v4-pro"                        # API 模型名
    api_key: str = ""                                          # API 密钥
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"  # API 端点
    temperature: float = 0.7                                   # 生成随机性 (0-2)
    max_tokens: int = 4096                                     # 最大输出 token 数


class ToolParameter(BaseModel):
    """工具参数定义。"""
    name: str                                                  # 参数名
    type: str = "string"                                       # 参数类型 (string/number/boolean/array)
    description: str = ""                                      # 参数说明
    required: bool = False                                     # 是否必填


class ToolConfig(BaseModel):
    """工具配置数据模型。"""
    name: str                                                  # 工具名称
    description: str = ""                                      # 工具功能描述
    parameters: List[ToolParameter] = []                       # 参数列表
    url: str = ""                                              # HTTP 工具 API 地址（为空则为内置工具）
    method: str = "GET"                                        # HTTP 请求方法
    headers: Dict[str, str] = {}                               # HTTP 自定义请求头


class PromptConfig(BaseModel):
    """提示词配置。"""
    content: str = "你是一个有用的AI助手。"                    # 系统提示词文本


class Message(BaseModel):
    """OpenAI 兼容的消息格式，用于多轮对话的消息数组。"""
    role: str                                                  # 角色: system/user/assistant/tool
    content: str = ""                                          # 消息内容
    name: Optional[str] = None                                 # 工具名称（tool 消息）或用户名称
    tool_call_id: Optional[str] = None                         # 工具调用 ID（tool 消息）
    tool_calls: Optional[List[Dict[str, Any]]] = None          # 工具调用列表（assistant 消息）
    reasoning_content: Optional[str] = None                    # DeepSeek-R1 思维链


class AgentRun(BaseModel):
    """Agent 执行请求体。"""
    model_name: str = "deepseek-chat"                          # 模型名
    api_key: str = ""                                          # API 密钥
    base_url: str = "https://api.deepseek.com/v1"              # API 端点
    system_prompt: str = "你是一个有用的AI助手。"              # 系统提示词
    tools: List[Dict[str, Any]] = []                           # 工具列表
    max_iterations: int = 10                                   # 最大推理轮数
    input: str = ""                                            # 用户输入（传统格式）
    messages: Optional[List[Message]] = None                   # OpenAI 格式消息数组（优先于 input）
    thread_id: str = ""                                        # 会话 ID，用于 Checkpointer 持久化


# ═══════════════════════════════════════════════════════════════
# 持久化存储 — JSON 文件读写
# ═══════════════════════════════════════════════════════════════

DATA_DIR = Path(__file__).parent.parent / "data"  # 数据目录: langgraph/data/
DATA_DIR.mkdir(exist_ok=True)                     # 确保目录存在
MODELS_FILE = DATA_DIR / "models.json"            # 模型配置文件
TOOLS_FILE = DATA_DIR / "tools.json"              # 工具配置文件
PROMPT_FILE = DATA_DIR / "prompt.json"            # 提示词配置文件


def _read_json(filepath: Path) -> Any:
    """
    安全读取 JSON 文件，文件不存在或解析失败时返回空字典。

    Args:
        filepath: JSON 文件路径

    Returns:
        dict | list: 解析后的 JSON 数据，失败时返回 {}
    """
    if filepath.exists():
        try:
            return json.loads(filepath.read_text(encoding="utf-8"))
        except Exception:
            pass  # 文件损坏时静默返回 {}
    return {}


def _write_json(filepath: Path, data: Any) -> None:
    """
    将数据写入 JSON 文件，ensure_ascii=False 保留中文。

    Args:
        filepath: 目标文件路径
        data: 待写入的数据
    """
    filepath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ═══════════════════════════════════════════════════════════════
# OpenAI ↔ LangChain 消息格式转换
# ═══════════════════════════════════════════════════════════════

# 角色名 → LangChain 消息类映射
ROLE_TO_LC = {
    "system": SystemMessage,     # 系统提示
    "user": HumanMessage,        # 用户输入
    "assistant": AIMessage,      # AI 回复
    "tool": ToolMessage,         # 工具返回
}


def _openai_messages_to_langchain(messages: List[Message]) -> List[BaseMessage]:
    """
    将 OpenAI 格式的消息数组转换为 LangChain 消息列表。

    处理字段:
      - tool_calls（assistant 消息的工具调用）
      - tool_call_id（tool 消息的工具调用关联 ID）
      - name（消息发送者名称）
      - reasoning_content（DeepSeek-R1 思维链）

    Args:
        messages: 前端传来的 Message 对象列表

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


# ═══════════════════════════════════════════════════════════════
# FastAPI 应用初始化
# ═══════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理：启动时确保数据目录存在。"""
    DATA_DIR.mkdir(exist_ok=True)
    yield  # 应用运行期间在此暂停，关闭时继续执行


# 创建 FastAPI 子应用实例（由 main.py 挂载到 /api）
app = FastAPI(
    title="LangGraph Agent Platform",
    description="基于 LangGraph 的 Agent 配置与执行平台",
    version="2.0.0",
    lifespan=lifespan,
)

# 添加 CORS 中间件 — 允许前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # 允许所有来源（开发环境）
    allow_credentials=True,       # 允许携带 Cookie
    allow_methods=["*"],          # 允许所有 HTTP 方法
    allow_headers=["*"],          # 允许所有请求头
)


# ═══════════════════════════════════════════════════════════════
# GET /health — 健康检查端点
# ═══════════════════════════════════════════════════════════════

@app.get("/health")
async def health_check():
    """返回服务健康状态，用于监控和负载均衡探测。"""
    return {"status": "ok", "service": "langgraph-agent-platform"}


# ═══════════════════════════════════════════════════════════════
# 模型配置 CRUD — /models
# ═══════════════════════════════════════════════════════════════

@app.get("/models")
async def list_models():
    """列出所有模型配置。返回 {模型名: 配置字典} 的 JSON 对象。"""
    return _read_json(MODELS_FILE)


@app.post("/models")
async def save_model(model: ModelConfig):
    """
    保存（新增或更新）一个模型配置。
    以 model.name 为键存储到 models.json。
    """
    models = _read_json(MODELS_FILE)                   # 读取现有配置
    models[model.name] = model.model_dump()            # Pydantic 模型转字典
    _write_json(MODELS_FILE, models)                   # 写回磁盘
    return {"message": f"模型 '{model.name}' 已保存", "name": model.name}


@app.delete("/models/{name}")
async def delete_model(name: str):
    """删除指定名称的模型配置。"""
    models = _read_json(MODELS_FILE)
    if name not in models:
        raise HTTPException(status_code=404, detail="模型不存在")
    del models[name]  # 从字典中删除
    _write_json(MODELS_FILE, models)
    return {"message": f"模型 '{name}' 已删除"}


# ═══════════════════════════════════════════════════════════════
# 工具配置 CRUD — /tools
# ═══════════════════════════════════════════════════════════════

@app.get("/tools")
async def list_tools():
    """列出所有工具配置。"""
    return _read_json(TOOLS_FILE)


@app.post("/tools")
async def save_tool(tool: ToolConfig):
    """
    保存（新增或更新）一个工具配置。
    会将参数列表转换为 OpenAI 兼容的 parameters_schema 格式。
    """
    tools = _read_json(TOOLS_FILE)
    tool_dict = tool.model_dump()
    # ── 构建 OpenAI 兼容的 JSON Schema ──
    tool_dict["parameters_schema"] = {
        "type": "object",
        "properties": {p.name: {"type": p.type, "description": p.description} for p in tool.parameters},
        "required": [p.name for p in tool.parameters if p.required],
    }
    # ── 如果未配置 HTTP 接口，移除 url/method/headers 字段 ──
    if not tool.url:
        tool_dict.pop("url", None)
        tool_dict.pop("method", None)
        tool_dict.pop("headers", None)
    tools[tool.name] = tool_dict
    _write_json(TOOLS_FILE, tools)
    return {"message": f"工具 '{tool.name}' 已保存", "name": tool.name}


@app.delete("/tools/{name}")
async def delete_tool(name: str):
    """删除指定名称的工具配置。"""
    tools = _read_json(TOOLS_FILE)
    if name not in tools:
        raise HTTPException(status_code=404, detail="工具不存在")
    del tools[name]
    _write_json(TOOLS_FILE, tools)
    return {"message": f"工具 '{name}' 已删除"}


# ═══════════════════════════════════════════════════════════════
# 提示词管理 — /prompt
# ═══════════════════════════════════════════════════════════════

@app.get("/prompt")
async def get_prompt():
    """获取当前系统提示词。"""
    data = _read_json(PROMPT_FILE)
    return {"content": data.get("content", "你是一个有用的AI助手。")}


@app.post("/prompt")
async def save_prompt(prompt: PromptConfig):
    """
    保存系统提示词。
    只存储 content 字段到 prompt.json。
    """
    _write_json(PROMPT_FILE, {"content": prompt.content})
    return {"message": "提示词已保存"}


# ═══════════════════════════════════════════════════════════════
# POST /run — 同步执行 Agent
# ═══════════════════════════════════════════════════════════════

@app.post("/run")
async def run_agent(run: AgentRun):
    """
    同步执行 Agent，返回完整结果（包括所有消息和日志）。

    支持两种输入模式:
      1. OpenAI 格式: 传入 messages 数组（优先），支持多轮历史
      2. 传统格式: 传入 input 字符串

    执行流程:
      1. 清空上次日志
      2. 生成/使用 thread_id
      3. 构建 input_messages
      4. 调用 build_workflow 构建图
      5. graph.invoke 带 callbacks 和 checkpointer
      6. 序列化输出消息为 OpenAI 兼容格式
    """
    clear_logs()  # 清空全局日志，确保是本轮执行的日志
    try:
        # ── 会话 ID：使用请求中的或自动生成 ──
        thread_id = run.thread_id or str(uuid.uuid4())

        # ── 构建输入消息 ──
        if run.messages:
            # OpenAI 格式：直接转换消息数组（支持多轮历史）
            input_messages = _openai_messages_to_langchain(run.messages)
            # 取最后一条 HumanMessage 作为用户输入文本（用于日志）
            user_input = next(
                (m.content for m in reversed(input_messages) if isinstance(m, HumanMessage)),
                ""
            )
            add_log("执行开始", f"OpenAI格式 | 消息数: {len(run.messages)} | 模型: {run.model_name} | 工具数: {len(run.tools)}")
        else:
            # 传统格式：单条 input 字符串
            input_messages = [HumanMessage(content=run.input or "")]
            user_input = run.input
            add_log("执行开始", f"传统格式 | 输入: {run.input[:50]}... | 模型: {run.model_name} | 工具数: {len(run.tools)}")

        # ── 组装运行时配置字典 ──
        config = {
            "model_name": run.model_name,
            "api_key": run.api_key,
            "base_url": run.base_url,
            "system_prompt": run.system_prompt,
            "tools": run.tools,
            "max_iterations": run.max_iterations,
        }
        add_log("构建图", f"system_prompt: {run.system_prompt[:40]}...")
        graph = await build_workflow(config)  # 异步构建 Agent 图

        # ── 提取图结构信息（用于日志展示） ──
        try:
            raw_graph = graph.get_graph()  # 获取图的可视化结构
            nodes = [{"id": n, "type": getattr(raw_graph.nodes.get(n, None), "__class__.__name__", "?")}
                     for n in raw_graph.nodes]
            edges = []
            for e in raw_graph.edges:
                src = getattr(e, "source", str(e))        # 边起点
                tgt = getattr(e, "target", "")            # 边终点
                cond = getattr(e, "conditional", False)   # 是否条件边
                edges.append({"from": src, "to": tgt} if not cond else {"from": src, "to": tgt, "conditional": True})
            graph_summary = {
                "节点": [n["id"] for n in nodes],
                "边": edges,
            }
            add_log("图构建完成", json.dumps(graph_summary, ensure_ascii=False, indent=2))
        except Exception:
            add_log("图构建完成", f"图类型: {type(graph).__name__}")

        # ── 记录完整的请求参数到日志 ──
        add_log("📤 请求参数",
            f"模型: {run.model_name}\n"
            f"API地址: {run.base_url}\n"
            f"API Key: {run.api_key[:12]}...{run.api_key[-4:] if len(run.api_key) > 16 else '****'}\n"
            f"系统提示词: {run.system_prompt[:80]}{'...' if len(run.system_prompt) > 80 else ''}\n"
            f"工具列表: {[t.get('name', '?') for t in run.tools] if run.tools else '(无)'}\n"
            f"最大迭代: {run.max_iterations}\n"
            f"输入消息数: {len(input_messages)}"
        )
        # 逐条记录输入消息内容
        for i, msg in enumerate(input_messages):
            role = getattr(msg, 'type', 'unknown')
            content = getattr(msg, 'content', '')
            add_log(f"  📝 消息#{i+1}", f"[{role}] {str(content)[:100]}")

        # ── 执行 Agent 图 ──
        add_log("执行图", f"开始 invoke, thread_id={thread_id}, 输入消息数: {len(input_messages)}")
        result = graph.invoke({
            "messages": input_messages,                              # 输入消息
            "remaining_steps": min(run.max_iterations + 10, 50),    # 剩余步数，预留 buffer
        }, {
            "configurable": {"thread_id": thread_id},                # 会话 ID（Checkpointer 关联）
            "callbacks": [LoggingCallbackHandler()],                 # 日志回调
        })

        # ── 序列化输出消息为 OpenAI 兼容格式 ──
        messages = []
        for i, msg in enumerate(result.get("messages", [])):
            try:
                entry = {
                    "role": getattr(msg, "type", "unknown"),      # human/ai/tool/system
                    "content": getattr(msg, "content", ""),
                }
                name = getattr(msg, "name", None)
                if name:
                    entry["name"] = name
                tc_id = getattr(msg, "tool_call_id", None)        # tool 消息的关联 ID
                if tc_id:
                    entry["tool_call_id"] = tc_id
                tc = getattr(msg, "tool_calls", None)             # assistant 的工具调用
                if tc:
                    entry["tool_calls"] = tc
                reasoning = getattr(msg, "reasoning_content", None)  # DeepSeek-R1 思维链
                if reasoning:
                    entry["reasoning_content"] = reasoning
                messages.append(entry)
            except Exception:
                messages.append({"role": "unknown", "content": str(msg)})  # 序列化失败的兜底

        # ── 提取最终输出文本（取最后一条 AI 消息的 content） ──
        output = ""
        for msg in reversed(result.get("messages", [])):
            if hasattr(msg, "type") and msg.type == "ai" and msg.content:
                output = msg.content
                break
        if not output:  # 如果没找到 AI 回复，取最后一条消息
            output = str(messages[-1]["content"]) if messages else "(无输出)"

        add_log("执行完成", f"共 {len(messages)} 条消息")

        return {
            "status": "success",
            "output": output,         # 最终文本输出
            "messages": messages,     # 完整消息历史（OpenAI 格式）
            "logs": get_logs(),       # 执行日志
            "thread_id": thread_id,   # 会话 ID
        }
    except Exception as e:
        add_log("执行失败", str(e), "error")
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════
# POST /run-stream — 流式执行 Agent（SSE）
# ═══════════════════════════════════════════════════════════════

@app.post("/run-stream")
async def run_agent_stream(run: AgentRun):
    """
    流式执行 Agent，通过 Server-Sent Events (SSE) 实时推送。

    相比 /run 的优势:
      - 前端可以逐条展示日志（不用等全部执行完）
      - 实时显示工具调用和 AI 回复
      - 支持"思考中"占位动画

    SSE 事件类型:
      - type: "log"    — 执行日志（模型请求/响应、工具调用等）
      - type: "msg"    — 聊天消息（assistant 文本、tool-start 通知）
      - type: "done"   — 执行完成信号
      - type: "error"  — 错误信号
    """
    clear_logs()  # 清空上次日志
    from datetime import datetime  # 时间戳生成

    thread_id = run.thread_id or str(uuid.uuid4())  # 会话 ID

    # ── 构建输入消息 ──
    if run.messages:
        input_messages = _openai_messages_to_langchain(run.messages)
        user_input = next(
            (m.content for m in reversed(input_messages) if isinstance(m, HumanMessage)),
            ""
        )
    else:
        input_messages = [HumanMessage(content=run.input or "")]
        user_input = run.input

    # ── 运行时配置 ──
    config = {
        "model_name": run.model_name,
        "api_key": run.api_key,
        "base_url": run.base_url,
        "system_prompt": run.system_prompt,
        "tools": run.tools,
        "max_iterations": run.max_iterations,
    }
    graph = await build_workflow(config)  # 异步构建图

    def _now():
        """返回当前时间的毫秒精度字符串，如 "14:32:05.123"。"""
        return datetime.now().strftime("%H:%M:%S.%f")[:-3]

    def _sse(data: dict) -> str:
        """
        将字典包装为 SSE 格式字符串。
        SSE 规范: "data: {JSON}\n\n"
        """
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

    collected_messages = []  # 收集执行过程中的消息片段

    async def event_generator():
        """
        异步生成器，逐条产出 SSE 事件。
        使用 graph.astream_events(v2) 获取事件流。
        """
        nonlocal thread_id  # 允许修改外层变量
        try:
            # ── 发送初始日志（执行开始、构建图、请求参数） ──
            init_logs = [
                {"step": "执行开始", "detail": f"传统格式 | 输入: {(user_input or '')[:50]}... | 模型: {run.model_name} | 工具数: {len(run.tools)}", "level": "info"},
                {"step": "构建图", "detail": f"system_prompt: {run.system_prompt[:40]}...", "level": "info"},
                {"step": "📤 请求参数", "detail": f"模型: {run.model_name}\nAPI地址: {run.base_url}\n系统提示词: {run.system_prompt[:80]}...\n工具列表: {[t.get('name', '?') for t in run.tools] if run.tools else '(无)'}\n最大迭代: {run.max_iterations}\n输入消息数: {len(input_messages)}", "level": "info"},
            ]
            for l in init_logs:
                l["timestamp"] = _now()
                yield _sse({"type": "log", **l})

            # ── 流式执行图，监听事件 ──
            model_call_count = 0  # 模型调用计数器
            async for event in graph.astream_events(
                {
                    "messages": input_messages,
                    "remaining_steps": min(run.max_iterations + 10, 50),
                },
                {"configurable": {"thread_id": thread_id}},  # Checkpointer 配置
                version="v2",  # 使用 v2 事件 API
            ):
                kind = event["event"]        # 事件类型: on_chat_model_start/end, on_tool_start/end
                name = event.get("name", "")  # 事件名称（如 model 名称、tool 名称）
                data = event.get("data", {})  # 事件数据

                # ── 模型调用开始 ──
                if kind == "on_chat_model_start":
                    model_call_count += 1
                    inv = data.get("input", {})            # 模型输入
                    meta = event.get("metadata", {})       # 元数据（含模型名、温度）
                    msgs = inv.get("messages", [])         # 输入消息
                    model_name = meta.get("ls_model_name", "?")     # 实际模型名
                    temperature = meta.get("ls_temperature", 0.7)   # 温度参数

                    # 序列化消息为 JSON
                    msgs_json = []
                    for msg_list in (msgs if isinstance(msgs, list) else [msgs]):
                        if isinstance(msg_list, list):
                            for m in msg_list:
                                entry = {"role": getattr(m, "type", "?"), "content": getattr(m, "content", "")[:200]}
                                for a in ("tool_calls", "tool_call_id", "name"):
                                    v = getattr(m, a, None)
                                    if v: entry[a] = v
                                msgs_json.append(entry)

                    req_body = {"model": model_name, "temperature": temperature, "messages": msgs_json}
                    if run.tools: req_body["tools"] = run.tools  # 工具列表

                    yield _sse({"type": "log", "timestamp": _now(), "step": f"🔵 模型请求 #{model_call_count}",
                        "detail": json.dumps(req_body, ensure_ascii=False, indent=2, default=str)[:5000], "level": "info"})

                # ── 模型调用完成 ──
                elif kind == "on_chat_model_end":
                    output = data.get("output", {})
                    content = getattr(output, "content", "") if hasattr(output, "content") else output.get("content", "")
                    tool_calls = getattr(output, "tool_calls", None) if hasattr(output, "tool_calls") else output.get("tool_calls")
                    add_kw = getattr(output, "additional_kwargs", {}) if hasattr(output, "additional_kwargs") else output.get("additional_kwargs", {})

                    raw = {"content": content, "tool_calls": tool_calls, "additional_kwargs": add_kw}
                    yield _sse({"type": "log", "timestamp": _now(), "step": f"🟢 模型响应 #{model_call_count}.1",
                        "detail": f"原始返回:\n{json.dumps(raw, ensure_ascii=False, indent=2, default=str)[:3000]}", "level": "info"})

                    # ── 思考链展示（DeepSeek-R1） ──
                    reasoning = add_kw.get("reasoning_content", "")
                    if reasoning:
                        yield _sse({"type": "log", "timestamp": _now(), "step": "💭 思考链 (R1)", "detail": str(reasoning)[:2000], "level": "info"})

                    # ── 模型决策：工具调用或直接回答 ──
                    if tool_calls:
                        for tc in tool_calls:
                            tc_name = tc.get("name", tc.get("function", {}).get("name", "?"))  # 兼容不同格式
                            tc_args = tc.get("args", tc.get("function", {}).get("arguments", {}))
                            yield _sse({"type": "log", "timestamp": _now(), "step": "💭 模型决策",
                                "detail": f"调用工具: {tc_name}\n参数: {json.dumps(tc_args, ensure_ascii=False)}", "level": "info"})
                            yield _sse({"type": "msg", "role": "tool-start", "content": f"🔧 开始调用工具: {tc_name}", "name": tc_name})
                    elif content and str(content).strip():
                        yield _sse({"type": "log", "timestamp": _now(), "step": "💭 模型决策", "detail": "直接回答，不调用工具", "level": "info"})
                        yield _sse({"type": "msg", "role": "assistant", "content": str(content)})

                    # 收集消息
                    collected_messages.append({"role": "ai" if not tool_calls else "ai", "content": str(content),
                        "tool_calls": tool_calls})

                # ── 工具调用开始 ──
                elif kind == "on_tool_start":
                    tool_input = data.get("input", "")
                    yield _sse({"type": "log", "timestamp": _now(), "step": "🔧 工具调用",
                        "detail": f"工具: {name}\n入参: {str(tool_input)[:500]}", "level": "info"})

                # ── 工具调用完成 ──
                elif kind == "on_tool_end":
                    tool_output = data.get("output", "")
                    yield _sse({"type": "log", "timestamp": _now(), "step": "🔧 工具返回",
                        "detail": str(tool_output)[:2000], "level": "info"})
                    collected_messages.append({"role": "tool", "content": str(tool_output), "name": name})

            # ── 所有事件处理完毕，发送完成信号 ──
            yield _sse({"type": "log", "timestamp": _now(), "step": "执行完成",
                "detail": f"共 {len(collected_messages)} 条消息", "level": "info"})
            yield _sse({"type": "done", "thread_id": thread_id})

        except Exception as e:
            # ── 异常时发送错误日志和错误信号 ──
            yield _sse({"type": "log", "timestamp": _now(), "step": "执行失败", "detail": str(e), "level": "error"})
            yield _sse({"type": "error", "message": str(e)})

    # 返回 SSE 流式响应
    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ═══════════════════════════════════════════════════════════════
# GET /logs — 获取最近一次执行日志
# ═══════════════════════════════════════════════════════════════

@app.get("/logs")
async def fetch_logs():
    """返回全局日志累积器中的日志列表。"""
    return {"logs": get_logs()}


# ═══════════════════════════════════════════════════════════════
# 历史对话 API — /conversations
# ═══════════════════════════════════════════════════════════════

@app.get("/conversations")
async def list_conversations():
    """
    列出所有历史对话。

    流程:
      1. 从 SQLite checkpoints 表获取所有 thread_id
      2. 用 checkpointer.aget_tuple 获取每个对话的 checkpoint
      3. 从消息中提取标题（第一条用户消息的前 50 字）
      4. 统计消息数和 checkpoint 数
      5. 按创建时间降序排列
    """
    import sqlite3  # 用于直接查询 checkpoints 表
    from pathlib import Path
    from app.agent_setup import get_checkpointer

    db_path = str(Path(__file__).parent.parent / "data" / "checkpoints.db")
    if not Path(db_path).exists():
        return {"conversations": []}  # 数据库不存在时返回空列表

    # ── 第 1 步: 获取所有 thread_id ──
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute("SELECT DISTINCT thread_id FROM checkpoints ORDER BY thread_id")
        thread_ids = [r[0] for r in cur.fetchall()]
    finally:
        conn.close()

    checkpointer = await get_checkpointer()

    # ── 第 2 步: 遍历每个 thread_id，获取对话信息 ──
    conversations = []
    for tid in thread_ids:
        try:
            # 获取该 thread 的最新 checkpoint
            result = await checkpointer.aget_tuple({"configurable": {"thread_id": tid}})
            if not result:
                continue

            cp = result.checkpoint                     # checkpoint 字典
            msgs = cp.get("channel_values", {}).get("messages", [])  # 消息列表
            msg_count = len(msgs)                      # 消息数量
            created_at = cp.get("ts", "")              # 创建时间戳

            # ── 获取标题：取第一条 human 消息的 content 前 50 字 ──
            title = "(空对话)"
            for m in msgs:
                mtype = getattr(m, "type", "")
                if mtype == "human":
                    title = str(getattr(m, "content", ""))[:50]
                    break

            # ── 统计该 thread 的 checkpoint 数量 ──
            conn2 = sqlite3.connect(db_path)
            try:
                cur = conn2.execute("SELECT COUNT(*) FROM checkpoints WHERE thread_id = ?", (tid,))
                cp_count = cur.fetchone()[0]
            finally:
                conn2.close()

            conversations.append({
                "thread_id": tid,
                "title": title,
                "msg_count": msg_count,
                "checkpoint_count": cp_count,
                "created_at": created_at,
            })
        except Exception:
            continue  # 单个对话解析失败不影响其他

    # ── 第 3 步: 按创建时间降序（最新在前） ──
    conversations.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return {"conversations": conversations}


@app.get("/conversations/{thread_id}")
async def get_conversation(thread_id: str):
    """
    获取指定对话的完整消息历史。

    Args:
        thread_id: 会话 ID（来自 URL 路径参数）
    """
    from app.agent_setup import get_checkpointer

    try:
        checkpointer = await get_checkpointer()
        config = {"configurable": {"thread_id": thread_id}}
        result = await checkpointer.aget_tuple(config)  # 获取 checkpoint

        if not result:
            raise HTTPException(status_code=404, detail="对话不存在")

        # ── 序列化消息为 OpenAI 兼容格式 ──
        msgs = result.checkpoint.get("channel_values", {}).get("messages", [])
        messages = []
        for m in msgs:
            entry = {
                "role": getattr(m, "type", "unknown"),
                "content": getattr(m, "content", ""),
            }
            name = getattr(m, "name", None)
            if name:
                entry["name"] = name
            tc = getattr(m, "tool_calls", None)
            if tc:
                entry["tool_calls"] = tc
            tc_id = getattr(m, "tool_call_id", None)
            if tc_id:
                entry["tool_call_id"] = tc_id
            messages.append(entry)

        return {"thread_id": thread_id, "messages": messages}
    except HTTPException:
        raise  # 直接传递 HTTP 异常
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/conversations/{thread_id}")
async def delete_conversation(thread_id: str):
    """
    删除指定对话及其所有 checkpoints。

    调用 checkpointer.adelete_thread 会清理:
      - checkpoints 表中的所有条目
      - writes 表中的所有关联记录
    """
    from app.agent_setup import get_checkpointer

    try:
        checkpointer = await get_checkpointer()
        await checkpointer.adelete_thread(thread_id)  # 异步删除整个 thread
        return {"status": "deleted", "thread_id": thread_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))