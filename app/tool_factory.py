"""
动态工具工厂。
职责:
  1. get_tools_from_config — 将前端配置转为可调用的工具对象列表
  2. 支持三类工具: 内置工具 / HTTP 工具 / Echo 回退工具
"""
import json

from typing import Any, Dict, List

from app.builtin_tools import BUILTIN_TOOLS
from app.execution_log import add_log


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