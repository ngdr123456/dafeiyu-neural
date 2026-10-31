# -*- coding: utf-8 -*-
"""靶向重抽的验收：真阳性保留率 vs 假阳性清除率。

★ 判据（先写，照 Gemini 批复第一节）：
  ① **真阳性保留率**：9 条好样本（3,4,28,43,44,77,93,102,187）里，
     至少 **≥6 条** 依然能抽出对应的两半冲突片段（即算子 4/1/2 之一仍能触发）
  ② **假阳性清除率**：29 条坏样本里，至少 **≥80%（≥23 条）** 不再触发
  ③ 假阳性率应从 80% 掉到 **≤25%**
"""
import io
import json
import sys

sys.path.insert(0, "engine")
sys.stdout.reconfigure(encoding="utf-8")

from cognition_ops import session_spans, think  # noqa: E402

NEW = "spec/cognition抽取_靶向_20261029.jsonl"
EVAL = "state/train/eval.jsonl"

GOOD = [3, 4, 28, 43, 44, 77, 93, 102, 187]
BAD = [1, 2, 16, 27, 36, 38, 39, 49, 50, 54, 58, 63, 79, 81, 87, 89, 92, 94,
       100, 107, 109, 110, 115, 120, 124, 126, 129, 130, 177]


def main():
    recs = {r["index"]: r for r in
            (json.loads(l) for l in io.open(NEW, encoding="utf-8") if l.strip())}
    rows = [json.loads(l) for l in io.open(EVAL, encoding="utf-8") if l.strip()]
    claims_by_turn = {i: r["result"]["claims"] for i, r in recs.items()}
    # ★ 靶向重抽只覆盖 51 行 ⇒ 其余行没有 claim（跨轮历史会变薄，如实标注）
    phase_by_turn = {i: (r.get("mech") or {}).get("phase")
                     for i, r in enumerate(rows) if (r.get("mech") or {}).get("phase")}
    for i, r in enumerate(rows):
        sig = (r.get("input_origin") or {}).get("signature_key")
        if sig:
            r["_signature_key"] = sig
    spans = session_spans(rows)

    out = {}
    for i in sorted(recs):
        t = think(i, claims_by_turn, rows, phase_by_turn, spans)
        if t is not None:
            out[i] = t

    print("  靶向重抽 %d 行 ⇒ 仍触发 %d 行" % (len(recs), len(out)))
    print()

    from collections import Counter
    print("  触发算子分布：%s" % dict(Counter(t.op for t in out.values())))
    print()

    print("=" * 78)
    print("  ① 真阳性保留率（9 条好样本）")
    print("=" * 78)
    kept = [i for i in GOOD if i in out]
    print("  仍在触发的：**%d / %d**" % (len(kept), len(GOOD)))
    for i in GOOD:
        mark = "✓ 保留" if i in out else "✗ 丢失"
        hint = out[i].hint[:56] if i in out else ""
        print("     行 %3d %s  %s" % (i, mark, hint))
    print("  判据 ≥6：**%s**" % ("成立" if len(kept) >= 6 else "不成立"))
    print()

    print("=" * 78)
    print("  ② 假阳性清除率（29 条坏样本）")
    print("=" * 78)
    still = [i for i in BAD if i in out]
    gone = len(BAD) - len(still)
    print("  被清除的：**%d / %d = %.0f%%**" % (gone, len(BAD), 100.0 * gone / len(BAD)))
    print("  仍触发的（我原来的判定是『假』，若仍触发请复核）：")
    for i in still:
        print("     行 %3d %-28s %s" % (i, out[i].op, out[i].hint[:50]))
    print("  判据 ≥80%%（≥23 条）：**%s**"
          % ("成立" if gone >= 23 else "不成立"))
    print()

    print("=" * 78)
    print("  ③ 假阳性率")
    print("=" * 78)
    tot = len(out)
    fp = len(still)
    print("  靶向集里仍触发 %d 条，其中我判为假 %d 条 ⇒ **假阳性率 %.0f%%**（原 80%%）"
          % (tot, fp, 100.0 * fp / max(1, tot)))
    print("  判据 ≤25%%：**%s**" % ("成立" if fp / max(1, tot) <= 0.25 else "不成立"))
    print()

    io.open("spec/cognition_thoughts_靶向_20261029.jsonl", "w", encoding="utf-8").write(
        "".join(json.dumps({"index": i, "op": t.op, "quotes": t.quotes,
                            "hint": t.hint, "yielded": t.yielded,
                            "input": (rows[i].get("input") or "").strip()},
                           ensure_ascii=False) + "\n"
                for i, t in sorted(out.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
