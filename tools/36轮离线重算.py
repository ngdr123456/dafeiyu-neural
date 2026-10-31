# -*- coding: utf-8 -*-
"""0 API：拿刚跑完的 36 轮台账，离线重算 idle_recombine / CONFIRMED / REBUFFED。

★ 用途（Gemini 第 ③ 节）：
  验证"空档回想 0 次"到底是不是他说的死锁，以及那 5 次 BOLD 里未确认的 2 次是谁。
"""
import io
import json
import sys

sys.path.insert(0, "engine")
sys.stdout.reconfigure(encoding="utf-8")

from association import classify_encounter  # noqa: E402
from cognition_ops import idle_recombine, session_spans, subject_compatible  # noqa: E402

LEDGER = "state/train/ledger.jsonl"


def main():
    rs = [json.loads(l) for l in io.open(LEDGER, encoding="utf-8") if l.strip()]
    rs = [e for e in rs if (e.get("raw_input") or "").strip()]
    last = rs[-36:]
    print("  台账 %d 轮，取最后 %d 轮" % (len(rs), len(last)))

    claims_by_turn = {}
    for i, e in enumerate(last):
        cog = e.get("cognition") or {}
        cl = cog.get("claims") or []
        if cl:
            claims_by_turn[i] = cl
    print("  有 claims 的轮：%d / %d" % (len(claims_by_turn), len(last)))
    print()

    # ── ① BOLD 与遭遇重算
    print("=" * 88)
    print("  ① 五次 BOLD 的明细 + 未确认的那两次是谁")
    print("=" * 88)
    for i, e in enumerate(last):
        act = e.get("action_observation") or {}
        cog = e.get("cognition") or {}
        bold = (act.get("actual") == "THOUGHT_EXECUTED_STRONG"
                or act.get("thought_level") in ("STRONG", "WEAK")
                or (bool(cog.get("op")) and act.get("actual") == "QUESTION"))
        if not bold:
            continue
        nxt = last[i + 1] if i + 1 < len(last) else None
        enc = classify_encounter(e, nxt) if nxt else ""
        cur = (e.get("raw_input") or "").strip()
        nx = ((nxt or {}).get("raw_input") or "").strip()
        cur_txt = {c.get("text") for c in ((e.get("cognition") or {}).get("claims") or [])}
        nx_txt = {c.get("text") for c in (((nxt or {}).get("cognition") or {}).get("claims") or [])}
        newc = nx_txt - cur_txt
        print("  轮 %2d｜op=%-26s level=%-6s actual=%-22s → **%s**"
              % (i + 1, cog.get("op") or "—", act.get("thought_level") or "",
                 act.get("actual"), enc or "（既非也）"))
        print("      她：%s" % (e.get("output") or "")[:64])
        if nxt is not None:
            print("      他下一轮（%d 字 / 上轮 %d 字 = %.2f）：%s"
                  % (len(nx), len(cur), len(nx) / max(1, len(cur)), nx[:60]))
            print("      新 claim：%s｜is_closing：%s"
                  % (len(newc), bool(((nxt.get("mech") or {}).get("is_closing")))))
        print()

    # ── ② idle_recombine 重算（当前规则）
    print("=" * 88)
    print("  ② idle_recombine 在当前规则下能配出几条")
    print("=" * 88)
    spans = [(0, len(last))]
    seen = []
    got = 0
    for t in range(len(last)):
        upto = {i: cs for i, cs in claims_by_turn.items() if i <= t}
        if len(upto) < 2:
            continue
        th = idle_recombine(upto, last, seen, spans)
        if th is None:
            continue
        got += 1
        print("  轮 %2d 之后：%r" % (t + 1, th.quotes))
        for s in (th.sources or []):
            seen.append((s["turn"], s["start"], s["end"]))
    print()
    print("  ⇒ 当前规则跑出 **%d** 条" % got)

    # ── ③ 死锁验证：dist==1 的合法对，有多少被 think() 吃掉了
    print()
    print("=" * 88)
    print("  ③ 死锁验证：每轮 think() 产出的 quotes 是否覆盖了所有 dist==1 的合法对")
    print("=" * 88)
    eaten = []
    for i, e in enumerate(last):
        cog = e.get("cognition") or {}
        if not cog.get("quotes"):
            continue
        srcs = cog.get("sources") or []
        turns = [s.get("turn") for s in srcs if isinstance(s.get("turn"), int)]
        if len(turns) >= 2:
            eaten.append((i + 1, sorted(set(turns)), cog.get("op"), cog.get("quotes")))
    for t, turns, op, qs in eaten:
        print("  轮 %2d｜op=%-28s 引用了轮次 %s｜%r" % (t, op, turns, qs[:2]))
    print()
    print("  ⇒ think() 吃过 **%d** 对" % len(eaten))

    # ── ④ 若放开 dist<=5（同 session），能多出几条？
    print()
    print("=" * 88)
    print("  ④ 若放开到 dist<=5（同会话），能多出几条")
    print("=" * 88)
    import cognition_ops as cops
    old = cops.subject_compatible

    def relaxed(c1, c2, *, same_session=True, t1=0, t2=0):
        s1 = cops.normalize_subject(c1.get("subject", "") or "")
        s2 = cops.normalize_subject(c2.get("subject", "") or "")
        d = abs(int(t1) - int(t2))
        pron = {"他", "她", "它", "那", "这", "对方"}
        if s1 and s2 and s1 != s2 and not (s1 in s2 or s2 in s1) \
                and not (s1 in pron or s2 in pron):
            return False
        if d == 0:
            return True
        if same_session and d <= 5:
            return bool(s1 or s2)
        return bool(s1 and s2 and (s1 == s2 or s1 in s2 or s2 in s1))

    cops.subject_compatible = relaxed
    seen2 = []
    got2 = 0
    for t in range(len(last)):
        upto = {i: cs for i, cs in claims_by_turn.items() if i <= t}
        if len(upto) < 2:
            continue
        th = cops.idle_recombine(upto, last, seen2, spans)
        if th is None:
            continue
        got2 += 1
        srcs = th.sources or []
        d = abs(srcs[0]["turn"] - srcs[1]["turn"]) if len(srcs) > 1 else 0
        print("  轮 %2d 之后（dist=%d）：%r" % (t + 1, d, th.quotes))
        for s in srcs:
            seen2.append((s["turn"], s["start"], s["end"]))
    cops.subject_compatible = old
    print()
    print("  ⇒ 放开到 dist<=5 跑出 **%d** 条（原 %d 条）" % (got2, got))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
