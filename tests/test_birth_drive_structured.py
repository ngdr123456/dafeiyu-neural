"""drive 结构化阶段单测：DriveCues 主路径优先于输入侧 MARKS 兜底（非听感验收）。

闸门：
1) 冲突时结构化优先（承诺在场 + 改口否定 → guard，压过 SATISFIED 收束）；
2) 好奇挂起 + filler → pursue（读「待接的话头：」结构，不扫 CURIOSITY_MARKS）；
3) session_ok 缺省 False → None（不推）；
4) 无结构信号时仍走 MARKS 兜底，原有行为不变。
"""

from __future__ import annotations

from birth.drive import infer_drive, is_neutral_filler
from birth.types import ThinContext


def test_commitments_conflict_structured_guard_beats_satisfied_mark():
    """承诺在场 + 改口否定（顺带命中收束词）→ 结构化 guard 优先，不走 hold。"""
    ctx = ThinContext(
        session_ok=True,
        last_commitments=["同场说好晚点再聊星空"],
    )
    sig = infer_drive("那刚才说的不算，够了", ctx)
    assert sig.direction == "guard"
    assert sig.salience == "mid"
    assert "要护" in sig.why and "没兑现" in sig.why, sig.why


def test_curiosity_hang_filler_pursues_open_question():
    """好奇挂起（待接的话头）+ filler → pursue mid，捡悬问。"""
    ctx = ThinContext(
        session_ok=True,
        open_questions=["待接的话头：为什么会闪"],
    )
    assert is_neutral_filler("嗯")
    sig = infer_drive("嗯", ctx)
    assert sig.direction == "pursue"
    assert sig.salience == "mid"
    assert "悬而未决" in sig.why and "为什么会闪" in sig.why, sig.why


def test_session_not_ok_returns_no_direction_before_marks():
    """session_ok=False → 结构化阶段直接 None，不扫 MARKS。"""
    ctx = ThinContext(session_ok=False)
    sig = infer_drive("为什么", ctx)
    assert sig.direction is None
    assert sig.salience == "low"
    assert sig.why == "新场未接上，先不推"


def test_empty_context_falls_back_to_marks_chain():
    """无结构信号（空 ThinContext）→ 兜底 MARKS 链，保持原行为。"""
    ctx = ThinContext()

    hello = infer_drive("你好", ctx)
    assert hello.direction == "hold"
    assert hello.salience == "low"

    done = infer_drive("够了先这样", ctx)
    assert done.direction == "hold"
    assert done.salience == "low"

    curious = infer_drive("为什么会闪", ctx)
    assert curious.direction == "pursue"
    assert curious.salience == "high"
    assert "好奇" in curious.why, curious.why

    filler = infer_drive("嗯", ctx)
    assert filler.direction is None
    assert filler.salience == "low"
