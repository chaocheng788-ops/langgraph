# LangGraph Agent Platform

基于 LangGraph + FastAPI 的 AI Agent 可视化编排平台，支持流式对话、工具调用、多轮历史持久化。

## 功能特性

- **可视化前端**：模型配置、工具管理、提示词编辑、实时对话
- **流式交互**：SSE 实时推送日志和 AI 响应，逐条展示
- **内置工具集**：6 个内置工具（网页搜索、计算器、摘要、翻译、情感分析、天气查询），支持函数名别名匹配
- **动态工具**：支持 HTTP API 工具配置，Echo 回退工具兜底
- **多轮对话**：基于 SQLite + AsyncSqliteSaver 持久化上下文，跨请求保持会话
- **历史管理**：右上角下拉面板查看/加载/删除历史对话
- **日志抽屉**：可拖拽调整宽度，查看模型请求/响应、工具调用/返回详情
- **模块化架构**：app/ 拆分为 11 个模块文件，职责清晰、易于维护

## 目录结构

```
langgraph/
├── main.py                     # 入口，启动 FastAPI + 挂载前端静态文件
├── requirements.txt            # Python 依赖
├── setup.ps1                   # Windows 一键安装脚本
├── .env                        # 环境变量配置
├── .gitignore                  # Git 忽略规则
├── langgraph.json              # LangGraph CLI 配置
├── config.models.example.json  # 模型配置模板（复制到 data/models.json）
├── config.tools.example.json   # 工具配置模板（复制到 data/tools.json）
├── app/
│   ├── __init__.py             # 包初始化
│   ├── agent_setup.py          # Agent 核心：AgentState 定义 + create_agent_graph 组装
│   ├── builtin_tools.py        # 6 个内置工具定义 + BUILTIN_TOOLS 注册表
│   ├── checkpointer.py         # AsyncSqliteSaver 单例管理
│   ├── config.py               # 工作流配置管理（JSON/YAML 持久化）
│   ├── execution_log.py        # 全局日志系统 + LoggingCallbackHandler
│   ├── graph.py                # 工作流构建入口（build_workflow）
│   ├── message_converter.py    # OpenAI ↔ LangChain 消息格式转换
│   ├── schemas.py              # Pydantic 数据模型（ModelConfig/ToolConfig/AgentRun 等）
│   ├── server.py               # FastAPI 路由：模型/工具/提示词 CRUD、对话 API、流式 API
│   ├── storage.py              # JSON 文件持久化读写 + 路径常量
│   └── tool_factory.py         # 动态工具工厂（内置/HTTP/Echo 三类工具）
├── frontend/
│   └── index.html              # 单页前端（React + Babel）
├── scripts/
│   ├── start.ps1               # PowerShell 启动脚本
│   └── start.bat               # Batch 启动脚本
└── data/
    ├── models.json             # 模型配置（持久化存储）
    ├── tools.json              # 工具配置（持久化存储）
    ├── checkpoints.db          # SQLite 对话上下文数据库（自动生成）
    ├── checkpoints.db-shm      # SQLite 共享内存文件
    └── checkpoints.db-wal      # SQLite WAL 预写日志
```

## 快速开始（从 GitHub 克隆后首次使用）

### 1. 安装依赖

**Python 版本要求**: 3.10+

```powershell
# Windows 一键安装（自动创建 venv + 安装依赖 + 创建 data 目录）
.\setup.ps1
```

或手动安装：

```bash
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate   # Linux/Mac
pip install -r requirements.txt
mkdir data                  # 创建数据目录
```

### 2. 配置模型和 API Key

仓库不包含 API 密钥（`data/` 已 gitignore），首次使用需要配置：

**方式一：复制示例文件（推荐）**

```powershell
copy config.models.example.json data\models.json
copy config.tools.example.json data\tools.json
# 然后编辑 data\models.json，把 api_key 改成你自己的密钥
```

**方式二：启动后在页面中配置**

直接启动服务，在左侧「模型」标签页点击「新增」填写模型名称和 API Key。

### 3. 启动服务

```bash
python main.py
```

访问 **http://localhost:19527** 即可使用。

## 依赖清单

| 包名 | 版本要求 | 用途 |
|------|---------|------|
| `langgraph` | >=1.2.0 | Agent 工作流编排 |
| `langgraph-checkpoint-sqlite` | - | SQLite 对话上下文持久化（langgraph 内置） |
| `langchain-openai` | >=0.1.0 | OpenAI 兼容模型调用 |
| `langchain-core` | >=0.1.0 | LangChain 核心消息类型 |
| `fastapi` | >=0.100.0 | Web API 框架 |
| `uvicorn` | >=0.20.0 | ASGI 服务器 |
| `pydantic` | >=2.0 | 数据模型验证 |
| `httpx` | >=0.25.0 | HTTP 客户端 |
| `aiosqlite` | >=0.20.0 | 异步 SQLite 驱动（Checkpointer 需要） |
| `msgpack` | >=1.0 | Checkpoint 二进制序列化 |

## 启动服务

```bash
# 激活虚拟环境后
python main.py

# 或使用启动脚本
.\scripts\start.ps1
# .\scripts\start.bat
```

访问地址：**http://localhost:19527**

## 默认配置

### 模型配置（data/models.json）

| 名称 | 模型 | API 地址 |
|------|------|---------|
| `deepseek` | `deepseek-v4-pro` | `https://dashscope.aliyuncs.com/compatible-mode/v1` |

> 首次使用需在页面左侧「模型」标签页填入你的 API Key。

### 内置工具（builtin_tools.py）

| 工具名 | 函数名 | 别名 | 功能 |
|--------|--------|------|------|
| `search` | `search_web` | `search_web` | 模拟网页搜索 |
| `calculator` | `calculator` | - | 安全数学表达式计算 |
| `summarize` | `summarize` | - | 文本摘要 |
| `translate` | `translate` | - | 多语言翻译 |
| `sentiment` | `analyze_sentiment` | `analyze_sentiment` | 情感分析 |
| `weather` | `get_weather` | `get_weather` | 天气查询（8 个内置城市真实数据 + 随机模拟） |

### 工具配置（data/tools.json）

内置工具通过 `BUILTIN_TOOLS` 注册表直接加载，无需在 tools.json 中配置。
tools.json 用于管理自定义工具（HTTP API 工具等）。

可在页面左侧「工具」标签页新增、编辑、删除工具。支持三种工具类型：
- **内置工具**：名称匹配 BUILTIN_TOOLS 注册表 → 直接调用
- **HTTP 工具**：配置了 url 字段 → 通过 HTTP 请求调用外部 API
- **Echo 回退**：未匹配到内置工具且无 url → 原样返回参数

### 系统提示词

默认为「你是一个有用的AI助手。」，可在「提示词」标签页修改。

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| GET | `/api/models` | 获取模型列表 |
| POST | `/api/models` | 新增/更新模型 |
| DELETE | `/api/models/{name}` | 删除模型 |
| GET | `/api/tools` | 获取工具列表 |
| POST | `/api/tools` | 新增/更新工具 |
| DELETE | `/api/tools/{name}` | 删除工具 |
| GET | `/api/prompt` | 获取系统提示词 |
| POST | `/api/prompt` | 保存系统提示词 |
| POST | `/api/run` | 同步执行 Agent（返回完整结果） |
| POST | `/api/run-stream` | 流式执行 Agent（SSE 实时推送） |
| GET | `/api/conversations` | 历史对话列表 |
| GET | `/api/conversations/{id}` | 对话消息详情 |
| DELETE | `/api/conversations/{id}` | 删除对话 |
| GET | `/api/logs` | 获取最近执行日志 |

## 架构说明

### 模块拆分

原 `agent_setup.py`（499 行）和 `server.py`（809 行）已拆分为 11 个模块文件：

| 拆分前 | 拆分后 | 职责 |
|--------|--------|------|
| agent_setup.py | agent_setup.py | AgentState + create_agent_graph（仅 115 行） |
| agent_setup.py | checkpointer.py | AsyncSqliteSaver 单例 |
| agent_setup.py | execution_log.py | 全局日志 + LoggingCallbackHandler |
| agent_setup.py | builtin_tools.py | 6 个内置工具 + BUILTIN_TOOLS 注册表 |
| agent_setup.py | tool_factory.py | 动态工具工厂（内置/HTTP/Echo） |
| server.py | server.py | FastAPI 路由（仅 660 行） |
| server.py | schemas.py | Pydantic 数据模型 |
| server.py | storage.py | JSON 文件读写 + 路径常量 |
| server.py | message_converter.py | OpenAI ↔ LangChain 消息转换 |

### 数据流

```
前端 index.html (React)
    │  POST /api/run-stream
    ▼
server.py (FastAPI 子应用 /api)
    │  build_workflow(config)
    ▼
graph.py (工作流构建入口)
    │  create_agent_graph(...)
    ▼
agent_setup.py (Agent 核心组装)
    ├── tool_factory.py → builtin_tools.py (内置工具)
    ├── checkpointer.py → checkpoints.db (持久化)
    └── execution_log.py (日志回调)
```