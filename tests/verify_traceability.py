# -*- coding: utf-8 -*-
"""目标验收：逐条核对"词表可追溯"这条硬约束

目标里明确写了「词表必须可追溯到原书措辞或标记层依据」。
上一轮我只验证了召回与误判，**没有验证这一条** —— 现在补上，因为它是目标的硬约束。

判据：
  · 收输入的原子（triggers/anchors 非空）**必须**有 basis
  · basis 必须指明来源，且只能落在这几类里：
      「原书」/「层」=  可追溯（合格）
      其他措辞        =  需人工确认（不合格，或必须补明出处）
  · 每条 counterexamples 也应当有（目标写了"反例"）—— 计为警告，不阻断
"""
from __future__ import annotations

import io
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
P = os.path.join(_ROOT, "rules", "atoms.json")

OK_SOURCES = ("原书", "层")
W = 78


def main() -> int:
    d = json.load(io.open(P, encoding="utf-8"))
    atoms = d["atoms"]
    print("═" * W)
    print("  验收：词表可追溯性（逐条核对）")
    print("═" * W)

    takes_input = [a for a in atoms if (a["lex"].get("triggers") or a["lex"].get("anchors"))]
    design_only = [a for a in atoms if a not in takes_input]

    print()
    print("  原子总数 %d ｜ 收输入的 %d ｜ 设计依据类 %d"
          % (len(atoms), len(takes_input), len(design_only)))
    print()
    print("  %-30s %-34s %s" % ("原子", "basis 摘要", "判定"))
    print("  " + "-" * 72)

    bad, warn = [], []
    for a in takes_input:
        b = (a["lex"].get("basis") or "").strip()
        good = b and any(s in b for s in OK_SOURCES)
        if not good:
            bad.append(a["id"])
        if not (a["lex"].get("counterexamples") or a["lex"].get("immune")):
            warn.append(a["id"])
        print("  %-30s %-34s %s"
              % (a["id"], (b[:32] + "…") if len(b) > 33 else b,
                 "OK" if good else "**不可追溯**"))

    print()
    print("  ── 设计依据类（不收输入，故无需识别词表）")
    for a in design_only:
        print("     %-30s %s" % (a["id"], a["source"]))

    print()
    print("  ── 结论")
    print("     不可追溯的原子：%d %s" % (len(bad), ("→ " + "、".join(bad)) if bad else ""))
    print("     无反例/免疫（警告）：%d %s"
          % (len(warn), ("→ " + "、".join(warn)) if warn else ""))

    # 另外核对：每条 basis 里是否有具体的页码／出处标记
    withcite = [a["id"] for a in takes_input if "[p" in (a["lex"].get("basis") or "")]
    print("     basis 里带具体页码 [pN] 的：%d/%d" % (len(withcite), len(takes_input)))

    print()
    ok = not bad
    print("  验收：%s" % ("通过" if ok else "**未通过**"))
    print("═" * W)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
