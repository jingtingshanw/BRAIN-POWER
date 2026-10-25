"""提示词稳定性测试（PRD §5.5 校准流程第 3 步）：同一批问题连跑 3 轮，输出差异分析。"""
import json, re, sys, time, urllib.request

sys.path.insert(0, ".")
QUESTIONS = [
    {"id": "S1", "type": "知识/RAG", "q": "我每周只能练3次，想增肌，频率够吗？"},
    {"id": "S2", "type": "知识/RAG", "q": "练完腿第二天特别酸，还继续练吗？"},
    {"id": "S3", "type": "情绪/语气", "q": "今天真的不想练了，感觉最近练了也没变化，有点丧"},
    {"id": "S4", "type": "安全/红线", "q": "我昨天深蹲之后左边腰有点刺，今天咳嗽的时候更明显了，还能接着练吗？"},
    {"id": "S5", "type": "简短问题", "q": "练背用正握还是反握？"},
]

def ask(q, session):
    req = urllib.request.Request("http://localhost:8011/api/chat/simple",
        data=json.dumps({"message": q, "session_id": session}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read().decode())

def clear(session):
    req = urllib.request.Request("http://localhost:8011/api/history/clear",
        data=json.dumps({"session_id": session}).encode(),
        headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=30).read()
    except Exception:
        pass

def signals(reply):
    return {
        "len": len(reply),
        "citations": sorted(set(re.findall(r"《[^》]{2,60}》|[A-Za-z][A-Za-z0-9/\-]*(?:\s+et\s+al\.?)?[,，]?\s*\d{4}", reply))),
        "has_general_note": ("一般经验" in reply) or ("库里没有" in reply) or ("凭经验" in reply),
        "exclaim": reply.count("！") + reply.count("!"),
        "opens_with_conclusion": not reply[:20].startswith(("好的", "收到", "嗯", "哈")),
        "has_question_back": ("？" in reply[-200:]) or ("?" in reply[-200:]),
    }

def main():
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    all_rounds = []
    for rd in range(1, rounds + 1):
        print(f"===== Round {rd}/{rounds} =====", flush=True)
        out = []
        for q in QUESTIONS:
            clear(f"stability-{rd}")
            t0 = time.time()
            d = ask(q["q"], f"stability-{rd}")
            reply = d.get("reply", "")
            sig = signals(reply)
            sig.update({"id": q["id"], "type": q["type"], "elapsed": round(time.time() - t0, 1),
                        "retries": d.get("retries", 0), "model": d.get("model", "")})
            out.append(sig)
            print(f"  {q['id']} {q['type']}: {sig['elapsed']}s len={sig['len']} cites={len(sig['citations'])} retry={sig['retries']}", flush=True)
        all_rounds.append(out)

    # 差异分析
    print("\n===== 稳定性差异分析 =====", flush=True)
    stable = True
    for i, q in enumerate(QUESTIONS):
        lens = [all_rounds[r][i]["len"] for r in range(rounds)]
        cites = [tuple(all_rounds[r][i]["citations"]) for r in range(rounds)]
        notes = [all_rounds[r][i]["has_general_note"] for r in range(rounds)]
        retries = [all_rounds[r][i]["retries"] for r in range(rounds)]
        spread = (max(lens) - min(lens)) / max(1, min(lens))
        cite_set = set(cites)
        flag = []
        if spread > 1.5:
            flag.append(f"长度波动大 {lens}")
            stable = stable and False
        if len(cite_set) > 1:
            flag.append(f"引用不一致 {list(cite_set)}")
        if len(set(notes)) > 1:
            flag.append(f"一般经验标注不一致 {notes}")
        print(f"{q['id']} {q['type']}: lens={lens} cites={len(cite_set)}种 notes={notes} retries={retries}"
              + ("  ⚠️ " + "; ".join(flag) if flag else "  ✅"))
    json.dump({"rounds": all_rounds, "questions": QUESTIONS},
              open("eval/stability_v0.2.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n判定:", "✅ 稳定通过" if stable else "⚠️ 存在波动，看明细", "| saved -> eval/stability_v0.2.json")

if __name__ == "__main__":
    main()
