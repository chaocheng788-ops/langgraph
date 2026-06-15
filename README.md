# LangGraph Agent Platform

基于 LangGraph + FastAPI 的 AI Agent 可视化编排平台，支持流式对话、工具调用、多轮历史持久化。

## 功能特性

- **可视化前端**：模型配置、工具管理、提示词编辑、实时对话
- **流式交互**：SSE 实时推送日志和 AI 响应，逐条展示
- **工具调用**：支持自定义工具（内置天气查询示例），日志中展示完整调用链路
- **多轮对话**：基于 SQLite + AsyncSqliteSaver 持久化上下文，跨请求保持会话
- **历史管理**：右上角下拉面板查看/加载/删除历史对话
- **日志抽屉**：可拖拽调整宽度，查看模型请求/响应、工具调用/返回详情

## 目录结构

```
langgraph/
├── main.py                 # 入口，启动 FastAPI + 挂载前端静态文件
├── requirements.txt        # Python 依赖
├── setup.ps1               # Windows 一键安装脚本
├── .env                    # 环境变量配置
├── langgraph.json          # LangGraph CLI 配置
├── config.models.example.json  # 模型配置模板（复制到 data/models.json）
├── config.tools.example.json   # 工具配置模板（复制到 data/tools.json）
├── app/
│   ├── agent_setup.py      # Agent 核心：模型初始化、工具注册、checkpointer、回调
│   ├── server.py           # FastAPI 路由：模型/工具/提示词 CRUD、对话 API、流式 API
│   ├── graph.py            # 工作流构建入口
│   └── config.py           # 配置管理
├── frontend/
│   └── index.html          # 单页前端（React + Babel）
├── scripts/
│   ├── start.ps1           # PowerShell 启动脚本
│   └── start.bat           # Batch 启动脚本
└── data/
    ├── models.json         # 模型配置（持久化存储）
    ├── tools.json          # 工具配置（持久化存储）
    └── checkpoints.db      # SQLite 对话上下文数据库（自动生成）
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
| `ds` | `deepseek-v4-pro` | `https://dashscope.aliyuncs.com/compatible-mode/v1` |

> 首次使用需在页面左侧「模型」标签页填入你的 API Key。

### 工具配置（data/tools.json）

内置一个天气查询示例工具：

```json
{
  "name": "weather",
  "description": "传入城市名字可查天气，如北京，传入北京",
  "parameters": [
    {
      "name": "query",
      "type": "string",
      "required": true
    }
  ]
}
```

可在页面左侧「工具」标签页新增、编辑、删除工具。

### 系统提示词

默认为「你是一个有用的AI助手。」，可在「提示词」标签页修改。

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/models` | 获取模型列表 |
| POST | `/api/models` | 新增/更新模型 |
| DELETE | `/api/models/{name}` | 删除模型 |
| GET | `/api/tools` | 获取工具列表 |
| POST | `/api/tools` | 新增/更新工具 |
| DELETE | `/api/tools/{name}` | 删除工具 |
| GET | `/api/prompt` | 获取系统提示词 |
| POST | `/api/prompt` | 保存系统提示词 |
| POST | `/api/run-stream` | 流式执行 Agent（SSE） |
| GET | `/api/conversations` | 历史对话列表 |
| GET | `/api/conversations/{id}` | 对话消息详情 |
| DELETE | `/api/conversations/{id}` | 删除对话 |
| GET | `/api/logs` | 获取最近执行日志 |