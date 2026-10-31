# -*- coding: utf-8 -*-
"""R1-R6：cliche 有显式规则；其余兜底语义不变（2026-10-28）。

背景：`cliche`（套话/泛泛评价）在阶梯里**没有任何规则**，于是掉到兜底 REFLECT，
输出「你用了这样一句话：「我觉得一个人最重要的品质是诚实」。」
而 mechanism.py 自己的注释写着「原样贴回去太浪费」「复述只是最低限度的兜底，从来不是目标」。

★ 曾经试过、又退回的修法：删掉 pipeline 里 `mcond.action not in explicit`，
  让机制动作无条件覆盖兜底。那个理由本身对，但副作用是真回归
  （REPLENISH 变成默认，而它的模板不适合"已经给了具体体验"的输入）。
  ⇒ 精准修法：只给 `cliche` 加一条显式规则。
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


def turn(raw, prev=None):
    d = tempfile.mkdtemp()
    p = Pipeline(ledger_path=os.path.join(d, "state/ledger.jsonl"),
                 character_path=os.path.join(d, "state/character.json"),
                 devlevel_path=os.path.join(d, "state/devlevel_verified.json"),
                 carry_root=d, gate_perception=True, auto_audit=False,
                 use_api=False, use_think=False)
    if prev:
        for x in prev:
            p.turn(x)
    return p.turn(raw)


print("=" * 78)
print("  cliche 的显式规则（R1-R6）")
print("=" * 78)

# ── R1 ★ 套话 → 要求具体（不再只复述）
r = turn("我觉得一个人最重要的品质是诚实")
case("R1 ★ cliche → REPLENISH（不再只复述）",
     r.behavior == "REPLENISH" and "cliche" in (r.markers or []),
     "behavior=%r markers=%s" % (r.behavior, r.markers))

# ── R2 输出不是元层措辞
case("R2 输出不是「你用了这样一句话」",
     "你用了这样一句话" not in (r.output or ""), (r.output or "")[:80])

# ── R3 ★ 已经给了具体体验的，**不该**再要求具体（这是我那次试错暴露的真问题）
r = turn("我站在那里闻了半小时桂花。")
case("R3 具体体验的输入**不**走 REPLENISH（不答非所问）",
     r.behavior != "REPLENISH" or "cliche" in (r.markers or []),
     "behavior=%r markers=%s" % (r.behavior, r.markers))

# ── R4 显式规则仍优先：over_intention
r = turn("我一定要得到那个结果，得不到我就难受")
case("R4 over_intention 仍只允许 REFLECT / ASK_MUST",
     r.behavior in {"REFLECT", "ASK_MUST"}, "behavior=%r" % (r.behavior,))

# ── R5 显式规则仍优先：opposed_pair
r = turn("一个人可以同时是好的和坏的吗？我认为可以")
case("R5 opposed_pair → JUXTAPOSE", r.behavior == "JUXTAPOSE",
     "behavior=%r" % (r.behavior,))

# ── R6 显式规则仍优先：immutable
r = turn("我爸妈已经离婚了，这件事改不了。")
case("R6 immutable → TURN_IMMUTABLE", r.behavior == "TURN_IMMUTABLE",
     "behavior=%r markers=%s" % (r.behavior, r.markers))

print("-" * 78)
print("结果: %d 通过 / %d 失败 / 共 %d" % (OK, FAIL, OK + FAIL))
print()
print("MUTATION 表")
print("  M1 删掉 ladder 里 cliche 那条                    → R1、R2")
print("  M2 把 cliche 那条挪到「其余情形」之后             → R1（永远轮不到）")
print("  M3 把 cliche 的 pick 改成 REFLECT                → R1")
sys.exit(1 if FAIL else 0)
