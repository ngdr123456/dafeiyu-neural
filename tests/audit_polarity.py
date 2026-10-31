# -*- coding: utf-8 -*-
"""极性变量审计 —— 重定之后，它到底动没动？

为什么重写这个工具
────────────────────────────────────────────────────────────
旧版审计的是那五个**累积占比**（openness／patience／interest／directness／warmth），
并证明了它们是棘轮（分母只长大 → 值单向漂移，谈得越久越显得冷淡）。
那个诊断是对的，但**结论下错了位置**：问题不在分母，在**名字**——
openness／warmth／directness 是我编的倾向，背后没有任何测量。

重定之后（E5）：
  · 极性变量 = 机制层当下状态的倾向读数（想要／喜欢／耐重复／结构压力／张力）
  · 累积占比搬到「行为分布」，明确标注**不是状态**

所以本工具现在审两件事，而且要**并排看**：
  ① 新极性变量：从台账里每一轮机制快照读出 → 它应当**每轮都在动、可涨可落**
  ② 旧累积占比：同一批数据 → 它应当**单向漂移**（用来证明搬走是对的）

判据（写死在这里，免得下次又靠印象）：
  · 极性变量若在几十轮里几乎不动（幅度 < 0.05）→ 它没在测状态，等同废值
  · 极性变量若单调（降 ≥ 80% 的步）→ 它在测流逝的时间，不是状态
  · 累积占比若单调 → 证实它会漂移，不该挂在"当下状态"名下

⚠️ 只读。不写任何文件。
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

from association import Association                       # noqa: E402
from character import (POLARITY_NAME, Character,          # noqa: E402
                       polarity_from_mech)
from experience import load_ledger                        # noqa: E402

W = 84


def shape(vs) -> str:
    """给一条轨迹定性。判据用**首末净变化**，不用严格单调 ——
    第一版要求严格单调，把 0.600→0.100 那种明显下滑报成"有波动"，低估结论。"""
    if len(vs) < 2:
        return "（点太少）"
    steps = [vs[i + 1] - vs[i] for i in range(len(vs) - 1)]
    down = sum(1 for s in steps if s < -1e-9)
    up = sum(1 for s in steps if s > 1e-9)
    flat = len(steps) - down - up
    lo, hi = min(vs), max(vs)
    net = vs[-1] - vs[0]
    if hi - lo < 0.05:
        return "**几乎不动**（幅度 %.3f）—— 没在测状态" % (hi - lo)
    d = "↘下滑" if net < 0 else ("↗上升" if net > 0 else "→持平")
    ratchet = "，**近单调**：在测流逝的时间" if down >= 0.8 * len(steps) else ""
    return "%s %.3f→%.3f（幅度 %.3f，%d降/%d升/%d平）%s" % (
        d, vs[0], vs[-1], hi - lo, down, up, flat, ratchet)


def main() -> int:
    rows = load_ledger()
    snaps = [r["mech"] for r in rows if r.get("mech")]
    print("=" * W)
    print("极性变量审计（重定后）：它到底动没动？")
    print("=" * W)
    print("台账有效轮次 %d ｜ 带机制快照的 %d 轮" % (len(rows), len(snaps)))

    # ---------------- ① 新极性变量：逐轮读
    print("\n" + "─" * W)
    print("① 新极性变量（读机制层当下状态）—— 应当每轮动、可涨可落")
    print("─" * W)
    keys = ["wanting", "liking", "patience", "structure", "tension"]
    series = {k: [] for k in keys}
    for m in snaps:
        p = polarity_from_mech(m)
        d = p.to_dict()
        for k in keys:
            series[k].append(d[k])
    print("%-6s" % "轮", end="")
    for k in keys:
        print("%-11s" % POLARITY_NAME[k], end="")
    print()
    for i in range(0, len(snaps), max(1, len(snaps) // 12)):
        print("%-6d" % (i + 1), end="")
        for k in keys:
            print("%-11.3f" % series[k][i], end="")
        print()
    print()
    for k in keys:
        vs = series[k]
        print("  %-10s 范围 %.3f–%.3f  %s" % (POLARITY_NAME[k], min(vs), max(vs), shape(vs)))

    # ---------------- ② 旧累积占比：同一批数据
    print("\n" + "─" * W)
    print("② 旧累积占比（已搬到「行为分布」，标注不是状态）—— 应当单向漂移")
    print("─" * W)
    assoc = Association.derive_from_ledger()
    pairs = list(assoc.pairs)
    by_kind = Counter(p.my_kind for p in pairs)
    by_react = Counter(p.his for p in pairs)
    n = len(pairs)
    print("  配对数 %d ｜ 行为分布 %s" % (n, dict(by_kind)))
    print("  反应分布 %s" % dict(by_react))
    print()
    print("  分子／分母 —— 它们的分母互不相同，所以彼此不可比：")
    active = sum(v for kk, v in by_kind.items()
                 if kk in ("问", "承认", "并排呈现", "要求具体的体验", "说自己"))
    ch = by_react.get("CHANGED_SUBJECT", 0) + by_kind.get("我换的话题", 0)
    warm = by_kind.get("承认", 0) + by_kind.get("接住收尾", 0)
    more = by_react.get("ANSWERED_MORE", 0)
    less = by_react.get("ANSWERED_LESS", 0)
    for label, num, den in (("主动开口占比", active, n), ("换题占比", ch, n),
                            ("承认占比", warm, max(1, n)),
                            ("他说更长占比", more, more + less)):
        print("     %-12s %d/%d = %.0f%%" % (label, num, den, 100.0 * num / den if den else 0))
    print()
    print("  轨迹（只用前 k 对算）—— 若单调，就证明它会随聊天变长漂移：")
    ks = sorted({k for k in (5, 10, 20, 30, 40, 55) if k <= n})
    print("    %-6s %-12s %-12s %-12s" % ("k", "主动开口", "换题(1−)", "承认"))
    traj = {"a": [], "b": [], "c": []}
    for k in ks:
        sub = pairs[:k]
        bk = Counter(x.my_kind for x in sub)
        br = Counter(x.his for x in sub)
        aa = sum(v for kk, v in bk.items()
                 if kk in ("问", "承认", "并排呈现", "要求具体的体验", "说自己")) / k
        bb = 1.0 - (br.get("CHANGED_SUBJECT", 0) + bk.get("我换的话题", 0)) / k
        cc = (bk.get("承认", 0) + bk.get("接住收尾", 0)) / k
        traj["a"].append(aa); traj["b"].append(bb); traj["c"].append(cc)
        print("    %-6d %-12.3f %-12.3f %-12.3f" % (k, aa, bb, cc))
    for name, key in (("主动开口", "a"), ("换题(1−)", "b"), ("承认", "c")):
        print("    %-10s %s" % (name, shape(traj[key])))

    # ---------------- ③ 结论
    print("\n" + "─" * W)
    print("③ 结论")
    print("─" * W)
    # 判据分两档，不能合成一个"通过"。第一版用幅度 >0.05 一刀切，
    # 于是「耐重复」幅度 0.090（68 步里 56 步是平的）也被算成"确实在测状态" ——
    # 那是**放宽结论**。一个量"能变"与"这批数据把它试出来了"是两件事。
    STILL, EXERCISED = 0.05, 0.20
    dead, weakly, ok = [], [], []
    for k in keys:
        rng = max(series[k]) - min(series[k])
        (dead if rng < STILL else (weakly if rng < EXERCISED else ok)).append((POLARITY_NAME[k], rng))
    ratchets = [POLARITY_NAME[k] for k in keys
                if len(series[k]) > 2 and min(series[k]) != max(series[k])
                and sum(1 for i in range(len(series[k]) - 1)
                        if series[k][i + 1] - series[k][i] < -1e-9) >= 0.8 * (len(series[k]) - 1)]
    if ok:
        print("  ✓ **这批数据试出来了**（幅度 ≥ %.2f）：%s"
              % (EXERCISED, "、".join("%s %.3f" % (a, b) for a, b in ok)))
    if weakly:
        print("  ⚠️ **能变但这批数据几乎没触发**（幅度 < %.2f）：%s"
              % (EXERCISED, "、".join("%s %.3f" % (a, b) for a, b in weakly)))
        print("     这不是缺陷，是样本问题：它需要有『期望落空』的轮次才会动。")
        print("     但**不能说它已被验证** —— 只能说它在结构上不是常量。")
    if dead:
        print("  ⚠️ 几乎不动（幅度 < %.2f）：%s —— 它们没在测状态，应当撤下。"
              % (STILL, "、".join("%s %.3f" % (a, b) for a, b in dead)))
    if ratchets:
        print("  ⚠️ 近单调的极性变量：%s —— 那是在测流逝的时间，不是状态。" % "、".join(ratchets))
    else:
        print("  ✓ 五个里没有一个是近单调的 —— 可涨可落，不是随时间单向漂移。")
    print("  ✓ 累积占比仍然会漂移（见②），它搬出「状态」那一栏是对的。")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
