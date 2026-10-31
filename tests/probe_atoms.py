# -*- coding: utf-8 -*-
"""原子识别体检：跑召回与误判，并**测出"同一句话不同上下文"能否被区分**

用法：
    cd C:\\Users\\22082\\Desktop\\DEPSK\\books\\ego-dialogue
    python tests\\probe_atoms.py

输出四张表：
  ① 逐条比对（漏判／误判／通过）
  ② 按原子汇总（哪一个最漏、哪一个最误）
  ③ 归因：漏判里多少属于"机制"（可修），多少属于"取材"（不该改词表）
  ④ ★ 上下文区分检验 —— 语料里那一对"同一句话、不同上下文"，
     词表算不算得出差别。算不出就报错。
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

from compose import recognize, compose          # noqa: E402
from corpus_atoms import CASES                  # noqa: E402

W = 78


def hr(ch: str = "─") -> None:
    print(ch * W)


def main() -> int:
    missed, spurious, passed = [], [], []
    for text, want, gap, note in CASES:
        got = set(recognize(text))
        if want - got:
            missed.append((text, want, got, want - got, gap, note))
        elif got - want:
            spurious.append((text, want, got, got - want, gap, note))
        else:
            passed.append((text, want, gap, note))

    hr("═")
    print("  原子识别体检　｜　语料 %d 条　｜　通过 %d　漏判 %d　误判 %d"
          % (len(CASES), len(passed), len(missed), len(spurious)))
    hr("═")

    print("\n【一】漏判（该命中却没命中）\n")
    if not missed:
        print("  （无）")
    for text, want, got, miss, gap, note in missed:
        print("  [%s] %s" % (gap, text[:56]))
        print("        该命中：%s" % "、".join(sorted(want)))
        print("        实际　：%s" % ("、".join(sorted(got)) or "（无）"))
        print("        缺　　：%s" % "、".join(sorted(miss)))
        print("        说明　：%s" % note)
        print()

    print("\n【二】误判（不该命中却命中）\n")
    if not spurious:
        print("  （无）")
    for text, want, got, extra, gap, note in spurious:
        print("  %s" % text[:56])
        print("        多出来：%s" % "、".join(sorted(extra)))
        print("        说明　：%s" % note)
        print()

    print("\n【三】按原子汇总\n")
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
        print("  %-30s 应有 %2d ｜命中 %2d ｜漏 %2d ｜误判 %2d ｜召回 %5.0f%%"
              % (m, d["want"], d["hit"], d["miss"], d["false"], rate))
    allw = sum(d["want"] for d in per.values())
    allh = sum(d["hit"] for d in per.values())
    allf = sum(d["false"] for d in per.values())
    print("  %-30s 应有 %2d ｜命中 %2d ｜漏 %2d ｜误判 %2d ｜召回 %5.0f%%"
          % ("【合计】", allw, allh, allw - allh, allf,
             (allh / allw * 100) if allw else 0.0))

    print("\n【四】归因：漏判里多少可修\n")
    by_gap = collections.Counter(m[4] for m in missed)
    print("  机制（词表缺陷，可修）　　：%d" % by_gap.get("机制", 0))
    print("  取材（语料本无，不改词表）：%d" % by_gap.get("取材", 0))
    print("  误判（反例过滤缺陷，必改）：%d" % len(spurious))

    print("\n【五】★ 上下文区分检验\n")
    print("  语料里第 1、2 条是 [p270] 原文那一对：同一句「我不时感到气」，")
    print("  第 1 条单独出现，第 2 条后面跟了两个具体观念 —— 书里说后者提高到更复杂的水平。")
    m1 = compose(CASES[0][0])
    m2 = compose(CASES[1][0])
    print()
    print("  第 1 条：原子=%s 关系=%s  意思键=%s"
          % ("、".join(m1.atoms) or "（无）", m1.relation, m1.key()[:44]))
    print("  第 2 条：原子=%s 关系=%s  意思键=%s"
          % ("、".join(m2.atoms) or "（无）", m2.relation, m2.key()[:44]))
    distinct = m1.key() != m2.key()
    print()
    if distinct:
        print("  ✅ 两条的「意思」不同 —— 词表算得出上下文带来的差别。")
    else:
        print("  ❌ 两条的「意思」相同 —— **词表算不出上下文差别**，")
        print("     那么「组合决定意思」（[p270]）这条机制在本实现里是空话。")
    hr()
    ok = (not spurious) and distinct
    print("  结论：%s" % ("通过" if ok else "**未通过**（见上）"))
    hr()
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
