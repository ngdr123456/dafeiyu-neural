# -*- coding: utf-8 -*-
"""N9-N11：端到端 —— 有界引用目标逐字核对通过时，主路径的 behavior 应被确认。

这一组专门钉住 2026-10-28 那个错：
  第一版读 `pending["goal_selection"]["result"]`，而那个 result
  要到 `_log()` 里 `self_goal.finish()` 之后才算出来，所以永远是 None。
  实测 LIVE 报告：3 个 FULFILLED_LITERAL 的 case 仍记成 UNCLASSIFIED。
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)
sys.path[:0] = [str(_ROOT), str(_ROOT + "/engine")]

from self_goal import literal_check  # noqa: E402
from action_observation import observe  # noqa: E402

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


PACKET = {"selected": {"id": "g1", "targets": [
    {"evidence": "甲项目押金由周老师收着"},
    {"evidence": "甲项目押金由赵老师收着"}]}}

GOOD = ("按你原话，「甲项目押金由周老师收着」——那是对「甲项目押金由李老师收着」的更正；"
        "后来你还说过「甲项目押金由赵老师收着」。哪句与外部实情相符，我没核实过。")
BAD = "按你原话，「甲项目押金由周老师收着」。就这一句。"

print("=" * 78)
print("  端到端：literal_check → observe（N9-N11）")
print("=" * 78)

# ── N9 引全了两条 → matched
c = literal_check(PACKET, GOOD)
case("N9 两段来源都逐字引到 → matched=True",
     isinstance(c, dict) and c.get("matched") is True, c)

# ── N10 漏了一段 → 不 matched（这一条防止把"漏引"也确认掉）
c = literal_check(PACKET, BAD)
case("N10 漏引一条 → matched=False 且 missing 指出缺哪条",
     isinstance(c, dict) and c.get("matched") is False
     and c.get("missing") == ["甲项目押金由赵老师收着"], c)

# ── N11 ★ 关键：用 literal_check 的结果喂 observe，应得确认标签
res = None
c = literal_check(PACKET, GOOD)
if isinstance(c, dict) and c.get("matched") is True:
    res = {"state": "FULFILLED_LITERAL", "literal_predicate": c}
a = observe(GOOD, "REFLECT", "brain", goal_result=res)
case("N11 ★ 走主路径时应得 QUOTE_SOURCE_SET_CONFIRMED（不是 UNCLASSIFIED）",
     a["actual"] == "QUOTE_SOURCE_SET_CONFIRMED" and a["confirmed"] is True, a)

# ── N12 漏引时**不能**确认（否则等于把没做到也算做到）
c = literal_check(PACKET, BAD)
res2 = ({"state": "FULFILLED_LITERAL", "literal_predicate": c}
        if isinstance(c, dict) and c.get("matched") is True else None)
a = observe(BAD, "REFLECT", "brain", goal_result=res2)
case("N12 漏引一条 → 仍 UNCLASSIFIED（不许把没做到算做到）",
     a["actual"] == "UNCLASSIFIED" and a["confirmed"] is False, a)

print("-" * 78)
print("结果: %d 通过 / %d 失败 / 共 %d" % (OK, FAIL, OK + FAIL))
print()
print("MUTATION 表")
print("  M1 matched 判断改成 `is not False`（None 也算过）    → N14/N12")
print("  M2 observe 里 state 判断改成 !=                     → N12")
print("  M3 literal_check 的 missing 永远返回 []              → N10")
sys.exit(1 if FAIL else 0)
