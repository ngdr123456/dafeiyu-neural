"""drive 结构化阶段单测：DriveCues 主路径优先于输入侧 MARKS 兜底（非听感验收）。

闸门：
1) 冲突时结构化优先（承诺在场 + 改口否定 → guard，压过 SATISFIED 收束；
   承诺在场 + 无任何形状词 → 结构化 guard 直接决定）；
2) 好奇挂起 + filler → pursue（主路径读 ThinContext.curiosity_hang_pending 布尔，
   「待接的话头：」前缀仅兜底兼容旧快照；不扫 CURIOSITY_MARKS）；
3) session_ok 缺省 False → None（不推）；
4) 无结构信号（空 ThinContext）时仍走 MARKS 兜底，原有行为逐字段不变。
"""

from __future__ import annotations

from birth.drive import drive_cues_from_context, infer_drive, is_neutral_filler
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
    """好奇挂起前缀兜底 + filler → pursue mid（无 flag 时仍可读「待接的话头：」）。"""
    ctx = ThinContext(
        session_ok=True,
        open_questions=["待接的话头：为什么会闪"],
    )
    assert is_neutral_filler("嗯")
    sig = infer_drive("嗯", ctx)
    assert sig.direction == "pursue"
    assert sig.salience == "mid"
    assert "悬而未决" in sig.why and "为什么会闪" in sig.why, sig.why


def test_curiosity_hang_flag_without_prefix_filler_pursues():
    """主路径：结构化 flag True（无「待接的话头：」前缀）+ filler → pursue mid。"""
    ctx = ThinContext(
        session_ok=True,
        curiosity_hang_pending=True,
        open_questions=["为什么会闪"],  # 无前缀
    )
    assert ctx.curiosity_hang_pending is True
    sig = infer_drive("嗯", ctx)
    assert sig.direction == "pursue"
    assert sig.salience == "mid"
    assert "悬而未决" in sig.why and "为什么会闪" in sig.why, sig.why
    assert "待接的话头" not in sig.why, sig.why


def test_curiosity_hang_prefix_fallback_without_flag():
    """兜底范围：flag 缺省/False 时，前缀扫 open_questions 仍探出好奇挂起（旧快照兼容）。"""
    ctx = ThinContext(
        session_ok=True,
        open_questions=["待接的话头：为什么会闪"],  # 无 flag，仅前缀
    )
    assert ctx.curiosity_hang_pending is False  # 兜底前 flag 本身缺省 False
    cues = drive_cues_from_context(ctx)
    assert cues.curiosity_hang_pending is True  # 前缀兜底探出
    sig = infer_drive("嗯", ctx)
    assert sig.direction == "pursue"
    assert sig.salience == "mid"
    assert "悬而未决" in sig.why and "为什么会闪" in sig.why, sig.why


def test_curiosity_hang_no_flag_no_prefix_does_not_pursue_via_cues():
    """无 flag 且无前缀 → 结构化不判好奇挂起（filler 留空路径，不误推）。"""
    ctx = ThinContext(
        session_ok=True,
        open_questions=["为什么会闪"],  # 无前缀且无 flag → S3 不触发
    )
    cues = drive_cues_from_context(ctx)
    assert cues.curiosity_hang_pending is False


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
