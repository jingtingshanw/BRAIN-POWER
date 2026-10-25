"""工具层（v2）：rag_search 替代 v1 的 get_concept/search_research 双轨，统一走知识库召回。"""
import json
from datetime import date

from sqlalchemy.orm import Session

from app.models import DailyRecord, Memory, Plan, PlanDay, Profile, SetLog
from app.services import rag

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "rag_search",
            "description": "在专业知识库（运动科学书籍与论文的全文切片）中检索。任何关键结论给用户前必须先检索，引用格式由工具返回的 citation 字段给出。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索主题，如'训练频率与肌肥大'"},
                    "top_k": {"type": "integer", "description": "召回条数，默认5，最多8"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_profile",
            "description": "读取用户档案（目标/经验/伤病/约束）。涉及个人化建议前先调用。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_profile",
            "description": "更新用户档案。仅在用户明确给出新的个人信息（如确诊、目标变更）时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "goal": {"type": "string"},
                    "experience": {"type": "string"},
                    "days_per_week": {"type": "integer"},
                    "injuries": {"type": "string", "description": "部位+性质+状态"},
                    "constraints": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "log_exercise",
            "description": "记录用户报告的训练数据，逐组一条。用户说'卧推80做了8个'时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "exercise": {"type": "string"},
                    "weight": {"type": "number"},
                    "reps": {"type": "integer"},
                    "rpe": {"type": "number", "description": "自感强度0-10，可选"},
                },
                "required": ["exercise", "weight", "reps"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_progress",
            "description": "查询某动作的历史训练记录（重量/次数/RPE随时间）。讨论进退步或调整重量前调用。",
            "parameters": {
                "type": "object",
                "properties": {"exercise": {"type": "string", "description": "动作名，支持模糊匹配"}},
                "required": ["exercise"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_full_plan",
            "description": "一次性创建多周训练计划。先 rag_search 检索计划设计原则、get_profile 确认档案后再调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "goal": {"type": "string"},
                    "weeks": {"type": "integer"},
                    "days": {
                        "type": "array",
                        "description": "逐日数组，每周每天一条",
                        "items": {
                            "type": "object",
                            "properties": {
                                "week": {"type": "integer"},
                                "day": {"type": "integer"},
                                "part": {"type": "string"},
                                "items": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "exercise": {"type": "string"},
                                            "sets": {"type": "integer"},
                                            "reps": {"type": "string"},
                                            "weight": {"type": "number"},
                                        },
                                        "required": ["exercise", "sets", "reps"],
                                    },
                                },
                            },
                            "required": ["week", "day", "part", "items"],
                        },
                    },
                },
                "required": ["goal", "weeks", "days"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "保存用户的重要长期信息（偏好/习惯/身体反应模式），供未来对话召回。不要存一次性内容。",
            "parameters": {"type": "object", "properties": {"content": {"type": "string"}}, "required": ["content"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_memory",
            "description": "检索关于用户的历史记忆。",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        },
    },
]

IMPLEMENTED = set()


def execute(db: Session, name: str, args: dict) -> dict:
    if name == "rag_search":
        return rag.search(db, args["query"], min(int(args.get("top_k", 5)), 8))
    if name == "get_profile":
        p = db.query(Profile).first()
        return {"profile": {"name": p.name, "goal": p.goal, "experience": p.experience, "days_per_week": p.days_per_week, "injuries": p.injuries, "constraints": p.constraints} if p else {}}
    if name == "update_profile":
        p = db.query(Profile).first()
        if not p:
            p = Profile()
            db.add(p)
        for k in ("goal", "experience", "injuries", "constraints"):
            if args.get(k) is not None:
                setattr(p, k, args[k])
        if args.get("days_per_week") is not None:
            p.days_per_week = args["days_per_week"]
        db.commit()
        return {"ok": True}
    if name == "log_exercise":
        log = SetLog(exercise=args["exercise"], weight=float(args["weight"]), reps=int(args["reps"]),
                     rpe=args.get("rpe"), trained_on=date.today())
        db.add(log)
        db.commit()
        return {"ok": True, "log_id": log.id}
    if name == "get_progress":
        kw = args["exercise"]
        logs = (db.query(SetLog).filter(SetLog.exercise.ilike(f"%{kw}%"))
                .order_by(SetLog.trained_on.desc()).limit(20).all())
        return {"exercise": kw, "records": [{"date": str(l.trained_on), "weight": l.weight, "reps": l.reps, "rpe": l.rpe} for l in reversed(logs)]}
    if name == "create_full_plan":
        plan = Plan(goal=args["goal"], weeks=args["weeks"], active=True)
        db.add(plan)
        db.flush()
        n = 0
        for d in args["days"]:
            db.add(PlanDay(plan_id=plan.id, week=int(d["week"]), day=int(d["day"]),
                           part=d.get("part", ""), items=d.get("items", [])))
            n += 1
        db.commit()
        return {"ok": True, "plan_id": plan.id, "days_created": n,
                "note": "计划已创建并向用户展示。本轮到此结束：不要再调用工具，直接向用户确认计划要点并说明首周执行方式。"}
    if name == "save_memory":
        emb = rag.embed_texts([args["content"]])[0]
        m = Memory(content=args["content"], embedding=emb)
        db.add(m)
        db.commit()
        return {"ok": True}
    if name == "search_memory":
        emb = rag.embed_texts([args["query"]])[0]
        rows = db.execute(
            __import__("sqlalchemy").text(
                "SELECT content, embedding <=> CAST(:e AS vector) AS dist FROM memories ORDER BY dist LIMIT 3"
            ),
            {"e": json.dumps(emb)},
        ).mappings().all()
        return {"memories": [{"content": r["content"], "distance": round(float(r["dist"]), 3)} for r in rows]}
    return {"error": f"unknown tool {name}"}
