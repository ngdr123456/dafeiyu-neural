# -*- coding: utf-8 -*-
"""R1-R5：机制层的动作在「阶梯只给兜底」时必须被采纳（2026-10-28 修）。

原条件的错：
    if bid == "REFLECT" and mcond.action != "REFLECT" and mcond.action not in explicit:
`explicit` 是「哪些动作有显式阶梯规则」。而 `bid == "REFLECT"` 已经证明
**这次没有显式规则命中**（否则 bid 就是那条的 pick）。
⇒ 多出来的 `not in explicit` 只会挡住「机制想选一个名字恰好也在显式集合里的动作」。

实测后果：`cliche`（套话）→ 输出「你用了这样一句话：……」
而 mechanism.py 自己的注释写着「原样贴回去太浪费」「复述只是最低限度的兜底」。
"""
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)
sys.path[:0] = [str(_ROOT), str(_ROOT + "/engine")]

from pipeline import Pipeline  # noqa: E402

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


def turn(raw):
    d = tempfile.mkdtemp()
    p = Pipeline(ledger_path=os.path.join(d, "state/ledger.jsonl"),
                 character_path=os.path.join(d, "state/character.json"),
                 devlevel_path=os.path.join(d, "state/devlevel_verified.json"),
                 carry_root=d, gate_perception=True, auto_audit=False,
                 use_api=False, use_think=False)
    return p.turn(raw)


print("=" * 78)
print("  机制动作的采纳（R1-R5）")
print("=" * 78)

# ── R1 ★ cliché（套话）：机制 NO_TENSION 的动作 REPLENISH 在 explicit 里，
#        修好后应被采纳 ⇒ 行为不再是 REFLECT
r = turn("我觉得一个人最重要的品质是诚实")
case("R1 ★ cliché 不再只复述（机制动作 REPLENISH 被采纳）",
     r.behavior != "REFLECT",
     "behavior=%r notes=%s" % (r.behavior, [n for n in (r.notes or []) if "机制" in n][:2]))

# ── R2 输出不该是元层面描述「你用了这样一句话」
case("R2 输出不是「你用了这样一句话」那种元层措辞",
     "你用了这样一句话" not in (r.output or ""),
     (r.output or "")[:80])

# ── R3 阶梯的显式规则仍然优先（over_intention → 只允许 REFLECT/ASK_MUST）
r = turn("我一定要得到那个结果，得不到我就难受")
case("R3 over_intention 仍只允许 REFLECT / ASK_MUST（显式规则优先）",
     r.behavior in {"REFLECT", "ASK_MUST"},
     "behavior=%r" % (r.behavior,))

# ── R4 阶梯显式规则优先（opposed_pair → JUXTAPOSE）
r = turn("一个人可以同时是好的和坏的吗？我认为可以")
case("R4 opposed_pair → JUXTAPOSE（阶梯显式规则优先）",
     r.behavior == "JUXTAPOSE", "behavior=%r" % (r.behavior,))

# ── R5 不可改变处境 → TURN_IMMUTABLE（阶梯显式规则优先）
r = turn("我爸妈已经离婚了，这件事改不了。")
case("R5 immutable → TURN_IMMUTABLE（阶梯显式规则优先）",
     r.behavior == "TURN_IMMUTABLE", "behavior=%r markers=%s" % (r.behavior, r.markers))

print("-" * 78)
print("结果: %d 通过 / %d 失败 / 共 %d" % (OK, FAIL, OK + FAIL))
print()
print("MUTATION 表")
print("  M1 把 `not in explicit` 加回去                        → R1、R2")
print("  M2 把条件改成无条件（连显式规则也覆盖）                → R3、R4、R5")
print("  M3 把 `mcond.action != \"REFLECT\"` 去掉（复述也能覆盖）  → 不会失败（需另测）")
sys.exit(1 if FAIL else 0)
