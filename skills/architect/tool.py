"""架构图渲染工具。生成自包含 HTML 文件，自动在浏览器中打开。"""
import json
import webbrowser
from pathlib import Path

MERMAID_CDN = "https://unpkg.com/mermaid@10/dist/mermaid.min.js"


def _render_html(mermaid_code: str, output_path: Path, title: str = "架构图") -> str:
    """生成自包含 HTML 文件，浏览器打开即可看到渲染后的架构图。"""
    escaped_code = mermaid_code.replace("`", "\\`").replace("${", "\\${")
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <script src="{MERMAID_CDN}"></script>
    <script>
        mermaid.initialize({{ startOnLoad: true, theme: 'default', securityLevel: 'loose' }});
    </script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f5f7fa;
            min-height: 100vh;
            padding: 30px;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            box-shadow: 0 2px 12px rgba(0,0,0,0.08);
            padding: 40px;
        }}
        h2 {{
            text-align: center;
            color: #1a1a2e;
            margin-bottom: 30px;
            font-size: 24px;
        }}
        .mermaid {{
            display: flex;
            justify-content: center;
            overflow-x: auto;
        }}
        .source {{
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #eee;
        }}
        .source summary {{
            cursor: pointer;
            color: #666;
            font-size: 13px;
        }}
        .source pre {{
            background: #f8f9fa;
            padding: 16px;
            border-radius: 8px;
            overflow-x: auto;
            font-size: 13px;
            margin-top: 10px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h2>{title}</h2>
        <div class="mermaid">
{escaped_code}
        </div>
        <details class="source">
            <summary>📋 查看 Mermaid 源码</summary>
            <pre>{escaped_code}</pre>
        </details>
    </div>
</body>
</html>"""
    output_path.write_text(html, encoding="utf-8")
    return str(output_path.absolute())


def _render(mermaid_code: str, output_name: str, fmt: str) -> str:
    """通用渲染函数：优先生成 HTML 文件，同时保存 .mmd 源文件。"""
    output_dir = Path("outputs")
    output_dir.mkdir(exist_ok=True)

    # 生成 HTML 文件（浏览器打开即可渲染）
    html_path = output_dir / f"{output_name}.html"
    html_path_str = _render_html(mermaid_code, html_path, output_name)

    # 同时保存 .mmd 源文件
    mmd_path = output_dir / f"{output_name}.mmd"
    mmd_path.write_text(mermaid_code, encoding="utf-8")

    # 自动在浏览器中打开生成的 HTML 文件
    try:
        webbrowser.open(f"file:///{html_path_str.replace(chr(92), '/')}")
    except Exception:
        pass

    return json.dumps({
        "status": "success",
        "renderer": "HTML (unpkg CDN)",
        "html_path": html_path_str,
        "mmd_path": str(mmd_path.absolute()),
        "type": "HTML 自渲染",
        "preview_url": f"/outputs/{html_path.name}",
        "usage": f"图表已自动打开，也可访问 /outputs/{html_path.name} 查看",
    }, ensure_ascii=False, indent=2)


def render_diagram(mermaid_code: str, output_name: str = "architecture") -> str:
    """
    将 Mermaid 代码渲染为 HTML 架构图，自动在浏览器中打开。
    同时保存 .mmd 源文件，可通过 /outputs/ 路径访问。
    """
    return _render(mermaid_code, output_name, "png")


def render_diagram_svg(mermaid_code: str, output_name: str = "architecture") -> str:
    """
    将 Mermaid 代码渲染为 HTML 架构图（SVG 矢量模式，可无损缩放）。
    """
    return _render(mermaid_code, output_name, "svg")