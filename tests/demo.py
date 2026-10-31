# -*- coding: utf-8 -*-
"""可运行演示：观察 S 固化、门控、疲劳、三条硬禁令

用法：python tests/demo.py
"""
from __future__ import annotations

import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "engine"))

from pipeline import Pipeline        # noqa: E402
from gear import GearConfig          # noqa: E402


def show(p: Pipeline, label: str, raw: str, topic: str) -> None:
    r = p.turn(raw, topic)
    print("─" * 76)
    print("【%s】题%s" % (label, topic))
    print("  用户：%s" % raw)
    print("  标记：%s" % (r.markers or "（无 → 废纸篓）"))
    print("  区间：[%s]   方向：%s" % (" / ".join(r.band), r.direction))
    print("  通道：%-10s 水平：%-6s 行为：%s" % (r.channel, r.level, r.behavior))
    print("  关系：%s" % r.relation)
    print("  回应：\n    " + r.output.replace("\n", "\n    "))
    fired = [n for n in r.notes if any(k in n for k in ("E1", "fuel", "过度意向", "门槛", "阈值", "档位", "nudge", "废纸篓", "S/B"))]
    if fired:
        print("  机制：" + " ｜ ".join(fired))


def main() -> None:
    d = tempfile.mkdtemp(prefix="ego_demo_")
    p = Pipeline(ledger_path=os.path.join(d, "ledger.jsonl"),
                 config=GearConfig(evidence_threshold=3), auto_audit=False)

    print("=" * 76)
    print("演示 A｜S 的诞生：同一签名反复出现 → 越过阈值 A → 意向成为习惯")
    print("  [E] 洛华德：『遵守大小便规则不再被体验为一种意向或要求，而成了一种习惯。』")
    print("=" * 76)
    for i in range(1, 5):
        show(p, "A%d" % i, "大家都这样，我也没办法。", "T08")

    print()
    print("=" * 76)
    print("演示 B｜门控：换一个签名族 → 旧 S 不得命中（前遵奉 / 后遵奉的分辨）")
    print("  [E]：『一个在遵奉量表上得分较低的人可能是前遵奉者或后遵奉者。』")
    print("=" * 76)
    show(p, "B1", "他已经走了，再也回不来了，这个我改变不了。", "T23")

    print()
    print("=" * 76)
    print("演示 C｜三条硬禁令")
    print("=" * 76)
    show(p, "C1 不可改变（E1）", "这件事已经发生，我再也回不去了。", "T21")
    show(p, "C2 过度意向", "我一定要做到，我必须证明给他们看。", "T35")
    show(p, "C3 燃料优先", "等以后吧，等我有了条件，将来总有一天。", "T36")

    print()
    print("=" * 76)
    print("演示 D｜两个对立观念并存 → JUXTAPOSE（只并列，不评论）")
    print("=" * 76)
    show(p, "D1", "一方面我想留在这里，另一方面我又想走，一直在拉扯。", "T33")

    print()
    print("=" * 76)
    print("快照")
    print("=" * 76)
    snap = p.gear.snapshot()
    print("  S 总数 %d（active %d / decayed %d）｜当前档位 %s（停留 %d 轮）"
          % (snap["S_count"], snap["S_active"], snap["S_decayed"],
             snap["gear"]["level"], snap["gear"]["dwell_turns"]))
    for s in snap["S"]:
        print("   · %s key=%s 行动水平=%s 命中=%d 一致率=%.2f 疲劳=%.3f 状态=%s"
              % (s["sid"], s["key"], s["action_level"], s["hits"],
                 s["recent_consistency"], s["fatigue"], s["status"]))
    print("  诚实声明：")
    for n in snap["honest_note"]:
        print("   · %s" % n)
    print()
    print("台账 %d 条，反事实示例：" % p.ledger.turns())
    for cf in p.ledger.counterfactuals()[:5]:
        print("   · %s" % cf)


if __name__ == "__main__":
    main()
