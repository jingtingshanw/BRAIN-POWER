"""22 题深度评测（v2 版）：每题清空历史防污染，自动统计引用落地/工具使用/速度。"""
import json
import time
import urllib.request
from pathlib import Path

sys_path = str(Path(__file__).resolve().parent.parent)
import sys
sys.path.insert(0, sys_path)

BASE = "http://localhost:8011"


def clear_history():
    req = urllib.request.Request(f"{BASE}/api/admin/clear-history", method="POST",
                                 data=json.dumps({"session_id": "eval"}).encode(),
                                 headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=30).read()


def run_one(q: str):
    t0 = time.time()
    req = urllib.request.Request(f"{BASE}/api/chat/simple",
        data=json.dumps({"message": q, "session_id": "eval"}).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        d = json.loads(r.read().decode())
    return d, round(time.time() - t0, 1)


def main():
    import yaml
    root = Path(__file__).resolve().parent.parent
    qs = yaml.safe_load((root / "eval" / "questions.yaml").read_text(encoding="utf-8"))["questions"]
    out = []
    for i, q in enumerate(qs, 1):
        print(f"[{i}/{len(qs)}] {q['id']}", flush=True)
        clear_history()
        d, t = run_one(q["q"])
        out.append({"id": q["id"], "dim": q["dim"], "question": q["q"], "reply": d.get("reply", ""),
                    "tools": [c.get("name") for c in d.get("tool_calls", [])],
                    "usage": d.get("usage", {}), "model": d.get("model"), "retries": d.get("retries", 0),
                    "elapsed_s": t})
        print(f"  {t}s tools={out[-1]['tools'][:4]}", flush=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    path = root / "eval" / f"results_{stamp}.json"
    path.write_text(json.dumps({"results": out}, ensure_ascii=False, indent=1), encoding="utf-8")

    import re
    cited = sum(1 for r in out if re.search(r"《[^》]+》|[（(][^（）()]{2,30}[,，]\s*\d{4}[)）]", r["reply"]))
    used_tools = sum(1 for r in out if r["tools"])
    rag_used = sum(1 for r in out if "rag_search" in r["tools"])
    print(f"\n==== 汇总（模型 {out[0]['model']}）====")
    print(f"知识检索使用：{rag_used}/{len(out)} | 工具使用：{used_tools}/{len(out)} | 引用落地（含出处格式）：{cited}/{len(out)}")
    print(f"平均耗时 {sum(r['elapsed_s'] for r in out)/len(out):.1f}s | 平均 tokens {sum(r['usage'].get('total_tokens',0) for r in out)/len(out):.0f}")
    print(f"saved -> {path.name}")


if __name__ == "__main__":
    main()
