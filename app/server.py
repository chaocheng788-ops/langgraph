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
from app.execution_log import get_logs, clear_logs, add_log, LoggingCallbackHandler
from app.skill_router import resolve_skills, get_all_skills, build_skill_meta_tools

from langchain_core.messages import (
    AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage,
)


# ═══════════════════════════════════════ Data Models ═════════════════════════════════════

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


class SkillToolConfig(BaseModel):
    name: str
    description: str = ""
    parameters: List[ToolParameter] = []
    url: str = ""
    method: str = "GET"
    headers: Dict[str, str] = {}


class SkillConfig(BaseModel):
    name: str
    description: str = ""
    tools: List[SkillToolConfig] = []
    prompt: str = ""


class PromptConfig(BaseModel):
    content: str = "你是一个有用的AI助手。"


class Message(BaseModel):
    """OpenAI 兼容的消息格式"""
    role: str
    content: str = ""
    name: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    reasoning_content: Optional[str] = None


class AgentRun(BaseModel):
    model_name: str = "deepseek-chat"
    api_key: str = ""
    base_url: str = "https://api.deepseek.com/v1"
    system_prompt: str = "你是一个有用的AI助手。"
    tools: List[Dict[str, Any]] = []
    skills: List[str] = []          # 手动指定技能名称（图内路由自动发现优先）
    max_iterations: int = 10
    input: str = ""
    messages: Optional[List[Message]] = None
    thread_id: str = ""


# ═══════════════════════════════════════ Persistence ═══════════════════════════════════

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
MODELS_FILE = DATA_DIR / "models.json"
TOOLS_FILE = DATA_DIR / "tools.json"
SKILLS_FILE = DATA_DIR / "skills.json"
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


# ═══════════════════════════════════════ Message Conversion ══════════════════════════════

ROLE_TO_LC = {
    "system": SystemMessage,
    "user": HumanMessage,
    "assistant": AIMessage,
    "tool": ToolMessage,
}


def _openai_messages_to_langchain(messages: List[Message]) -> List[BaseMessage]:
    """将 OpenAI 格式的消息数组转换为 LangChain 消息列表"""
    lc_messages = []
    for msg in messages:
        msg_cls = ROLE_TO_LC.get(msg.role)
        if msg_cls is None:
            add_log("消息转换", f"未知角色 '{msg.role}'，跳过", "warning")
            continue
        kwargs = {"content": msg.content}
        if msg.role == "tool":
            kwargs["tool_call_id"] = msg.tool_call_id or ""
            if msg.name: kwargs["name"] = msg.name
        elif msg.role == "assistant" and msg.tool_calls:
            kwargs["tool_calls"] = msg.tool_calls
            if msg.reasoning_content: kwargs["reasoning_content"] = msg.reasoning_content
        elif msg.name: kwargs["name"] = msg.name
        if msg.reasoning_content and "reasoning_content" not in kwargs:
            kwargs["reasoning_content"] = msg.reasoning_content
        lc_messages.append(msg_cls(**kwargs))
    return lc_messages


# ═══════════════════════════════════════ App Setup ════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    DATA_DIR.mkdir(exist_ok=True)
    yield


app = FastAPI(title="LangGraph Agent Platform", description="基于 LangGraph 的 Agent 配置与执行平台", version="2.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


# ═══════════════════════════════════════ CRUD APIs ════════════════════════════════════

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "langgraph-agent-platform"}


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
    if name not in models: raise HTTPException(status_code=404, detail="模型不存在")
    del models[name]
    _write_json(MODELS_FILE, models)
    return {"message": f"模型 '{name}' 已删除"}


@app.get("/tools")
async def list_tools():
    return _read_json(TOOLS_FILE)


@app.post("/tools")
async def save_tool(tool: ToolConfig):
    tools = _read_json(TOOLS_FILE)
    tool_dict = tool.model_dump()
    tool_dict["parameters_schema"] = {"type": "object", "properties": {p.name: {"type": p.type, "description": p.description} for p in tool.parameters}, "required": [p.name for p in tool.parameters if p.required]}
    if not tool.url: tool_dict.pop("url", None); tool_dict.pop("method", None); tool_dict.pop("headers", None)
    tools[tool.name] = tool_dict
    _write_json(TOOLS_FILE, tools)
    return {"message": f"工具 '{tool.name}' 已保存", "name": tool.name}


@app.delete("/tools/{name}")
async def delete_tool(name: str):
    tools = _read_json(TOOLS_FILE)
    if name not in tools: raise HTTPException(status_code=404, detail="工具不存在")
    del tools[name]
    _write_json(TOOLS_FILE, tools)
    return {"message": f"工具 '{name}' 已删除"}


@app.get("/skills")
async def list_skills():
    return get_all_skills()


@app.post("/skills")
async def save_skill(skill: SkillConfig):
    skills = _read_json(SKILLS_FILE)
    skill_dict = skill.model_dump()
    for tool in skill_dict.get("tools", []):
        params = tool.get("parameters", [])
        tool["parameters_schema"] = {"type": "object", "properties": {p["name"]: {"type": p["type"], "description": p["description"]} for p in params}, "required": [p["name"] for p in params if p.get("required")]}
        if not tool.get("url"): tool.pop("url", None); tool.pop("method", None); tool.pop("headers", None)
    skills[skill.name] = skill_dict
    _write_json(SKILLS_FILE, skills)
    return {"message": f"技能 '{skill.name}' 已保存", "name": skill.name}


@app.delete("/skills/{name}")
async def delete_skill(name: str):
    skills = _read_json(SKILLS_FILE)
    if name not in skills: raise HTTPException(status_code=404, detail="技能不存在")
    del skills[name]
    _write_json(SKILLS_FILE, skills)
    return {"message": f"技能 '{name}' 已删除"}


@app.get("/prompt")
async def get_prompt():
    data = _read_json(PROMPT_FILE)
    return {"content": data.get("content", "你是一个有用的AI助手。")}


@app.post("/prompt")
async def save_prompt(prompt: PromptConfig):
    _write_json(PROMPT_FILE, {"content": prompt.content})
    return {"message": "提示词已保存"}


# ═══════════════════════════════════════ Agent Run (non-streaming) ═══════════════════════

@app.post("/run")
async def run_agent(run: AgentRun):
    clear_logs()
    try:
        thread_id = run.thread_id or str(uuid.uuid4())
        if run.messages:
            input_messages = _openai_messages_to_langchain(run.messages)
            user_input = next((m.content for m in reversed(input_messages) if isinstance(m, HumanMessage)), "")
        else:
            input_messages = [HumanMessage(content=run.input or "")]
            user_input = run.input
        resolved_tools = run.tools
        if run.skills and not run.tools:
            skill_tools, _ = resolve_skills(run.skills)
            if skill_tools: resolved_tools = skill_tools
        config = {"model_name": run.model_name, "api_key": run.api_key, "base_url": run.base_url, "system_prompt": run.system_prompt, "tools": resolved_tools, "max_iterations": run.max_iterations}
        graph = await build_workflow(config)
        result = graph.invoke({"messages": input_messages, "remaining_steps": min(run.max_iterations + 10, 50)}, {"configurable": {"thread_id": thread_id}, "callbacks": [LoggingCallbackHandler()]})
        messages = []
        for msg in result.get("messages", []):
            try:
                entry = {"role": getattr(msg, "type", "unknown"), "content": getattr(msg, "content", "")}
                for attr in ("name", "tool_calls", "tool_call_id", "reasoning_content"):
                    v = getattr(msg, attr, None)
                    if v: entry[attr] = v
                messages.append(entry)
            except Exception:
                messages.append({"role": "unknown", "content": str(msg)})
        output = ""
        for msg in reversed(result.get("messages", [])):
            if hasattr(msg, "type") and msg.type == "ai" and msg.content:
                output = msg.content; break
        if not output: output = str(messages[-1]["content"]) if messages else "(无输出)"
        return {"status": "success", "output": output, "messages": messages, "logs": get_logs(), "thread_id": thread_id}
    except Exception as e:
        add_log("执行失败", str(e), "error")
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════ Agent Run (SSE streaming) ═══════════════════════

@app.post("/run-stream")
async def run_agent_stream(run: AgentRun):
    """流式执行 Agent，通过 SSE 实时推送日志和消息到前端"""
    clear_logs()
    from datetime import datetime
    thread_id = run.thread_id or str(uuid.uuid4())

    # ── 构建输入消息 ──
    if run.messages:
        input_messages = _openai_messages_to_langchain(run.messages)
        user_input = next((m.content for m in reversed(input_messages) if isinstance(m, HumanMessage)), "")
    else:
        input_messages = [HumanMessage(content=run.input or "")]
        user_input = run.input

    # ── 技能发现：图内 route 节点自行处理，这里仅处理手动 skills 回退 ──
    resolved_tools = run.tools
    if run.skills and not run.tools:
        skill_tools, _ = resolve_skills(run.skills)
        if skill_tools: resolved_tools = skill_tools

    config = {"model_name": run.model_name, "api_key": run.api_key, "base_url": run.base_url, "system_prompt": run.system_prompt, "tools": resolved_tools, "max_iterations": run.max_iterations}
    graph = await build_workflow(config)

    def _now(): return datetime.now().strftime("%H:%M:%S.%f")[:-3]                        # 毫秒精度时间戳
    def _sse(data: dict) -> str: return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"  # SSE 格式化
    collected_messages = []                                                                  # 收集最终消息用于返回

    async def event_generator():
        try:
            # ── 初始日志 ──
            init_logs = [
                {"step": "执行开始", "detail": f"输入: {(user_input or '')} | 模型: {run.model_name} | 工具数: {len(resolved_tools)}", "level": "info"},
                {"step": "构建图", "detail": f"system_prompt: {run.system_prompt}", "level": "info"},
                {"step": "📤 请求参数", "detail": f"模型: {run.model_name}\nAPI地址: {run.base_url}\n系统提示词: {run.system_prompt}\n工具列表: {[t.get('name', '?') for t in resolved_tools] if resolved_tools else '(无)'}\n最大迭代: {run.max_iterations}\n输入消息数: {len(input_messages)}", "level": "info"},
            ]
            for l in init_logs: l["timestamp"] = _now(); yield _sse({"type": "log", **l})

            model_call_count = 0; route_state = {}; agent_depth = 0; agent_state = {}

            # ── 遍历 LangGraph astream_events v2 事件流 ──
            async for event in graph.astream_events({"messages": input_messages, "remaining_steps": min(run.max_iterations + 10, 50)}, {"configurable": {"thread_id": thread_id}}, version="v2"):
                kind = event["event"]; name = event.get("name", ""); data = event.get("data", {})

                # ── route 节点：技能发现 ──
                if kind == "on_chain_start" and name == "route":
                    route_state["input"] = data.get("input", {})
                elif kind == "on_chain_end" and name == "route":
                    route_state["output"] = data.get("output", {})
                    out = route_state["output"]; inp = route_state.get("input", {})
                    yield _sse({"type": "log", "timestamp": _now(), "step": "🧠 技能路由结果", "detail": json.dumps({"selected_skills": out.get("selected_skills", []), "remaining_steps": inp.get("remaining_steps", "?")}, ensure_ascii=False, indent=2), "level": "info"})

                # ── agent 节点：ReAct 推理循环 ──
                elif kind == "on_chain_start" and name == "agent":
                    agent_depth += 1
                    if agent_depth == 1: agent_state["input"] = data.get("input", {})
                elif kind == "on_chain_end" and name == "agent":
                    if agent_depth == 1:
                        agent_state["output"] = data.get("output", {})
                        yield _sse({"type": "log", "timestamp": _now(), "step": "📤 agent 节点出参", "detail": json.dumps({"selected_skills": agent_state["output"].get("selected_skills", []), "remaining_steps": agent_state["output"].get("remaining_steps", "?"), "messages_count": len(agent_state["output"].get("messages", []))}, ensure_ascii=False, indent=2), "level": "info"})
                    agent_depth -= 1

                # ── 模型请求开始：序列化请求参数到日志 ──
                elif kind == "on_chat_model_start":
                    model_call_count += 1
                    is_route_call = (model_call_count == 1)          # 第1次调用 = 路由节点
                    is_first_agent_call = (model_call_count == 2)    # 第2次调用 = Agent 首次推理
                    inv = data.get("input", {}); meta = event.get("metadata", {})
                    msgs = inv.get("messages", []); model_name = meta.get("ls_model_name", "?"); temperature = meta.get("ls_temperature", 0.7)
                    msgs_json = []
                    for msg_list in (msgs if isinstance(msgs, list) else [msgs]):
                        if isinstance(msg_list, list):
                            for m in msg_list:
                                entry = {"role": getattr(m, "type", "?"), "content": getattr(m, "content", "")}
                                for a in ("tool_calls", "tool_call_id", "name"):
                                    v = getattr(m, a, None)
                                    if v: entry[a] = v
                                msgs_json.append(entry)
                    req_body = {"model": model_name, "temperature": temperature, "messages": msgs_json}
                    if is_route_call:
                        route_tools = build_skill_meta_tools(get_all_skills())
                        if route_tools: req_body["tools"] = route_tools
                    elif resolved_tools: req_body["tools"] = resolved_tools
                    step_label = f"🔵 模型请求 #{model_call_count}"
                    detail = json.dumps(req_body, ensure_ascii=False, indent=2, default=str)
                    if is_route_call and route_state.get("input"):
                        rs = route_state["input"]
                        step_label = f"🔵 路由发现 #{model_call_count}"
                        detail = json.dumps({"_state": {"selected_skills": rs.get("selected_skills", []), "remaining_steps": rs.get("remaining_steps", "?"), "messages_count": len(rs.get("messages", []))}, "_model_request": req_body}, ensure_ascii=False, indent=2, default=str)
                    elif is_first_agent_call and agent_state.get("input"):
                        ag = agent_state["input"]
                        step_label = f"🔵 Agent 推理 #{model_call_count}"
                        detail = json.dumps({"_state": {"selected_skills": ag.get("selected_skills", []), "remaining_steps": ag.get("remaining_steps", "?"), "messages_count": len(ag.get("messages", []))}, "_model_request": req_body}, ensure_ascii=False, indent=2, default=str)
                    yield _sse({"type": "log", "timestamp": _now(), "step": step_label, "detail": detail, "level": "info"})

                # ── 模型响应：推送 AI 文字 + 工具调用到前端聊天区 ──
                elif kind == "on_chat_model_end":
                    output = data.get("output", {})
                    content = getattr(output, "content", "") if hasattr(output, "content") else output.get("content", "")
                    tool_calls = getattr(output, "tool_calls", None) if hasattr(output, "tool_calls") else output.get("tool_calls")
                    add_kw = getattr(output, "additional_kwargs", {}) if hasattr(output, "additional_kwargs") else output.get("additional_kwargs", {})

                    # 日志：原始返回
                    raw = {"content": content, "tool_calls": tool_calls, "additional_kwargs": add_kw}
                    yield _sse({"type": "log", "timestamp": _now(), "step": f"🟢 模型响应 #{model_call_count}.1", "detail": f"原始返回:\n{json.dumps(raw, ensure_ascii=False, indent=2, default=str)}", "level": "info"})

                    # 思考链（DeepSeek-R1）
                    reasoning = add_kw.get("reasoning_content", "")
                    if reasoning: yield _sse({"type": "log", "timestamp": _now(), "step": "💭 思考链 (R1)", "detail": str(reasoning)[:2000], "level": "info"})

                    # AI 文字先推送（先表态，再触发工具调用 — 符合自然对话顺序）
                    if content and str(content).strip():
                        if not tool_calls: yield _sse({"type": "log", "timestamp": _now(), "step": "💭 模型决策", "detail": "直接回答，不调用工具", "level": "info"})
                        yield _sse({"type": "msg", "role": "assistant", "content": str(content)})

                    # 工具调用推送（所有 tool_call 都推送，包括 use_skill__ 路由伪工具）
                    if tool_calls:
                        for tc in tool_calls:
                            tc_name = tc.get("name", tc.get("function", {}).get("name", "?"))
                            tc_args = tc.get("args", tc.get("function", {}).get("arguments", {}))
                            yield _sse({"type": "log", "timestamp": _now(), "step": "💭 模型决策", "detail": f"调用工具: {tc_name}\n参数: {json.dumps(tc_args, ensure_ascii=False)}", "level": "info"})
                            yield _sse({"type": "msg", "role": "tool-start", "content": f"🔧 开始调用工具: {tc_name}", "name": tc_name})

                    collected_messages.append({"role": "ai", "content": str(content), "tool_calls": tool_calls})

                # ── 工具开始执行 ──
                elif kind == "on_tool_start":
                    tool_input = data.get("input", "")
                    yield _sse({"type": "log", "timestamp": _now(), "step": "🔧 工具调用", "detail": f"工具: {name}\n入参: {str(tool_input)[:500]}", "level": "info"})

                # ── 工具执行完毕：日志 + 推送 tool 消息到前端（用于标记 tool-start 完成 + 提取 preview_url） ──
                elif kind == "on_tool_end":
                    tool_output = data.get("output", "")
                    yield _sse({"type": "log", "timestamp": _now(), "step": "🔧 工具返回", "detail": str(tool_output)[:2000], "level": "info"})
                    yield _sse({"type": "msg", "role": "tool", "content": str(tool_output), "name": name})
                    collected_messages.append({"role": "tool", "content": str(tool_output), "name": name})

            # ── 完成 ──
            yield _sse({"type": "log", "timestamp": _now(), "step": "执行完成", "detail": f"共 {len(collected_messages)} 条消息", "level": "info"})
            yield _sse({"type": "done", "thread_id": thread_id})
        except Exception as e:
            yield _sse({"type": "log", "timestamp": _now(), "step": "执行失败", "detail": str(e), "level": "error"})
            yield _sse({"type": "error", "message": str(e)})
    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/logs")
async def fetch_logs():
    return {"logs": get_logs()}


# ═══════════════════════════════════════ Conversation History ═════════════════════════════

@app.get("/conversations")
async def list_conversations():
    import sqlite3
    from pathlib import Path
    from app.agent_setup import get_checkpointer
    db_path = str(Path(__file__).parent.parent / "data" / "checkpoints.db")
    if not Path(db_path).exists(): return {"conversations": []}
    conn = sqlite3.connect(db_path)
    try: thread_ids = [r[0] for r in conn.execute("SELECT DISTINCT thread_id FROM checkpoints ORDER BY thread_id").fetchall()]
    finally: conn.close()
    checkpointer = await get_checkpointer()
    conversations = []
    for tid in thread_ids:
        try:
            result = await checkpointer.aget_tuple({"configurable": {"thread_id": tid}})
            if not result: continue
            cp = result.checkpoint; msgs = cp.get("channel_values", {}).get("messages", [])
            msg_count = len(msgs); created_at = cp.get("ts", "")
            title = "(空对话)"
            for m in msgs:
                if getattr(m, "type", "") == "human": title = str(getattr(m, "content", ""))[:50]; break
            conn2 = sqlite3.connect(db_path)
            try: cp_count = conn2.execute("SELECT COUNT(*) FROM checkpoints WHERE thread_id = ?", (tid,)).fetchone()[0]
            finally: conn2.close()
            conversations.append({"thread_id": tid, "title": title, "msg_count": msg_count, "checkpoint_count": cp_count, "created_at": created_at})
        except Exception: continue
    conversations.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return {"conversations": conversations}


@app.get("/conversations/{thread_id}")
async def get_conversation(thread_id: str):
    from app.agent_setup import get_checkpointer
    try:
        checkpointer = await get_checkpointer()
        result = await checkpointer.aget_tuple({"configurable": {"thread_id": thread_id}})
        if not result: raise HTTPException(status_code=404, detail="对话不存在")
        msgs = result.checkpoint.get("channel_values", {}).get("messages", [])
        messages = []
        for m in msgs:
            entry = {"role": getattr(m, "type", "unknown"), "content": getattr(m, "content", "")}
            for attr in ("name", "tool_calls", "tool_call_id"):
                v = getattr(m, attr, None)
                if v: entry[attr] = v
            messages.append(entry)
        return {"thread_id": thread_id, "messages": messages}
    except HTTPException: raise
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))


@app.delete("/conversations/{thread_id}")
async def delete_conversation(thread_id: str):
    from app.agent_setup import get_checkpointer
    try:
        checkpointer = await get_checkpointer()
        await checkpointer.adelete_thread(thread_id)
        return {"status": "deleted", "thread_id": thread_id}
    except Exception as e: raise HTTPException(status_code=500, detail=str(e))