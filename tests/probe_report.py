# -*- coding: utf-8 -*-
"""规则层体检：拿真实语料过一遍 markers.py，量化"机制缺口"与"误判"

用法：
    cd C:\\Users\\22082\\Desktop\\DEPSK\\books\\ego-dialogue
    python tests\\corpus_probe.py

输出三张表：
  ① 逐条比对（漏判 / 误判 / 通过）
  ② 按标记汇总（哪一个标记最漏、哪一个最误）
  ③ 结论：漏判里有多少属于"机制"（该修规则），多少属于"取材"（不该动规则）

判据来自 tests/corpus_probe.py 的 `gap` 字段，不由本脚本猜测。
"""
from __future__ import annotations

import collections
import io
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "engine"))
sys.path.insert(0, _HERE)

from markers import MarkerEngine          # noqa: E402
from corpus_probe import CASES            # noqa: E402

W = 78


def hr(ch: str = "─") -> None:
    print(ch * W)


def main() -> int:
    eng = MarkerEngine()

    missed = []      # 该命中却没命中
    spurious = []    # 不该命中却命中
    passed = []

    for text, want, gap, note in CASES:
        pr = eng.parse(text, None)
        got = set(pr.markers)
        if want - got:
            missed.append((text, want, got, want - got, gap, note))
        elif got - want:
            spurious.append((text, want, got, got - want, gap, note))
        else:
            passed.append((text, want, gap, note))

    hr("═")
    print("  规则层体检　｜　语料 %d 条　｜　通过 %d　漏判 %d　误判 %d"
          % (len(CASES), len(passed), len(missed), len(spurious)))
    hr("═")

    print("\n【一】漏判（该命中却没命中）\n")
    if not missed:
        print("  （无）")
    for text, want, got, miss, gap, note in missed:
        print("  [%s] %s" % (gap, text))
        print("        该命中：%s" % "、".join(sorted(want)))
        print("        实际　：%s" % ("、".join(sorted(got)) or "（无）"))
        print("        缺　　：%s" % "、".join(sorted(miss)))
        print("        说明　：%s" % note)
        print()

    print("\n【二】误判（不该命中却命中）\n")
    if not spurious:
        print("  （无）")
    for text, want, got, extra, gap, note in spurious:
        print("  %s" % text)
        print("        不该命中：%s" % ("、".join(sorted(extra))))
        print("        说明　　：%s" % note)
        print()

    print("\n【三】按标记汇总\n")
    per = collections.defaultdict(lambda: {"want": 0, "hit": 0, "miss": 0, "false": 0})
    for text, want, got, miss, gap, note in missed:
        for m in want:
            per[m]["want"] += 1
            per[m]["miss"] += 1
    for text, want, got, extra, gap, note in spurious:
        for m in extra:
            per[m]["false"] += 1
    for text, want, gap, note in passed:
        for m in want:
            per[m]["want"] += 1
            per[m]["hit"] += 1
    for m in sorted(per):
        d = per[m]
        rate = (d["hit"] / d["want"] * 100) if d["want"] else 0.0
        print("  %-18s 应有 %2d ｜命中 %2d ｜漏 %2d ｜误判 %2d ｜召回 %5.0f%%"
              % (m, d["want"], d["hit"], d["miss"], d["false"], rate))
    allw = sum(d["want"] for d in per.values())
    allh = sum(d["hit"] for d in per.values())
    allf = sum(d["false"] for d in per.values())
    print("  %-18s 应有 %2d ｜命中 %2d ｜漏 %2d ｜误判 %2d ｜召回 %5.0f%%"
          % ("【合计】", allw, allh, allw - allh, allf,
             (allh / allw * 100) if allw else 0.0))

    print("\n【四】结论：漏判的归因\n")
    by_gap = collections.Counter(m[4] for m in missed)
    print("  机制（规则缺陷，可修）　：%d" % by_gap.get("机制", 0))
    print("  取材（语料本无特征，不改规则）：%d" % by_gap.get("取材", 0))
    print("  误判（反例过滤缺陷，必须修）：%d" % len(spurious))
    print()

    return 0 if not spurious else 2


if __name__ == "__main__":
    sys.exit(main())
