"""架构图渲染工具 - 增强版（类 ChatGPT Canvas 效果）。
生成美观的自包含 HTML 文件，支持多主题切换、一键导出 PNG/SVG。
"""
import json
import webbrowser
from pathlib import Path

MERMAID_CDN = "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"
HTML2CANVAS_CDN = "https://cdn.jsdelivr.net/npm/html2canvas@1.0.0-alpha.12/dist/html2canvas.min.js"


# ============================================================
# 预设主题配置（类似 ChatGPT Canvas 风格）
# ============================================================

THEMES = {
    "modern": {
        "name": "现代简约",
        "theme": "base",
        "themeVariables": {
            "primaryColor": "#e3f2fd",
            "primaryTextColor": "#1a237e",
            "primaryBorderColor": "#1565c0",
            "lineColor": "#5c6bc0",
            "secondaryColor": "#f3e5f5",
            "tertiaryColor": "#fff3e0",
            "fontFamily": "'Inter', 'PingFang SC', 'Microsoft YaHei', sans-serif",
            "fontSize": "16px",
            "nodeBorderRadius": "8px",
            "edgeLabelBackground": "#ffffff",
            "clusterBkg": "#f5f7fa",
            "clusterBorder": "#d1d5db",
            "titleColor": "#1f2937",
            "edgeColor": "#6b7280",
            "mainBkg": "#ffffff",
            "secondBkg": "#f9fafb",
            "border1": "#d1d5db",
            "border2": "#9ca3af",
            "arrowheadColor": "#6b7280",
            "textColor": "#374151",
        },
        "flowchart": {
            "curve": "basis",
            "padding": 20,
            "nodeSpacing": 50,
            "rankSpacing": 80,
        },
    },
    "linear": {
        "name": "Linear 风格",
        "theme": "base",
        "themeVariables": {
            "primaryColor": "#f0f4ff",
            "primaryTextColor": "#1e293b",
            "primaryBorderColor": "#3b82f6",
            "lineColor": "#64748b",
            "secondaryColor": "#fef3c7",
            "tertiaryColor": "#dbeafe",
            "fontFamily": "'SF Pro Display', 'Inter', 'PingFang SC', sans-serif",
            "fontSize": "15px",
            "nodeBorderRadius": "6px",
            "edgeLabelBackground": "#ffffff",
            "clusterBkg": "#fafafa",
            "clusterBorder": "#e5e7eb",
            "titleColor": "#0f172a",
            "edgeColor": "#94a3b8",
            "mainBkg": "#ffffff",
            "secondBkg": "#f8fafc",
            "border1": "#e2e8f0",
            "border2": "#cbd5e1",
            "arrowheadColor": "#64748b",
            "textColor": "#334155",
        },
        "flowchart": {
            "curve": "catmullRom",
            "padding": 24,
            "nodeSpacing": 60,
            "rankSpacing": 90,
        },
    },
    "vercel": {
        "name": "Vercel 风格",
        "theme": "base",
        "themeVariables": {
            "primaryColor": "#fafafa",
            "primaryTextColor": "#000000",
            "primaryBorderColor": "#000000",
            "lineColor": "#666666",
            "secondaryColor": "#f5f5f5",
            "tertiaryColor": "#eeeeee",
            "fontFamily": "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
            "fontSize": "14px",
            "nodeBorderRadius": "4px",
            "edgeLabelBackground": "#ffffff",
            "clusterBkg": "#fafafa",
            "clusterBorder": "#eaeaea",
            "titleColor": "#000000",
            "edgeColor": "#888888",
            "mainBkg": "#ffffff",
            "secondBkg": "#fafafa",
            "border1": "#eaeaea",
            "border2": "#dcdcdc",
            "arrowheadColor": "#666666",
            "textColor": "#444444",
        },
        "flowchart": {
            "curve": "linear",
            "padding": 20,
            "nodeSpacing": 50,
            "rankSpacing": 70,
        },
    },
    "dark": {
        "name": "深色模式",
        "theme": "dark",
        "themeVariables": {
            "primaryColor": "#1e293b",
            "primaryTextColor": "#f1f5f9",
            "primaryBorderColor": "#475569",
            "lineColor": "#94a3b8",
            "secondaryColor": "#334155",
            "tertiaryColor": "#1e293b",
            "fontFamily": "'Inter', 'PingFang SC', sans-serif",
            "fontSize": "16px",
            "nodeBorderRadius": "8px",
            "edgeLabelBackground": "#0f172a",
            "clusterBkg": "#0f172a",
            "clusterBorder": "#334155",
            "titleColor": "#f8fafc",
            "edgeColor": "#64748b",
            "mainBkg": "#1e293b",
            "secondBkg": "#0f172a",
            "border1": "#334155",
            "border2": "#475569",
            "arrowheadColor": "#94a3b8",
            "textColor": "#e2e8f0",
        },
        "flowchart": {
            "curve": "basis",
            "padding": 20,
            "nodeSpacing": 50,
            "rankSpacing": 80,
        },
    },
}


def _get_theme_config(theme_name: str = "modern") -> dict:
    """获取主题配置，无效名称时回退到 modern。"""
    return THEMES.get(theme_name, THEMES["modern"])


def _render_html(
    mermaid_code: str,
    output_path: Path,
    title: str = "架构图",
    theme_name: str = "modern",
    enable_export: bool = True,
) -> str:
    """生成自包含 HTML 文件，支持 Beautiful-Mermaid 风格和高质量导出。"""
    theme_config = _get_theme_config(theme_name)
    escaped_code = mermaid_code.replace("`", "\\`").replace("${", "\\${")

    # 构建 Mermaid 初始化配置
    theme_vars_json = json.dumps(theme_config["themeVariables"], ensure_ascii=False)
    flowchart_json = json.dumps(theme_config["flowchart"], ensure_ascii=False)

    # 导出功能脚本
    export_script = ""
    if enable_export:
        export_script = f"""
        <script src="{HTML2CANVAS_CDN}"></script>
        <script>
            async function exportAsPNG() {{
                const element = document.getElementById('diagram-container');
                try {{
                    const canvas = await html2canvas(element, {{
                        scale: 3,
                        backgroundColor: '#ffffff',
                        useCORS: true,
                        logging: false
                    }});
                    const link = document.createElement('a');
                    link.download = '{title}.png';
                    link.href = canvas.toDataURL('image/png', 1.0);
                    link.click();
                }} catch (err) {{
                    alert('导出失败: ' + err.message);
                }}
            }}

            async function exportAsSVG() {{
                const svgElement = document.querySelector('.mermaid svg');
                if (!svgElement) {{
                    alert('未找到 SVG 元素');
                    return;
                }}
                const svgData = new XMLSerializer().serializeToString(svgElement);
                const blob = new Blob([svgData], {{ type: 'image/svg+xml;charset=utf-8' }});
                const url = URL.createObjectURL(blob);
                const link = document.createElement('a');
                link.download = '{title}.svg';
                link.href = url;
                link.click();
                URL.revokeObjectURL(url);
            }}
        </script>
        """

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <script src="{MERMAID_CDN}"></script>
    {export_script}
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'PingFang SC', 'Microsoft YaHei', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 40px 20px;
        }}
        .container {{
            max-width: 1600px;
            margin: 0 auto;
            background: white;
            border-radius: 16px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.15), 0 0 0 1px rgba(255,255,255,0.1);
            overflow: hidden;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px 40px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 16px;
        }}
        .header h2 {{
            font-size: 28px;
            font-weight: 600;
            letter-spacing: -0.5px;
        }}
        .actions {{
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
        }}
        .btn {{
            padding: 10px 20px;
            border: none;
            border-radius: 8px;
            background: rgba(255,255,255,0.2);
            color: white;
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
            backdrop-filter: blur(10px);
        }}
        .btn:hover {{
            background: rgba(255,255,255,0.3);
            transform: translateY(-1px);
        }}
        .btn:active {{
            transform: translateY(0);
        }}
        .content {{
            padding: 40px;
        }}
        #diagram-container {{
            background: #fafafa;
            border-radius: 12px;
            padding: 40px;
            box-shadow: inset 0 2px 4px rgba(0,0,0,0.06);
        }}
        .mermaid {{
            display: flex;
            justify-content: center;
            overflow-x: auto;
        }}
        .mermaid svg {{
            max-width: 100%;
            height: auto;
        }}
        .source {{
            margin-top: 30px;
            padding-top: 20px;
            border-top: 2px solid #e5e7eb;
        }}
        .source summary {{
            cursor: pointer;
            color: #6b7280;
            font-size: 14px;
            font-weight: 500;
            user-select: none;
        }}
        .source summary:hover {{
            color: #374151;
        }}
        .source pre {{
            background: #f9fafb;
            padding: 20px;
            border-radius: 8px;
            overflow-x: auto;
            font-size: 13px;
            line-height: 1.6;
            margin-top: 12px;
            border: 1px solid #e5e7eb;
        }}
        .info {{
            margin-top: 20px;
            padding: 16px;
            background: #eff6ff;
            border-left: 4px solid #3b82f6;
            border-radius: 6px;
            font-size: 14px;
            color: #1e40af;
        }}
        .theme-badge {{
            display: inline-block;
            padding: 4px 12px;
            background: rgba(255,255,255,0.25);
            border-radius: 20px;
            font-size: 12px;
            font-weight: 500;
            margin-left: 12px;
            backdrop-filter: blur(10px);
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2>{title}<span class="theme-badge">{theme_name}</span></h2>
            <div class="actions">
                <button class="btn" onclick="exportAsPNG()">📥 导出 PNG</button>
                <button class="btn" onclick="exportAsSVG()">📥 导出 SVG</button>
            </div>
        </div>
        <div class="content">
            <div id="diagram-container">
                <div class="mermaid">
{escaped_code}
                </div>
            </div>
            <details class="source">
                <summary>📋 查看 Mermaid 源码</summary>
                <pre>{escaped_code}</pre>
            </details>
            <div class="info">
                💡 提示：点击顶部按钮可导出 PNG（3x 高清）或 SVG（矢量无损）格式图片
            </div>
        </div>
    </div>
    <script>
        mermaid.initialize({{
            startOnLoad: true,
            theme: '{theme_config["theme"]}',
            securityLevel: 'loose',
            themeVariables: {theme_vars_json},
            flowchart: {flowchart_json}
        }});
    </script>
</body>
</html>"""
    output_path.write_text(html, encoding="utf-8")
    return str(output_path.absolute())


def _render(
    mermaid_code: str,
    output_name: str,
    fmt: str = "html",
    theme_name: str = "modern",
    enable_export: bool = True,
) -> str:
    """通用渲染函数：生成美观的 HTML 文件，同时保存 .mmd 源文件。"""
    output_dir = Path("outputs")
    output_dir.mkdir(exist_ok=True)

    # 生成 HTML 文件（浏览器打开即可渲染）
    html_path = output_dir / f"{output_name}.html"
    html_path_str = _render_html(
        mermaid_code, html_path, output_name, theme_name, enable_export
    )

    # 同时保存 .mmd 源文件
    mmd_path = output_dir / f"{output_name}.mmd"
    mmd_path.write_text(mermaid_code, encoding="utf-8")

    # 自动在浏览器中打开生成的 HTML 文件
    try:
        webbrowser.open(f"file:///{html_path_str.replace(chr(92), '/')}")
    except Exception:
        pass

    return json.dumps(
        {
            "status": "success",
            "renderer": "HTML (Enhanced with Beautiful-Mermaid)",
            "theme": theme_name,
            "html_path": html_path_str,
            "mmd_path": str(mmd_path.absolute()),
            "type": "HTML 自渲染（增强版）",
            "preview_url": f"/outputs/{html_path.name}",
            "features": ["Beautiful-Mermaid 主题", "一键导出 PNG/SVG", "高分辨率渲染"],
            "usage": f"图表已自动打开，也可访问 /outputs/{html_path.name} 查看",
        },
        ensure_ascii=False,
        indent=2,
    )


def render_diagram(
    mermaid_code: str,
    output_name: str = "architecture",
    theme: str = "modern",
) -> str:
    """
    将 Mermaid 代码渲染为美观的 HTML 架构图（类 ChatGPT Canvas 效果）。

    Args:
        mermaid_code: Mermaid 图表代码
        output_name: 输出文件名（不含扩展名）
        theme: 主题名称，可选值：modern, linear, vercel, dark

    Returns:
        JSON 字符串，包含文件路径和功能说明
    """
    return _render(mermaid_code, output_name, "html", theme, enable_export=True)


def render_diagram_svg(
    mermaid_code: str,
    output_name: str = "architecture",
    theme: str = "modern",
) -> str:
    """
    将 Mermaid 代码渲染为 HTML 架构图（SVG 矢量模式，可无损缩放）。

    Args:
        mermaid_code: Mermaid 图表代码
        output_name: 输出文件名（不含扩展名）
        theme: 主题名称，可选值：modern, linear, vercel, dark

    Returns:
        JSON 字符串，包含文件路径和功能说明
    """
    return _render(mermaid_code, output_name, "svg", theme, enable_export=True)