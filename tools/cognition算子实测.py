# -*- coding: utf-8 -*-
"""零 API：在已落盘的 508 条 Claim 上离线跑算子 1–4。

★ 判据（先写，照 Gemini 批复第二节）：
  · **0 次 API 调用**，纯本地读 spec/cognition抽取_20261029.jsonl + state/train/eval.jsonl
  · 跨轮匹配**必须**在同一会话内（否则第 11 行和第 104 行会被硬凑）
  · 报出算子 1/2/3/4 各自**真实触发次数**（不是估算）
  · **把所有触发出来的 Thought 全部列出**（算子名、两条原话、hint、行号）供人眼质检
"""
import io
import json
import sys

sys.path.insert(0, "engine")
sys.stdout.reconfigure(encoding="utf-8")

from cognition_ops import (OP_ORDER, Thought, normalize_subject,  # noqa: E402
                           session_spans, think)

CLAIMS = "spec/cognition抽取_20261029.jsonl"
EVAL = "state/train/eval.jsonl"


def main():
    recs = [json.loads(l) for l in io.open(CLAIMS, encoding="utf-8") if l.strip()]
    rows = [json.loads(l) for l in io.open(EVAL, encoding="utf-8") if l.strip()]
    claims_by_turn = {r["index"]: r["result"]["claims"] for r in recs}
    phase_by_turn = {}
    for i, r in enumerate(rows):
        ph = (r.get("mech") or {}).get("phase")
        if ph:
            phase_by_turn[i] = ph
        sig = (r.get("input_origin") or {}).get("signature_key")
        if sig:
            r["_signature_key"] = sig

    spans = session_spans(rows)
    n_real = sum(1 for a, b in spans
                 if (rows[a].get("input_origin") or {}).get("session_id") is not None)
    print("  会话切分：%d 段（其中 %d 段有**真** session_id，其余用 ts 间隔近似）"
          % (len(spans), n_real))
    from collections import Counter
    sz = Counter(b - a for a, b in spans)
    print("  段长分布：%s" % dict(sorted(sz.items())[:8]))
    print()

    thoughts = []
    for i in range(len(rows)):
        t = think(i, claims_by_turn, rows, phase_by_turn, spans)
        if t is not None:
            thoughts.append((i, t))

    print("=" * 80)
    print("  真实触发次数")
    print("=" * 80)
    c = Counter(t.op for _, t in thoughts)
    for op in OP_ORDER[:-1]:
        print("  %-30s **%d** 次" % (op, c.get(op, 0)))
    print("  %-30s %d 次（兜底，不进 Thought）" % ("CONCRETE_CURIOSITY", 0))
    print("  合计触发：**%d / %d = %.1f%%** 的轮次"
          % (len(thoughts), len(rows), 100.0 * len(thoughts) / len(rows)))
    print()

    print("=" * 80)
    print("  全部 Thought（供人眼质检）")
    print("=" * 80)
    for i, t in thoughts:
        raw = (rows[i].get("input") or "").strip()
        print("  行 %3d｜%-28s%s" % (i, t.op,
                                     ("  ｜让位=%s" % t.yielded) if t.yielded else ""))
        for q in t.quotes:
            print("        quote: %r" % q)
        print("        hint : %s" % t.hint)
        print("        原话 : %s" % raw[:60])
        print()

    # 落盘
    out = [{"index": i, "op": t.op, "quotes": t.quotes, "hint": t.hint,
            "yielded": t.yielded, "input": (rows[i].get("input") or "").strip()}
           for i, t in thoughts]
    io.open("spec/cognition_thoughts_20261029.jsonl", "w", encoding="utf-8").write(
        "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in out))
    print("  已落盘：spec/cognition_thoughts_20261029.jsonl（%d 条）" % len(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
