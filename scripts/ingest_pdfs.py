"""书籍/论文 PDF 入库（Q-2 书目部分到位，小王 10-26 提供）。

- 文本提取：pypdf 逐页提取，空页跳过。
- 切块：按句子边界聚合到 ~700-1100 字符（PDF 无 markdown 标题，heading 记页码范围）。
- 元数据：REGISTRY 登记真实书目信息（引用可落地的前提）。
- 跳过：978-88-470-2418-2.pdf（同书第一版，第二版已入库，内容重复）。
"""
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PDF_DIR = Path(r"C:/Users/17378/WorkBuddy/2026-10-26-01-38-30/ironhall-knowledge/free-layer/pdfs")

PDF_REGISTRY = {
    "1073.full.pdf": {
        "type": "paper", "year": 2023,
        "title": "IOC consensus statement on Relative Energy Deficiency in Sport (REDs)",
        "authors": "Mountjoy M, et al. (IOC)", "url": "https://doi.org/10.1136/bjsports-2023-106994",
    },
    "376.full.pdf": {
        "type": "paper", "year": 2018,
        "title": "A systematic review, meta-analysis and meta-regression of the effect of protein supplementation on resistance training-induced gains in muscle mass and strength",
        "authors": "Morton RW, et al.", "url": "https://doi.org/10.1136/bjsports-2017-097608",
    },
    "978-3-030-05258-4.pdf": {
        "type": "book", "year": 2019, "edition": "1st",
        "title": "Exercise and Sports Pulmonology",
        "authors": "Cogo A, Bonini M, Onorati P (eds.)", "url": "https://doi.org/10.1007/978-3-030-05259-1",
    },
    "978-3-030-33376-8.pdf": {
        "type": "book", "year": 2020,
        "title": "Endocrinology of Physical Activity and Sport",
        "authors": "Hackney AC, Constantini NW (eds.)", "url": "https://doi.org/10.1007/978-3-030-33376-8",
    },
    "978-3-031-15485-0.pdf": {
        "type": "book", "year": 2023, "edition": "3rd",
        "title": "The Active Female: Health Issues throughout the Lifespan",
        "authors": "Robert-McComb JJ, Zumwalt M, Fernandez-del-Valle M (eds.)", "url": "https://doi.org/10.1007/978-3-031-15485-0",
    },
    "978-3-031-27192-2.pdf": {
        "type": "book", "year": 2023, "edition": "2nd",
        "title": "Cellular Physiology and Metabolism of Physical Exercise: Topical Clinical Issues",
        "authors": "Luzi L (ed.)", "url": "https://doi.org/10.1007/978-3-031-27192-2",
    },
    # 978-88-470-2418-2.pdf 跳过：同书第一版
    "Helms-2014-Natural-Bodybuilding-JISSN.pdf": {
        "type": "paper", "year": 2014,
        "title": "Evidence-based recommendations for natural bodybuilding contest preparation: nutrition and supplementation",
        "authors": "Helms ER, Aragon AA, Fitschen PJ", "url": "https://doi.org/10.1186/1550-2783-11-20",
    },
    "ISSN-2011-Meal-Frequency-Aragon.pdf": {  # 文件名与内容不符，实际为 Bloomer 甜菜碱论文
        "type": "paper", "year": 2011,
        "title": "Effect of betaine supplementation on plasma nitrate/nitrite in exercise-trained men",
        "authors": "Bloomer RJ, et al.", "url": "",
    },
    "ISSN-2017-Creatine-Position-Stand-Kreider.pdf": {
        "type": "paper", "year": 2017,
        "title": "ISSN position stand: safety and efficacy of creatine supplementation in exercise, sport, and medicine",
        "authors": "Kreider RB, et al.", "url": "https://doi.org/10.1186/s12970-017-0173-z",
    },
    "ISSN-2017-Nutrient-Timing-Kerksick.pdf": {
        "type": "paper", "year": 2017,
        "title": "ISSN position stand: nutrient timing",
        "authors": "Kerksick CM, et al.", "url": "https://doi.org/10.1186/s12970-017-0189-4",
    },
    "ISSN-2017-Protein-Position-Stand-Jager.pdf": {
        "type": "paper", "year": 2017,
        "title": "ISSN Position Stand: protein and exercise",
        "authors": "Jäger R, et al.", "url": "https://doi.org/10.1186/s12970-017-0177-8",
    },
    "ISSN-2021-Caffeine-Position-Stand-Guest.pdf": {
        "type": "paper", "year": 2021,
        "title": "ISSN position stand: caffeine and exercise performance",
        "authors": "Guest NS, et al.", "url": "https://doi.org/10.1186/s12970-021-00483-8",
    },
    "Schoenfeld-2014-Fasted-Cardio-JISSN.pdf": {
        "type": "paper", "year": 2014,
        "title": "Body composition changes associated with fasted versus non-fasted aerobic exercise",
        "authors": "Schoenfeld BJ, Aragon AA", "url": "https://doi.org/10.1186/1550-2783-11-43",
    },
}

SKIP = {"978-88-470-2418-2.pdf"}

SENT_SPLIT = __import__("re").compile(r"(?<=[.!?。])\s+")


def extract_pdf_text(path: Path) -> str:
    from pypdf import PdfReader
    r = PdfReader(str(path))
    pages = []
    for i, p in enumerate(r.pages):
        t = (p.extract_text() or "").strip()
        if t:
            pages.append(f"[p{i + 1}] {t}")
    return "\n".join(pages)


import re as _re

PAGE_MARK = _re.compile(r"^\[p(\d+)\] ")


def chunk_pdf_text(raw: str, target: int = 700, hard_max: int = 1100) -> list[tuple[str, str]]:
    """按页聚合，页内按句子切；返回 [(heading=页码范围, content)]。"""
    chunks: list[tuple[str, str]] = []
    buf: list[str] = []
    buf_len = 0
    cur_pages: list[int] = []

    def flush():
        nonlocal buf, buf_len, cur_pages
        if not buf:
            return
        pr = f"p{min(cur_pages)}-p{max(cur_pages)}" if cur_pages else ""
        chunks.append((pr, "\n".join(buf)))
        buf, buf_len, cur_pages = [], 0, []

    for line in raw.split("\n"):
        m = PAGE_MARK.match(line)
        page_no = int(m.group(1)) if m else None
        body = line[m.end() :].strip() if m else line.strip()
        if not body:
            continue
        # 单页文本超长时按句子硬切
        for piece in ([body] if len(body) <= target else _split_long(body, target)):
            if buf and buf_len + len(piece) > target:
                flush()
            buf.append(piece)
            buf_len += len(piece)
            if page_no:
                cur_pages.append(page_no)
        if buf_len >= hard_max:
            flush()
    flush()
    return chunks


def _split_long(text: str, target: int) -> list[str]:
    parts, buf = [], ""
    for s in SENT_SPLIT.split(text):
        if len(buf) + len(s) > target and buf:
            parts.append(buf)
            buf = ""
        buf += " " + s
    if buf:
        parts.append(buf)
    return parts


def main():
    import logging
    logging.disable(logging.WARNING)
    from app.db import SessionLocal, Base, engine
    from app.services.rag import ingest_source
    from sqlalchemy import text as sql_text

    with engine.begin() as conn:
        conn.execute(sql_text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(engine)

    db = SessionLocal()
    total = 0
    try:
        for name, meta in sorted(PDF_REGISTRY.items()):
            if name in SKIP:
                print(f"SKIP {name}（同书第一版，内容重复）")
                continue
            path = PDF_DIR / name
            if not path.exists():
                print(f"MISSING {name}")
                continue
            stub = type("P", (), {"name": name})()
            raw = extract_pdf_text(path)
            chunks = chunk_pdf_text(raw)
            # 直接复用 ingest_source 的落库逻辑，跳过它的文件读取：临时写入 md 文件不可取，
            # 所以在这里手动执行（与 ingest_source 相同的流程）
            from app.models import KbChunk, KbSource
            old = db.query(KbSource).filter_by(source_key=name).one_or_none()
            if old:
                db.query(KbChunk).filter_by(source_id=old.id).delete()
                src = old
                for k, v in meta.items():
                    setattr(src, k, v)
            else:
                src = KbSource(source_key=name, **meta)
                db.add(src)
                db.flush()
            from app.services.rag import embed_texts
            emb_list = embed_texts([c for _, c in chunks])
            for idx, ((heading, content), emb) in enumerate(zip(chunks, emb_list)):
                db.add(KbChunk(source_id=src.id, chunk_index=idx, heading=heading, content=content, embedding=emb))
            db.commit()
            total += len(chunks)
            print(f"OK {name} | {meta['title'][:50]} | {len(chunks)} chunks")
        print(f"\nPDF 入库完成：{total} 个切片")
    finally:
        db.close()


if __name__ == "__main__":
    main()
