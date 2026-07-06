"""通用架构图生成工具 v2 - 接收 LLM 生成的完整 HTML，仅负责存储和预览。"""
import json
import webbrowser
from pathlib import Path

# ═══════════════════════════════════════════════════════════════
# 路径常量 — 输出目录 + 模板目录
# ═══════════════════════════════════════════════════════════════

OUTPUT_DIR = Path("outputs")                              # HTML 文件输出目录
TEMPLATE_DIR = Path(__file__).parent / "templates"         # 模板文件存放目录

# ═══════════════════════════════════════════════════════════════
# 模板名称 → 文件名映射表
# 新增模板时只需在此字典添加映射 + templates/ 目录放入对应 HTML 文件
# ═══════════════════════════════════════════════════════════════

TEMPLATE_FILES = {
    "product_arch": "product_arch.html",      # 四层产品架构（Flex 纵向）
    "microservice": "microservice.html",      # 微服务网格（Grid 布局）
    "topology": "topology.html",              # 分布式拓扑（绝对定位 + 连线）
}


# ═══════════════════════════════════════════════════════════════
# get_architecture_template — 按需加载模板，供 LLM 参考后定制修改
# ═══════════════════════════════════════════════════════════════

def get_architecture_template(template_name: str) -> str:
    """
    按需加载架构图 HTML 模板，返回完整 HTML 字符串供 LLM 参考和定制修改。

    调用时机：LLM 在生成架构图 HTML 之前，先调用此工具获取适合场景的模板。
    优势：模板只在实际需要时才加载到上下文，避免每次请求都消耗全部模板 token。

    Args:
        template_name: 模板名称，可选 product_arch / microservice / topology

    Returns:
        完整 HTML 模板字符串（LLM 可基于此模板按用户需求替换模块名称、增删层级、调整配色）
        若模板名不合法或文件不存在，返回 JSON 格式的错误信息
    """
    # ── 校验模板名合法性 ──
    filename = TEMPLATE_FILES.get(template_name)
    if not filename:
        return json.dumps({
            "error": f"未知模板: {template_name}",
            "available": list(TEMPLATE_FILES.keys()),       # 返回可用模板列表，方便 LLM 纠正
        }, ensure_ascii=False, indent=2)

    # ── 校验模板文件是否存在 ──
    template_path = TEMPLATE_DIR / filename
    if not template_path.exists():
        return json.dumps({
            "error": f"模板文件不存在: {filename}",
        }, ensure_ascii=False, indent=2)

    # ── 读取并返回模板内容（UTF-8 编码，保留中文） ──
    return template_path.read_text(encoding="utf-8")


# ═══════════════════════════════════════════════════════════════
# generate_architecture_diagram_v2 — 接收 HTML 并写入文件 + 预览
# ═══════════════════════════════════════════════════════════════

def generate_architecture_diagram_v2(
    user_request: str,                 # 用户原始需求描述
    html_content: str = "",            # LLM 生成的完整 HTML 字符串
    title: str = "",                   # 架构图标题，用于兜底模板
    output_name: str = "architecture", # 输出文件名（不含扩展名）
) -> str:
    """
    生成架构图 HTML 文件。LLM 提供完整 HTML，工具负责存储和预览。

    调用时机：LLM 完成 HTML 定制后，调用此工具将 HTML 写入本地文件并触发预览。
    注意：LLM 必须先调用 get_architecture_template 获取模板，基于模板定制后再调用此工具。

    Args:
        user_request: 用户原始需求描述，如 "绘制微信宏观产品架构图"
        html_content: LLM 生成的完整 HTML 文档字符串（含 <!DOCTYPE html>、<html>、<head>、<body>）
        title: 架构图标题，当 html_content 为空时用于生成兜底模板
        output_name: 输出文件名，不含扩展名，默认 "architecture"

    Returns:
        JSON 字符串，包含 status/html_path/preview_url/title/message
        前端通过 preview_url 字段自动渲染 iframe 预览
    """
    # ── 确保输出目录存在 ──
    OUTPUT_DIR.mkdir(exist_ok=True)

    # ── 兜底机制：LLM 未传入合法 HTML 时使用极简模板 ──
    if not html_content or not html_content.strip():
        html_content = _generate_fallback_html(title or "系统架构图")

    # ── 写入 HTML 文件 ──
    html_path = OUTPUT_DIR / f"{output_name}.html"
    html_path.write_text(html_content, encoding="utf-8")

    # ── 尝试自动打开浏览器预览（非关键路径，失败静默忽略） ──
    try:
        webbrowser.open(f"file:///{str(html_path.absolute()).replace(chr(92), '/')}")
    except Exception:
        pass

    # ── 返回结果 JSON（前端通过 preview_url 渲染 iframe） ──
    return json.dumps({
        "status": "success",
        "html_path": str(html_path.absolute()),              # 文件绝对路径
        "preview_url": f"/outputs/{html_path.name}",         # 前端 iframe 预览 URL
        "title": title or "架构图",
        "message": "架构图已生成，可在浏览器中查看或导出 PDF",
    }, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════════════════════════
# _generate_fallback_html — 极简兜底模板（私有函数）
# ═══════════════════════════════════════════════════════════════

def _generate_fallback_html(title: str) -> str:
    """
    生成极简兜底模板，当 LLM 未传入 HTML 时使用。

    设计意图：确保工具在任何情况下都不会崩溃，至少返回一个可渲染的页面。
    正常情况下不应该走到这里——LLM 应当在 prompt.md 指导下生成完整 HTML。

    Args:
        title: 页面标题

    Returns:
        极简 HTML 字符串，仅包含标题和提示文字
    """
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        * {{ margin:0; padding:0; box-sizing:border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Microsoft YaHei', sans-serif;
            background: #f5f6fa; min-height: 100vh; padding: 40px 20px;
        }}
        .container {{ max-width: 1400px; margin:0 auto; text-align: center; }}
        h1 {{ color: #1a1a2e; margin-bottom: 20px; }}
        p {{ color: #666; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{title}</h1>
        <p>此为兜底模板，请确保 LLM 传入完整的 HTML 内容以生成精美架构图。</p>
    </div>
</body>
</html>"""