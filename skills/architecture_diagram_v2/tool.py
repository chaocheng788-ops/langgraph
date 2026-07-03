"""通用架构图生成工具 v2 - 接收LLM生成的完整HTML，仅负责存储和预览。"""
import json
import webbrowser
from pathlib import Path

OUTPUT_DIR = Path("outputs")


def generate_architecture_diagram_v2(
    user_request: str,
    html_content: str = "",
    title: str = "",
    output_name: str = "architecture",
) -> str:
    """
    生成架构图 HTML 文件。LLM 提供完整 HTML，工具负责存储和预览。

    Args:
        user_request: 用户原始需求描述
        html_content: LLM 生成的完整 HTML 字符串（含 DOCTYPE、html、head、body）
        title: 架构图标题，用于兜底模板
        output_name: 输出文件名，不含扩展名，默认 "architecture"

    Returns:
        JSON 字符串，包含 html_path、preview_url 和操作结果
    """
    OUTPUT_DIR.mkdir(exist_ok=True)

    # 如果 LLM 未传入合法 HTML，使用极简兜底模板
    if not html_content or not html_content.strip():
        html_content = _generate_fallback_html(title or "系统架构图")

    html_path = OUTPUT_DIR / f"{output_name}.html"
    html_path.write_text(html_content, encoding="utf-8")

    # 自动在浏览器中打开
    try:
        webbrowser.open(f"file:///{str(html_path.absolute()).replace(chr(92), '/')}")
    except Exception:
        pass

    return json.dumps({
        "status": "success",
        "html_path": str(html_path.absolute()),
        "preview_url": f"/outputs/{html_path.name}",
        "title": title or "架构图",
        "message": "架构图已生成，可在浏览器中查看或导出 PDF",
    }, ensure_ascii=False, indent=2)


def _generate_fallback_html(title: str) -> str:
    """生成极简兜底模板，当 LLM 未传入 HTML 时使用。"""
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
