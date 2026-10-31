# -*- coding: utf-8 -*-
"""2 场 × 6 轮同题连贯长会话实测（2026-10-29，Gemini 第 ③ 步）。

★ 这是第一次在**四项全开**下跑：
  · 同题连贯 6 轮（`train.py` 的种子共享已修好，不再每轮换题）
  · 去助手化三件套（FRAME_SYSTEM 存在姿态 / DILEMMA / 按需 FACT_GUIDE）
  · 意识海（当轮算子 / 空档回想 / 2 环连锁 / 自主悬念 unfinished_focus）
  · 第一人称授权

★ 成本：2 场 × 6 轮 ×（抽取 2 + 生成 1 + 家教 1）≈ 48 次调用
"""
import io
import json
import os
import re
import sys
import tempfile
import time

sys.path.insert(0, "engine")
sys.stdout.reconfigure(encoding="utf-8")

from pipeline import Pipeline   # noqa: E402
from train import load_topics  # noqa: E402
from understand import ApiReader  # noqa: E402
from train import Tutor  # noqa: E402

WANT = re.compile(r"我想(知道|问|听|看看|了解)|我好奇|我在想|我一直在想|我惦记")
CONT = re.compile(r"我(刚才|上一轮|前面|一直|刚)|上次我|我之前说|我想了一|还挂着")
ASSIST = re.compile(r"我替你(定|挑|判|决定|选)|决定权在你|这得看你自己|我帮不了你")

SESSIONS = 2
LEN = 6


def main():
    rd = ApiReader()
    if not rd.available:
        print("  ★ API 不可用")
        return 2
    tt = Tutor(rd)
    stems = load_topics()
    import random
    rnd = random.Random(20261029)
    seeds = rnd.sample(stems, SESSIONS)

    all_turns = []
    t0 = time.time()
    for si, seed in enumerate(seeds, 1):
        d = tempfile.mkdtemp()
        p = Pipeline(ledger_path=os.path.join(d, "state/ledger.jsonl"),
                     character_path=os.path.join(d, "state/character.json"),
                     devlevel_path=os.path.join(d, "state/devlevel_verified.json"),
                     carry_root=d, gate_perception=True, auto_audit=False,
                     use_api=True, use_think=True, use_cognition=True)
        p._input_origin = None
        hist = []
        stem = (seed.get("text") or seed.get("title") or str(seed))[:120]
        print("=" * 92)
        print("  第 %d 场｜种子题面：%s" % (si, stem[:60]))
        print("=" * 92)
        for n in range(1, LEN + 1):
            said = tt.speak(stem, hist)
            if not said:
                print("  [%d/%d] ★ 家教没说出话，本场中止" % (n, LEN))
                break
            e0 = len(p.ledger.effective_entries)
            t1 = time.time()
            res = p.turn(said)
            dt = time.time() - t1
            out = (res.output or "").strip()
            e = (p.ledger.effective_entries[-1]
                 if len(p.ledger.effective_entries) > e0 else None)
            cog = (getattr(e, "cognition", None) or {}) if e is not None else {}
            act = (getattr(res, "action_observation", None) or {})
            uf = getattr(p, "_unfinished_focus", None)
            rec = {"session": si, "turn": n, "stem": stem[:60], "user": said,
                   "her": out, "seconds": round(dt, 1),
                   "cog_op": cog.get("op"), "cog_quotes": cog.get("quotes"),
                   "idle": cog.get("idle"),
                   "thought_level": act.get("thought_level"),
                   "actual": act.get("actual"),
                   "unfinished_focus": (uf or {}).get("quotes"),
                   # ★ 2026-10-29：把 claims 与 ruminate 状态也存下来 ——
                   #   否则"空档回想 0 次"永远只能猜（claim 的 kind/subject 是判据）。
                   "claims": cog.get("claims") or [],
                   "idle_error": getattr(p, "_idle_error", ""),
                   "cog_claims_turns": sorted(getattr(p, "_cog_claims", {}).keys()),
                   "want": bool(WANT.search(out)), "cont": bool(CONT.search(out)),
                   "assistant_tone": bool(ASSIST.search(out))}
            all_turns.append(rec)
            hist.append((said, out))
            print("  [%d/%d] %4.1fs 他：%s" % (n, LEN, dt, said[:56]))
            print("          她：%s" % (out[:66] or "（空）"))
            print("          动作=%-24s 思考=%s%s"
                  % (act.get("actual"), cog.get("op") or "—",
                     ("｜★悬念仍在" if (uf or {}).get("quotes") else "")))
            if cog.get("quotes"):
                print("          引文=%r" % ((cog.get("quotes") or [])[:2],))
            if (cog.get("idle") or {}).get("op"):
                print("          ☆空档回想=%r" % ((cog["idle"].get("quotes") or [])[:2],))
            print()

    el = time.time() - t0
    print("=" * 92)
    print("  统计（%d 场 × 最多 %d 轮，实际 %d 轮｜%.0f 秒）"
          % (SESSIONS, LEN, len(all_turns), el))
    print("=" * 92)
    n = len(all_turns) or 1
    print("  第一人称「想要/好奇」：**%d / %d**" % (sum(1 for r in all_turns if r["want"]), n))
    for r in all_turns:
        if r["want"]:
            print("     第%d场-第%d轮：%s" % (r["session"], r["turn"], r["her"][:70]))
    print("  自我连续性（我刚才/还挂着）：**%d / %d**" % (sum(1 for r in all_turns if r["cont"]), n))
    for r in all_turns:
        if r["cont"]:
            print("     第%d场-第%d轮：%s" % (r["session"], r["turn"], r["her"][:70]))
    print("  ★ 助手腔（我替你定/决定权在你）：**%d / %d**"
          % (sum(1 for r in all_turns if r["assistant_tone"]), n))
    print("  自主悬念曾被记下：%d / %d" % (sum(1 for r in all_turns if r["unfinished_focus"]), n))
    print()
    from collections import Counter
    print("  当轮算子：%s" % dict(Counter(r["cog_op"] for r in all_turns if r["cog_op"])))
    print("  空档回想：%d 次" % sum(1 for r in all_turns if (r.get("idle") or {}).get("op")))

    io.open("spec/2场6轮同题实测_20261029.jsonl", "w", encoding="utf-8").write(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in all_turns))
    print()
    print("  已落盘：spec/2场6轮同题实测_20261029.jsonl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
