"""
内置工具定义。
职责:
  1. 模拟工具函数（search/calculator/summarize/translate/sentiment/weather）
  2. 架构图工具 v2（get_architecture_template + generate_architecture_diagram_v2）
  3. BUILTIN_TOOLS 注册表（名称 → 函数映射）
"""
import random  # 用于非内置城市的随机模拟

from skills.architecture_diagram_v2.tool import (
    generate_architecture_diagram_v2,
    get_architecture_template,
)


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
    # ── 函数名别名 ──
    "search_web": search_web,
    "analyze_sentiment": analyze_sentiment,
    "get_weather": get_weather,
    # ── 架构图工具 v2 ──
    "get_architecture_template": get_architecture_template,       # 按需加载模板
    "generate_architecture_diagram_v2": generate_architecture_diagram_v2,  # 保存并预览
}