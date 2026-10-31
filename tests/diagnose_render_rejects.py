# -*- coding: utf-8 -*-
"""查渲染闸门到底在拦什么 —— 台账只记了「未过」，没记哪一项。

为什么要查：用户实测三轮里**两轮渲染被打回**，退回模板后输出全是生硬的模板句。
"带渲染"这个功能花了两次 API 调用、4–8 秒，结果大部分时候没生效 ——
那它现在等于没有。要修就得先知道拦在哪一条。

做法：把用户那两轮原样重放，直接调渲染层，把违规明细打出来。
⚠️ 只读（不写台账）。
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_ROOT, os.path.join(_ROOT, "engine"), os.path.join(_ROOT, "state")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from compose import compose                       # noqa: E402
from markers import MarkerEngine                  # noqa: E402
from render import Renderer, make_brief           # noqa: E402

# ⚠️ 标记必须**实时识别**，不能写死。
#    第一版把 markers 写死在用例里，于是改完词表再跑，它还在用旧标记 ——
#    测的是一个**已经不会发生的场景**。诊断工具的输入若不跟着现实走，
#    它给出的结论也是过期的。
CASES = [
    ("我一定要得到那个结果，得不到我就难受", "REFLECT", "observe_only",
     "用户第 3 轮：台账记『机械闸门未过』"),
    ("一个人可以同时是好的和坏的吗？我认为可以", "JUXTAPOSE", "observe_only",
     "用户第 2 轮：台账记『语义复核未过』（根因是 blame_external 的坏 pattern）"),
    ("我觉得一个人最重要的品质是诚实", "REFLECT", "observe_only",
     "用户第 1 轮：渲染通过了，但输出仍是「你觉得…」"),
]


def main() -> int:
    r = Renderer()
    eng = MarkerEngine()
    print("渲染层可用:", r.available)
    if not r.available:
        return 2
    print("=" * 80)
    for raw, beh, stance, tag in CASES:
        markers = [h.id for h in eng.parse(raw).hits]
        print("\n【%s】" % tag)
        print("  你说：%s" % raw)
        print("  标记（实时识别）=%s 行为=%s" % (markers or "无", beh))
        m = compose(raw, markers)
        b = make_brief(m, raw, stance)
        print("  材料（只许用这些 id）：%s" % "、".join(x["id"] for x in b.material) or "（无）")
        print("  锚点：%s" % (b.anchor or "（无）"))
        print("  最具体的一句：%s" % (b.concrete or "（无）"))
        sp = r.render(b)
        if sp.rendered:
            print("  ✅ 通过闸门｜%s" % sp.text.replace("\n", " / "))
            print("     用材料：%s" % ("、".join(sp.used) or "无"))
        else:
            print("  ❌ 退回模板｜原因：%s" % sp.reason)
            if sp.text:
                print("     它本来想说：%s" % sp.text.replace("\n", " / "))
        # 机械闸门逐条自检（把违规项全摊开，而不是只报"未过"）
        if sp.text:
            bad = r.mechanical_check(sp.text, b)
            if bad:
                print("     机械闸门违规明细：")
                for x in bad:
                    print("        · %s" % x)
    print("\n" + "=" * 80)
    print("统计：尝试 %d｜退回 %d｜通过率 %.0f%%"
          % (r.attempts, r.rejected,
             (100.0 * (r.attempts - r.rejected) / r.attempts) if r.attempts else 0))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
