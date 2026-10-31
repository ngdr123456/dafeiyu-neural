# -*- coding: utf-8 -*-
"""C4 实测：把已抽好的 Thought 注入 Frame，看她的真实造句形态。

★ 依据（Gemini 批复第三节）：
  不重跑抽取器 —— 直接用 `spec/cognition_thoughts_靶向_20261029.jsonl` 里那 16 条
  Thought，注入 `Frame`，跑 `Thinker` 生成，与**旧系统输出**（eval.jsonl）对照。

★ 判据（先写）：
  ① 每行的新输出**是否逐字包含** Thought 的两段引文（至少一段）
  ② 新输出是否**更短、更少以"你用了这样一句话"开头**
  ③ 人眼判断：这次是不是"接住了那两处拉扯"

★ 成本：16 行 × (1 次生成 + 1 次保真核对) ≈ 32–48 次调用
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

from cognition_ops import Thought          # noqa: E402
from pipeline import Pipeline              # noqa: E402

TH = "spec/cognition_thoughts_靶向_20261029.jsonl"
EVAL = "state/train/eval.jsonl"


def main():
    ths = [json.loads(l) for l in io.open(TH, encoding="utf-8") if l.strip()]
    rows = [json.loads(l) for l in io.open(EVAL, encoding="utf-8") if l.strip()]
    print("  待跑 %d 条触发行" % len(ths))
    print()

    out = []
    t0 = time.time()
    for n, x in enumerate(ths, 1):
        i = x["index"]
        raw = (rows[i].get("input") or "").strip()
        old = (rows[i].get("output") or "").strip()
        th = Thought(x["op"], x["quotes"], x["hint"])
        d = tempfile.mkdtemp()
        p = Pipeline(ledger_path=os.path.join(d, "state/ledger.jsonl"),
                     character_path=os.path.join(d, "state/character.json"),
                     devlevel_path=os.path.join(d, "state/devlevel_verified.json"),
                     carry_root=d, gate_perception=True, auto_audit=False,
                     use_api=True, use_think=True)
        p._input_origin = None
        p._pending_thought = th
        t1 = time.time()
        try:
            res = p.turn(raw)
            new = (res.output or "").strip()
            notes = list(res.notes or [])
        except Exception as exc:                               # noqa: BLE001
            new, notes = "", ["ERROR:%s" % type(exc).__name__]
        dt = time.time() - t1
        hit = [q for q in x["quotes"] if q and q in new]
        rec = {"index": i, "op": x["op"], "quotes": x["quotes"],
               "hint": x["hint"], "raw": raw, "old": old, "new": new,
               "hit": hit, "seconds": round(dt, 1),
               "notes": [z for z in notes if "渲染" in z or "退回" in z][:2]}
        out.append(rec)
        print("  [%2d/%2d] %4.1fs 引文命中 %d/%d｜新：%s"
              % (n, len(ths), dt, len(hit), len(x["quotes"]), new[:52]), flush=True)

    el = time.time() - t0
    print()
    print("  完成：%d 行｜%.0f 秒｜均 %.1f 秒/行" % (len(out), el, el / max(1, len(out))))
    print()

    # ---------- 判据 ----------
    any_hit = sum(1 for r in out if r["hit"])
    both = sum(1 for r in out if len(r["hit"]) >= 2)
    print("  ① 引文命中：至少一段 **%d/%d**｜两段都中 **%d/%d**"
          % (any_hit, len(out), both, len(out)))
    n_old_tpl = sum(1 for r in out if "你用了这样一句话" in r["old"])
    n_new_tpl = sum(1 for r in out if "你用了这样一句话" in r["new"])
    print("  ② 「你用了这样一句话」：旧 **%d** → 新 **%d**" % (n_old_tpl, n_new_tpl))
    Ln = sorted(len(r["new"]) for r in out)
    Lo = sorted(len(r["old"]) for r in out)
    print("     输出长度中位：旧 %d → 新 **%d**" % (Lo[len(Lo) // 2], Ln[len(Ln) // 2]))
    n_q = sum(1 for r in out if re.search(r"[？?]", r["new"]))
    print("     含问号：新 **%d/%d**" % (n_q, len(out)))
    print()

    print("=" * 100)
    print("  对照表（人眼看这一张）")
    print("=" * 100)
    for r in out:
        print("  行 %3d｜%-28s" % (r["index"], r["op"]))
        print("     他：%s" % r["raw"][:76])
        print("     思：一边「%s」 ｜ 另一边「%s」" % tuple((r["quotes"] + ["", ""])[:2]))
        print("     旧：%s" % (r["old"][:76] or "（无）"))
        print("     新：%s   ← 引文命中 %d/2" % (r["new"][:76] or "（空）", len(r["hit"])))
        print()

    io.open("spec/cognition_C4实测_20261029.jsonl", "w", encoding="utf-8").write(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out))
    print("  已落盘：spec/cognition_C4实测_20261029.jsonl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
