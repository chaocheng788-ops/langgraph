"""
Pydantic 数据模型。
职责:
  1. 定义所有请求/响应的数据结构和默认值
  2. 模型配置、工具配置、提示词配置、消息格式、Agent 执行请求体
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel  # 请求/响应数据模型


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