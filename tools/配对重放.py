# -*- coding: utf-8 -*-
"""24 轮家教历史原话配对重放（Gemini 第四封的封板验收）。

★ 为什么用配对重放而不是跑 train.py：
  `train.py:481` 的 `picks = list(rnd.choice(usable)["turns"])` 在
  `session_len == 3` 时会把 3 个位置一上来就填满，`while` 一次都不执行，
  于是 100% 抽到 `sequences.json`（押金/楼层）—— 那就是上次"78%"被污染的原因。
  ⇒ 这次直接重放**历史真实原话**（eval.jsonl 191–214），输入不变、只换系统。

★ 判据（先写，照 Gemini 第四封）：
  ① META 劫持率：旧 83%（20/24 是 META_REPLY）⇒ 预期显著下降
  ② 长陈述回声率（非问句 且 >18 字 且 新词占比 ≤0.30）⇒ 预期下降
  ③ 精准锚点追问率（抽出 anchor 的轮次中，输出含 anchor 且（问句 或 ≤18 字））⇒ 预期上升

★ 数据集：eval.jsonl 第 191–214 行 = 12 个 2 轮会话，全部是家教生成的真实倾诉。
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

from pipeline import Pipeline          # noqa: E402
from respond import Responder          # noqa: E402

EVAL = "state/train/eval.jsonl"
OUT = "spec/配对重放_20261028.jsonl"
LO, HI = 191, 215


def new_rate(out, user):
    if not out:
        return 0.0
    return sum(1 for ch in out if ch not in user) / len(out)


def main():
    rows = [json.loads(l) for l in io.open(EVAL, encoding="utf-8") if l.strip()][LO:HI]
    R = Responder()
    pairs = [(rows[i], rows[i + 1]) for i in range(0, len(rows) - 1, 2)]
    print("  重放 %d 个会话 × 2 轮 = %d 轮" % (len(pairs), len(pairs) * 2))
    print()

    recs = []
    t0 = time.time()
    for si, (a, b) in enumerate(pairs, 1):
        d = tempfile.mkdtemp()
        p = Pipeline(ledger_path=os.path.join(d, "state/ledger.jsonl"),
                     character_path=os.path.join(d, "state/character.json"),
                     devlevel_path=os.path.join(d, "state/devlevel_verified.json"),
                     carry_root=d, gate_perception=True, auto_audit=False,
                     use_api=True, use_think=True)
        for ti, r in enumerate((a, b), 1):
            raw = (r.get("input") or "").strip()
            t1 = time.time()
            try:
                res = p.turn(raw)
                out = res.output or ""
                planned = res.planned_behavior
                channel = res.channel
                actual = (res.action_observation or {}).get("actual")
            except Exception as exc:                              # noqa: BLE001
                out, planned, channel, actual = "", "ERROR:%s" % type(exc).__name__, "", ""
                res = None
            dt = time.time() - t1
            _k, anchor = R._pick_anchor(raw)
            hit = bool(anchor) and anchor in out and (
                bool(re.search(r"[？?]", out)) or len(out) <= 18)
            rec = {"session": si, "turn": ti,
                   "input": raw, "old_output": (r.get("output") or "").strip(),
                   "old_planned": r.get("planned_behavior"),
                   "new_output": out, "new_planned": planned,
                   "channel": channel, "actual": actual,
                   "anchor": anchor, "anchor_hit": hit,
                   "seconds": round(dt, 1)}
            recs.append(rec)
            print("  [%2d-%d] %-12s→%-12s anchor=%-8r hit=%-5s %5.1fs | %s"
                  % (si, ti, rec["old_planned"], planned, anchor, hit, dt, out[:26]), flush=True)
        # 落盘（断点可读）
        with io.open(OUT, "a", encoding="utf-8") as fh:
            for rec in recs[-2:]:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    el = time.time() - t0
    print()
    print("  完成：%d 轮｜%.0f 秒｜均 %.1f 秒/轮" % (len(recs), el, el / max(1, len(recs))))
    print()

    # ---------- 三条判据 ----------
    def meta_rate(rs, key):
        return sum(1 for r in rs if r[key] == "META_REPLY")

    old_meta = meta_rate(recs, "old_planned")
    new_meta = meta_rate(recs, "new_planned")
    print("  ① META 劫持率：旧 **%d/%d = %.0f%%** → 新 **%d/%d = %.0f%%**"
          % (old_meta, len(recs), 100.0 * old_meta / len(recs),
             new_meta, len(recs), 100.0 * new_meta / len(recs)))

    def echo(rs, key, rawkey):
        n = 0
        for r in rs:
            o = r[key] or ""
            if re.search(r"[？?]", o):
                continue
            if len(o.strip()) <= 18:
                continue
            if new_rate(o, r[rawkey]) <= 0.30:
                n += 1
        return n

    old_e = echo(recs, "old_output", "input")
    new_e = echo(recs, "new_output", "input")
    print("  ② 长陈述回声率：旧 **%d/%d = %.0f%%** → 新 **%d/%d = %.0f%%**"
          % (old_e, len(recs), 100.0 * old_e / len(recs),
             new_e, len(recs), 100.0 * new_e / len(recs)))

    have = [r for r in recs if r["anchor"]]
    hit = sum(1 for r in have if r["anchor_hit"])
    print("  ③ 精准锚点追问率：抽出锚点 %d 轮，命中 **%d/%d = %.0f%%**（旧基线 0/15 = 0%%）"
          % (len(have), hit, max(1, len(have)), 100.0 * hit / max(1, len(have))))
    print()
    print("  明细已落盘：%s" % OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
