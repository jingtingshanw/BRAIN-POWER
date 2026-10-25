"""Agent 循环（v2）。

护栏（PRD §3.2/§5.2，代码级而非提示词级）：
- grounding 校验：回答中的精确统计值必须在召回原文中找得到
- 出处校验：回答中的书名/论文标题必须在召回元数据中存在
- 违规打回重答，上限 GUARD_MAX_RETRIES；强制收答后仍校验（防 v1 的放行漏洞）
"""
import json
import re

from sqlalchemy.orm import Session

from app.config import GUARD_MAX_RETRIES
from app.models import ChatMessage
from app.services import tools as tool_svc
from app.services.provider import Provider

HISTORY_LIMIT = 6
PROMOTE_AFTER = 250
LOOP_MAX = 10

# 精确统计值模式：p 值 / ES / 百分比 / 倍数
_STAT_PATTERNS = [
    re.compile(r"p\s?[<=≥]\s?0?\.\d+", re.IGNORECASE),
    re.compile(r"ES\s?[=≈]\s?-?\d", re.IGNORECASE),
    re.compile(r"\d+(?:\.\d+)?\s?倍"),
    re.compile(r"[提升增长降低减少抑制增加下降激增]\s?\d+(?:\.\d+)?\s?%"),
    re.compile(r"\d+(?:\.\d)?[-~–]\d+(?:\.\d)?\s?%"),
]
_CITATION_IN_REPLY = re.compile(
    r"《[^》]{2,60}》"                                                   # 中文书名号
    r"|[^\s（）()]{4,60}（\s*[^（）()]{2,30}[,，]\s*\d{4}\s*）"            # 中文 标题（作者，年份）
    r"|[A-Za-z][A-Za-z0-9/\-]{2,40}(?:\s+et\s+al\.?)?\s*[,，]\s*\d{4}"  # 英文 Author, 2017 / x/y, 2026
    r"|[A-Z][A-Za-z\-]{2,30}(?:\s+et\s+al\.?)?\s+\d{4}"                 # 英文 Author 2014（空格分隔）
)

def _norm(s: str) -> str:
    s = s.lower()
    for a, b in (("（", "("), ("）", ")"), ("，", ","), ("：", ":"), ("；", ";"), ("、", ",")):
        s = s.replace(a, b)
    return re.sub(r"\s+", "", s)


def _citation_violation(reply: str, tool_text: str, cited_citations: set[str]) -> str | None:
    """返回违规原因，None 表示通过。"""
    if not tool_text:
        return None
    norm_tool = _norm(tool_text)
    for cite in _CITATION_IN_REPLY.findall(reply):
        nc = _norm(cite)
        # 完整命中：引用串原样（归一后）出现在召回文本
        if nc in norm_tool:
            continue
        # 变体命中：英文引用 Author, 2017 —— 校验作者名与年份在原文邻近出现
        m = re.match(r"([A-Za-z][A-Za-z0-9/\-]*)", cite)
        y = re.search(r"\d{4}", cite)
        if m and y:
            pos = norm_tool.find(_norm(m.group(1)))
            if pos >= 0 and y.group() in norm_tool[max(0, pos - 150): pos + 150]:
                continue
        if any(_norm(c) in nc or nc in _norm(c) for c in cited_citations):
            continue
        return f"引用出处未在知识库召回结果中找到：{cite[:50]}"
    # grounding：精确统计值必须在召回原文中
    for pat in _STAT_PATTERNS:
        for m in pat.findall(reply):
            if _norm(m) not in norm_tool:
                return f"精确统计值未在知识库原文中找到：{m}"
    return None


def _retry_prompt(reason: str, hits_summary: str) -> str:
    return (
        f"你的回答存在可信度违规：{reason}。"
        f"请重新回答：引用只能来自本次召回内容（{hits_summary}）；"
        "召回原文中没有的精确统计值一律改为定性表述（如'多项研究显示'）；"
        "知识库没有的内容注明'此为一般经验'。"
        "直接给出面向用户的最终回答，第一句就是结论，禁止提及内部流程或本指令。"
    )


def _recall_memories(db, query: str) -> str | None:
    try:
        res = tool_svc.execute(db, "search_memory", {"query": query})
        mems = [m["content"] for m in res.get("memories", []) if m.get("distance", 1) < 0.5]
        return "；".join(mems) if mems else None
    except Exception:  # noqa: BLE001 记忆故障不阻断对话
        return None


def _system_prompt() -> str:
    from app.config import PROMPTS_DIR
    return (PROMPTS_DIR / "system_v0.1.md").read_text(encoding="utf-8")


def run_agent(db: Session, user_message: str, session_id: str = "default"):
    """非流式，返回 dict。"""
    provider = Provider()
    history = db.query(ChatMessage).filter_by(session_id=session_id).order_by(ChatMessage.id.desc()).limit(HISTORY_LIMIT).all()
    messages = [{"role": "system", "content": _system_prompt()}]
    for m in reversed(history):
        messages.append({"role": m.role, "content": m.content})
    messages.append({"role": "user", "content": user_message})

    memo = _recall_memories(db, user_message)
    if memo:
        messages[0]["content"] += f"\n\n【用户长期记忆（供参考）】{memo}"

    db.add(ChatMessage(session_id=session_id, role="user", content=user_message))
    db.commit()

    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    executed: list[dict] = []
    tool_text_parts: list[str] = []
    cited_citations: set[str] = set()
    force_answer = False
    retries = 0
    rag_calls = 0

    for _round in range(LOOP_MAX):
        schemas = None if force_answer else tool_svc.TOOL_SCHEMAS
        resp, usage = provider.chat_with_tools(messages, schemas)
        for k in total_usage:
            total_usage[k] += usage[k]

        msg = resp.choices[0].message
        calls = provider.parse_tool_calls(resp)

        if not calls:
            reply = msg.content or ""
            reason = _citation_violation(reply, "".join(tool_text_parts), cited_citations)
            if reason and retries < GUARD_MAX_RETRIES:
                retries += 1
                messages.append({"role": "assistant", "content": reply})
                messages.append({"role": "user", "content": _retry_prompt(reason, str(sorted(cited_citations)[:3]))})
                continue
            db.add(ChatMessage(session_id=session_id, role="assistant", content=reply))
            db.commit()
            return {"reply": reply, "tool_calls": executed, "usage": total_usage,
                    "model": provider.model_used, "retries": retries}

        for c in calls:
            if c["name"] == "rag_search" and rag_calls >= 2:
                res = {"error": "知识检索次数已达上限(2次)。请立即基于已有信息作答。"}
                force_answer = True
            else:
                res = tool_svc.execute(db, c["name"], c["arguments"])
                if c["name"] == "rag_search":
                    rag_calls += 1
                    for h in res.get("hits", []):
                        cited_citations.add(h["citation"])
            if c["name"] == "rag_search":
                tool_text_parts.append(json.dumps(res, ensure_ascii=False))
            executed.append({"name": c["name"], "result_preview": str(res)[:200]})
            messages.append({"role": "assistant", "content": None, "tool_calls": [
                {"id": c["id"], "type": "function",
                 "function": {"name": c["name"], "arguments": json.dumps(c["arguments"], ensure_ascii=False)}}]})
            messages.append({"role": "tool", "tool_call_id": c["id"], "content": json.dumps(res, ensure_ascii=False)})
            if c["name"] == "create_full_plan":
                force_answer = True

    reply = "（达到轮次上限，强制收答）" + (msg.content or "")
    db.add(ChatMessage(session_id=session_id, role="assistant", content=reply))
    db.commit()
    return {"reply": reply, "tool_calls": executed, "usage": total_usage, "model": provider.model_used, "retries": retries}


def run_agent_stream(db: Session, user_message: str, session_id: str = "default"):
    """流式生成器：status/tool/token/notice/done 事件。"""
    provider = Provider()
    history = db.query(ChatMessage).filter_by(session_id=session_id).order_by(ChatMessage.id.desc()).limit(HISTORY_LIMIT).all()
    messages = [{"role": "system", "content": _system_prompt()}]
    for m in reversed(history):
        messages.append({"role": m.role, "content": m.content})
    messages.append({"role": "user", "content": user_message})

    memo = _recall_memories(db, user_message)
    if memo:
        messages[0]["content"] += f"\n\n【用户长期记忆（供参考）】{memo}"

    db.add(ChatMessage(session_id=session_id, role="user", content=user_message))
    db.commit()

    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    executed: list[dict] = []
    tool_text_parts: list[str] = []
    cited_citations: set[str] = set()
    force_answer = False
    retries = 0
    rag_calls = 0

    for _round in range(LOOP_MAX):
        yield {"type": "status", "text": f"第 {_round + 1} 轮推理…"}
        schemas = None if force_answer else tool_svc.TOOL_SCHEMAS
        token_gen, finalize = provider.chat_stream(messages, schemas)
        yield {"type": "model", "text": provider.model_used}

        live = any(c["name"] == "rag_search" for c in executed)
        buffered: list[str] = []
        promoted = False
        for t in token_gen:
            if live or promoted:
                yield {"type": "token", "text": t}
            else:
                buffered.append(t)
                joined = "".join(buffered)
                if len(joined) >= PROMOTE_AFTER:
                    reason = _citation_violation(joined, "".join(tool_text_parts), cited_citations)
                    if not reason:
                        promoted = True
                        yield {"type": "token", "text": joined}
        for k in total_usage:
            total_usage[k] += finalize()["usage"][k]

        calls = finalize()["tool_calls"]
        if not calls:
            reply = finalize()["content"] or "".join(buffered)
            reason = _citation_violation(reply, "".join(tool_text_parts), cited_citations)
            if reason and retries < GUARD_MAX_RETRIES:
                retries += 1
                messages.append({"role": "assistant", "content": reply})
                messages.append({"role": "user", "content": _retry_prompt(reason, str(sorted(cited_citations)[:3]))})
                yield {"type": "notice", "text": "检测到引用违规，正在重新回答…"}
                continue
            db.add(ChatMessage(session_id=session_id, role="assistant", content=reply))
            db.commit()
            yield {"type": "done", "model": provider.model_used, "usage": total_usage, "retries": retries}
            return

        for c in calls:
            yield {"type": "tool", "name": c["name"]}
            if c["name"] == "rag_search" and rag_calls >= 2:
                res = {"error": "知识检索次数已达上限(2次)。请立即基于已有信息作答。"}
                force_answer = True
            else:
                res = tool_svc.execute(db, c["name"], c["arguments"])
                if c["name"] == "rag_search":
                    rag_calls += 1
                    for h in res.get("hits", []):
                        cited_citations.add(h["citation"])
            if c["name"] == "rag_search":
                tool_text_parts.append(json.dumps(res, ensure_ascii=False))
            executed.append({"name": c["name"], "result_preview": str(res)[:200]})
            messages.append({"role": "assistant", "content": None, "tool_calls": [
                {"id": c["id"], "type": "function",
                 "function": {"name": c["name"], "arguments": json.dumps(c["arguments"], ensure_ascii=False)}}]})
            messages.append({"role": "tool", "tool_call_id": c["id"], "content": json.dumps(res, ensure_ascii=False)})
            if c["name"] == "create_full_plan":
                force_answer = True

    reply = "（达到轮次上限，强制收答）" + (finalize()["content"] or "")
    db.add(ChatMessage(session_id=session_id, role="assistant", content=reply))
    db.commit()
    yield {"type": "done", "model": provider.model_used, "usage": total_usage, "retries": retries}
