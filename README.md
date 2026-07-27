# LangGraph Agent Platform

基于 LangGraph + FastAPI 的 AI Agent 可视化编排平台，支持流式对话、工具调用、多轮历史持久化、本地 RAG 知识库。

## 功能特性

- **可视化前端**：模型配置、工具管理、提示词编辑、实时对话
- **流式交互**：SSE 实时推送日志和 AI 响应，逐条展示
- **Skill 路由**：内置 2 个 Skill（架构图生成、知识库 RAG），支持 Function Calling 自动路由
- **RAG 知识库**：基于 FAISS + SQLite 的本地向量检索，支持 Markdown 文档智能切分入库、语义搜索
- **动态工具**：支持 HTTP API 工具配置，Echo 回退工具兜底
- **架构图生成**：自然语言描述 → HTML 架构图，自动浏览器打开，支持 /outputs/ 静态访问
- **多轮对话**：基于 SQLite + AsyncSqliteSaver 持久化上下文，跨请求保持会话
- **历史管理**：右上角下拉面板查看/加载/删除历史对话
- **日志抽屉**：可拖拽调整宽度，查看模型请求/响应、工具调用/返回详情
- **模块化架构**：app/ 拆分为多个模块文件，职责清晰、易于维护

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
├── skills/                     # Skill 插件目录
│   ├── architecture_diagram_v2/ # 架构图生成 Skill
│   │   ├── prompt.md           # 技能提示词
│   │   ├── tools.json          # 工具声明
│   │   ├── tool.py             # 工具实现
│   │   └── templates/          # HTML 模板
│   └── knowledge_base/         # RAG 知识库 Skill
│       ├── prompt.md           # 技能提示词
│       ├── tools.json          # 工具声明（add_knowledge / search_knowledge）
│       └── tool.py             # FAISS + SQLite + Embedding + 工具实现
├── outputs/                    # 架构图等生成文件（HTML + .mmd）
├── scripts/
│   ├── start.ps1               # PowerShell 启动脚本
│   └── start.bat               # Batch 启动脚本
├── data/
    ├── models.json             # 模型配置（持久化存储）
    ├── tools.json              # 工具配置（持久化存储）
    ├── prompt.json             # 系统提示词（持久化存储）
    ├── skills.json             # 前端创建的技能（持久化存储）
    ├── knowledge.db            # 知识库 SQLite 元数据（自动生成）
    ├── knowledge.index         # 知识库 FAISS 向量索引（自动生成）
    ├── checkpoints.db          # SQLite 对话上下文数据库（自动生成）
    ├── checkpoints.db-shm      # SQLite 共享内存文件
    └── checkpoints.db-wal      # SQLite WAL 预写日志
```

## 快速开始（从 GitHub 克隆后首次使用）

### 1. 安装依赖

**Python 版本要求**: 3.14（faiss-cpu 预编译包兼容性，建议使用 3.14）

> 注意：Windows 用户需安装 [Visual C++ Redistributable](https://aka.ms/vs/17/release/vc_redist.x64.exe)，否则 faiss-cpu 会报"动态链接库初始化失败"。

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
| `faiss-cpu` | >=1.8.0 | FAISS 向量索引（知识库 RAG 检索） |
| `sentence-transformers` | >=3.0.0 | 文本 Embedding 模型（bge-small-zh-v1.5） |

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

### 内置 Skill（skills/ 目录）

Skill 支持路由模式：路由 LLM 根据用户意图自动选择最合适的 Skill 加载。

| Skill | 工具函数 | 功能 |
|--------|---------|------|
| `architecture_diagram_v2` | `get_architecture_template`, `generate_architecture_diagram_v2` | 架构图生成：自然语言 → HTML 架构图，自动浏览器打开 |
| `knowledge_base` | `add_knowledge`, `search_knowledge` | RAG 知识库：FAISS 向量检索 + SQLite 元数据，支持 Markdown 文档智能切分 |

### 内置工具（builtin_tools.py）

| 工具名 | 函数名 | 别名 | 功能 |
|--------|--------|------|------|
| `search` | `search_web` | `search_web` | 模拟网页搜索 |
| `calculator` | `calculator` | - | 安全数学表达式计算 |
| `summarize` | `summarize` | - | 文本摘要 |
| `translate` | `translate` | - | 多语言翻译 |
| `sentiment` | `analyze_sentiment` | `analyze_sentiment` | 情感分析 |
| `weather` | `get_weather` | `get_weather` | 天气查询 |
| `get_architecture_template` | `get_architecture_template` | - | 按需加载架构图 HTML 模板 |
| `generate_architecture_diagram_v2` | `generate_architecture_diagram_v2` | - | 生成并保存架构图 HTML |
| `add_knowledge` | `add_knowledge` | - | 文档入库：切分 → Embedding → FAISS + SQLite |
| `search_knowledge` | `search_knowledge` | - | 语义搜索：Embedding → FAISS 检索 → SQLite 查原文 |

### 知识库 RAG（skills/knowledge_base/）

基于 FAISS + SQLite 的本地向量检索知识库，完全自包含在 skill 目录内。

#### 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| Embedding 模型 | `BAAI/bge-small-zh-v1.5` | 智源中文语义模型，512 维，2400 万参数，~100MB |
| 推理引擎 | `sentence-transformers` | 加载模型 + `model.encode()` 一键转换文本→向量 |
| 向量索引 | FAISS `IndexFlatIP` | 内积精确搜索（归一化后等价于余弦相似度） |
| 元数据存储 | SQLite | 文档标题、原文、来源、时间戳 |
| 文本切分 | Markdown 感知切分 | 按 `#` 标题分节，每节内 ≤500 字 |

#### 核心流程

```
入库: add_knowledge → Markdown 切分 → bge Embedding → SQLite + FAISS 双写
检索: search_knowledge → bge Embedding → FAISS 内积搜索 → SQLite 查原文
```

#### Embedding 模型原理

```
文本 "迟到几次算旷工？"
  → bge-small-zh-v1.5（12层 Transformer，2400万参数）
  → 512 维向量 [0.08, 0.92, -0.34, 0.17, ...]
  → L2 归一化（向量长度 = 1）
  → 内积 = 余弦相似度（0~1，越接近 1 越相似）
```

> 模型越大 → 向量维度越多 → 区分能力越强。bge-small（512维）适合主题差异明显的文档；
bge-large（1024维）适合需要区分细微差异的场景。

#### FAISS 匹配逻辑

FAISS 是一个**向量搜索引擎库**（非数据库），只负责"找相似"，不存原文：
- `knowledge.index`：FAISS 二进制索引文件，存向量数字 + id 映射
- `knowledge.db`：SQLite 数据库，存原文 + 元数据
- 搜索时 FAISS 返回 id → SQLite 查原文，两者通过 id 关联

```
相似度: 查询向量·文档向量 = 内积值
0.9-1.0 → 高度相关  0.7-0.9 → 比较相关
0.5-0.7 → 有一定关联  0.5以下 → 基本不相关
```

> 和关键词搜索的区别：搜"旷工"也能匹配"缺勤""未到岗"等语义相近的表述。

#### 数据存储

| 文件 | 类型 | 存什么 | 读取方式 |
|------|------|--------|---------|
| `knowledge.index` | FAISS 二进制 | 向量数字 + id 映射 | `faiss.read_index()` |
| `knowledge.db` | SQLite 数据库 | 原文 + 标题 + 来源 | `sqlite3.connect()` |

> SQLite 理论上限 281TB，FAISS 在 10 万条以内用 Flat 索引毫秒级搜索。

#### Embedding 模型 vs 对话模型

| | Embedding 模型 | 对话模型（LLM） |
|------|------|------|
| 做什么 | 文本 → 向量 | 文本 → 文本 |
| 本项目用 | `bge-small-zh-v1.5` | `deepseek-v4-pro` |
| 输出 | 512个数字 | 自然语言回答 |
| 运行方式 | 本地免费 | 调 API 付费 |

> DeepSeek 对话模型暂不支持 Embedding。如需改用 API 形式（如阿里云 text-embedding-v3），
> 只需替换 `_get_model()` 和 `model.encode()` 两个调用点，FAISS + SQLite 逻辑完全不变。

#### 使用方式
1. 前端左侧「技能」标签页开启 `knowledge_base`
2. 对话中输入 `把以下内容加入知识库，标题：xxx` 即可入库
3. 提问时 Agent 自动调用 `search_knowledge` 检索并基于结果回答

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
| GET | `/api/skills` | 获取技能列表 |
| POST | `/api/skills` | 新增/更新技能 |
| DELETE | `/api/skills/{name}` | 删除技能 |
| GET | `/api/prompt` | 获取系统提示词 |
| POST | `/api/prompt` | 保存系统提示词 |
| POST | `/api/run` | 同步执行 Agent（返回完整结果） |
| POST | `/api/run-stream` | 流式执行 Agent（SSE 实时推送） |
| GET | `/api/conversations` | 历史对话列表 |
| GET | `/api/conversations/{id}` | 对话消息详情 |
| DELETE | `/api/conversations/{id}` | 删除对话 |
| GET | `/api/logs` | 获取最近执行日志 |

## 架构说明

### Skill 路由架构

项目采用 **Skill-as-Tool 路由模式**，实现技能自动发现和动态绑定：

```
用户输入 → Skill Router（LLM Function Calling）
    │
    ├─ 每个 Skill 生成一个 meta-tool（name=use_skill__xxx）
    ├─ LLM 通过 tool_calls 选择最匹配的技能
    └─ 解析选中的技能名 → 加载对应工具 + 注入专属提示词
```

**技能来源**（两套体系，合并使用）：
- `skills/` 目录：文件定义的技能（prompt.md + YAML Front Matter + tools.json + tool.py）
- `data/skills.json`：前端 API 创建的技能

**路由策略**：
- 首次对话：LLM Function Calling 自动发现
- 后续轮次：复用已选技能，不重复路由
- Fallback：LLM 不可用时，基于关键词匹配路由

### 工具注册架构（三层分离）

```
skills/{name}/tool.py     ← 工具实现（Python 函数）
skills/{name}/tools.json  ← 工具声明（接口描述）
app/builtin_tools.py      ← 注册中心（import 并注册到 BUILTIN_TOOLS 字典）
app/tool_factory.py       ← 查找入口（按名称匹配 BUILTIN_TOOLS/HTTP/Echo）
```

支持三种工具类型：
- **内置工具**：名称匹配 BUILTIN_TOOLS 注册表 → 直接调用函数
- **HTTP 工具**：配置了 url 字段 → 通过 HTTP 请求调用外部 API
- **Echo 回退**：未匹配到内置工具且无 url → 原样返回参数

### Skill 提示词机制

每个 Skill 的 `prompt.md` 包含 YAML Front Matter（元数据）和 Markdown 正文（专属提示词）：

```
---
name: knowledge_base
description: 知识库检索与问答
keywords: [知识库, 文档, 搜索]
---

# 一、技能权责
你是一个知识库助手...
```

路由选中后，正文作为 SystemMessage 注入到 Agent 上下文，指导 LLM 调用哪些工具、如何回答。

### 工作流编排（graph.py）

```
START → route（技能发现）→ agent（动态绑定工具执行）→ END
          │
          ├─ 首次对话: LLM Function Calling 选择技能
          └─ 后续轮次: 复用已选技能
                       │
                       ▼
              agent_node: 根据 selected_skills 动态创建 ReAct Agent
                         仅绑定选中技能的工具（不再全部绑定）
```

### 执行日志与流式推送

`execution_log.py` 提供全局日志系统，所有模块通过 `add_log()` 记录：
- 模型请求/响应详情
- 工具调用参数和返回值
- 技能发现过程
- 错误信息

`server.py` 通过 SSE（Server-Sent Events）实时推送日志和 AI 响应到前端。

### 多轮对话持久化

`checkpointer.py` 基于 `AsyncSqliteSaver` 实现对话上下文持久化：
- 存储到 `data/checkpoints.db`
- 单例模式，全局复用数据库连接
- 跨请求保持会话状态（selected_skills、messages 等）

### 消息格式转换

`message_converter.py` 负责 OpenAI 格式 ↔ LangChain 格式互转：
- OpenAI 角色（system/user/assistant/tool）映射到 LangChain 消息类
- 处理 tool_calls、tool_call_id、reasoning_content 等字段

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
前端 index.html (React + Babel)
    │  POST /api/run-stream
    ▼
server.py (FastAPI 子应用 /api)
    │  build_workflow(config)
    ▼
graph.py (工作流编排入口)
    ├── route_node: skill_router.py → LLM Function Calling 选择技能
    └── agent_node: create_agent_graph() → 动态绑定选中技能的工具
         │
         ▼
agent_setup.py (Agent 核心组装)
    ├── tool_factory.py → builtin_tools.py (内置工具)
    ├── skill_router.py → skills/ 目录 (技能加载)
    ├── checkpointer.py → checkpoints.db (持久化)
    └── execution_log.py → SSE 推送 (日志回调)
```