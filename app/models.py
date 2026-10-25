"""v2 表结构。与 v1 的差异：废除概念卡相关表，新增 kb_sources / kb_chunks / events。"""
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.config import EMBEDDING_DIM
from app.db import Base


# ---------- 知识库（RAG 核心） ----------
class KbSource(Base):
    """文献元数据：引用可落地的前提。每条知识源入库必须登记。"""
    __tablename__ = "kb_sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_key: Mapped[str] = mapped_column(String(64), unique=True)  # 文件名或登记号
    type: Mapped[str] = mapped_column(String(16))  # book / paper
    title: Mapped[str] = mapped_column(String(300))
    authors: Mapped[str] = mapped_column(String(300), default="")
    year: Mapped[int] = mapped_column(default=0)
    url: Mapped[str] = mapped_column(String(500), default="")  # DOI/PubMed/出版页
    edition: Mapped[str] = mapped_column(String(100), default="")  # 版次/章节说明
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class KbChunk(Base):
    """知识切片：按章节/小节切，带来源与标题元数据，供引用生成。"""
    __tablename__ = "kb_chunks"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("kb_sources.id"))
    chunk_index: Mapped[int] = mapped_column(Integer)
    heading: Mapped[str] = mapped_column(String(300), default="")  # 章节/小节标题
    content: Mapped[str] = mapped_column(Text)
    embedding = mapped_column(Vector(EMBEDDING_DIM))


# ---------- 训练数据 ----------
class Profile(Base):
    """单用户档案（V1 单机单用户，PRD Q-5）。"""
    __tablename__ = "profile"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), default="")
    goal: Mapped[str] = mapped_column(String(200), default="")
    experience: Mapped[str] = mapped_column(String(50), default="")  # 新手/初中高
    days_per_week: Mapped[int] = mapped_column(default=0)
    injuries: Mapped[str] = mapped_column(Text, default="")  # 部位+诊断状态
    constraints: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class Plan(Base):
    __tablename__ = "plans"
    id: Mapped[int] = mapped_column(primary_key=True)
    goal: Mapped[str] = mapped_column(String(200), default="")
    weeks: Mapped[int] = mapped_column(default=8)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PlanDay(Base):
    __tablename__ = "plan_days"
    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id"))
    week: Mapped[int] = mapped_column(Integer)
    day: Mapped[int] = mapped_column(Integer)
    part: Mapped[str] = mapped_column(String(50), default="")  # 胸/背/腿/...
    status: Mapped[str] = mapped_column(String(20), default="planned")  # planned/done/rest
    items: Mapped[dict] = mapped_column(JSON, default=list)  # [{exercise, sets, reps, weight}]


class SetLog(Base):
    """逐组数据落库（北向指标②的数据基础）。"""
    __tablename__ = "set_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    plan_day_id: Mapped[int | None] = mapped_column(ForeignKey("plan_days.id"), nullable=True)
    exercise: Mapped[str] = mapped_column(String(100))
    weight: Mapped[float] = mapped_column(Float, default=0)
    reps: Mapped[int] = mapped_column(Integer, default=0)
    rpe: Mapped[float | None] = mapped_column(Float, nullable=True)
    trained_on: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class DailyRecord(Base):
    """每日记录：睡眠/酸痛/体重/主观（训练记录与每日记录合并页）。"""
    __tablename__ = "daily_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    record_date: Mapped[date] = mapped_column(Date)
    sleep_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    soreness: Mapped[str] = mapped_column(String(200), default="")
    soreness_level: Mapped[int | None] = mapped_column(nullable=True)  # 0-10
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    mood: Mapped[str] = mapped_column(String(200), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ---------- 对话与记忆 ----------
class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), default="default")
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Memory(Base):
    """长期记忆：教练越用越懂用户（北向指标③）。"""
    __tablename__ = "memories"
    id: Mapped[int] = mapped_column(primary_key=True)
    content: Mapped[str] = mapped_column(Text)
    embedding = mapped_column(Vector(EMBEDDING_DIM))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ---------- 埋点（PRD §9） ----------
class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64))  # 对象_动作
    props: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
