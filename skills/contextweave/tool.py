"""ContextWeave 绘图工具 - 封装 ContextWeave API 调用。"""
import json
import uuid
import urllib.request
import urllib.error

API_BASE = "https://pptx.chenxitech.site"
API_KEY = "94a05d02-9ade-4d9d-9f39-88734d9e34b4"
SKILL_VERSION = "7336738"


def _call_api(endpoint: str, payload: dict) -> dict:
    """通用 API 调用函数。"""
    url = f"{API_BASE}{endpoint}"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": API_KEY,
            "X-Request-ID": uuid.uuid4().hex,
            "X-Skill-Version": SKILL_VERSION,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        return {
            "status": "error",
            "code": f"HTTP_{e.code}",
            "message": f"API 请求失败 ({e.code}): {error_body[:300]}",
        }
    except Exception as e:
        return {
            "status": "error",
            "code": "NETWORK_ERROR",
            "message": f"网络请求失败: {str(e)}",
        }

    return result


def generate_diagram(
    user_request: str,
    initial_cw_code: str = "",
) -> str:
    """
    生成新的架构图或图表。将结构化的图表描述转化为可视化图形。

    Args:
        user_request: 详细的图表描述，包含实体、关系、层级与叙事路径（50-5000字符）
        initial_cw_code: 已有的 CW 代码，修改已有图表时提供，首次生成留空

    Returns:
        JSON 字符串，包含 session_id、svg_url 和操作结果
    """
    payload = {
        "mode": "3",
        "user_request": user_request,
        "initial_cw_code": initial_cw_code,
        "export_svg": True,
        "export_pptx": False,
        "editor_protocol": "trae",
    }

    result = _call_api("/run", payload)

    if result.get("status") == "error":
        return json.dumps(result, ensure_ascii=False, indent=2)

    output = {
        "status": "success",
        "session_id": result.get("session_id", ""),
        "svg_url": result.get("svg_url", ""),
        "message": result.get("message", "图表生成成功"),
    }

    if result.get("feedback_url"):
        output["feedback_url"] = result["feedback_url"]

    return json.dumps(output, ensure_ascii=False, indent=2)


def edit_diagram(
    session_id: str,
    user_request: str,
    initial_cw_code: str = "",
) -> str:
    """
    编辑已有的图表。基于 session_id 提交修改意图。

    Args:
        session_id: 之前生成图表时返回的会话 ID
        user_request: 修改描述，说明需要变更的内容
        initial_cw_code: 当前图表的 CW 代码

    Returns:
        JSON 字符串，包含更新后的 svg_url 和操作结果
    """
    payload = {
        "mode": "3",
        "user_request": user_request,
        "initial_cw_code": initial_cw_code,
        "session_id": session_id,
        "export_svg": True,
        "export_pptx": False,
        "editor_protocol": "trae",
        "stage_execution": "stage2_only",
    }

    result = _call_api("/run", payload)

    if result.get("status") == "error":
        return json.dumps(result, ensure_ascii=False, indent=2)

    output = {
        "status": "success",
        "session_id": result.get("session_id", session_id),
        "svg_url": result.get("svg_url", ""),
        "message": result.get("message", "图表编辑成功"),
    }

    if result.get("feedback_url"):
        output["feedback_url"] = result["feedback_url"]

    return json.dumps(output, ensure_ascii=False, indent=2)