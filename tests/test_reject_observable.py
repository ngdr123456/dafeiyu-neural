# -*- coding: utf-8 -*-
"""J1-J6：输出被退回，必须成为她自己的状态（2026-10-28）。

事由（实测）：
  eval.jsonl 215 条 tutor 判定，最大一类 mechanical 20 条。
  而 MechanismState 的全部字段里没有任何一个记录"我这一轮被退回了"
  ⇒ 机制层的 e/tension 只在**被放行的那句话**上算
  ⇒ 她读不到自己的失败 ⇒ 不会因为说不好而改变。

判据（为什么这不是"把外部意见喂回去"）：
  退回是**事实**（话没被放出去），本地可观察；
  tutor 的"太机械"是**别人的评判**，不该进记忆（train.py:348-350）。
  所以这里只用 render_note，不用 tutor 的任何字段。
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)
sys.path[:0] = [str(_ROOT), str(_ROOT + "/engine")]

import constants as C  # noqa: E402
from mechanism import Mechanism, MechanismConfig, MechanismState  # noqa: E402

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


def fresh():
    return Mechanism(MechanismConfig())


print("=" * 78)
print("  退回成为她自己的状态（J1-J6）")
print("=" * 78)

# ── J1 状态里有这两个字段
st = fresh().step(markers=[], raw="今天有点累。", channel="B", context_key="k1")
case("J1 MechanismState 有 rejected / reject_streak",
     hasattr(st, "rejected") and hasattr(st, "reject_streak"),
     "keys=%s" % [f for f in ("rejected", "reject_streak") if hasattr(st, f)])

# ── J2 默认没有退回 ⇒ streak 0、rejected False
case("J2 没有登记退回时，rejected=False、streak=0",
     st.rejected is False and st.reject_streak == 0,
     "rejected=%r streak=%r" % (st.rejected, st.reject_streak))

# ── J3 ★ 登记退回后，**下一轮** state 反映它
m = fresh()
m.step(markers=[], raw="甲。", channel="B", context_key="k1")
m.note_rejected(True)
st2 = m.step(markers=[], raw="乙。", channel="B", context_key="k1")
case("J3 ★ 登记退回后，下一轮 rejected=True、streak=1",
     st2.rejected is True and st2.reject_streak == 1,
     "rejected=%r streak=%r" % (st2.rejected, st2.reject_streak))

# ── J4 ★ 退回真的推高了 e（与没退回的同序列对照）
m_a, m_b = fresh(), fresh()
for _ in range(6):
    m_a.step(markers=[], raw="同一句。", channel="B", context_key="k")
    m_b.step(markers=[], raw="同一句。", channel="B", context_key="k")
sa = m_a.step(markers=[], raw="同一句。", channel="B", context_key="k")
m_b.note_rejected(True)
sb = m_b.step(markers=[], raw="同一句。", channel="B", context_key="k")
case("J4 ★ 退回使 e 高于同条件下未退回的 e",
     sb.e > sa.e, "有退回 e=%.4f vs 无退回 e=%.4f" % (sb.e, sa.e))

# ── J5 连续退回会累积 streak，一旦不再退回就清零
m = fresh()
m.step(markers=[], raw="甲。", channel="B", context_key="k")
for _ in range(3):
    m.note_rejected(True)
    m.step(markers=[], raw="甲。", channel="B", context_key="k")
st5 = m.step(markers=[], raw="甲。", channel="B", context_key="k")
streak3 = m._reject_streak
m.note_rejected(False)
st6 = m.step(markers=[], raw="甲。", channel="B", context_key="k")
case("J5 连续退回累积，不再退回后清零",
     streak3 == 0 and st6.reject_streak == 0, "streak3=%r st6=%r" % (streak3, st6.reject_streak))

# ── J6 上界不变：退回权重 + 翻转 + 僵化 叠加也超不过 1.0
m = fresh()
worst = 0.0
for i in range(200):
    m.note_rejected(True)
    s = m.step(markers=[], raw="句。", channel=("B" if i % 2 else "S"), context_key="k")
    worst = max(worst, abs(s.e))
case("J6 叠加退回后 |e| 仍不超过 1.0",
     worst <= 1.0 + 1e-9, "max|e|=%.4f" % worst)

print("-" * 78)
print("结果: %d 通过 / %d 失败 / 共 %d" % (OK, FAIL, OK + FAIL))
print()
print("MUTATION 表")
print("  M1 删掉 e 里的退回合并            → J4")
print("  M2 streak 不清零                  → J5")
print("  M3 note_rejected 不设 pending      → J3、J4")
sys.exit(1 if FAIL else 0)
