"""drive 结构化阶段单测：DriveCues 主路径优先于输入侧 MARKS 兜底（非听感验收）。

闸门：
1) 冲突时结构化优先（承诺在场 + 改口否定 → guard，压过 SATISFIED 收束；
   承诺在场 + 无任何形状词 → 结构化 guard 直接决定）；
2) 好奇挂起 + filler → pursue（主路径读 ThinContext.curiosity_hang_pending 布尔，
   「待接的话头：」前缀仅兜底兼容旧快照；不扫 CURIOSITY_MARKS）；
3) session_ok 缺省 False → None（不推）；
4) 无结构信号（空 ThinContext）时仍走 MARKS 兜底，原有行为逐字段不变；
5) 非 S3：drive_greet_pending／drive_hold_pending 有结构时 hold，不依赖 GREETINGS／SATISFIED_MARKS；
   drive_open_topic_pending／drive_curiosity_pending 有结构时 pursue，不依赖 OPEN_TOPIC_PREFIXES／CURIOSITY_MARKS。
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


def test_commitment_deny_flag_without_marks_guards():
    """主路径：结构化 commitment_deny_pending=True，且用户文本不含任何
    COMMIT_DENY_MARKS（「够了先这样」只命中 SATISFIED 收束词）→ 仍 guard mid。
    证明 S2 主路径读 flag，不靠词表：无 flag 时该文本会走 SATISFIED → hold。"""
    ctx = ThinContext(
        session_ok=True,
        last_commitments=["同场说好晚点再聊星空"],
        commitment_deny_pending=True,
    )
    sig = infer_drive("够了先这样", ctx)
    assert sig.direction == "guard"
    assert sig.salience == "mid"
    assert "要护" in sig.why and "没兑现" in sig.why, sig.why


def test_commitment_deny_marks_fallback_without_flag():
    """兜底范围：无 flag（False）时，_denies_commitment 词表仍探出改口否定 → guard。
    与旧行为一致（兼容未写 flag 的直调／旧路径；兜底匹配此前行为）。"""
    ctx = ThinContext(
        session_ok=True,
        last_commitments=["同场说好晚点再聊星空"],
        commitment_deny_pending=False,
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


def test_drive_greet_flag_without_greeting_marks_holds():
    """主路径：drive_greet_pending=True，文案不含 GREETINGS → 仍 hold low。"""
    ctx = ThinContext(session_ok=True, drive_greet_pending=True)
    # 故意用不在 GREETINGS 集合、也不含「你好」短句的中性陈述
    sig = infer_drive("今天天气怎样啊兄弟", ctx)
    assert sig.direction == "hold"
    assert sig.salience == "low"
    assert "招呼" in sig.why, sig.why


def test_drive_hold_flag_without_satisfied_marks_holds():
    """主路径：drive_hold_pending=True，文案不含 SATISFIED_MARKS → 仍 hold low。"""
    ctx = ThinContext(session_ok=True, drive_hold_pending=True)
    sig = infer_drive("再说两句星空的事吧", ctx)
    assert sig.direction == "hold"
    assert sig.salience == "low"
    assert "满足" in sig.why or "收束" in sig.why, sig.why


def test_drive_greet_marks_fallback_without_flag():
    """兜底：无 drive_greet_pending 时，GREETINGS 仍探出招呼 → hold（与旧行为一致）。"""
    ctx = ThinContext(session_ok=True, drive_greet_pending=False)
    sig = infer_drive("你好", ctx)
    assert sig.direction == "hold"
    assert sig.salience == "low"
    assert "招呼" in sig.why, sig.why


def test_drive_hold_marks_fallback_without_flag():
    """兜底：无 drive_hold_pending 时，SATISFIED_MARKS 仍探出收束 → hold。"""
    ctx = ThinContext(session_ok=True, drive_hold_pending=False)
    sig = infer_drive("够了先这样", ctx)
    assert sig.direction == "hold"
    assert sig.salience == "low"
    assert "满足" in sig.why or "收束" in sig.why, sig.why


def test_drive_greet_structured_beats_curiosity_marks_in_text():
    """有 greet 结构时，即使文案含 CURIOSITY_MARKS 也不先 pursue（S4 在好奇 MARKS 前）。"""
    ctx = ThinContext(session_ok=True, drive_greet_pending=True)
    sig = infer_drive("为什么呀", ctx)  # 会命中 CURIOSITY_MARKS，但 flag 优先
    assert sig.direction == "hold"
    assert "招呼" in sig.why, sig.why


def test_should_set_drive_greet_hold_helpers():
    """写入侧 helper：结构 cue 优先；无结构时词表兜底；marks_fallback=False 不扫。"""
    from birth.drive import (
        should_set_drive_greet_pending,
        should_set_drive_hold_pending,
    )

    assert should_set_drive_greet_pending(greet_cue=True, user_text="xxx", marks_fallback=False)
    assert not should_set_drive_greet_pending(greet_cue=False, user_text="xxx", marks_fallback=False)
    assert should_set_drive_greet_pending(greet_cue=False, user_text="你好", marks_fallback=True)
    assert not should_set_drive_greet_pending(greet_cue=False, user_text="今天天气", marks_fallback=True)

    assert should_set_drive_hold_pending(hold_cue=True, user_text="xxx", marks_fallback=False)
    assert not should_set_drive_hold_pending(hold_cue=False, user_text="xxx", marks_fallback=False)
    assert should_set_drive_hold_pending(hold_cue=False, user_text="够了先这样", marks_fallback=True)
    assert not should_set_drive_hold_pending(hold_cue=False, user_text="再说星空", marks_fallback=True)


def test_pipeline_structured_greet_hold_without_marks():
    """live turn：上游 structured_drive_greet／hold → flag 置位 → drive hold，文案无词表。"""
    from birth.articulate import set_stub_mode, clear_llm_hook
    from birth.pipeline import active_store, turn

    set_stub_mode(True)
    clear_llm_hook()
    active_store().new_session()

    r = turn("今天天气怎样啊兄弟", stub=True, structured_drive_greet=True)
    assert r.brief.drive.direction == "hold"
    assert r.brief.drive.salience == "low"
    assert "招呼" in r.brief.drive.why

    active_store().new_session()
    r2 = turn("再说两句星空的事吧", stub=True, structured_drive_hold=True)
    assert r2.brief.drive.direction == "hold"
    assert r2.brief.drive.salience == "low"
    assert "满足" in r2.brief.drive.why or "收束" in r2.brief.drive.why

def test_drive_curiosity_flag_without_curiosity_marks_pursues():
    """主路径：drive_curiosity_pending=True，文案不含 CURIOSITY_MARKS → 仍 pursue high。"""
    ctx = ThinContext(session_ok=True, drive_curiosity_pending=True)
    sig = infer_drive("今天天气怎样啊兄弟", ctx)
    assert sig.direction == "pursue"
    assert sig.salience == "high"
    assert "好奇" in sig.why, sig.why


def test_drive_open_topic_flag_without_prefix_pursues():
    """主路径：drive_open_topic_pending=True，文案不含 OPEN_TOPIC_PREFIXES → 仍 pursue mid。"""
    ctx = ThinContext(session_ok=True, drive_open_topic_pending=True)
    sig = infer_drive("今天天气怎样啊兄弟", ctx)
    assert sig.direction == "pursue"
    assert sig.salience == "mid"
    assert "话头" in sig.why, sig.why


def test_drive_curiosity_marks_fallback_without_flag():
    """兜底：无 drive_curiosity_pending 时，CURIOSITY_MARKS 仍探出好奇 → pursue high。"""
    ctx = ThinContext(session_ok=True, drive_curiosity_pending=False)
    sig = infer_drive("为什么会闪", ctx)
    assert sig.direction == "pursue"
    assert sig.salience == "high"
    assert "好奇" in sig.why, sig.why


def test_drive_open_topic_marks_fallback_without_flag():
    """兜底：无 drive_open_topic_pending 时，OPEN_TOPIC_PREFIXES 仍探出打开话题 → pursue mid。"""
    ctx = ThinContext(session_ok=True, drive_open_topic_pending=False)
    sig = infer_drive("我想聊星空", ctx)
    assert sig.direction == "pursue"
    assert sig.salience == "mid"
    assert "话头" in sig.why and "星空" in sig.why, sig.why


def test_drive_open_topic_structured_beats_curiosity_marks_in_text():
    """有 open_topic 结构时，即使文案含 CURIOSITY_MARKS 也先 pursue mid（S6 在 S7／好奇 MARKS 前）。"""
    ctx = ThinContext(session_ok=True, drive_open_topic_pending=True)
    sig = infer_drive("为什么呀", ctx)
    assert sig.direction == "pursue"
    assert sig.salience == "mid"
    assert "话头" in sig.why, sig.why


def test_should_set_drive_curiosity_open_topic_helpers():
    """写入侧 helper：结构 cue 优先；无结构时词表兜底；marks_fallback=False 不扫。"""
    from birth.drive import (
        should_set_drive_curiosity_pending,
        should_set_drive_open_topic_pending,
    )

    assert should_set_drive_curiosity_pending(
        curiosity_cue=True, user_text="xxx", marks_fallback=False
    )
    assert not should_set_drive_curiosity_pending(
        curiosity_cue=False, user_text="xxx", marks_fallback=False
    )
    assert should_set_drive_curiosity_pending(
        curiosity_cue=False, user_text="为什么会闪", marks_fallback=True
    )
    assert not should_set_drive_curiosity_pending(
        curiosity_cue=False, user_text="今天天气", marks_fallback=True
    )

    assert should_set_drive_open_topic_pending(
        open_topic_cue=True, user_text="xxx", marks_fallback=False
    )
    assert not should_set_drive_open_topic_pending(
        open_topic_cue=False, user_text="xxx", marks_fallback=False
    )
    assert should_set_drive_open_topic_pending(
        open_topic_cue=False, user_text="我想聊星空", marks_fallback=True
    )
    assert not should_set_drive_open_topic_pending(
        open_topic_cue=False, user_text="今天天气", marks_fallback=True
    )


def test_pipeline_structured_curiosity_open_topic_without_marks():
    """live turn：上游 structured_drive_curiosity／open_topic → flag 置位 → pursue，文案无词表。"""
    from birth.articulate import set_stub_mode, clear_llm_hook
    from birth.pipeline import active_store, turn

    set_stub_mode(True)
    clear_llm_hook()
    active_store().new_session()

    r = turn("今天天气怎样啊兄弟", stub=True, structured_drive_curiosity=True)
    assert r.brief.drive.direction == "pursue"
    assert r.brief.drive.salience == "high"
    assert "好奇" in r.brief.drive.why

    active_store().new_session()
    r2 = turn("今天天气怎样啊兄弟", stub=True, structured_drive_open_topic=True)
    assert r2.brief.drive.direction == "pursue"
    assert r2.brief.drive.salience == "mid"
    assert "话头" in r2.brief.drive.why

