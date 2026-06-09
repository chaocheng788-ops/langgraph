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
from pydantic import BaseModel

from app.graph import build_workflow
from app.agent_setup import get_logs, clear_logs, add_log

from langchain_core.messages import (
    AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage,
)


# ============================================================
# Data Models
# ============================================================

class ModelConfig(BaseModel):
    name: str
    model_name: str = "deepseek-v4-flash"
    api_key: str = ""
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
    model_name: str = "fake"
    api_key: str = ""
    system_prompt: str = "你是一个有用的AI助手。"
    tools: List[Dict[str, Any]] = []
    max_iterations: int = 10
    input: str = ""
    messages: Optional[List[Message]] = None  # OpenAI 格式消息数组（优先于 input）


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
            "system_prompt": run.system_prompt,
            "tools": run.tools,
            "max_iterations": run.max_iterations,
        }
        add_log("构建图", f"system_prompt: {run.system_prompt[:40]}...")
        graph = build_workflow(config)
        add_log("图构建完成", f"图类型: {type(graph).__name__}")

        add_log("执行图", f"开始 invoke, 输入消息数: {len(input_messages)}")
        result = graph.invoke({
            "messages": input_messages,
            "remaining_steps": min(run.max_iterations + 10, 50),
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
                add_log(f"第{i+1}步", f"[{entry['role']}] {str(entry['content'])[:60]}")
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
        }
    except Exception as e:
        add_log("执行失败", str(e), "error")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/logs")
async def fetch_logs():
    """Get the most recent execution logs."""
    return {"logs": get_logs()}
