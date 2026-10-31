# -*- coding: utf-8 -*-
"""U1-U9：C5 三级核对（2026-10-29）。

★ 判据（先写，用户与 Gemini 已批）：
  U1 ★ 两段都命中 ⇒ STRONG 且 **confirmed**
  U2 ★ 只命中一段 ⇒ WEAK 且 **不 confirmed**（经验层不学"只用碎片"）
  U3 一段都没中 ⇒ 不走新分支（落到原有 UNCLASSIFIED / 其他）
  U4 ★ 人称转换：quotes「我腿都软了」 vs 输出「你腿都软了」⇒ 算命中
  U5 ★ 分句引用：quotes「他已经走了，再也回不来了」 vs 输出「再也回不来了」⇒ 算命中
  U6 ★ 虚词剥壳：quotes「我又怕他知道」 vs 输出「怕他知道」⇒ 算命中
  U7 ★ 不凑数：quotes「你别真不盯啊」+「不知道拿它怎么办了」，输出只用了前一段 ⇒ WEAK
  U8 没有 thought_quotes 时，行为与改动前完全一致（向后兼容）
  U9 已在 ALLOWED_BEHAVIORS 里（否则 append 会抛 ValueError）
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)
sys.path[:0] = [str(_ROOT), str(_ROOT + "/engine"), str(_ROOT + "/state")]

from action_observation import (SILENCE_TOKEN, observe,  # noqa: E402
                                quote_hit, thought_level)
from ledger import ALLOWED_BEHAVIORS  # noqa: E402

OK = 0
FAIL = 0


def case(name, cond, why=""):
    global OK, FAIL
    if cond:
        OK += 1
        print("  [PASS] 【%s】" % name)
    else:
        FAIL += 1
        print("  [FAIL] 【%s】%s" % (name, why))


print("=" * 78)
print("  C5 三级核对（U1-U9）")
print("=" * 78)

Q = ["那碗面泡烂在桌上", "我说吃了"]

# ── U1 两段都中 ⇒ STRONG
both = "「那碗面泡烂在桌上」，你嘴上说「我说吃了」。"
a = observe(both, "REFLECT", "brain", raw="那碗面泡烂在桌上，我说吃了。", thought_quotes=Q)
case("U1 ★ 两段都命中 ⇒ STRONG 且 confirmed",
     a["actual"] == "THOUGHT_EXECUTED_STRONG" and a["confirmed"] is True,
     "%r confirmed=%r" % (a["actual"], a["confirmed"]))

# ── U2 ★ 只中一段 ⇒ `thought_level == "WEAK"`（**独立字段，不是 actual**）
#
#   ⚠️ 2026-10-29 实测改判：原定把 WEAK 做成一个 `actual`（confirmed=False）。
#      但 16 条真实输出里 WEAK **一次都没落** —— 因为"只用了碎片"的三种情况
#      全都以问号结尾或含"我答不了"，被 QUESTION / REPORT_OWN_STATE 先抓走。
#      ⇒ 改成独立字段 `thought_level`，`actual` 仍是 QUESTION（confirmed 照旧）。
#      ⇒ 所以这里用**不以问号结尾**的输出来测 thought_level 本身。
one = "「我说吃了」，这话我记着。"
b = observe(one, "REFLECT", "brain", raw="那碗面泡烂在桌上，我说吃了。", thought_quotes=Q)
case("U2 ★ 只命中一段 ⇒ thought_level == WEAK",
     b["thought_level"] == "WEAK" and len(b["thought_quote_hits"]) == 1,
     "level=%r hits=%r" % (b["thought_level"], b["thought_quote_hits"]))

# ── U3 一段都没中 ⇒ 走原有分支
none_out = "你最近怎么样？"
c = observe(none_out, "REFLECT", "brain", raw="那碗面泡烂在桌上，我说吃了。", thought_quotes=Q)
case("U3 一段都没中 ⇒ 不落新分支（这里是 QUESTION）",
     c["actual"] == "QUESTION", "%r" % (c["actual"],))

# ── U4 人称转换
case("U4 ★ 人称转换（我腿都软了 ↔ 你腿都软了）算命中",
     quote_hit("我腿都软了", "「就想跟他说」的时候，你「腿都软了」。"),
     "")

# ── U5 分句引用
case("U5 ★ 分句引用（他已经走了，再也回不来了 ↔ 再也回不来了）算命中",
     quote_hit("他已经走了，再也回不来了", "「再也回不来了」，还有「不敢点开」。"),
     "")

# ── U6 虚词剥壳
case("U6 ★ 虚词剥壳（我又怕他知道 ↔ 怕他知道）算命中",
     quote_hit("我又怕他知道", "「想让他知道」，又「怕他知道」——"),
     "")

# ── U7 不凑数
d = observe("「我是不是挺烦人的」这个我答不了。但「你别真不盯啊」这句我接着——我没走开。",
            "REFLECT", "brain", raw="哎你别真不盯啊…我是不是挺烦人的。",
            thought_quotes=["你别真不盯啊", "不知道拿它怎么办了"])
lv, hits = thought_level("「我是不是挺烦人的」这个我答不了。但「你别真不盯啊」这句我接着——我没走开。",
                         ["你别真不盯啊", "不知道拿它怎么办了"])
case("U7 ★ 不凑数：只用了其中一段 ⇒ 仍是 WEAK（不升 STRONG）",
     lv == "WEAK" and len(hits) == 1, "level=%r hits=%r" % (lv, hits))

# ── U8 向后兼容
e = observe("你刚才说的是：「随便」。", "REFLECT", "brain", raw="随便。")
case("U8 没有 thought_quotes 时行为与改动前一致（thought_level 为空）",
     e["actual"] != "THOUGHT_EXECUTED_STRONG" and e["thought_level"] == "",
     "%r level=%r" % (e["actual"], e["thought_level"]))

# ── U9 台账白名单
#   ★ 只有 STRONG 是 actual；WEAK 已改为独立字段（见 U2 的注释）
case("U9 ★ THOUGHT_EXECUTED_STRONG 在白名单里（否则 append 会抛 ValueError）",
     "THOUGHT_EXECUTED_STRONG" in ALLOWED_BEHAVIORS,
     "不在白名单")

# ── 附：沉默记号仍然优先
f = observe(SILENCE_TOKEN, "REFLECT", "brain", raw="x", thought_quotes=Q)
case("附 沉默记号仍然优先于 Thought 分支",
     f["actual"] == "SILENCE", "%r" % (f["actual"],))

print("-" * 78)
print("结果: %d 通过 / %d 失败 / 共 %d" % (OK, FAIL, OK + FAIL))
print()
print("MUTATION 表")
print("  MUT-A 去掉人称/虚词剥壳                  → U4、U6")
print("  MUT-B 去掉分句剥壳                        → U5")
print("  MUT-C 把 WEAK 也升成 STRONG                → U2、U7")
print("  MUT-D 把 STRONG 的条件改成 ≥1 段          → U7")
sys.exit(1 if FAIL else 0)
