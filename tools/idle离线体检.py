# -*- coding: utf-8 -*-
"""离线体检：在已落盘的 508 条 Claim 上跑 `idle_recombine`（0 次 API）。

★ 依据（Gemini Q4 第 1 点）：
  「你把 `idle_recombine` 直接跑在这 215 行历史台账上，看它在哪些会话空档里
    配出了哪些跨轮新组合 `(quote_a, quote_b)`，打印出来我们一眼就能像验 C3 一样验它。」

★ 做法：
  按"时间推进"模拟 —— 第 t 轮之后她闲着，用**截至第 t 轮**的 claim 想一次。
  每次想完之后把那两段的 `(turn, start, end)` 记进 `seen`，下一轮不许重复。
"""
import io
import json
import sys

sys.path.insert(0, "engine")
sys.stdout.reconfigure(encoding="utf-8")

from cognition_ops import idle_recombine, session_spans  # noqa: E402

CLAIMS = "spec/cognition抽取_20261029.jsonl"
EVAL = "state/train/eval.jsonl"


def main():
    recs = [json.loads(l) for l in io.open(CLAIMS, encoding="utf-8") if l.strip()]
    rows = [json.loads(l) for l in io.open(EVAL, encoding="utf-8") if l.strip()]
    claims_by_turn = {r["index"]: r["result"]["claims"] for r in recs}
    spans = session_spans(rows)
    print("  数据：%d 轮有 claim｜%d 个会话段" % (len(claims_by_turn), len(spans)))
    print()

    out = []
    seen = []
    for t in range(len(rows)):
        # 只用截至第 t 轮的历史
        upto = {i: cs for i, cs in claims_by_turn.items() if i <= t}
        if len(upto) < 2:
            continue
        th = idle_recombine(upto, rows, seen, spans)
        if th is None:
            continue
        # ★ 来源由产生者给出（`Thought.sources`），不按字符串反查 ——
        #   同一段文本会在不同轮、不同 kind 出现，反查会配错。
        rec = {"at_turn": t, "op": th.op, "quotes": th.quotes,
               "hint": th.hint, "where": th.sources}
        for src in th.sources:
            seen.append((src["turn"], src["start"], src["end"]))
        out.append(rec)

    print("=" * 96)
    print("  自发想跑出了 **%d 条**（在 215 轮里）" % len(out))
    print("=" * 96)
    for r in out:
        where = r.get("where") or []
        print("  第 %d 轮之后｜她闲着时想到：" % r["at_turn"])
        for k, w in enumerate(where):
            print("     [%d] 第 %2d 轮 %-10s subject=%-8r 「%s」"
                  % (k + 1, w["turn"], w["kind"], w["subject"], r["quotes"][k]))
        print("     ⇒ %s" % r["hint"][:110])
        print()

    if not out:
        print("  **一条都没有** —— 说明守卫太严，或历史里确实没有可配的对。")
        print()

    io.open("spec/idle_recombine_离线体检_20261029.jsonl", "w", encoding="utf-8").write(
        "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in out))
    print("  已落盘：spec/idle_recombine_离线体检_20261029.jsonl（%d 条）" % len(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
