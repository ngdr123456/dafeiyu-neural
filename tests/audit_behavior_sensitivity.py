# -*- coding: utf-8 -*-
"""敏感性实测：行为选择到底对机制层的哪些量敏感？

为什么必须先做这一步
────────────────────────────────────────────────────────────
第 3 步要做"让性格影响行为"。而极性变量是**从机制层读出来的**：
    wanting←w  liking←l  patience←a  structure←e  tension←tension
如果机制层的条件表**已经在用**这五个量，那么"让行为读极性变量"
就只是同一个数换了个刻度 —— 一个看起来像功能、实际什么都没加的空转。

所以先测清楚：把每个字段分别扰动，重跑 classify，看结果变不变。
对一个字段"怎么改都不影响结果" → 行为选择对它**不敏感** → 它携带的是新信息。
反过来，若某字段一动结果就变，那从它推出的极性变量就是冗余的。

方法（不读代码，只做实验）
  取台账里每一轮的机制快照 → 对每个字段做正负扰动 → 重新 classify
  → 统计"该字段能改变结果的轮次占比"。
这比读源码可靠：条件表里有 15 条 lambda，人读会漏，实验不会。

⚠️ 只读。
"""
from __future__ import annotations

import os
import sys
from collections import Counter

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_ROOT, os.path.join(_ROOT, "engine"), os.path.join(_ROOT, "state")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import mechanism as M                     # noqa: E402
from experience import load_ledger        # noqa: E402

# 参与扰动的数值字段与布尔字段
NUMERIC = ["w", "l", "novelty", "lean", "delta_r", "a", "e", "tension",
           "completed", "unfinished", "capacity"]
BOOLS = ["askable", "has_attitude", "is_closing", "forbidden_layer1", "tension_measured"]


def rebuild(m: dict) -> M.MechanismState:
    fields = set(M.MechanismState.__dataclass_fields__)
    return M.MechanismState(**{k: v for k, v in m.items() if k in fields})


def main() -> int:
    cfg = M.MechanismConfig()
    rows = [r for r in load_ledger() if r.get("mech")]
    states = []
    for r in rows:
        try:
            states.append(rebuild(r["mech"]))
        except Exception:
            pass
    print("=" * 80)
    print("行为选择敏感性实测：哪些机制量真的会改变选中的行为？")
    print("=" * 80)
    print("可用机制快照 %d 轮" % len(states))

    base = []
    for st in states:
        try:
            base.append(M.classify(st, cfg).id)
        except Exception:
            base.append(None)

    print("\n%-18s %-12s %s" % ("字段", "能改变结果", "含义"))
    print("-" * 80)
    sensitive, insensitive = [], []
    for f in NUMERIC:
        changed = 0
        for st, b in zip(states, base):
            if b is None:
                continue
            cur = getattr(st, f)
            if cur is None:
                continue
            hit = False
            for factor in (0.5, 1.5, 0.0):
                try:
                    st2 = rebuild(st.to_dict())
                    setattr(st2, f, float(cur) * factor)
                    if M.classify(st2, cfg).id != b:
                        hit = True
                        break
                except Exception:
                    continue
            if hit:
                changed += 1
        pct = 100.0 * changed / max(1, len(states))
        (sensitive if changed else insensitive).append((f, pct))
        print("%-18s %-12s" % (f, "%d 轮（%.0f%%）" % (changed, pct)))

    for f in BOOLS:
        changed = 0
        for st, b in zip(states, base):
            if b is None:
                continue
            try:
                st2 = rebuild(st.to_dict())
                setattr(st2, f, not bool(getattr(st, f)))
                if M.classify(st2, cfg).id != b:
                    changed += 1
            except Exception:
                continue
        pct = 100.0 * changed / max(1, len(states))
        (sensitive if changed else insensitive).append((f, pct))
        print("%-18s %-12s" % (f, "%d 轮（%.0f%%）" % (changed, pct)))

    print("\n" + "─" * 80)
    print("结论")
    print("─" * 80)
    print("  行为选择**不敏感**的字段（它们携带的是新信息）：")
    for f, _ in insensitive:
        print("     · %s" % f)
    if not insensitive:
        print("     （无 —— 每个字段都在影响行为）")
    print()
    print("  极性变量 ← 机制量的对应关系，逐条核对：")
    for name, field in (("wanting", "w"), ("liking", "l"), ("patience", "a"),
                        ("structure", "e"), ("tension", "tension")):
        src = "**敏感（冗余）**" if any(f == field for f, _ in sensitive) else "不敏感（新信息）"
        print("     %-10s ← %-10s %s" % (name, field, src))
    print()
    print("  ★ 若五个极性变量全部来自敏感字段，那么『让行为读极性变量』就是空转：")
    print("    同一个数换一个刻度而已，什么都没加。以上表为准。")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
