"""通用架构图生成工具 - 纯 HTML+CSS 四层分层架构图渲染。"""
import json
import webbrowser
from pathlib import Path

OUTPUT_DIR = Path("outputs")

# 四层标准配色
LAYER_COLORS = {
    "terminal":   {"bg": "#e8f5e9", "border": "#81c784", "title": "#2e7d32", "label": "终端/接入层"},
    "business":   {"bg": "#e3f2fd", "border": "#64b5f6", "title": "#1565c0", "label": "核心业务/应用层"},
    "middleware": {"bg": "#f3e5f5", "border": "#ba68c8", "title": "#7b1fa2", "label": "公共中台/能力层"},
    "infrastructure": {"bg": "#fff3e0", "border": "#ffb74d", "title": "#e65100", "label": "基础技术/底座层"},
}


def _build_html(title: str, layers: list) -> str:
    """构建完整的 HTML 架构图。"""
    layer_html = ""
    for layer in layers:
        color = LAYER_COLORS.get(layer.get("key", ""), LAYER_COLORS["terminal"])
        cards = ""
        for mod in layer.get("modules", []):
            name = mod.get("name", "")
            desc = mod.get("desc", "")
            cards += f"""
                <div class="card">
                    <div class="card-title">{name}</div>
                    <div class="card-desc">{desc}</div>
                </div>"""
        layer_html += f"""
        <div class="layer" style="background:{color['bg']};border-color:{color['border']}">
            <div class="layer-title" style="color:{color['title']}">{color['label']}</div>
            <div class="cards">{cards}</div>
        </div>"""

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
        .container {{ max-width: 1400px; margin:0 auto; }}
        .main-title {{
            text-align: center; font-size: 32px; font-weight: 700; color: #1a1a2e;
            margin-bottom: 40px; letter-spacing: 2px;
        }}
        .layer {{
            border-radius: 12px; border: 2px solid; padding: 24px; margin-bottom: 24px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        }}
        .layer-title {{
            font-size: 18px; font-weight: 700; margin-bottom: 16px;
            padding-bottom: 8px; border-bottom: 1px solid rgba(0,0,0,0.1);
        }}
        .cards {{ display: flex; flex-wrap: wrap; gap: 12px; }}
        .card {{
            flex: 1 1 200px; min-width: 160px; max-width: 280px;
            background: #fff; border-radius: 8px; padding: 16px;
            box-shadow: 0 1px 4px rgba(0,0,0,0.08);
        }}
        .card-title {{ font-size: 15px; font-weight: 600; color: #333; margin-bottom: 4px; }}
        .card-desc {{ font-size: 12px; color: #999; line-height: 1.5; }}
        .footer-note {{
            text-align: center; margin-top: 40px; font-size: 12px; color: #aaa;
        }}
        .export-bar {{
            display: flex; justify-content: flex-end; gap: 12px; margin-bottom: 20px;
        }}
        .btn {{
            padding: 8px 20px; border: none; border-radius: 6px; font-size: 14px;
            cursor: pointer; background: #1a1a2e; color: #fff; transition: 0.2s;
        }}
        .btn:hover {{ background: #333; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="export-bar">
            <button class="btn" onclick="window.print()">打印 / 导出 PDF</button>
        </div>
        <div class="main-title">{title}</div>
        {layer_html}
        <div class="footer-note">基于公开行业信息梳理的通用宏观架构</div>
    </div>
</body>
</html>"""


def generate_architecture_diagram(
    user_request: str,
    layers_json: str = "",
    title: str = "",
    output_name: str = "architecture",
) -> str:
    """
    生成通用分层架构图 HTML 文件。自动按四层标准架构（终端层→业务层→中台层→底座层）拆解目标系统。

    Args:
        user_request: 目标系统描述，包含系统名称、主要模块、功能场景等
        layers_json: JSON 字符串，定义四层架构的模块结构，格式:
            [{"key":"terminal","modules":[{"name":"Web","desc":"浏览器"}]},
             {"key":"business","modules":[{"name":"订单","desc":"下单支付"}]},
             {"key":"middleware","modules":[{"name":"认证","desc":"SSO"}]},
             {"key":"infrastructure","modules":[{"name":"MySQL","desc":"主库"}]}]
            留空则使用通用模板
        title: 架构图标题，如 "电商系统宏观架构图"，留空则自动生成
        output_name: 输出文件名，不含扩展名，默认 "architecture"

    Returns:
        JSON 字符串，包含 html_path、preview_url 和操作结果
    """
    OUTPUT_DIR.mkdir(exist_ok=True)

    # 解析 LLM 传入的 layers JSON，解析失败则用通用模板兜底
    layers = []
    if layers_json and layers_json.strip():
        try:
            layers = json.loads(layers_json)
        except json.JSONDecodeError:
            pass

    if not layers:
        # 通用模板兜底
        layers = [
            {"key": "terminal", "modules": [
                {"name": "Web 应用", "desc": "浏览器端主入口"},
                {"name": "移动端 App", "desc": "iOS / Android 客户端"},
                {"name": "小程序", "desc": "微信/支付宝小程序"},
                {"name": "开放 API", "desc": "第三方接入接口"},
            ]},
            {"key": "business", "modules": [
                {"name": "核心业务模块", "desc": "主要业务逻辑处理"},
                {"name": "用户中心", "desc": "注册登录、个人中心"},
                {"name": "订单/交易", "desc": "订单管理与交易处理"},
                {"name": "内容管理", "desc": "内容发布与审核"},
            ]},
            {"key": "middleware", "modules": [
                {"name": "统一认证", "desc": "SSO 单点登录"},
                {"name": "消息推送", "desc": "站内信/短信/邮件"},
                {"name": "AI 能力", "desc": "智能推荐/搜索"},
                {"name": "风控系统", "desc": "反欺诈/内容审核"},
            ]},
            {"key": "infrastructure", "modules": [
                {"name": "云服务器", "desc": "ECS/容器化部署"},
                {"name": "数据库", "desc": "MySQL/Redis/MongoDB"},
                {"name": "对象存储", "desc": "OSS/COS 文件存储"},
                {"name": "监控运维", "desc": "日志/告警/链路追踪"},
            ]},
        ]

    # 标题处理
    if not title:
        title = "XX 系统宏观架构图"
        if user_request:
            short = user_request.strip().replace("画", "").replace("生成", "").replace("架构图", "").strip()
            if short:
                title = f"{short[:30]} 宏观架构图"

    html_path = OUTPUT_DIR / f"{output_name}.html"
    html_content = _build_html(title, layers)
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
        "title": title,
        "message": "架构图已生成，可在浏览器中查看或导出 PDF",
    }, ensure_ascii=False, indent=2)