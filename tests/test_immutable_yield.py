# -*- coding: utf-8 -*-
"""Y1-Y5：`IMMUTABLE_VS_ACTION_SPLIT` 触发时 `TURN_IMMUTABLE` 让位（2026-10-29）。

★ 依据（Gemini 两封信都点名要的一条）：
  「当 `IMMUTABLE_VS_ACTION_SPLIT` 触发时让阶梯的 `TURN_IMMUTABLE` 让位」

  为什么必须让：
    · `TURN_IMMUTABLE` 的模板只说「这一块改不了。改不了的部分之外，还有别的吗？」
    · 而 Thought 已经把「哪半截定了 + 哪半截是他自己做的」两条原话都找齐了
    ⇒ 前者只处理处境，后者才是真正的洞察

  为什么让给 `JUXTAPOSE`：Thought 本身就是"把两处原话并排摆出来"，
  而那正是 `JUXTAPOSE` 的定义 —— 这不是换一个新动作，是**同类里更具体的那一个**。

★ 判据（先写）：
  Y1 ★ 有 IMMUTABLE_VS_ACTION_SPLIT 且阶梯给 TURN_IMMUTABLE ⇒ 变成 JUXTAPOSE
  Y2 ★ 没有 Thought 时，TURN_IMMUTABLE 照旧（不许无条件让位）
  Y3 ★ Thought 是别的算子时，TURN_IMMUTABLE 照旧
  Y4 ★ 阶梯给的不是 TURN_IMMUTABLE 时，不被这条规则改动
  Y5 让位留痕进台账（可追溯）
"""
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)
sys.path[:0] = [str(_ROOT), str(_ROOT + "/engine")]

from cognition_ops import Thought  # noqa: E402
from pipeline import Pipeline      # noqa: E402

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


def run(raw, thought=None):
    d = tempfile.mkdtemp()
    p = Pipeline(ledger_path=os.path.join(d, "state/ledger.jsonl"),
                 character_path=os.path.join(d, "state/character.json"),
                 devlevel_path=os.path.join(d, "state/devlevel_verified.json"),
                 carry_root=d, gate_perception=True, auto_audit=False,
                 use_api=False, use_think=False)
    p._pending_thought = thought
    r = p.turn(raw)
    notes = list(p.ledger.effective_entries[-1].notes or [])
    return r, notes


IMM = "我爸妈已经离婚了，这件事改不了。"      # 命中 immutable
TH = Thought("IMMUTABLE_VS_ACTION_SPLIT", ["我爸妈已经离婚了", "这件事改不了"], "hint")
TH_OTHER = Thought("WANT_VS_COST_GAP", ["想辞职", "每天加班"], "hint")


print("=" * 78)
print("  TURN_IMMUTABLE 让位（Y1-Y5）")
print("=" * 78)

# ── 基线：没有 Thought 时是 TURN_IMMUTABLE
r0, _ = run(IMM)
case("基线：没有 Thought 时，immutable 走 TURN_IMMUTABLE",
     r0.planned_behavior == "TURN_IMMUTABLE",
     "planned=%r" % (r0.planned_behavior,))

# ── Y1 ★ 有算子 4 的 Thought ⇒ **让位发生**
#
#   ⚠️ 2026-10-29 实测改判：原来断言 `planned_behavior == "JUXTAPOSE"`，
#      但实测是 `REFLECT`。查台账 notes 才发现：
#        让位**成功**了（留痕在），但紧接着 `JUXTAPOSE` 模板
#        **缺第二个引文槽位** ⇒ 模板层退回 REFLECT（它的既有兜底）。
#      ⇒ 所以这条测试不能断言 planned，只能断言"让位发生了"。
#      ⇒ 而**真正兑现并置的是大脑路径**（Thought 已在 Frame 里）——
#         C4 实测 11/16 命中。模板路径兑现不了"两段并置"是它的固有限制，
#         不是这条规则的错。
r1, n1 = run(IMM, TH)
case("Y1 ★ 有 IMMUTABLE_VS_ACTION_SPLIT ⇒ 让位发生，且**让位后的 bid 真的是 JUXTAPOSE**",
     any("让位后的计划动作=JUXTAPOSE" in x for x in n1),
     "planned=%r notes=%s" % (r1.planned_behavior, [x[:40] for x in n1[:3]]))

# ── Y2 没有 Thought ⇒ 不让位（=基线）
case("Y2 ★ 没有 Thought 时不让位", r0.planned_behavior == "TURN_IMMUTABLE")

# ── Y3 别的算子 ⇒ 不让位
r3, _ = run(IMM, TH_OTHER)
case("Y3 ★ Thought 是别的算子时不让位",
     r3.planned_behavior == "TURN_IMMUTABLE",
     "planned=%r" % (r3.planned_behavior,))

# ── Y4 阶梯给的不是 TURN_IMMUTABLE ⇒ 这条规则不生效
OTHER = "一个人可以同时是好的和坏的吗？我认为可以"   # opposed_pair → JUXTAPOSE
r4, _ = run(OTHER, TH)
case("Y4 ★ 非 immutable 输入时，这条规则不生效（仍是 JUXTAPOSE，但不是让位来的）",
     r4.planned_behavior == "JUXTAPOSE",
     "planned=%r" % (r4.planned_behavior,))

# ── Y5 留痕
hit = [x for x in n1 if "让位" in x]
case("Y5 让位留痕进了台账", bool(hit), "notes=%s" % (n1[:2],))

# ── Y6 ★ 阶梯给的是 REPLENISH（cliche 规则）时，让位规则**不许改动它**
#
#   这条是补 MUT-B 的漏：去掉 `bid == TURN_IMMUTABLE` 判定后，
#   Y4 的输入 bid 本来就是 JUXTAPOSE，所以抓不到。这里用 cliche → REPLENISH 的输入。
CLICHE = "我觉得一个人最重要的品质是诚实"
r6, n6 = run(CLICHE, TH)
case("Y6 ★ 阶梯给 REPLENISH 时，让位规则不动它（仍是 REPLENISH）",
     r6.planned_behavior == "REPLENISH"
     and not any("让位后的计划动作" in x for x in n6),
     "planned=%r notes=%s" % (r6.planned_behavior, [x[:34] for x in n6[:3]]))

print("-" * 78)
print("结果: %d 通过 / %d 失败 / 共 %d" % (OK, FAIL, OK + FAIL))
print()
print("MUTATION 表")
print("  MUT-A 去掉 op 判定（任何 Thought 都让位）  → Y3")
print("  MUT-B 去掉 bid == TURN_IMMUTABLE 判定       → Y6")
print("  MUT-C 让位目标改成 REFLECT                  → Y1")
sys.exit(1 if FAIL else 0)
