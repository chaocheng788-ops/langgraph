"""
Checkpointer 单例管理。
职责:
  1. AsyncSqliteSaver 全局单例（线程安全惰性初始化）
  2. 避免重复创建数据库连接
"""
from typing import Optional
from pathlib import Path

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver  # 异步 SQLite 持久化

from app.execution_log import add_log  # 全局日志


# ═══════════════════════════════════════════════════════════════
# Checkpointer 单例 — 全局唯一，避免重复创建数据库连接
# ═══════════════════════════════════════════════════════════════

_checkpointer: Optional[AsyncSqliteSaver] = None  # 模块级全局变量，缓存单例


async def get_checkpointer(db_path: str = "") -> AsyncSqliteSaver:
    """
    获取全局唯一的 AsyncSqliteSaver 实例（线程安全惰性初始化）。

    Args:
        db_path: SQLite 数据库路径，为空时默认使用 data/checkpoints.db

    Returns:
        AsyncSqliteSaver: 异步 SQLite Checkpointer，用于持久化 Agent 状态
    """
    global _checkpointer  # 声明修改模块级变量
    if _checkpointer is None:  # 只有首次调用时初始化
        import aiosqlite  # 延迟导入，减少启动开销
        if not db_path:  # 未指定路径时使用默认路径
            Path(Path(__file__).parent.parent / "data").mkdir(exist_ok=True)  # 确保 data 目录存在
            db_path = str(Path(__file__).parent.parent / "data" / "checkpoints.db")
        conn = await aiosqlite.connect(db_path)  # 创建异步 SQLite 连接
        _checkpointer = AsyncSqliteSaver(conn)  # 用连接初始化 Saver
        add_log("Checkpointer", f"AsyncSQLite 已连接: {db_path}")
    return _checkpointer