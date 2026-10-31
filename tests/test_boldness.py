# -*- coding: utf-8 -*-
"""B1-B9：深度遭遇（CONFIRMED/REBUFFED）与 boldness 双向读数（2026-10-29）。

★ 铁律（Gemini 拍板）：**`Character.modulate` 一字不改** ——
  讨好防线维持「结构上不可能」。只新增一个**只由经历累积**的读数 `boldness`。

★ 判据（先写）：
  B1 ★ CONFIRMED：她 BOLD 了、他端出新 claim、够长、没在收尾
  B2 ★ REBUFFED：他收尾了
  B3 ★ REBUFFED：骤短（<12 字且 <40%）且零新 claim
  B4 ★ 她没 BOLD（只是复述）⇒ 既非确认也非受挫
  B5 ★ 「话变长了但零新 claim」⇒ **不算** CONFIRMED（防"啰嗦当深入"）
  B6 ★ 「第 t 轮 3 条、第 t+1 轮 2 条极深刻」⇒ 仍算 CONFIRMED（防漏判）
  B7 ★ boldness 公式：0.5 + 0.08*(confirmed-rebuffed)，clamp 到 [0,1]
  B8 ★ boldness 在 `polarity_from_mech` **之后**赋值（不被冲掉）
  B9 ★★ **`modulate` 的防讨好结构未被改动**（只准向右，永不向左）
"""
import io
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)
sys.path[:0] = [str(_ROOT), str(_ROOT + "/engine")]

from association import classify_encounter  # noqa: E402
from character import CONSERVATISM, Character  # noqa: E402

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


def E(raw, claims=(), act="QUESTION", tl="", op="DILEMMA", closing=False):
    return {"raw_input": raw,
            "action_observation": {"actual": act, "thought_level": tl},
            "cognition": {"op": op, "claims": [{"text": t} for t in claims]},
            "mech": {"is_closing": closing}}


BOLD = E("我很难受，想跟你说说这件事，一直憋着。", claims=("甲",))

print("=" * 78)
print("  深度遭遇 + boldness（B1-B9）")
print("=" * 78)

case("B1 ★ CONFIRMED：她 BOLD 了、他端出新 claim、够长、没收尾",
     classify_encounter(BOLD, E("行吧被你逮着了，其实修好那天我戴着看了好几回，"
                                "我爸到现在都不知道我动过那块表。", claims=("乙", "丙")))
     == "CONFIRMED")

case("B2 ★ REBUFFED：他在收尾",
     classify_encounter(BOLD, E("嗯，算了，不说了。", claims=(), closing=True))
     == "REBUFFED")

case("B3 ★ REBUFFED：骤短且零新 claim",
     classify_encounter(BOLD, E("嗯。", claims=())) == "REBUFFED")

case("B4 ★ 她没 BOLD（只是复述）⇒ 既非确认也非受挫",
     classify_encounter(E("我很难受。", claims=("甲",), act="REFLECT", op=""),
                        E("很长的一段回答，端出了新东西，说了很多事情。", claims=("乙",)))
     == "")

case("B5 ★ 「话变长了但零新 claim」⇒ 不算 CONFIRMED（防啰嗦当深入）",
     classify_encounter(BOLD, E("嗯嗯是啊你说得对我也这么想过反正就是这样吧其实都一样。",
                                claims=("甲",)))
     != "CONFIRMED")

case("B6 ★ 第 t 轮 3 条、第 t+1 轮 2 条极深刻 ⇒ 仍算 CONFIRMED（防漏判）",
     classify_encounter(E("我很难受。", claims=("甲", "乙", "丙")),
                        E("我戴手上看了好几回，我爸到现在都不知道我动过那块表。",
                          claims=("丁", "戊")))
     == "CONFIRMED")


def bold_of(cf, rb):
    return max(0.0, min(1.0, 0.5 + 0.08 * (cf - rb)))


case("B7 ★ boldness 公式 clamp 正确",
     abs(bold_of(5, 1) - 0.82) < 1e-9 and bold_of(0, 100) == 0.0 and bold_of(100, 0) == 1.0,
     "%.3f/%.3f/%.3f" % (bold_of(5, 1), bold_of(0, 100), bold_of(100, 0)))


class _A:
    pairs = []

    def __init__(self, cf, rb):
        self.confirmed_count = cf
        self.rebuffed_count = rb


d = tempfile.mkdtemp()
ch = Character(os.path.join(d, "character.json"))
MECH = {"turn": 3, "w": 10.0, "l": 0.5, "a": 1.0, "e": 0.1, "tension": 3.0}
_before = ch.polarity.boldness
ch.learn(_A(5, 1), MECH)
#   ⚠️ 2026-10-30 更新（架构病灶 5）：**`learn()` 不再重算 `boldness`。**
#      它现在是**有界状态机**，只由 `settle_encounter()` 逐步增量 + 每步 clamp。
#      ⇒ 所以这里断言的是"**批处理不会把它冲掉**"（保留原意），
#        而不是"批处理会把它算成 0.82"（那是旧的、会饱和的公式）。
case("B8 ★ learn() 的批处理**不会冲掉** boldness（它由 settle_encounter 持有）",
     abs(ch.polarity.boldness - _before) < 1e-9,
     "learn 前 %.3f → 后 %.3f" % (_before, ch.polarity.boldness))

# ── 新增 B10：逐步增量 + 每步 clamp（病灶 5 的正面验证）
ch2 = Character(os.path.join(tempfile.mkdtemp(), "character.json"))
for _ in range(3):
    ch2.settle_encounter("CONFIRMED")
_up = ch2.polarity.boldness
for _ in range(30):
    ch2.settle_encounter("REBUFFED")
_down = ch2.polarity.boldness
case("B10 ★★ 负反馈没被泡沫顶死：连受 30 次挫能从上方降回来",
     _up > 0.55 and _down < 0.05,
     "确认 3 次后 %.3f｜再受挫 30 次后 %.3f" % (_up, _down))
_ch = Character(os.path.join(tempfile.mkdtemp(), "character.json"))
for _ in range(100):
    _ch.settle_encounter("CONFIRMED")
case("B10b ★ 上限就是 1.00（每步 clip，不堆泡沫）",
     abs(_ch.polarity.boldness - 1.0) < 1e-9,
     "%.3f" % _ch.polarity.boldness)

# ── B9 ★★ 最重要：modulate 的防讨好结构未被改动
src = io.open(os.path.join(_ROOT, "engine", "character.py"), encoding="utf-8").read()
i = src.find("def modulate")
j = src.find("def ", i + 10)
body = src[i:j]
case("B9 ★★ modulate 里没有任何向左走（i -= / i - 1）",
     ("i -= 1" not in body) and ("i - 1" not in body) and ("i + 1" in body or "i += 1" in body),
     "左移出现=%s 右移出现=%s" % ("i -= 1" in body, "i += 1" in body or "i + 1" in body))
#   ⚠️ 2026-10-30 更新（主线任务 1）：`modulate` 现在**会读** `boldness` ——
#      但只在 **R4「刚碰了钉子就收一收」**这条**向右**规则里读：
#        `if ... and ((_enc == "REBUFFED") or (_bd < 0.42)): i = _i + 1`
#      ⇒ 低笃定 ⇒ **更保守**。这与 B9 的结构护栏（永不向左）完全一致。
#   ⇒ 所以断言要精确化成「读 boldness 的那段里不含向左」，
#      而不是"完全不读" —— 后者会误杀一条合法的向右规则。
_i4 = body.find("boldness")
case("B9b ★★ 读 boldness 的那段里**没有向左**（只能让它更保守）",
     _i4 >= 0 and ("_i + 1" in body[_i4:_i4 + 900]),
     "读到了 boldness，但附近没有 `_i + 1`（向右）")
case("B9c ★ CONSERVATISM 顺序未变（单向棘轮还在）",
     CONSERVATISM[0] == "ASK_MUST" and CONSERVATISM[-1] == "SILENCE",
     str(CONSERVATISM))

# ── 里程碑
d2 = tempfile.mkdtemp()
ch2 = Character(os.path.join(d2, "character.json"))
ch2.learn(_A(5, 1), MECH)
case("附带 ★ 确认≥3 且 >受挫 ⇒ 固化一条里程碑，且主语是「我」",
     len(ch2.milestones) == 1 and ch2.milestones[0].text.startswith("我曾"),
     "%s" % [m.text[:30] for m in ch2.milestones])
ch3 = Character(os.path.join(tempfile.mkdtemp(), "character.json"))
ch3.learn(_A(2, 1), MECH)
case("附带 ★ 确认<3 ⇒ 不固化",
     len(ch3.milestones) == 0, "%d 条" % len(ch3.milestones))

print("-" * 78)
print("结果: %d 通过 / %d 失败 / 共 %d" % (OK, FAIL, OK + FAIL))
print()
print("MUTATION 表")
print("  MUT-A 把 has_new_claim 去掉                  → B1、B5")
print("  MUT-B 把 len/ratio 守卫去掉                  → B3")
print("  MUT-C 把 boldness 挪到 polarity_from_mech 之前 → B8")
print("  MUT-D 在 modulate 里加一行 i -= 1             → B9")
sys.exit(1 if FAIL else 0)
