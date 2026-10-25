"""知识库入库脚本。等真实书籍文本到位后（Q-2），在此登记元数据再跑。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import SessionLocal, Base, engine
from app.config import SOURCES_DIR
from app.services.rag import ingest_all
from app.models import KbSource  # noqa: F401

# 文献元数据登记表（PRD §5.2：引用可落地的前提）
# 以下为种子文献（GitHub sport 仓库的综述汇总），真实书籍到位后按同样格式登记
REGISTRY = {
    "2024-2026前沿研究汇总.md": {"type": "paper", "title": "2024-2026 健身科学前沿研究汇总", "authors": "Yangzn666/sport 社区综述", "year": 2026, "url": "https://github.com/Yangzn666/sport"},
    "力量训练科学.md": {"type": "paper", "title": "力量训练科学综述", "authors": "Yangzn666/sport 社区综述", "year": 2026, "url": "https://github.com/Yangzn666/sport"},
    "周期化训练高级理论.md": {"type": "paper", "title": "周期化训练高级理论综述", "authors": "Yangzn666/sport 社区综述", "year": 2026, "url": "https://github.com/Yangzn666/sport"},
    "心理训练与认知表现.md": {"type": "paper", "title": "心理训练与认知表现综述", "authors": "Yangzn666/sport 社区综述", "year": 2026, "url": "https://github.com/Yangzn666/sport"},
    "有氧训练与耐力科学.md": {"type": "paper", "title": "有氧训练与耐力科学综述", "authors": "Yangzn666/sport 社区综述", "year": 2026, "url": "https://github.com/Yangzn666/sport"},
    "营养与恢复科学.md": {"type": "paper", "title": "营养与恢复科学综述", "authors": "Yangzn666/sport 社区综述", "year": 2026, "url": "https://github.com/Yangzn666/sport"},
    "运动生理学基础.md": {"type": "paper", "title": "运动生理学基础综述", "authors": "Yangzn666/sport 社区综述", "year": 2026, "url": "https://github.com/Yangzn666/sport"},
    "README_快速导航.md": {"type": "paper", "title": "知识库快速导航", "authors": "Yangzn666/sport", "year": 2026, "url": "https://github.com/Yangzn666/sport"},
}


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
