# -*- coding: utf-8 -*-
"""Z1-Z8：僵尸悬念 + 好奇门槛 + 严厉禁令收窄（2026-10-30）。

★ 依据：Gemini `第二天4.md` 的两条精确根因
★ 判据（先写）：
  Z1 ★★ 悬念**用过一轮就过期**（绝不跨轮僵尸驻留）
  Z2 ★★ 隔了 ≥2 轮的旧悬念在 P2 检查时被清空
  Z3 ★ 换会话后旧悬念被清空
  Z4 ★ hint 里必须含「务必带引号逐字点出」+ 第一人称起手式
  Z5 ★ 好奇解锁门槛是 0.52（不是 0.60）
  Z6 ★ ★ 严厉禁令只在 REBUFFED 或 boldness<0.42 时给
  Z7 ★ R1/R2/R3 的常规平滑**不给**严厉禁令
  Z8 ★ CONFIRMED 也解锁好奇（不必等 boldness 涨到 0.52）
"""
import io
import os
import sys

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
print("  僵尸悬念 + 好奇门槛 + 禁令收窄（Z1-Z8）")
print("=" * 78)

case("Z1 ★★ 悬念有「用完即焚」标记 `_unfinished_consumed`",
     "_unfinished_consumed" in SRC)
case("Z2 ★★ P2 检查里有「隔了 ≥2 轮就清空」的判据（`- _uf_turn == 1`）",
     "- _uf_turn == 1" in SRC)
case("Z3 ★ 换会话后旧悬念被清空（session_id 比较）",
     "_uf_sess" in SRC and "_cur_sess" in SRC)
case("Z4 ★ 悬念 hint 含「务必带引号逐字点出」与第一人称起手式",
     "务必带引号逐字点出" in SRC and "我还在想你刚说的" in SRC)
#   ⚠️ 必须先剥掉注释再判 —— `0.60` 还会出现在**解释旧门槛的注释**里。
#      第一版没剥，于是这条测试被自己的注释判失败（和 G12/W7 是同一个坑，第三次了）。
from test_gate_wiring import _strip_literals  # noqa: E402

_SRC_CODE = _strip_literals(SRC)
case("Z5 ★ 好奇解锁门槛是 0.52（代码里不再有 0.60 的比较）",
     ">= 0.52" in _SRC_CODE and ">= 0.60" not in _SRC_CODE,
     "0.60 残留=%r" % (">= 0.60" in _SRC_CODE))
case("Z8 ★ CONFIRMED 也解锁好奇",
     '_last_enc == "CONFIRMED"' in SRC)

# ── Z6 / Z7：stance 的严厉禁令收窄（真跑）
sys.path.insert(0, os.path.join(_ROOT, "engine"))
from stance import stance_for  # noqa: E402

_s6 = stance_for("ASKABLE", final_bid="REFLECT", char_note="R4 刚碰了钉子",
                 last_encounter="REBUFFED", boldness=0.5)
case("Z6 ★ 严厉禁令在 REBUFFED 时**给出**", "性格收敛" in _s6, "%r" % _s6[:30])
_s6b = stance_for("ASKABLE", final_bid="REFLECT", char_note="R4",
                  last_encounter="", boldness=0.35)
case("Z6b ★ 低笃定（<0.42）时也**给出**", "性格收敛" in _s6b)
_s7 = stance_for("ASKABLE", final_bid="REFLECT", char_note="R1 耐心递减",
                 last_encounter="", boldness=0.56)
case("Z7 ★★ R1/R2/R3 的常规平滑**不给**严厉禁令",
     "性格收敛" not in _s7, "%r" % _s7[:40])
_s7b = stance_for("ASKABLE", final_bid="REFLECT", char_note="R2 动作平滑",
                  last_encounter="CONFIRMED", boldness=0.59)
case("Z7b ★★ 刚被 CONFIRMED 更不该收敛（那正是该深聊的时候）",
     "性格收敛" not in _s7b, "%r" % _s7b[:40])

print("-" * 78)
print("结果: %d 通过 / %d 失败 / 共 %d" % (OK, FAIL, OK + FAIL))
print()
print("MUTATION 表")
print("  MUT-A 去掉「用完即焚」                     → Z1")
print("  MUT-B 把 - _uf_turn == 1 改回无条件         → Z2")
print("  MUT-C 严厉禁令改回只判 char_note            → Z7")
print("  MUT-D 门槛改回 0.60                         → Z5")
sys.exit(1 if FAIL else 0)
