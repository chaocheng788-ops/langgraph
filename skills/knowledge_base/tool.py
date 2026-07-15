"""
知识库工具 — 基于 FAISS + SQLite 的本地 RAG 知识库。
所有逻辑收敛在 skill 目录内，完全自包含。

核心流程:
  入库: add_knowledge → 文本切分 → Embedding → SQLite + FAISS 双写
  检索: search_knowledge → Embedding → FAISS 搜索 → SQLite 查原文
"""
import json
import sqlite3
from pathlib import Path
from typing import List, Dict

import re

import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

# ═══════════════════════════════════════════════════════════════
# 路径常量
# ═══════════════════════════════════════════════════════════════

SKILL_DIR = Path(__file__).parent
DATA_DIR = SKILL_DIR.parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "knowledge.db"
INDEX_PATH = DATA_DIR / "knowledge.index"

# ═══════════════════════════════════════════════════════════════
# 全局单例
# ═══════════════════════════════════════════════════════════════

_EMBEDDING_MODEL = None
CHUNK_SIZE = 500


def _get_model() -> SentenceTransformer:
    """加载 Embedding 模型（单例，进程内只加载一次）"""
    global _EMBEDDING_MODEL
    if _EMBEDDING_MODEL is None:
        _EMBEDDING_MODEL = SentenceTransformer("BAAI/bge-small-zh-v1.5")
    return _EMBEDDING_MODEL


def _get_db() -> sqlite3.Connection:
    """获取 SQLite 连接，自动建表"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            source TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return conn


# ═══════════════════════════════════════════════════════════════
# 文本切分
# ═══════════════════════════════════════════════════════════════

def _split_text(text: str) -> List[str]:
    """
    智能切分：优先按 Markdown 标题（#）分节，保持标题+正文完整；
    每节内按段落 + 500 字上限再切分，确保每个 chunk 都携带上下文标题。
    """
    # ── 第一步：按 # 标题分节，保留标题作为上下文前缀 ──
    sections = re.split(r'\n(?=#{1,4}\s)', text)
    all_chunks = []
    for section in sections:
        section = section.strip()
        if not section:
            continue
        # 提取当前节的标题行（第一行如果是 # 开头）
        heading = ""
        body_start = section
        first_line = section.split("\n", 1)[0].strip()
        if first_line.startswith("#"):
            heading = first_line + "\n"
            if "\n" in section:
                body_start = section.split("\n", 1)[1].strip()
            else:
                body_start = ""
        if not body_start:
            if heading:
                all_chunks.append(heading.strip())
            continue
        # ── 第二步：节内按段落 + 500 字上限切分 ──
        paragraphs = [p.strip() for p in body_start.split("\n") if p.strip()]
        current = ""
        for para in paragraphs:
            if len(current) + len(para) <= CHUNK_SIZE:
                current += para + "\n"
            else:
                if current:
                    all_chunks.append((heading + current).strip())
                current = para + "\n"
        if current:
            all_chunks.append((heading + current).strip())
    return all_chunks if all_chunks else [text]


# ═══════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════

def add_knowledge(title: str, content: str, source: str = "") -> str:
    """
    添加文档到知识库。
    流程: 切分 → Embedding → SQLite 写元数据 + FAISS 写向量

    Args:
        title: 文档标题（如"考勤管理制度"）
        content: 文档正文
        source: 来源（可选，如 URL 或文件名）
    """
    model = _get_model()
    chunks = _split_text(content)
    if not chunks:
        return json.dumps({
            "success": False,
            "result_type": "empty",
            "summary": "文档内容为空",
            "error_hint": "传入的 content 为空",
            "next_action": "请提供有效的文档内容",
        }, ensure_ascii=False)

    embeddings = model.encode(chunks, normalize_embeddings=True).astype(np.float32)
    dim = embeddings.shape[1]

    conn = _get_db()
    doc_ids = []
    for i, chunk in enumerate(chunks):
        cursor = conn.execute(
            "INSERT INTO documents (title, content, chunk_index, source) VALUES (?, ?, ?, ?)",
            (title, chunk, i, source)
        )
        doc_ids.append(cursor.lastrowid)
    conn.commit()
    conn.close()

    # FAISS 写入
    if INDEX_PATH.exists():
        index = faiss.read_index(str(INDEX_PATH))
    else:
        index = faiss.IndexIDMap(faiss.IndexFlatIP(dim))

    start_id = max(doc_ids) - len(doc_ids) + 1
    index.add_with_ids(embeddings, np.array(doc_ids, dtype=np.int64))
    faiss.write_index(index, str(INDEX_PATH))

    return json.dumps({
        "success": True,
        "result_type": "json",
        "summary": f"文档「{title}」已入库，共 {len(chunks)} 个片段",
        "detail": {"title": title, "chunk_count": len(chunks)},
        "next_action": "现在可以通过 search_knowledge 搜索该文档内容",
    }, ensure_ascii=False)


def search_knowledge(query: str, top_k: int = 5) -> str:
    """
    语义搜索知识库。
    流程: 查询 Embedding → FAISS 内积搜索 → SQLite 查原文

    Args:
        query: 搜索关键词或问题
        top_k: 返回结果数量，默认 5
    """
    if not INDEX_PATH.exists():
        return json.dumps({
            "success": False,
            "result_type": "empty",
            "summary": "知识库为空，暂无索引",
            "error_hint": "尚未添加任何文档",
            "next_action": "请先通过 add_knowledge 添加文档到知识库",
        }, ensure_ascii=False)

    model = _get_model()
    query_vec = model.encode([query], normalize_embeddings=True).astype(np.float32)

    index = faiss.read_index(str(INDEX_PATH))
    scores, ids = index.search(query_vec, top_k)

    conn = _get_db()
    results = []
    for score, doc_id in zip(scores[0], ids[0]):
        if doc_id < 0:
            continue
        row = conn.execute(
            "SELECT title, content, source FROM documents WHERE id = ?", (int(doc_id),)
        ).fetchone()
        if row:
            results.append({
                "title": row[0],
                "content": row[1],
                "source": row[2],
                "score": round(float(score), 4),
            })
    conn.close()

    if not results:
        return json.dumps({
            "success": False,
            "result_type": "empty",
            "summary": "未找到相关内容",
            "error_hint": "知识库中无匹配的文档",
            "next_action": "尝试换个关键词搜索，或先添加相关文档",
        }, ensure_ascii=False)

    return json.dumps({
        "success": True,
        "result_type": "json",
        "summary": f"找到 {len(results)} 条相关内容",
        "detail": results,
        "next_action": "基于以上检索结果回答用户问题，并注明来源文档标题",
    }, ensure_ascii=False)