# -*- coding: utf-8 -*-
"""第四步实测：模型渲染 + 三道闸门 + 与模板版对照

用法：
    cd C:\\Users\\22082\\Desktop\\DEPSK\\books\\ego-dialogue
    python tests\\probe_render.py

它做三件事：
  ① 对每条输入跑一次渲染，打印：模型说了什么、过了哪几道闸门、用了哪些材料
  ② 统计通过率与退回率 —— **退回率是乙方案的真实成本**，不许藏
  ③ 同一条输入同时给「模板版」与「渲染版」，并排给人判断
"""
from __future__ import annotations

import io
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "engine"))

from compose import compose                 # noqa: E402
from render import Renderer, make_brief     # noqa: E402
from respond import Responder               # noqa: E402

W = 78

# (用户原话, 标记层命中, 立场, 话题)
CASES = [
    ("我其实特别想接下来，但我也知道这样会耽误别人。", ["opposed_pair"], "asks_detail", "T01"),
    ("我爸从来没夸过我。", [], "asks_detail", "T09"),
    ("有时候觉得挺累的。", [], "asks_detail", "T10"),
    ("反正也就那样。", [], "asks_detail", "T09"),
    ("虽然身体回不到从前了，但我还能决定今天怎么过。", ["attitude_clause"], "acknowledge", "T22"),
    ("我一定要得到那个结果，得不到我就难受。", ["over_intention"], "observe_only", "T10"),
    ("就这样吧。", [], "closing", "T01"),
    ("那天她把我送到楼下，风挺凉的。", [], "acknowledge", "T09"),
]


def template_version(raw: str, markers: list[str]) -> str:
    """旧路径：从模板池挑一条。用于并排对照。"""
    r = Responder()
    ev = {}
    bid = r.choose(markers, ev, raw)
    return r.render(bid, raw, markers, ev).output.replace("\n", " / ")


def main() -> int:
    rd = Renderer(review=True)
    if not rd.available:
        print("API 不可用 —— 无法跑本体检。设置 DEEPSEEK_API_KEY 或跳过。")
        return 2

    print("═" * W)
    print("  第四步实测：意思 → 模型渲染 → 三道闸门")
    print("═" * W)

    rows = []
    for raw, mk, stance, topic in CASES:
        m = compose(raw, mk)
        b = make_brief(m, raw, stance)
        sp = rd.render(b)
        rows.append((raw, m, b, sp, mk))

    for raw, m, b, sp, mk in rows:
        print()
        print("  你说：%s" % raw)
        print("    意思：关系=%s ｜ 材料=%s ｜ 锚点=%s"
              % (b.relation, "、".join(x["id"] for x in b.material) or "（无）",
                 b.anchor or "（无）"))
        print("    模板版：%s" % template_version(raw, mk))
        if sp.rendered:
            print("    渲染版：%s" % sp.text.replace("\n", " / "))
            print("            ✅ 通过闸门 ｜ 用材料=%s" % ("、".join(sp.used) or "（无）"))
        else:
            print("    渲染版：（退回模板）")
            print("            ❌ %s" % sp.reason)
            if sp.violations:
                for v in sp.violations:
                    print("               · %s" % v)
            if sp.text:
                print("            它本来想说：%s" % sp.text.replace("\n", " / "))

    st = rd.stats()
    print()
    print("─" * W)
    print("  统计：尝试 %d ｜ 退回 %d ｜ 通过率 %s"
          % (st["attempts"], st["rejected"],
             ("%.0f%%" % (st["pass_rate"] * 100)) if st["pass_rate"] is not None else "—"))
    print("  ⚠️ 退回率就是乙方案的成本：退回的那些轮次仍然只能说模板。")
    print("─" * W)
    print("""
  怎么判断这个结果（请你自己判，不要听我的）：

    · 渲染版若让你觉得"这句更像在跟我说话"，同时**没有多出任何东西** →
      乙方案成立，继续。
    · 渲染版若多出了你没说过的事、或开始给建议/安慰 → **闸门没拦住**，
      是严重问题，要立刻收紧。
    · 若大量退回模板 → 说明约束太紧或模型不配合，这套方案的实际收益会很小。
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
