"""模型选型横评脚本（PRD §6.2，W3 执行）。
用法：改 .env 的 MODEL_PRIMARY 为候选模型 → python scripts/model_bakeoff.py → 结果追加 eval/bakeoff-*.md
维度：22 题回答质量（人工评）+ 工具调用成功率 + 速度 + 单次成本（自动）。
"""
import json
import sys
import time
from pathlib import Path

import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
BASE = "http://localhost:8011"


def run_one(q: str):
    t0 = time.time()
    req = urllib.request.Request(f"{BASE}/api/chat/simple",
        data=json.dumps({"message": q}).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        d = json.loads(r.read().decode())
    return {"reply": d.get("reply", ""), "tools": [c["name"] for c in d.get("tool_calls", [])],
            "usage": d.get("usage", {}), "model": d.get("model"), "elapsed_s": round(time.time() - t0, 1)}


def main():
    import yaml
    qs = yaml.safe_load((Path(__file__).resolve().parent.parent / "eval" / "questions.yaml").read_text(encoding="utf-8"))
    out = []
    for i, q in enumerate(qs, 1):
        print(f"[{i}/{len(qs)}] {q['id']}", flush=True)
        rec = {"id": q["id"], "dim": q["dim"], "question": q["q"], **run_one(q["q"])}
        out.append(rec)
        # 每题独立 session 防污染
    stamp = time.strftime("%Y%m%d_%H%M%S")
    path = Path(__file__).resolve().parent.parent / "eval" / f"bakeoff_{stamp}.json"
    path.write_text(json.dumps({"results": out}, ensure_ascii=False, indent=1), encoding="utf-8")
    ok = sum(1 for r in out if r["tools"])
    avg_t = sum(r["elapsed_s"] for r in out) / len(out)
    avg_tok = sum(r["usage"].get("total_tokens", 0) for r in out) / len(out)
    print(f"\n模型={out[0]['model']}\n工具调用使用率 {ok}/{len(out)} | 平均耗时 {avg_t:.1f}s | 平均 tokens {avg_tok:.0f}")
    print(f"saved -> {path.name}（回答质量人工评审后填入 eval/bakeoff 报告）")


if __name__ == "__main__":
    main()
