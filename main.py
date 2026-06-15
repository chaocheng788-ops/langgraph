"""
LangGraph Platform - Main Entry Point
启动 FastAPI 服务器，挂载 API 子应用和前端静态文件。

架构说明:
  main.py (顶层 FastAPI app)
    └── app.mount("/api", api_app)  → app/server.py (API 路由子应用)
    └── app.mount("/static", ...)   → frontend/ (前端静态资源)
    └── @app.get("/")               → frontend/index.html (单页应用入口)
"""
import os
import sys
from pathlib import Path

import uvicorn  # ASGI 服务器，用于运行 FastAPI 应用
from fastapi import FastAPI  # Web 框架
from fastapi.staticfiles import StaticFiles  # 静态文件挂载
from fastapi.responses import HTMLResponse  # HTML 响应类型

# 将项目根目录加入 Python 搜索路径，确保能导入 app 模块
sys.path.insert(0, str(Path(__file__).parent))

# 从 app/server.py 导入 FastAPI 子应用实例（别名 api_app 避免和本文件的 app 冲突）
from app.server import app as api_app

# 创建顶层 FastAPI 应用，作为统一入口
app = FastAPI(title="LangGraph Platform")

# 将 API 子应用挂载到 /api 路径下
# server.py 中定义的所有路由自动获得 /api 前缀（如 /models → /api/models）
app.mount("/api", api_app)

# 挂载前端静态文件目录（CSS、JS 等资源，当前项目前端为单 HTML 文件，此项为预留）
frontend_dir = Path(__file__).parent / "frontend"
if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

    # 根路径直接返回前端单页 HTML（React + Babel 在浏览器端渲染）
    @app.get("/")
    async def serve_frontend():
        """读取 index.html 并作为 HTML 响应返回"""
        content = (frontend_dir / "index.html").read_text(encoding="utf-8")
        return HTMLResponse(content=content, media_type="text/html")
else:
    # 如果 frontend 目录不存在，返回纯 API 模式提示
    @app.get("/")
    async def root():
        return {"message": "LangGraph Platform API", "docs": "/docs"}


# 直接执行 python main.py 时启动 uvicorn 服务器
if __name__ == "__main__":
    uvicorn.run(
        "main:app",        # 模块:应用实例，uvicorn 会导入 main 模块的 app 对象
        host="0.0.0.0",    # 监听所有网络接口，允许外部访问
        port=19527,        # 服务端口号
        reload=False,      # 生产模式不自动重载（开发时可改为 True）
        log_level="info",  # 日志级别
    )