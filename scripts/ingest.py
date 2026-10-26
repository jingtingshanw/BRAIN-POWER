"""知识库入库脚本。等真实书籍文本到位后（Q-2），在此登记元数据再跑。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal, Base, engine
from app.config import SOURCES_DIR
from app.services.rag import ingest_all
from app.models import KbSource  # noqa: F401

# 文献元数据登记表
# 主入库入口是 scripts/ingest_pdfs.py（Springer 专著 + 开放获取论文，含 DOI）。
# 早期种子的二手社区综述（Yangzn666/sport GitHub 汇总）已于 10-26 全部下架：
# 来源可信度不足，会污染引用质量。如需重新入库，请替换为权威文献文本并登记元数据。
REGISTRY = {}


def main():
    from sqlalchemy import text as sql_text
    with engine.begin() as conn:
        conn.execute(sql_text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        results = ingest_all(db, REGISTRY)
        total = 0
        for r in results:
            print(r)
            total += r.get("chunks", 0)
        n = db.query(KbSource).count()
        print(f"\n入库完成：{n} 个文献源，{total} 个切片")
    finally:
        db.close()


if __name__ == "__main__":
    main()
