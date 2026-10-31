# -*- coding: utf-8 -*-
"""S1-S8：五段式管线重构的结构断言（2026-10-30）。

★ 依据：Gemini `deepseek_20261030.md` 五大架构病灶
★ 判据（先写）：
  S1 ★ 病灶 1+2：`cognition.extract` 必须在 `_settle_previous_encounter` **之前**
  S2 ★ 病灶 1：`_settle_previous_encounter` 必须在 `_arbitrate_focus` **之前**
  S3 ★ 病灶 4：`ruminate()` **不在** `turn()` 开头（只在 `_arbitrate_focus` 的 P3 里调）
  S4 ★ 病灶 4：P3 的五个门控条件都在（REBUFFED / 低笃定 / 冷却 / cognition 关 / 无 P1P2）
  S5 ★ 病灶 3：`_build_frame` 组 stance 时**传了** `final_bid` 与 `char_note`
  S6 ★ 病灶 3：`char_note` 非空且落在收敛集 ⇒ stance 真的被覆盖
  S7 ★ 病灶 3：`char_note` 为空 ⇒ **不覆盖**（REFLECT 是兜底，不是刹车）
  S8 ★ 病灶 5：`boldness` 每步 clip（连受 30 次挫能降回来）
"""
import io
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)
sys.path[:0] = [str(_ROOT), str(_ROOT + "/engine")]

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


SRC = io.open(os.path.join(_ROOT, "engine", "pipeline.py"), encoding="utf-8").read()
STANCE = io.open(os.path.join(_ROOT, "engine", "stance.py"), encoding="utf-8").read()

print("=" * 78)
print("  五段式管线（S1-S8）")
print("=" * 78)

i_extract = SRC.find("_cog.extract(self.reader, raw, passes=2)")
i_settle = SRC.find("self._settle_previous_encounter(")
i_arb = SRC.find("self._arbitrate_focus(raw, mst, mech_note)")
case("S1 ★ extract 在 settle 之前（病灶 2：未感知先裁决）",
    0 < i_extract < i_settle, "%d < %d" % (i_extract, i_settle))
case("S2 ★ settle 在 arbitrate 之前（漏斗要读结算结果）",
     0 < i_settle < i_arb, "%d < %d" % (i_settle, i_arb))

# ── S3：turn() 开头不能有 ruminate()
i_turn = SRC.find("    def turn(self, raw: str")
i_desc = SRC.find("    def _describe_last(self)")
turn_body = SRC[i_turn:i_desc]
case("S3 ★ `ruminate()` 不在 `turn()` 开头（已移到 P3）",
     "self.ruminate()" not in turn_body,
     "turn() 里仍在调")

# ── S4：P3 五个门控
i_arbdef = SRC.find("    def _arbitrate_focus(self")
i_arbend = SRC.find("    def _settle_previous_encounter(self")
arb = SRC[i_arbdef:i_arbend]
gates = {
    "P1 当轮算子": "_pending_thought" in arb,
    "P2 悬念": "unfinished_focus" in arb,
    "REBUFFED 门控": '== "REBUFFED"' in arb,
    "低笃定门控": "< 0.42" in arb,
    "冷却一轮": "_idle_prev_turn" in arb,
    "cognition 关闭": "use_cognition" in arb,
    "真的调 ruminate": "self.ruminate()" in arb,
}
missing = [k for k, v in gates.items() if not v]
case("S4 ★ P3 的七个组成都在（P1/P2/REBUFFED/低笃定/冷却/cognition/调用）",
     not missing, "缺：%s" % missing)

# ── S5：_build_frame 传 final_bid / char_note
case("S5 ★ `_build_frame` 组 stance 时传了 final_bid 与 char_note",
     "final_bid=getattr(self, \"_final_bid\"" in SRC
     and "char_note=getattr(self, \"_char_note\"" in SRC)

# ── S6 / S7：stance 的覆盖条件
sys.path.insert(0, os.path.join(_ROOT, "engine"))
from stance import stance_for  # noqa: E402

#   ⚠️ 2026-10-30 更新（Z6/Z7）：严厉禁令现在**只给真碰壁**
#      （`last_encounter == "REBUFFED"` 或 `boldness < 0.42`），
#      因为 R1/R2/R3 的常规平滑不该下"不要追问"的全局禁令。
_s6 = stance_for("ASKABLE", final_bid="REFLECT", char_note="R4 刚碰了钉子",
                 last_encounter="REBUFFED", boldness=0.5)
case("S6 ★ char_note 非空 + 收敛集 ⇒ stance 被覆盖为「性格收敛」",
     "性格收敛" in _s6, "%r" % _s6[:40])
_s7 = stance_for("ASKABLE", final_bid="REFLECT", char_note=None)
case("S7 ★ char_note 为空 ⇒ **不覆盖**（REFLECT 是兜底，不是刹车）",
     "性格收敛" not in _s7, "%r" % _s7[:40])

# ── S8：boldness 每步 clip
from character import Character  # noqa: E402

_ch = Character(os.path.join(tempfile.mkdtemp(), "character.json"))
for _ in range(3):
    _ch.settle_encounter("CONFIRMED")
_up = _ch.polarity.boldness
for _ in range(30):
    _ch.settle_encounter("REBUFFED")
case("S8 ★ 病灶 5：连受 30 次挫能从上方降回来（负反馈未被顶死）",
     _up > 0.55 and _ch.polarity.boldness < 0.05,
     "升到 %.2f → 降到 %.2f" % (_up, _ch.polarity.boldness))

print("-" * 78)
print("结果: %d 通过 / %d 失败 / 共 %d" % (OK, FAIL, OK + FAIL))
print()
print("MUTATION 表")
print("  MUT-A 把 ruminate() 挪回 turn() 开头        → S3")
print("  MUT-B 去掉 char_note 判据（只判 final_bid）  → S7")
print("  MUT-C 把 boldness 改回全量累加后 clamp       → S8")
print("  MUT-D stance 不传 final_bid                  → S5")
sys.exit(1 if FAIL else 0)
