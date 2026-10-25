import json
from datetime import date
from pathlib import Path

from fastapi import FastAPI, Depends, Request
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text as sql_text

from app.db import Base, engine, get_db, SessionLocal
from app.models import DailyRecord, PlanDay, Profile, SetLog  # noqa: F401 注册表
from app.services import agent as agent_svc

app = FastAPI(title="coach-v2")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@app.on_event("startup")
def startup():
    # pgvector 扩展 + 建表
    with engine.begin() as conn:
        conn.execute(sql_text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(engine)


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@app.get("/api/health")
def health(db=Depends(get_db)):
    ok = True
    try:
        db.execute(sql_text("SELECT 1"))
    except Exception:  # noqa: BLE001
        ok = False
    return {"status": "ok" if ok else "db_down", "provider": "v2"}


class ChatIn(BaseModel):
    message: str
    session_id: str = "default"


@app.post("/api/chat/simple")
def chat_simple(body: ChatIn, db=Depends(get_db)):
    return agent_svc.run_agent(db, body.message, body.session_id)


@app.post("/api/chat/stream")
def chat_stream(body: ChatIn, request: Request, db=Depends(get_db)):
    def sse():
        for ev in agent_svc.run_agent_stream(db, body.message, body.session_id):
            if await_disconnected(request):
                break
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

    import json
    return StreamingResponse(sse(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"})


def await_disconnected(request: Request) -> bool:
    return request.client is None  # 简化处理；断连主要靠前端捕获


@app.put("/api/profile")
def update_profile(p: dict, db=Depends(get_db)):
    row = db.query(Profile).first()
    if not row:
        row = Profile()
        db.add(row)
    for k in ("name", "goal", "experience", "injuries", "constraints"):
        if k in p:
            setattr(row, k, p[k])
    if "days_per_week" in p:
        row.days_per_week = int(p["days_per_week"] or 0)
    db.commit()
    return {"ok": True}


@app.get("/api/profile")
def get_profile(db=Depends(get_db)):
    row = db.query(Profile).first()
    if not row:
        return {"profile": {}}
    return {"profile": {"name": row.name, "goal": row.goal, "experience": row.experience,
                        "days_per_week": row.days_per_week, "injuries": row.injuries, "constraints": row.constraints}}


@app.get("/api/plan")
def get_plan(db=Depends(get_db)):
    days = db.query(PlanDay).order_by(PlanDay.week, PlanDay.day).all()
    return {"days": [{"id": d.id, "week": d.week, "day": d.day, "part": d.part, "status": d.status, "items": d.items} for d in days]}


@app.post("/api/plan/day/{day_id}/punch")
def punch(day_id: int, logs: list[dict], db=Depends(get_db)):
    day = db.query(PlanDay).get(day_id)
    if not day:
        return JSONResponse({"error": "day not found"}, status_code=404)
    for l in logs:
        db.add(SetLog(plan_day_id=day_id, exercise=l["exercise"], weight=float(l.get("weight", 0)),
                      reps=int(l.get("reps", 0)), rpe=l.get("rpe"), trained_on=date.today()))
    day.status = "done"
    db.commit()
    return {"ok": True}


class DailyIn(BaseModel):
    sleep_hours: float | None = None
    soreness: str = ""
    soreness_level: int | None = None
    weight_kg: float | None = None
    mood: str = ""
    notes: str = ""


@app.post("/api/admin/clear-history")
def clear_history(body: dict, db=Depends(get_db)):
    from app.models import ChatMessage
    n = db.query(ChatMessage).filter_by(session_id=body.get("session_id", "default")).delete()
    db.commit()
    return {"ok": True, "deleted": n}


@app.post("/api/daily")
def daily(body: DailyIn, db=Depends(get_db)):
    existing = db.query(DailyRecord).filter_by(record_date=date.today()).one_or_none()
    if existing:
        for k, v in body.model_dump().items():
            setattr(existing, k, v)
    else:
        db.add(DailyRecord(record_date=date.today(), **body.model_dump()))
    db.commit()
    return {"ok": True, "date": str(date.today())}


@app.get("/api/daily/today")
def daily_today(db=Depends(get_db)):
    row = db.query(DailyRecord).filter_by(record_date=date.today()).one_or_none()
    return {"record": {"sleep_hours": row.sleep_hours, "soreness": row.soreness, "soreness_level": row.soreness_level,
                       "weight_kg": row.weight_kg, "mood": row.mood, "notes": row.notes} if row else None}
