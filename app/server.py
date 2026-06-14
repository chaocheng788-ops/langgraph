"""
LangGraph Platform Server
Provides API for:
1. Model config CRUD
2. Tool config CRUD
3. Prompt config management
4. Agent workflow execution
"""
import json
import uuid
from typing import Any, Dict, List, Optional
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.graph import build_workflow
from app.agent_setup import get_logs, clear_logs, add_log, LoggingCallbackHandler

from langchain_core.messages import (
    AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage,
)


# ============================================================
# Data Models
# ============================================================

class ModelConfig(BaseModel):
    name: str
    model_name: str = "deepseek-v4-pro"
    api_key: str = ""
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    temperature: float = 0.7
    max_tokens: int = 4096


class ToolParameter(BaseModel):
    name: str
    type: str = "string"
    description: str = ""
    required: bool = False


class ToolConfig(BaseModel):
    name: str
    description: str = ""
    parameters: List[ToolParameter] = []
    url: str = ""
    method: str = "GET"
    headers: Dict[str, str] = {}


class PromptConfig(BaseModel):
    content: str = "你是一个有用的AI助手。"


class Message(BaseModel):
    """OpenAI-compatible message format."""
    role: str  # "system", "user", "assistant", "tool"
    content: str = ""
    name: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    reasoning_content: Optional[str] = None  # DeepSeek-R1 思维链


class AgentRun(BaseModel):
    model_name: str = "deepseek-chat"
    api_key: str = ""
    base_url: str = "https://api.deepseek.com/v1"
    system_prompt: str = "你是一个有用的AI助手。"
    tools: List[Dict[str, Any]] = []
    max_iterations: int = 10
    input: str = ""
    messages: Optional[List[Message]] = None  # OpenAI 格式消息数组（优先于 input）
    thread_id: str = ""  # 会话 ID，用于 Checkpointer 持久化上下文


# ============================================================
# Global State & Persistence
# ============================================================

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
MODELS_FILE = DATA_DIR / "models.json"
TOOLS_FILE = DATA_DIR / "tools.json"
PROMPT_FILE = DATA_DIR / "prompt.json"


def _read_json(filepath: Path) -> Any:
    if filepath.exists():
        try:
            return json.loads(filepath.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _write_json(filepath: Path, data: Any) -> None:
    filepath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ============================================================
# OpenAI ↔ LangChain 消息转换
# ============================================================

ROLE_TO_LC = {
    "system": SystemMessage,
    "user": HumanMessage,
    "assistant": AIMessage,
    "tool": ToolMessage,
}


def _openai_messages_to_langchain(messages: List[Message]) -> List[BaseMessage]:
    """将 OpenAI 格式的消息数组转换为 LangChain 消息列表。"""
    lc_messages = []
    for msg in messages:
        msg_cls = ROLE_TO_LC.get(msg.role)
        if msg_cls is None:
            add_log("消息转换", f"未知角色 '{msg.role}'，跳过", "warning")
            continue

        kwargs = {"content": msg.content}

        if msg.role == "tool":
            kwargs["tool_call_id"] = msg.tool_call_id or ""
            if msg.name:
                kwargs["name"] = msg.name
        elif msg.role == "assistant" and msg.tool_calls:
            kwargs["tool_calls"] = msg.tool_calls
            if msg.reasoning_content:
                kwargs["reasoning_content"] = msg.reasoning_content
        elif msg.name:
            kwargs["name"] = msg.name

        # 传递 reasoning_content（DeepSeek-R1 思维链）
        if msg.reasoning_content and "reasoning_content" not in kwargs:
            kwargs["reasoning_content"] = msg.reasoning_content

        lc_messages.append(msg_cls(**kwargs))

    return lc_messages


# ============================================================
# App Setup
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    DATA_DIR.mkdir(exist_ok=True)
    yield


app = FastAPI(
    title="LangGraph Agent Platform",
    description="基于 LangGraph 的 Agent 配置与执行平台",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# Health
# ============================================================

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "langgraph-agent-platform"}


# ============================================================
# Model Config CRUD
# ============================================================

@app.get("/models")
async def list_models():
    return _read_json(MODELS_FILE)


@app.post("/models")
async def save_model(model: ModelConfig):
    models = _read_json(MODELS_FILE)
    models[model.name] = model.model_dump()
    _write_json(MODELS_FILE, models)
    return {"message": f"模型 '{model.name}' 已保存", "name": model.name}


@app.delete("/models/{name}")
async def delete_model(name: str):
    models = _read_json(MODELS_FILE)
    if name not in models:
        raise HTTPException(status_code=404, detail="模型不存在")
    del models[name]
    _write_json(MODELS_FILE, models)
    return {"message": f"模型 '{name}' 已删除"}


# ============================================================
# Tool Config CRUD
# ============================================================

@app.get("/tools")
async def list_tools():
    return _read_json(TOOLS_FILE)


@app.post("/tools")
async def save_tool(tool: ToolConfig):
    tools = _read_json(TOOLS_FILE)
    tool_dict = tool.model_dump()
    # Store parameters in OpenAI-compatible format
    tool_dict["parameters_schema"] = {
        "type": "object",
        "properties": {p.name: {"type": p.type, "description": p.description} for p in tool.parameters},
        "required": [p.name for p in tool.parameters if p.required],
    }
    # Ensure url/method/headers are stored
    if not tool.url:
        tool_dict.pop("url", None)
        tool_dict.pop("method", None)
        tool_dict.pop("headers", None)
    tools[tool.name] = tool_dict
    _write_json(TOOLS_FILE, tools)
    return {"message": f"工具 '{tool.name}' 已保存", "name": tool.name}


@app.delete("/tools/{name}")
async def delete_tool(name: str):
    tools = _read_json(TOOLS_FILE)
    if name not in tools:
        raise HTTPException(status_code=404, detail="工具不存在")
    del tools[name]
    _write_json(TOOLS_FILE, tools)
    return {"message": f"工具 '{name}' 已删除"}


# ============================================================
# Prompt Config
# ============================================================

@app.get("/prompt")
async def get_prompt():
    data = _read_json(PROMPT_FILE)
    return {"content": data.get("content", "你是一个有用的AI助手。")}


@app.post("/prompt")
async def save_prompt(prompt: PromptConfig):
    _write_json(PROMPT_FILE, {"content": prompt.content})
    return {"message": "提示词已保存"}


# ============================================================
# Agent Run
# ============================================================

@app.post("/run")
async def run_agent(run: AgentRun):
    """Execute the agent with given configuration and input.
    
    Supports two modes:
    1. OpenAI 格式: 传入 messages 数组（优先）
    2. 传统格式: 传入 input 字符串
    """
    clear_logs()
    try:
        # ── 会话 ID ──
        thread_id = run.thread_id or str(uuid.uuid4())

        # ── 构建输入消息 ──
        if run.messages:
            # OpenAI 格式：直接转换消息数组
            input_messages = _openai_messages_to_langchain(run.messages)
            user_input = next(
                (m.content for m in reversed(input_messages) if isinstance(m, HumanMessage)),
                ""
            )
            add_log("执行开始", f"OpenAI格式 | 消息数: {len(run.messages)} | 模型: {run.model_name} | 工具数: {len(run.tools)}")
        else:
            # 传统格式：单条 input
            input_messages = [HumanMessage(content=run.input or "")]
            user_input = run.input
            add_log("执行开始", f"传统格式 | 输入: {run.input[:50]}... | 模型: {run.model_name} | 工具数: {len(run.tools)}")

        config = {
            "model_name": run.model_name,
            "api_key": run.api_key,
            "base_url": run.base_url,
            "system_prompt": run.system_prompt,
            "tools": run.tools,
            "max_iterations": run.max_iterations,
        }
        add_log("构建图", f"system_prompt: {run.system_prompt[:40]}...")
        graph = await build_workflow(config)
        # 提取图结构 (for /run endpoint)
        try:
            raw_graph = graph.get_graph()
            nodes = [{"id": n, "type": getattr(raw_graph.nodes.get(n, None), "__class__.__name__", "?")}
                     for n in raw_graph.nodes]
            edges = []
            for e in raw_graph.edges:
                src = getattr(e, "source", str(e))
                tgt = getattr(e, "target", "")
                cond = getattr(e, "conditional", False)
                edges.append({"from": src, "to": tgt} if not cond else {"from": src, "to": tgt, "conditional": True})
            graph_summary = {
                "节点": [n["id"] for n in nodes],
                "边": edges,
            }
            add_log("图构建完成", json.dumps(graph_summary, ensure_ascii=False, indent=2))
        except Exception:
            add_log("图构建完成", f"图类型: {type(graph).__name__}")

        # ── 记录完整请求参数 ──
        add_log("📤 请求参数",
            f"模型: {run.model_name}\n"
            f"API地址: {run.base_url}\n"
            f"API Key: {run.api_key[:12]}...{run.api_key[-4:] if len(run.api_key) > 16 else '****'}\n"
            f"系统提示词: {run.system_prompt[:80]}{'...' if len(run.system_prompt) > 80 else ''}\n"
            f"工具列表: {[t.get('name', '?') for t in run.tools] if run.tools else '(无)'}\n"
            f"最大迭代: {run.max_iterations}\n"
            f"输入消息数: {len(input_messages)}"
        )
        for i, msg in enumerate(input_messages):
            role = getattr(msg, 'type', 'unknown')
            content = getattr(msg, 'content', '')
            add_log(f"  📝 消息#{i+1}", f"[{role}] {str(content)[:100]}")

        add_log("执行图", f"开始 invoke, thread_id={thread_id}, 输入消息数: {len(input_messages)}")
        result = graph.invoke({
            "messages": input_messages,
            "remaining_steps": min(run.max_iterations + 10, 50),
        }, {
            "configurable": {"thread_id": thread_id},
            "callbacks": [LoggingCallbackHandler()],
        })

        # Serialize messages → OpenAI 兼容格式
        messages = []
        for i, msg in enumerate(result.get("messages", [])):
            try:
                entry = {
                    "role": getattr(msg, "type", "unknown"),
                    "content": getattr(msg, "content", ""),
                }
                name = getattr(msg, "name", None)
                if name:
                    entry["name"] = name
                # 保留 tool_call_id（tool 消息）
                tc_id = getattr(msg, "tool_call_id", None)
                if tc_id:
                    entry["tool_call_id"] = tc_id
                # 保留 tool_calls（assistant 消息）
                tc = getattr(msg, "tool_calls", None)
                if tc:
                    entry["tool_calls"] = tc
                # 保留 reasoning_content（DeepSeek-R1 思维链）
                reasoning = getattr(msg, "reasoning_content", None)
                if reasoning:
                    entry["reasoning_content"] = reasoning
                messages.append(entry)
            except Exception:
                messages.append({"role": "unknown", "content": str(msg)})

        # Extract output from last AI message
        output = ""
        for msg in reversed(result.get("messages", [])):
            if hasattr(msg, "type") and msg.type == "ai" and msg.content:
                output = msg.content
                break
        if not output:
            output = str(messages[-1]["content"]) if messages else "(无输出)"

        add_log("执行完成", f"共 {len(messages)} 条消息")

        return {
            "status": "success",
            "output": output,
            "messages": messages,
            "logs": get_logs(),
            "thread_id": thread_id,
        }
    except Exception as e:
        add_log("执行失败", str(e), "error")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/run-stream")
async def run_agent_stream(run: AgentRun):
    """流式执行 Agent，通过 SSE 实时推送日志和消息。"""
    clear_logs()
    from datetime import datetime

    thread_id = run.thread_id or str(uuid.uuid4())

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

    config = {
        "model_name": run.model_name,
        "api_key": run.api_key,
        "base_url": run.base_url,
        "system_prompt": run.system_prompt,
        "tools": run.tools,
        "max_iterations": run.max_iterations,
    }
    graph = await build_workflow(config)

    def _now():
        return datetime.now().strftime("%H:%M:%S.%f")[:-3]

    def _sse(data: dict) -> str:
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

    collected_messages = []  # 收集最终消息用于返回
    log_index = 0

    async def event_generator():
        nonlocal log_index
        try:
            # ── 初始日志 ──
            init_logs = [
                {"step": "执行开始", "detail": f"传统格式 | 输入: {(user_input or '')[:50]}... | 模型: {run.model_name} | 工具数: {len(run.tools)}", "level": "info"},
                {"step": "构建图", "detail": f"system_prompt: {run.system_prompt[:40]}...", "level": "info"},
                {"step": "📤 请求参数", "detail": f"模型: {run.model_name}\nAPI地址: {run.base_url}\n系统提示词: {run.system_prompt[:80]}...\n工具列表: {[t.get('name', '?') for t in run.tools] if run.tools else '(无)'}\n最大迭代: {run.max_iterations}\n输入消息数: {len(input_messages)}", "level": "info"},
            ]
            for l in init_logs:
                l["timestamp"] = _now()
                yield _sse({"type": "log", **l})

            # ── 流式执行图 ──
            model_call_count = 0
            async for event in graph.astream_events(
                {
                    "messages": input_messages,
                    "remaining_steps": min(run.max_iterations + 10, 50),
                },
                {"configurable": {"thread_id": thread_id}},
                version="v2",
            ):
                kind = event["event"]
                name = event.get("name", "")
                data = event.get("data", {})

                if kind == "on_chat_model_start":
                    model_call_count += 1
                    inv = data.get("input", {})
                    meta = event.get("metadata", {})
                    msgs = inv.get("messages", [])
                    model_name = meta.get("ls_model_name", "?")
                    temperature = meta.get("ls_temperature", 0.7)

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
                    if run.tools: req_body["tools"] = run.tools

                    yield _sse({"type": "log", "timestamp": _now(), "step": f"🔵 模型请求 #{model_call_count}",
                        "detail": json.dumps(req_body, ensure_ascii=False, indent=2, default=str)[:5000], "level": "info"})

                elif kind == "on_chat_model_end":
                    output = data.get("output", {})
                    content = getattr(output, "content", "") if hasattr(output, "content") else output.get("content", "")
                    tool_calls = getattr(output, "tool_calls", None) if hasattr(output, "tool_calls") else output.get("tool_calls")
                    add_kw = getattr(output, "additional_kwargs", {}) if hasattr(output, "additional_kwargs") else output.get("additional_kwargs", {})

                    raw = {"content": content, "tool_calls": tool_calls, "additional_kwargs": add_kw}
                    yield _sse({"type": "log", "timestamp": _now(), "step": f"🟢 模型响应 #{model_call_count}.1",
                        "detail": f"原始返回:\n{json.dumps(raw, ensure_ascii=False, indent=2, default=str)[:3000]}", "level": "info"})

                    # 思考链
                    reasoning = add_kw.get("reasoning_content", "")
                    if reasoning:
                        yield _sse({"type": "log", "timestamp": _now(), "step": "💭 思考链 (R1)", "detail": str(reasoning)[:2000], "level": "info"})

                    if tool_calls:
                        for tc in tool_calls:
                            tc_name = tc.get("name", tc.get("function", {}).get("name", "?"))
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

                elif kind == "on_tool_start":
                    tool_input = data.get("input", "")
                    yield _sse({"type": "log", "timestamp": _now(), "step": "🔧 工具调用",
                        "detail": f"工具: {name}\n入参: {str(tool_input)[:500]}", "level": "info"})

                elif kind == "on_tool_end":
                    tool_output = data.get("output", "")
                    yield _sse({"type": "log", "timestamp": _now(), "step": "🔧 工具返回",
                        "detail": str(tool_output)[:2000], "level": "info"})
                    # 收集 tool 消息
                    collected_messages.append({"role": "tool", "content": str(tool_output), "name": name})

            # ── 完成 ──
            yield _sse({"type": "log", "timestamp": _now(), "step": "执行完成",
                "detail": f"共 {len(collected_messages)} 条消息", "level": "info"})
            yield _sse({"type": "done", "thread_id": thread_id})

        except Exception as e:
            yield _sse({"type": "log", "timestamp": _now(), "step": "执行失败", "detail": str(e), "level": "error"})
            yield _sse({"type": "error", "message": str(e)})

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/logs")
async def fetch_logs():
    """Get the most recent execution logs."""
    return {"logs": get_logs()}


# ============================================================
# Conversation History APIs
# ============================================================

@app.get("/conversations")
async def list_conversations():
    """列出所有历史对话（thread_id + 标题）。"""
    import sqlite3
    from pathlib import Path
    from app.agent_setup import get_checkpointer

    db_path = str(Path(__file__).parent.parent / "data" / "checkpoints.db")
    if not Path(db_path).exists():
        return {"conversations": []}

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute("SELECT DISTINCT thread_id FROM checkpoints ORDER BY thread_id")
        thread_ids = [r[0] for r in cur.fetchall()]
    finally:
        conn.close()

    checkpointer = await get_checkpointer()

    conversations = []
    for tid in thread_ids:
        try:
            result = await checkpointer.aget_tuple({"configurable": {"thread_id": tid}})
            if not result:
                continue

            cp = result.checkpoint
            msgs = cp.get("channel_values", {}).get("messages", [])
            msg_count = len(msgs)
            created_at = cp.get("ts", "")

            # Get title from first human message
            title = "(空对话)"
            for m in msgs:
                mtype = getattr(m, "type", "")
                if mtype == "human":
                    title = str(getattr(m, "content", ""))[:50]
                    break

            # Count checkpoints
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
            continue

    # Sort by created_at descending (newest first)
    conversations.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return {"conversations": conversations}


@app.get("/conversations/{thread_id}")
async def get_conversation(thread_id: str):
    """获取指定对话的完整消息历史。"""
    from app.agent_setup import get_checkpointer

    try:
        checkpointer = await get_checkpointer()
        config = {"configurable": {"thread_id": thread_id}}
        result = await checkpointer.aget_tuple(config)

        if not result:
            raise HTTPException(status_code=404, detail="对话不存在")

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
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/conversations/{thread_id}")
async def delete_conversation(thread_id: str):
    """删除指定对话及其所有 checkpoints。"""
    from app.agent_setup import get_checkpointer

    try:
        checkpointer = await get_checkpointer()
        await checkpointer.adelete_thread(thread_id)
        return {"status": "deleted", "thread_id": thread_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
