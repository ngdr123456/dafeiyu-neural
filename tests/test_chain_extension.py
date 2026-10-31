# -*- coding: utf-8 -*-
"""C1-C9：2 环连锁 CHAIN_EXTENSION（2026-10-29，Gemini 第 ③ 步）。"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)
sys.path[:0] = [str(_ROOT), str(_ROOT + "/engine")]

from cognition_ops import (CHAIN_BASE_OPS, CHAIN_LOOKBACK, OP_ORDER,  # noqa: E402
                           chain_extension)

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


def C(kind, text, start=0, subject=""):
    return {"kind": kind, "text": text, "start": start,
            "end": start + len(text), "subject": subject}


PREV = {0: {"op": "WANT_VS_COST_GAP",
            "quotes": ["想证明给他们看", "昨天熬到两点改"],
            "sources": [{"turn": 0, "start": 0, "end": 7, "kind": "WANT_MUST", "subject": "方案"},
                        {"turn": 0, "start": 10, "end": 17, "kind": "COST_FEEL", "subject": "方案"}]}}

print("=" * 78)
print("  2 环连锁（C1-C9）")
print("=" * 78)

# ── C1 ★ 同对象延续 ⇒ 产出
CUR = {1: [C("FIXED", "今早还是被一句话打回来了", 0, "方案")]}
t = chain_extension(1, CUR, PREV)
case("C1 ★ 同对象延续（subject 都是「方案」）⇒ 产出",
     t is not None and t.op == "CHAIN_EXTENSION",
     "%r" % (t.as_dict() if t else None))

# ── C2 ★ quotes 只放两段（不是三段）
case("C2 ★ quotes 只两段 [q2, c_new]（不是 [q1,q2,c_new]）",
     t is not None and len(t.quotes) == 2 and t.quotes[0] == "昨天熬到两点改",
     "%r" % (t.quotes if t else None,))

# ── C3 ★ hint 是"三点一线"的简报
case("C3 ★ hint 写明「你把前后的事串成了一条线」",
     t is not None and "串成了一条线" in t.hint,
     "%r" % (t.hint[:44] if t else None))

# ── C4 ★★ 深度锁：prev 若是 CHAIN_EXTENSION，绝不再套
#
#   ⚠️ 这条用例必须做到"**只可能因为深度锁被拒**"，否则测的是别的东西。
#      第一版写成 `sources: []` 且不传 executed ⇒ 它是因为"没有 subject 也不紧邻"
#      被拒的，深度锁删掉也照样通过（变异 MUT-A 抓不到就是这个原因）。
#   ⇒ 现在给它 subject + 上一轮 STRONG 执行 ⇒ 关联性两条都成立，
#      唯一的拒绝理由就只剩"prev 是 CHAIN_EXTENSION"。
PREV_CHAIN = {0: {"op": "CHAIN_EXTENSION",
                  "quotes": ["想证明给他们看", "昨天熬到两点改"],
                  "sources": [{"turn": 0, "start": 0, "end": 7, "kind": "WANT_MUST", "subject": "方案"},
                              {"turn": 0, "start": 10, "end": 17, "kind": "COST_FEEL", "subject": "方案"}]}}
case("C4 ★★ 深度锁：prev.op 是 CHAIN_EXTENSION ⇒ 不连锁（关联性两条都成立也不行）",
     chain_extension(1, CUR, PREV_CHAIN, executed={0: "STRONG"}) is None)

# ── C5 prev 若是未知算子 ⇒ 不连锁
PREV_BAD = {0: {"op": "CONCRETE_CURIOSITY", "quotes": ["甲", "乙"], "sources": []}}
case("C5 prev 的 op 不在允许集 ⇒ 不连锁",
     chain_extension(1, CUR, PREV_BAD) is None)

# ── C6 ★ 隔太远（>k 轮）⇒ 不连锁
PREV_FAR = {0: dict(PREV[0])}
case("C6 ★ prev 超过 %d 轮 ⇒ 不连锁" % CHAIN_LOOKBACK,
     chain_extension(9, {9: [C("FIXED", "被一句话打回来了", 0, "方案")]}, PREV_FAR) is None)

# ── C7 ★ 关联性守卫：subject 不匹配 且 不是紧邻轮 ⇒ 不连锁
CUR_FAR = {5: [C("ACTION", "我把手机扔了", 0, "手机")]}
case("C7 ★ subject 不匹配 + 不是紧邻轮 ⇒ 不连锁",
     chain_extension(5, CUR_FAR, PREV) is None)

# ── C8 ★★ 紧邻轮承接：prev 在 t-1 且上一轮执行了 ⇒ 允许（即使 subject 不同）
CUR_ADJ = {1: [C("ACTION", "我把方案删了", 0, "别的东西")]}
t8 = chain_extension(1, CUR_ADJ, PREV, executed={0: "STRONG"})
case("C8 ★★ 紧邻轮 + 上一轮 STRONG 执行 + 本轮 ACTION ⇒ 允许",
     t8 is not None and t8.op == "CHAIN_EXTENSION",
     "%r" % (t8.as_dict() if t8 else None))

# ── C9 紧邻轮但上一轮**没**执行（level 空）⇒ 不放宽
t9 = chain_extension(1, CUR_ADJ, PREV, executed={0: ""})
case("C9 紧邻轮但上一轮未执行 ⇒ 不放宽关联性",
     t9 is None)

# ── C10 ★ 优先级：CHAIN_EXTENSION 排在算子 3 之后、单跳之前
case("C10 ★ OP_ORDER：算子3 → CHAIN → 单跳",
     OP_ORDER.index("HABITUATION_LOOP_BREAK") < OP_ORDER.index("CHAIN_EXTENSION")
     < OP_ORDER.index("IMMUTABLE_VS_ACTION_SPLIT"),
     str(OP_ORDER))

print("-" * 78)
print("结果: %d 通过 / %d 失败 / 共 %d" % (OK, FAIL, OK + FAIL))
print()
print("MUTATION 表")
print("  MUT-A 去掉 prev.op != CHAIN_EXTENSION 深度锁     → C4")
print("  MUT-B 去掉关联性守卫（任意 c_new 都连）           → C7")
print("  MUT-C quotes 改成三段                              → C2")
print("  MUT-D 去掉紧邻轮承接路径                           → C8")
sys.exit(1 if FAIL else 0)
