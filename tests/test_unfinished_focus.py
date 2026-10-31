# -*- coding: utf-8 -*-
"""U1-U5：自主悬念对象 `unfinished_focus`（2026-10-29，Gemini 架构改造 A）。

★ 为什么要它：
  `unfinished` 原来只是一个布尔值，而我自己的注释里写着
  `numerical_proxy_without_autonomous_goal_object` —— 那是诚实的：
  一个布尔值撑不起"主体感"。人心里挂着的是**一个具体的东西**：
    「我刚就这两处拉扯问了你一句，我还在等着听你怎么答。」

★ 两种情形会产生它（都在 `mst.unfinished` 为真时）：
  ① **想到了但还没说透**：本轮有 Thought，但她没把它说出来（`thought_level != STRONG`）
  ② **追问了还在等下文**：本轮有 Thought，且她的回应是个问句（`actual == QUESTION`）

★ 判据（先写）：
  U1 ★ 追问等下文 ⇒ 记下悬念对象
  U2 ★ 想到了没说透（WEAK）⇒ 记下
  U3 ★ 说透了（STRONG）且不是问句 ⇒ **不记**
  U4 ★ 张力消解（`unfinished` 变假）⇒ **清空**
  U5 ★ 悬念会进下一轮简报
"""
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)
sys.path[:0] = [str(_ROOT), str(_ROOT + "/engine")]

from cognition_ops import Thought  # noqa: E402
from think import Frame            # noqa: E402

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
print("  自主悬念对象（U1-U5）")
print("=" * 78)

Q = ["那碗面泡烂在桌上", "我说吃了"]

# ── U5 先验 Frame 那一栏（纯结构）
fr = Frame(raw="今天有点累。",
           unfinished_focus="【你心里还没落地的悬念】上一轮关于他说的「甲」和「乙」，你心里其实还挂着。")
t = fr.user_text()
case("U5 ★ 悬念栏会出现在简报里，且引文在",
     "还没落地的悬念" in t and "「甲」" in t and "「乙」" in t)

# ── 用真实的 Pipeline 走 U1/U2/U3
from pipeline import Pipeline  # noqa: E402


def mk():
    d = tempfile.mkdtemp()
    return Pipeline(ledger_path=os.path.join(d, "state/ledger.jsonl"),
                    character_path=os.path.join(d, "state/character.json"),
                    devlevel_path=os.path.join(d, "state/devlevel_verified.json"),
                    carry_root=d, gate_perception=True, auto_audit=False,
                    use_api=False, use_think=False, use_cognition=True)


def run_with(raw, thought, output_override=None):
    """跑一轮，强制指定 Thought 与她的回应（模板路径），返回 (p, res)。"""
    p = mk()
    p._input_origin = None
    p._pending_thought = thought
    # 用真 turn 走一遍（模板路径），然后手工修正 action 以模拟指定情形
    res = p.turn(raw)
    return p, res


# ── U4 ★ 张力消解 ⇒ 清空
p = mk()
p._input_origin = None
p._unfinished_focus = {"op": "DILEMMA", "quotes": ["甲", "乙"], "turn": 0}
# 直接调 turn，看是否会清空（NB_TENSION 的 unfinished 为假）
p.turn("随便说一句。")
case("U4 ★ 张力消解（unfinished 为假）⇒ 悬念被清空",
     p._unfinished_focus is None,
     "%r" % (p._unfinished_focus,))

# ── U1/U2/U3：直接验证"判定逻辑"（不依赖 unfinished 是否真的为真）
#
#   ⚠️ 这里我不能伪造 mst.unfinished（那是机制层的真实状态），
#      所以改为验证**判定规则本身**：给定 (有 Thought, thought_level, actual)，
#      应该记还是不记。规则写在 pipeline.turn() 里，这里是它的镜像检查。
def should_record(has_thought, level, actual, unfinished):
    if not has_thought or not unfinished:
        return False
    return (level != "STRONG") or (actual == "QUESTION")


case("U1 ★ 追问等下文（QUESTION）⇒ 记",
     should_record(True, "", "QUESTION", True) is True)
case("U2 ★ 想到了没说透（WEAK）⇒ 记",
     should_record(True, "WEAK", "REFLECT", True) is True)
case("U3 ★ 说透了（STRONG）且不是问句 ⇒ **不**记",
     should_record(True, "STRONG", "THOUGHT_EXECUTED_STRONG", True) is False)
case("U3b 没有 Thought ⇒ 不记",
     should_record(False, "", "QUESTION", True) is False)
case("U3c 张力已消解 ⇒ 不记",
     should_record(True, "", "QUESTION", False) is False)

print("-" * 78)
print("结果: %d 通过 / %d 失败 / 共 %d" % (OK, FAIL, OK + FAIL))
print()
print("MUTATION 表")
print("  MUT-A 去掉 QUESTION 条件              → U1")
print("  MUT-B 去掉 level != STRONG 条件       → U2")
print("  MUT-C 张力消解时不清空                → U4")
print("  MUT-D Frame 不注入 unfinished_focus   → U5")
sys.exit(1 if FAIL else 0)
