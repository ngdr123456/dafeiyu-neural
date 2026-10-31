# -*- coding: utf-8 -*-
"""12 轮真实开启实验：`use_cognition=True`。

★ 依据（Gemini 第 ③ 步）：
  「显式打开 `--cognition` 跑一次小规模多轮实测…
    看看那两个 `0 / 40`（第一人称想要 / 自我连续性）破零了没有」

★ 输入：`state/train/eval.jsonl` 里连续 N 行真实历史原话，按顺序跑成一段连续对话。
  ⚠️ 如实说明：这 N 行**不是同一个真实会话**，是从语料里取的连续块。
     所以"跨轮"是真跨轮（同一个 Pipeline 连续 N 轮），"同一段对话"是构造的。

⚠️ 本工具的 `except` **一律把异常打印出来** —— 这个项目里我已经三次因为
   `except: pass` 把真错盖住（`time` 未导入、恢复循环位置错、这里），
   所以这一版宁可不捕获，捕获了也一定要响。
"""
import io
import json
import os
import re
import sys
import tempfile
import time
from collections import Counter

sys.path.insert(0, "engine")
sys.stdout.reconfigure(encoding="utf-8")

from pipeline import Pipeline  # noqa: E402

EVAL = "state/train/eval.jsonl"
START = int(sys.argv[1]) if len(sys.argv) > 1 else 0
N = int(sys.argv[2]) if len(sys.argv) > 2 else 12

WANT = re.compile(r"我想(知道|问|听|看看|了解)|我好奇|我在想|我一直在想|我惦记")
CONT = re.compile(r"我(刚才|上一轮|前面|一直|刚)|上次我|我之前说|我想了一")


def main():
    rows = [json.loads(l) for l in io.open(EVAL, encoding="utf-8") if l.strip()]
    todo = [(i, r) for i, r in enumerate(rows)
            if (r.get("input") or "").strip()][START:START + N]
    d = tempfile.mkdtemp()
    p = Pipeline(ledger_path=os.path.join(d, "state/ledger.jsonl"),
                 character_path=os.path.join(d, "state/character.json"),
                 devlevel_path=os.path.join(d, "state/devlevel_verified.json"),
                 carry_root=d, gate_perception=True, auto_audit=False,
                 use_api=True, use_think=True, use_cognition=True)
    p._input_origin = None
    print("  待跑 %d 轮｜use_cognition=%s｜thinker=%s｜reader=%s"
          % (len(todo), getattr(p, "use_cognition", None),
             p.thinker is not None, getattr(p, "reader", None) is not None))
    print()

    out = []
    t0 = time.time()
    for n, (i, r) in enumerate(todo, 1):
        raw = (r.get("input") or "").strip()
        t1 = time.time()
        said, err = "", ""
        try:
            res = p.turn(raw)
            said = (res.output or "").strip()
        except Exception as exc:                                  # noqa: BLE001
            err = "%s: %s" % (type(exc).__name__, exc)
            print("         ★★ 异常：%s" % err, flush=True)
        dt = time.time() - t1
        e = (p.ledger.effective_entries[-1] if p.ledger.effective_entries else None)
        cog = (getattr(e, "cognition", None) or {}) if e is not None else {}
        rec = {"n": n, "eval_row": i, "raw": raw, "said": said, "error": err,
               "cog_op": cog.get("op"), "cog_quotes": cog.get("quotes"),
               "cog_origin": cog.get("origin"), "idle": cog.get("idle"),
               "seconds": round(dt, 1),
               "want": bool(WANT.search(said)), "cont": bool(CONT.search(said))}
        out.append(rec)
        print("  [%2d/%2d] %4.1fs 他：%s" % (n, len(todo), dt, raw[:40]), flush=True)
        print("         她：%s" % (said[:66] or "（空）"), flush=True)
        if cog.get("op"):
            print("         ★ 思考：%s %r" % (cog["op"], (cog.get("quotes") or [])[:2]),
                  flush=True)
        if (cog.get("idle") or {}).get("op"):
            print("         ☆ 空档回想：%r"
                  % ((cog["idle"].get("quotes") or [])[:2],), flush=True)

    el = time.time() - t0
    print()
    print("  完成：%d 轮｜%.0f 秒｜均 %.1f 秒/轮" % (len(out), el, el / max(1, len(out))))
    print()
    print("=" * 92)
    print("  ★ 两个 0/40 破零了吗")
    print("=" * 92)
    nw = sum(1 for r in out if r["want"])
    nc = sum(1 for r in out if r["cont"])
    print("  第一人称「想要/好奇」：**%d / %d**" % (nw, len(out)))
    for r in out:
        if r["want"]:
            print("     轮 %2d：%s" % (r["n"], r["said"][:72]))
    print("  自我连续性（我刚才/我上一轮/我一直在想）：**%d / %d**" % (nc, len(out)))
    for r in out:
        if r["cont"]:
            print("     轮 %2d：%s" % (r["n"], r["said"][:72]))
    nerr = sum(1 for r in out if r["error"])
    if nerr:
        print("  ★ 异常轮数：%d（见 JSONL 的 error 字段）" % nerr)
    print()
    print("=" * 92)
    print("  算子触发统计")
    print("=" * 92)
    print("  当轮算子：%s" % dict(Counter(r["cog_op"] for r in out if r["cog_op"])))
    print("  空档回想：%d 次｜连锁：%d 次" % (
        sum(1 for r in out if (r.get("idle") or {}).get("op")),
        sum(1 for r in out if r["cog_op"] == "CHAIN_EXTENSION")))

    io.open("spec/cognition_12轮实测_20261029.jsonl", "w", encoding="utf-8").write(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out))
    print()
    print("  已落盘：spec/cognition_12轮实测_20261029.jsonl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
