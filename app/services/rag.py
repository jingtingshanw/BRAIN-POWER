"""RAG 管线：文献登记 → 切块 → embedding → pgvector 入库 → 混合召回。

设计要点（PRD §5.2）：
- 切块按 markdown 标题层级切（## / ###），超长再按 800 字硬切，每块带 heading 与 source_id。
- 元数据登记在 kb_sources，引用（书目/论文+链接）由元数据生成，禁止模型自造出处。
- 召回 = 向量 top-k 为主，命中块附带来源元数据一起返回。
"""
import json
import re

import requests

from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from app.config import api_key, EMBEDDING_DIM, EMBEDDING_MODEL, SOURCES_DIR
from app.models import KbChunk, KbSource

DASHSCOPE_EMB_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings"
CHUNK_TARGET = 700
CHUNK_MAX = 1100


# ---------- embedding ----------
def embed_texts(texts: list[str]) -> list[list[float]]:
    """批量 embedding（DashScope 兼容接口，text-embedding-v4）。"""
    out: list[list[float]] = []
    batch_size = 10
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        resp = requests.post(
            DASHSCOPE_EMB_URL,
            headers={"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json"},
            json={"model": EMBEDDING_MODEL, "input": batch, "dimensions": EMBEDDING_DIM},
            timeout=60,
        )
        resp.raise_for_status()
        data = sorted(resp.json()["data"], key=lambda d: d["index"])
        out.extend(d["embedding"] for d in data)
    return out


# ---------- 切块 ----------
def split_sections(md_text: str) -> list[tuple[str, str]]:
    """按 #/##/### 标题切块，返回 [(heading, content)]。超长块按段落硬切。"""
    sections: list[tuple[str, str]] = []
    parts = re.split(r"\n(?=#{1,3} )", md_text)
    for part in parts:
        body = part.strip()
        if not body:
            continue
        lines = body.splitlines()
        heading = lines[0].lstrip("# ").strip()[:200] if lines[0].startswith("#") else ""
        content = "\n".join(lines[1:]).strip() if heading else body
        if len(content) <= CHUNK_MAX:
            if content:
                sections.append((heading, content))
            continue
        # 超长：按段落聚合到目标大小
        buf, buf_len = [], 0
        for para in content.split("\n\n"):
            if buf and buf_len + len(para) > CHUNK_TARGET:
                sections.append((heading, "\n\n".join(buf)))
                buf, buf_len = [], 0
            buf.append(para)
            buf_len += len(para)
        if buf:
            sections.append((heading, "\n\n".join(buf)))
    return sections


# ---------- 入库 ----------
def ingest_source(db: Session, path, meta: dict, raw_text: str | None = None) -> dict:
    """登记文献元数据并切块入库；重复 source_key 走覆盖（先删旧块）。
    raw_text 传入时使用其内容（PDF 等非纯文本文件提取后的文本），否则读 path 文件。"""
    source_key = path.name
    raw = raw_text if raw_text is not None else path.read_text(encoding="utf-8", errors="ignore")
    sections = split_sections(raw)
    if not sections:
        return {"source": source_key, "chunks": 0, "skipped": "empty"}

    old = db.query(KbSource).filter_by(source_key=source_key).one_or_none()
    if old:
        db.query(KbChunk).filter_by(source_id=old.id).delete()
        src = old
        src.type = meta.get("type", src.type)
        src.title = meta.get("title", src.title)
        src.authors = meta.get("authors", src.authors)
        src.year = meta.get("year", src.year)
        src.url = meta.get("url", src.url)
        src.edition = meta.get("edition", src.edition)
    else:
        src = KbSource(
            source_key=source_key,
            type=meta.get("type", "paper"),
            title=meta.get("title", path.stem),
            authors=meta.get("authors", ""),
            year=meta.get("year", 0),
            url=meta.get("url", ""),
            edition=meta.get("edition", ""),
        )
        db.add(src)
        db.flush()

    embeddings = embed_texts([c for _, c in sections])
    for idx, ((heading, content), emb) in enumerate(zip(sections, embeddings)):
        db.add(KbChunk(source_id=src.id, chunk_index=idx, heading=heading, content=content, embedding=emb))
    db.commit()
    return {"source": source_key, "chunks": len(sections), "title": src.title}


def ingest_all(db: Session, registry: dict) -> list[dict]:
    """批量入库。registry: {文件名: {type,title,authors,year,url,edition}}；
    未登记的文件按 paper/文件名兜底，但引用质量依赖元数据，建议登记。"""
    results = []
    for path in sorted(SOURCES_DIR.glob("*.md")):
        meta = registry.get(path.name, {})
        results.append(ingest_source(db, path, meta))
    return results


# ---------- 召回 ----------
def search(db: Session, query: str, top_k: int = 5) -> dict:
    """混合召回：向量 top-k；query 过短直接拒绝。返回块+来源元数据。"""
    if not query.strip():
        return {"error": "query 不能为空"}
    [emb] = embed_texts([query])
    rows = db.execute(
        sql_text(
            "SELECT c.id, c.heading, c.content, s.source_key, s.type, s.title, s.authors, s.year, s.url, "
            "c.embedding <=> CAST(:e AS vector) AS dist "
            "FROM kb_chunks c JOIN kb_sources s ON s.id = c.source_id "
            "ORDER BY dist LIMIT :k"
        ),
        {"e": json.dumps(emb), "k": top_k},
    ).mappings().all()
    hits = []
    for r in rows:
        cite = f"《{r['title']}》" if r["type"] == "book" else f"{r['title']}（{r['authors']}，{r['year']}）"
        hits.append(
            {
                "heading": r["heading"],
                "content": r["content"],
                "distance": round(float(r["dist"]), 4),
                "citation": cite,
                "url": r["url"],
                "source_key": r["source_key"],
            }
        )
    return {"query": query, "hits": hits, "note": "引用必须来自以上召回内容；未召回的部分注明'此为一般经验'"}
