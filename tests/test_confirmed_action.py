# -*- coding: utf-8 -*-
"""N1-N8：有界引用目标核对通过时，动作应被确认为可学习的结构标签。

事由（2026-10-28 实测）：
  真实训练走大脑路径 ⇒ observe() 除纯问句外全部 UNCLASSIFIED
  ⇒ pipeline 用 actual 覆盖 behavior ⇒ 台账 behavior = UNCLASSIFIED
  ⇒ association 学不到、experience 不产生事件、orientation 变"无"
  ⇒ 一轮大脑跑完学到的东西是零

判据：`QUOTE_SOURCE_SET_CONFIRMED` 说的是「你确实逐字引用了指定的 N 段来源」，
      这是本地核对的事实（self_goal 在比对 evidence 是否逐字出现），
      不是"你看起来像在复述"这种语义猜测。所以它**可以** confirmed=True。

⚠️ 变异纪律：每条都要能因为改坏 observe() 或映射表而失败。
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)
sys.path[:0] = [str(_ROOT), str(_ROOT + "/engine")]

from action_observation import observe, learning_action  # noqa: E402
import experience  # noqa: E402
import association  # noqa: E402

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


FULFILLED = {"state": "FULFILLED_LITERAL", "semantic_goal_fit": "UNKNOWN"}
PENDING = {"state": "PENDING", "semantic_goal_fit": "UNKNOWN"}

print("=" * 78)
print("  有界引用目标的确认动作（N1-N8）")
print("=" * 78)

# ── N1 核对通过 → 确认
a = observe("按你原话「甲项目押金由周老师收着」。", "REFLECT", "brain",
            goal_result=FULFILLED)
case("N1 逐字核对通过 → QUOTE_SOURCE_SET_CONFIRMED，confirmed=True",
     a["actual"] == "QUOTE_SOURCE_SET_CONFIRMED" and a["confirmed"] is True
     and a["basis"] == "literal_goal_predicate_matched", a)

# ── N2 未核对（PENDING）→ 仍然不确认
a = observe("按你原话「押金由周老师收着」。", "REFLECT", "brain", goal_result=PENDING)
case("N2 目标 PENDING → 仍 UNCLASSIFIED、confirmed=False（不许提前确认）",
     a["actual"] == "UNCLASSIFIED" and a["confirmed"] is False, a)

# ── N3 没有 goal_result → 行为不变（向后兼容）
a = observe("按你原话「押金由周老师收着」。", "REFLECT", "brain")
case("N3 不传 goal_result → 与从前完全一致（UNCLASSIFIED）",
     a["actual"] == "UNCLASSIFIED" and a["confirmed"] is False, a)

# ── N4 模板路径不受影响
a = observe("（模板输出）", "REFLECT", "template", goal_result=FULFILLED)
case("N4 模板路径仍以 planned 为准（不被 goal 覆盖）",
     a["actual"] == "REFLECT" and a["confirmed"] is True, a)

# ── N5 纯问句仍优先（顺序不能被打乱）
a = observe("押金由谁收着？", "ASK_DETAIL", "brain", goal_result=FULFILLED)
case("N5 纯问句优先判 QUESTION（不被 goal 分支抢走）",
     a["actual"] == "QUESTION", a)

# ── N6 新标签能被 learning_action 取到（这是"可学"的关键）
a = observe("按你原话「押金由周老师收着」。", "REFLECT", "brain",
            goal_result=FULFILLED)
row = {"action_observation": a}
case("N6 learning_action 返回新标签（不再返回 None）",
     learning_action(row) == "QUOTE_SOURCE_SET_CONFIRMED", learning_action(row))

# ── N7 经验层认识它（否则仍然不产生事件）
k = experience.SELF_ACT_KIND.get("QUOTE_SOURCE_SET_CONFIRMED")
case("N7 SELF_ACT_KIND 认识新标签，且 KIND_LABEL 有中文",
     k == "SELF_QUOTED_SOURCE" and k in experience.KIND_LABEL,
     "k=%r label=%r" % (k, experience.KIND_LABEL.get(k)))

# ── N8 关联矩阵认识它
case("N8 association.MY_KIND 认识新标签",
     association.MY_KIND.get("QUOTE_SOURCE_SET_CONFIRMED") == "引用来源",
     association.MY_KIND.get("QUOTE_SOURCE_SET_CONFIRMED"))

print("-" * 78)
print("结果: %d 通过 / %d 失败 / 共 %d" % (OK, FAIL, OK + FAIL))
print()
print("MUTATION 表")
print("  M1 去掉 FULFILLED_LITERAL 分支                 → N1、N6")
print("  M2 把 state 判断改成 !=  → PENDING 也确认       → N2")
print("  M3 把 confirmed 写成 False                     → N1、N6")
print("  M4 把新分支放到 template 分支之前               → N4")
print("  M5 把新分支放到问句分支之前                     → N5")
print("  M6 SELF_ACT_KIND 删掉新标签                     → N7")
print("  M7 MY_KIND 删掉新标签                           → N8")
sys.exit(1 if FAIL else 0)
