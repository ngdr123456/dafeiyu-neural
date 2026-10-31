# -*- coding: utf-8 -*-
"""A1-A6：锚点抽取的碎片守卫（2026-10-28）。

★ 病灶：`_ANCHOR_THING` 有单字项（钱／车／病／学），`_ANCHOR_PERSON` 也有
  （爸／妈／妻…），于是"毛病"里切出"病"、"同学"里切出"学"。
  接进 Frame 之后，模型会问「你说的「病」是怎么回事」——
  **比复述更糟：它在引用一个对方没说过的词**（违反"不许编"）。

★ 判据：单字项只有在前面紧跟人称代词、或前面是句首/标点时才算数。
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)
sys.path[:0] = [str(_ROOT), str(_ROOT + "/engine")]

from respond import Responder  # noqa: E402

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


def anchor(raw):
    return Responder()._pick_anchor(raw)[1]


print("=" * 78)
print("  锚点碎片守卫（A1-A6）")
print("=" * 78)

# ── A1 ★ "毛病" 不许切出 "病"
case("A1 ★ 「有点毛病」不切出「病」",
     anchor("你说我这是不是有点毛病啊。") != "病",
     repr(anchor("你说我这是不是有点毛病啊。")))

# ── A2 ★ "同学" 不许切出 "学"
case("A2 ★ 「同学」不切出「学」",
     anchor("我同学昨天跟我说了件事。") != "学",
     repr(anchor("我同学昨天跟我说了件事。")))

# ── A3 带人称代词的单字仍可用
case("A3 「我妈」仍抽出「我妈」",
     anchor("我妈只问了一句第一是谁。") == "我妈",
     repr(anchor("我妈只问了一句第一是谁。")))

# ── A4 句首单字仍可用
case("A4 句首的「爸」仍可抽出",
     "爸" in anchor("爸，我跟你说个事。"),
     repr(anchor("爸，我跟你说个事。")))

# ── A5 双字词不受影响
case("A5 「工作」仍抽出「工作」",
     anchor("我那工作干了八年。") == "工作",
     repr(anchor("我那工作干了八年。")))

# ── A6 ★ 抽出的锚点必须逐字出现在原话里（不编）
for t in ("你说我这是不是有点毛病啊。", "我妈只问了一句第一是谁。",
          "我那工作干了八年。", "那天晚上我坐在楼下。"):
    a = anchor(t)
    if a and a not in t:
        case("A6 ★ 锚点必须逐字出现在原话里", False, "%r 不在 %r" % (a, t))
        break
else:
    case("A6 ★ 锚点必须逐字出现在原话里", True)

print("-" * 78)
print("结果: %d 通过 / %d 失败 / 共 %d" % (OK, FAIL, OK + FAIL))
print()
print("MUTATION 表")
print("  MUT-A 删掉单字守卫                 → A1、A2")
print("  MUT-B 把守卫改成恒真（永远跳过）      → A3、A4")
sys.exit(1 if FAIL else 0)
