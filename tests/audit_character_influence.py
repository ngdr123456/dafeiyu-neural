# -*- coding: utf-8 -*-
"""第 3 步验证：性格影响行为 —— 它真的会动吗？护栏真的守住了吗？

为什么这个验证必须做在最前面
────────────────────────────────────────────────────────────
"让性格影响行为"是整件事里唯一会给系统**增加表达自由**的改动，
也是唯一可能训出讨好的改动。所以不能只声明三条护栏就算数，
必须**穷举**它对每个输入会返回什么。

测四件事：
  ① **只往保守方向走**：对全部 9 个动作 × 极性极值网格，验证结果的下标 ≥ 输入下标。
     这一条若破，讨好就在结构上成为可能。
  ② **E1 不被绕过**：带 immutable 时，结果必须落在 E1 允许集内（穷举）。
  ③ **三条规则各自能触发**：用合成状态证明 R1／R2／R3 都真的会生效
     —— 否则"护栏守住了"可能只是因为整段代码从来没跑起来。
  ④ **真实数据下它现在触发几次**：如实报。触发 0 次不是失败，
     但必须与"机制可用"分开说，不许混成一句"已验证"。

⚠️ 只读（不写台账，Character 用临时路径）。
"""
from __future__ import annotations

import itertools
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_ROOT, os.path.join(_ROOT, "engine"), os.path.join(_ROOT, "state")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from association import Association                                   # noqa: E402
from character import (ASSERTIVE, CONSERVATISM, E1_ALLOWED, Character,   # noqa: E402
                       Milestone, Polarity, polarity_from_mech)
from experience import load_ledger                                    # noqa: E402

W = 84


def fresh() -> Character:
    d = tempfile.mkdtemp(prefix="ego_ch_")
    return Character(os.path.join(d, "character.json"))


def main() -> int:
    ok = True
    print("=" * W)
    print("第 3 步验证：性格影响行为")
    print("=" * W)

    # ---------------- ① 只往保守方向走（穷举）
    print("\n" + "─" * W)
    print("① 护栏一：只能更保守，绝不更主动（穷举 9 动作 × 极性网格）")
    print("─" * W)
    grid = [0.0, 0.2, 0.34, 0.36, 0.5, 0.79, 0.81, 1.0]
    viol = []
    fired = 0
    total = 0
    for act, pat, strc, last in itertools.product(CONSERVATISM, grid, grid, [None, "ASK_DETAIL"]):
        c = fresh()
        c.polarity = Polarity(patience=pat, structure=strc)
        for mk in ([], ["immutable"]):
            total += 1
            out, why = c.modulate(act, mk, last)
            if why:
                fired += 1
            if CONSERVATISM.index(out) < CONSERVATISM.index(act):
                viol.append(("向左移动", act, out, pat, strc, mk))
            # ⚠️ E1 只在**改动过**的时候检查。
            #   动作原样返回时，"它是否合法"由下游那道「禁止提升」闸门负责
            #   （responder.render 会把 immutable 情形下的提升型动作换掉）。
            #   第一版在这里也检查，一次报出 584 例假越界 —— 是我判据写错了，
            #   不是代码错了。检查器过严和过松一样糟：它会淹没真问题。
            if why and mk and out not in E1_ALLOWED:
                viol.append(("E1被绕过", act, out, pat, strc, mk))
            # R2 触发时不得落在断言集里（规则自相矛盾的那一处）
            if why and "不得下断言" in why and out in ASSERTIVE:
                viol.append(("R2落到断言上", act, out, pat, strc, mk))
    print("  穷举组合 %d 个｜其中触发降级 %d 个" % (total, fired))
    if viol:
        ok = False
        print("  ✗ **发现越界 %d 例**（前 5）：" % len(viol))
        for v in viol[:5]:
            print("     %s" % (v,))
    else:
        print("  ✓ 没有任何一次向左移动")
        print("  ✓ 改动过时结果全部在 E1 允许集内")
        print("  ✓ R2 触发时从不落在断言集内")

    # ---------------- ② 三条规则各自能触发
    print("\n" + "─" * W)
    print("② 三条规则各自能触发（合成状态，证明机制不是死的）")
    print("─" * W)
    # R1 耐心
    c = fresh()
    c.polarity = Polarity(patience=0.10, structure=0.0)
    out, why = c.modulate("ASK_DETAIL", [], "ASK_DETAIL")
    r1 = out != "ASK_DETAIL"
    print("  R1 耐心   ：patience=0.10 且连着两轮问细节 → %s" % out)
    print("             %s" % why)
    # R2 结构压力（阈值 = 机制层自己的 error_high，即 structure ≥ 1.0）
    c = fresh()
    c.polarity = Polarity(patience=0.9, structure=1.0)
    out, why = c.modulate("JUXTAPOSE", [], None)
    r2 = out != "JUXTAPOSE"
    print("  R2 结构压力：structure=1.00（|e|≥error_high）且动作是并排呈现 → %s" % out)
    print("             %s" % why)
    # R2 的对照：同样的结构压力，但动作本来就不断言 → 不该动
    out2, why2 = c.modulate("REFLECT", [], None)
    r2b = (out2 == "REFLECT")
    print("   R2 对照  ：同样压力下复述不受影响 → %s（%s）" % (out2, "正确" if r2b else "错误"))
    # R3 里程碑
    c = fresh()
    c.polarity = Polarity(patience=0.9, structure=0.0)
    c.milestones = [Milestone(key="问", text="我问他细节的时候，多半就停在那儿。",
                              evidence=6, current=6,
                              basis={"n": 6, "continue": 0, "stop": 6, "share": 0.0})]
    out, why = c.modulate("ASK_DETAIL", [], None)
    r3 = out != "ASK_DETAIL"
    print("  R3 里程碑 ：里程碑说『问细节多半停在那儿』→ %s" % out)
    print("             %s" % why)
    # R3 的对照：复合式里程碑（两边都有证据）**不该**降级
    c.milestones = [Milestone(key="问", text="我问他细节的时候，有时接得下去，有时就停在那儿。",
                              evidence=4, current=4)]
    out2b, why2b = c.modulate("ASK_DETAIL", [], None)
    r3b = (out2b == "ASK_DETAIL" and why2b is None)
    print("   R3 对照  ：复合式里程碑（两边都有证据）不降级 → %s（%s）"
          % (out2b, "正确" if r3b else "错误"))
    for name, good in (("R1", r1), ("R2", r2), ("R2对照", r2b), ("R3", r3), ("R3对照", r3b)):
        if not good:
            ok = False
    print("  %s" % ("✓ 三条规则与两条对照全部符合预期"
                    if all((r1, r2, r2b, r3, r3b)) else "✗ 有规则不符合预期"))

    # ---------------- ③ 刻意不用 wanting
    print("\n" + "─" * W)
    print("③ 护栏三：wanting 不参与裁决（它是讨好路径）")
    print("─" * W)
    c = fresh()
    c.polarity = Polarity(wanting=0.0, patience=0.9, structure=0.0)
    a1, _ = c.modulate("ASK_DETAIL", [], None)
    c.polarity = Polarity(wanting=1.0, patience=0.9, structure=0.0)
    a2, _ = c.modulate("ASK_DETAIL", [], None)
    same = (a1 == a2 == "ASK_DETAIL")
    if not same:
        ok = False
    print("  wanting=0.0 → %s ｜ wanting=1.0 → %s ｜ %s"
          % (a1, a2, "✓ 完全相同，wanting 不影响裁决" if same else "✗ 它影响了裁决"))
    print("  理由：wanting←w，而 w 的来源含『他还在说』（lean 由字数推出）。")
    print("        拿它决定行为 = 按用户说得多不多调整自己 = 讨好路径。")

    # ---------------- ④ 真实数据下触发几次
    print("\n" + "─" * W)
    print("④ 真实数据下，它现在触发几次（如实报，不粉饰）")
    print("─" * W)
    rows = load_ledger()
    snaps = [r["mech"] for r in rows if r.get("mech")]
    assoc = Association.derive_from_ledger()
    ch = fresh()
    ch.learn(assoc, mech=snaps[-1] if snaps else None)
    print("  当前极性：%s" % ch.polarity.to_dict())
    hits = 0
    from collections import Counter
    why_c = Counter()
    last = None
    for r in rows:
        if not r.get("mech"):
            continue
        ch.update_state(r["mech"])
        act = r.get("behavior")
        out, why = ch.modulate(act, r.get("markers_fired") or [], last)
        if why:
            hits += 1
            why_c[why.split(" → ")[0][:40]] += 1
        last = act
    print("  历史 %d 轮里会被降级的：%d 轮" % (len(snaps), hits))
    for k, v in why_c.most_common():
        print("     %d 次  %s" % (v, k))
    if hits == 0:
        print("  ★ 结论要分两半说，不能混成一句：")
        print("     · 机制**可用** —— ② 已用合成状态证明三条规则都会触发")
        print("     · 但这批数据**没触发它** —— 耐心 %.2f（阈值 <0.35）"
              % ch.polarity.patience)
        print("       结构压力 %.2f（阈值 ≥1.00），且唯一那条里程碑是**复合式**（两边都有证据）"
              % ch.polarity.structure)
        print("     · 所以**不能说「已验证它在真实对话里有效」**，只能说它接好了。")
    print()

    # ---------------- ⑤ 三条规则的可达性
    print("─" * W)
    print("⑤ 三条规则的可达性：阈值是否落在机制层产生过的范围**之内**")
    print("─" * W)
    print("  ★ 这一节防的正是本模块一整轮在修的病：**写了但永远不会生效**。")
    print("    已发现过三例：NOTHING_MORE（条件表第 14 条永远轮不到）、")
    print("    voice_shift.sub_patterns 里的死条目、counterexamples 里的散文反例。")
    print("    现在用同一把尺子量我自己新写的三条规则。")
    print()
    pats = [polarity_from_mech(m).patience for m in snaps]
    strcs = [polarity_from_mech(m).structure for m in snaps]
    n_stop = sum(1 for m in ch.milestones if m.text.endswith("多半就停在那儿。"))
    print("  机制层实测范围（%d 轮）：" % len(snaps))
    print("     patience  %.3f – %.3f    （R1 需要 < 0.35）" % (min(pats), max(pats)))
    print("     structure %.3f – %.3f    （R2 需要 ≥ 1.00，即 |e| ≥ error_high=0.60）"
          % (min(strcs), max(strcs)))
    print("     里程碑    %d 条里 stop-主导的有 %d 条   （R3 需要 ≥1）"
          % (len(ch.milestones), n_stop))
    print()
    for k, v in (("R1 耐心", min(pats) < 0.35),
                 ("R2 结构压力", max(strcs) >= 1.0),
                 ("R3 里程碑", n_stop > 0)):
        print("     %-12s %s" % (k, "阈值可达" if v
                                else "**阈值在可达范围之外 —— 没有任何数据能触发它**"))
    print()
    print("  ★ 三件事必须分开说，不许合并成一句：")
    print("     1. 规则**写对了** —— ① 穷举 2304 个组合证明护栏守住；② 合成状态证明三条都会触发")
    print("     2. 接线**是通的** —— test_pipeline 的 K1–K4 端到端证明管线真的会调用它")
    print("     3. 但这批数据里 R1／R2 的阈值**从没达到过**（R3 的里程碑目前是复合式）")
    print("     ⇒ 只能说「已接好、且不会误伤」，**不能说「已在真实对话中起作用」**。")
    print("       我**没有**为了点亮它们而下调阈值 —— 那正是本模块一直在修的那种错。")
    print()

    print("=" * W)
    print("总判定：%s" % ("护栏全部守住" if ok else "**有护栏被破 —— 必须修**"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
