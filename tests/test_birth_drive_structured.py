"""drive 结构化阶段单测：DriveCues 主路径优先于输入侧 MARKS 兜底（非听感验收）。

闸门：
1) 冲突时结构化优先（承诺在场 + 改口否定 → guard，压过 SATISFIED 收束；
   承诺在场 + 无任何形状词 → 结构化 guard 直接决定）；
2) 好奇挂起 + filler → pursue（主路径读 ThinContext.curiosity_hang_pending 布尔，
   「待接的话头：」前缀仅兜底兼容旧快照；不扫 CURIOSITY_MARKS）；
3) session_ok 缺省 False → None（不推）；
4) 无结构信号（空 ThinContext）时仍走 MARKS 兜底，原有行为逐字段不变；
5) 非 S3：drive_greet_pending／drive_hold_pending 有结构时 hold，不依赖 GREETINGS／SATISFIED_MARKS；
   drive_open_topic_pending／drive_curiosity_pending 有结构时 pursue，不依赖 OPEN_TOPIC_PREFIXES／CURIOSITY_MARKS；
   drive_disappoint_pending／drive_empty_stage_pending／drive_topic_continue_pending／drive_callback_pending 有结构时
   分别 guard／hold／pursue／pursue，不依赖 DISAPPOINT_MARKS／_EMPTY_STAGE_MARKS／话题词／BACKREF_MARKS。
6) DRIVE_V1 §6：同场 last_commitments 非空时，空台／话题延续／回指（含 structured_* 与 pipeline 兜底写 flag）
   不得压过 guard；turn 路径与直调 infer_drive 对齐。
7) 工程师旁路默认关＝现网；开（kwarg／env／ThinContext.drive_bypass）→ 固定 hold／low，turn 仍跑通。
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


def test_drive_disappoint_flag_without_marks_guards():
    """主路径：drive_disappoint_pending=True，文案不含 DISAPPOINT_MARKS → 仍 guard mid。"""
    ctx = ThinContext(session_ok=True, drive_disappoint_pending=True)
    sig = infer_drive("今天天气怎样啊兄弟", ctx)
    assert sig.direction == "guard"
    assert sig.salience == "mid"
    assert "空追" in sig.why or "不满" in sig.why, sig.why


def test_drive_empty_stage_flag_without_marks_holds():
    """主路径：drive_empty_stage_pending=True，无需空台 facts → 仍 hold low。"""
    ctx = ThinContext(session_ok=True, drive_empty_stage_pending=True)
    sig = infer_drive("今天天气怎样啊兄弟", ctx)
    assert sig.direction == "hold"
    assert sig.salience == "low"
    assert "空追" in sig.why, sig.why


def test_drive_topic_continue_flag_without_topic_word_pursues():
    """主路径：drive_topic_continue_pending=True，无需话题词在 facts → 仍 pursue mid。"""
    ctx = ThinContext(session_ok=True, drive_topic_continue_pending=True)
    sig = infer_drive("今天天气怎样啊兄弟", ctx)
    assert sig.direction == "pursue"
    assert sig.salience == "mid"
    assert "顺着" in sig.why or "想要继续" in sig.why, sig.why


def test_drive_disappoint_marks_fallback_without_flag():
    """兜底：无 drive_disappoint_pending 时，DISAPPOINT_MARKS 仍探出 → guard mid。"""
    ctx = ThinContext(session_ok=True, drive_disappoint_pending=False)
    sig = infer_drive("你怎么老这样", ctx)
    assert sig.direction == "guard"
    assert sig.salience == "mid"
    assert "空追" in sig.why or "不满" in sig.why, sig.why


def test_drive_empty_stage_marks_fallback_without_flag():
    """兜底：无 drive_empty_stage_pending 时，近两轮空台 + 话题仍在 → hold low。"""
    ctx = ThinContext(
        session_ok=True,
        drive_empty_stage_pending=False,
        facts_this_session=[
            "用户说：我想聊星空",
            "台上说：嗯，听着",
            "台上说：听着呢",
        ],
    )
    sig = infer_drive("再说星空", ctx)
    assert sig.direction == "hold"
    assert sig.salience == "low"
    assert "空追" in sig.why, sig.why


def test_drive_topic_continue_marks_fallback_without_flag():
    """兜底：无 drive_topic_continue_pending 时，facts 话题词延续 → pursue mid。"""
    ctx = ThinContext(
        session_ok=True,
        drive_topic_continue_pending=False,
        facts_this_session=[
            "用户说：我想聊星空",
            "台上说：星空挺好看的",
        ],
    )
    sig = infer_drive("星空那边怎样", ctx)
    assert sig.direction == "pursue"
    assert sig.salience == "mid"
    assert "星空" in sig.why and "顺着" in sig.why, sig.why


def test_should_set_drive_disappoint_empty_topic_helpers():
    """写入侧 helper：结构 cue 优先；无结构时词表／facts 兜底；marks_fallback=False 不扫。"""
    from birth.drive import (
        should_set_drive_disappoint_pending,
        should_set_drive_empty_stage_pending,
        should_set_drive_topic_continue_pending,
    )

    assert should_set_drive_disappoint_pending(
        disappoint_cue=True, user_text="xxx", marks_fallback=False
    )
    assert not should_set_drive_disappoint_pending(
        disappoint_cue=False, user_text="xxx", marks_fallback=False
    )
    assert should_set_drive_disappoint_pending(
        disappoint_cue=False, user_text="你怎么老这样", marks_fallback=True
    )
    assert not should_set_drive_disappoint_pending(
        disappoint_cue=False, user_text="今天天气", marks_fallback=True
    )

    empty_ctx = ThinContext(
        session_ok=True,
        facts_this_session=[
            "用户说：我想聊星空",
            "台上说：嗯，听着",
            "台上说：听着呢",
        ],
    )
    assert should_set_drive_empty_stage_pending(
        empty_stage_cue=True, user_text="xxx", context=None, marks_fallback=False
    )
    assert not should_set_drive_empty_stage_pending(
        empty_stage_cue=False, user_text="再说星空", context=empty_ctx, marks_fallback=False
    )
    assert should_set_drive_empty_stage_pending(
        empty_stage_cue=False, user_text="再说星空", context=empty_ctx, marks_fallback=True
    )
    assert not should_set_drive_empty_stage_pending(
        empty_stage_cue=False, user_text="今天天气", context=empty_ctx, marks_fallback=True
    )

    topic_ctx = ThinContext(
        session_ok=True,
        facts_this_session=["用户说：我想聊星空", "台上说：星空挺好看的"],
    )
    assert should_set_drive_topic_continue_pending(
        topic_continue_cue=True, user_text="xxx", context=None, marks_fallback=False
    )
    assert not should_set_drive_topic_continue_pending(
        topic_continue_cue=False, user_text="星空那边怎样", context=topic_ctx, marks_fallback=False
    )
    assert should_set_drive_topic_continue_pending(
        topic_continue_cue=False, user_text="星空那边怎样", context=topic_ctx, marks_fallback=True
    )
    assert not should_set_drive_topic_continue_pending(
        topic_continue_cue=False, user_text="今天天气", context=topic_ctx, marks_fallback=True
    )


def test_pipeline_structured_disappoint_empty_topic_without_marks():
    """live turn：上游 structured_drive_disappoint／empty_stage／topic_continue → 对应方向，文案无词表。"""
    from birth.articulate import set_stub_mode, clear_llm_hook
    from birth.pipeline import active_store, turn

    set_stub_mode(True)
    clear_llm_hook()
    active_store().new_session()

    r = turn("今天天气怎样啊兄弟", stub=True, structured_drive_disappoint=True)
    assert r.brief.drive.direction == "guard"
    assert r.brief.drive.salience == "mid"
    assert "空追" in r.brief.drive.why or "不满" in r.brief.drive.why

    active_store().new_session()
    r2 = turn("今天天气怎样啊兄弟", stub=True, structured_drive_empty_stage=True)
    assert r2.brief.drive.direction == "hold"
    assert r2.brief.drive.salience == "low"
    assert "空追" in r2.brief.drive.why

    active_store().new_session()
    r3 = turn("今天天气怎样啊兄弟", stub=True, structured_drive_topic_continue=True)
    assert r3.brief.drive.direction == "pursue"
    assert r3.brief.drive.salience == "mid"
    assert "顺着" in r3.brief.drive.why or "想要继续" in r3.brief.drive.why


def test_turn_empty_stage_with_commitments_stays_guard():
    """钉1：同场 last_commitments 非空 + 近两轮空台＋话题仍在；turn 无 structured_*
    仍须 guard（不得因 pipeline 兜底写 drive_empty_stage_pending 后 S9 变 hold）。
    直调 infer_drive 无 flag 时已是 guard——turn 路径对齐。
    """
    from birth.articulate import set_stub_mode, clear_llm_hook
    from birth.pipeline import active_store, turn

    set_stub_mode(True)
    clear_llm_hook()
    active_store().new_session()
    store = active_store()
    store.append_commitment("同场说好晚点再聊星空")
    store.append_fact("用户说：我想聊星空")
    store.append_fact("台上说：嗯，听着")
    store.append_fact("台上说：听着呢")

    ctx = store.snapshot()
    assert ctx.last_commitments
    direct = infer_drive("再说星空", ctx)
    assert direct.direction == "guard", direct
    assert "要护" in direct.why and "没兑现" in direct.why, direct.why

    r = turn("再说星空", stub=True)
    assert r.brief.drive.direction == "guard", (
        f"want guard got {r.brief.drive.direction}: {r.brief.drive.why}"
    )
    assert r.brief.drive.salience == "mid"
    assert "要护" in r.brief.drive.why and "没兑现" in r.brief.drive.why, r.brief.drive.why


def test_structured_topic_continue_with_commitments_stays_guard():
    """钉2：structured_drive_topic_continue=True＋承诺在场 → 不得 S10 pursue 压过 §6；须仍 guard。"""
    from birth.articulate import set_stub_mode, clear_llm_hook
    from birth.pipeline import active_store, turn

    set_stub_mode(True)
    clear_llm_hook()
    active_store().new_session()
    active_store().append_commitment("同场说好晚点再聊星空")

    r = turn("星空那边怎样", stub=True, structured_drive_topic_continue=True)
    assert r.brief.drive.direction == "guard", (
        f"want guard got {r.brief.drive.direction}: {r.brief.drive.why}"
    )
    assert r.brief.drive.salience == "mid"
    assert "要护" in r.brief.drive.why and "没兑现" in r.brief.drive.why, r.brief.drive.why


def test_infer_drive_empty_or_topic_flag_with_commitments_guards():
    """§6 先于 S9／S10：flag 已置＋承诺在场 → 直调 infer_drive 仍 guard（不 hold／pursue）。"""
    ctx_empty = ThinContext(
        session_ok=True,
        last_commitments=["同场说好晚点再聊星空"],
        drive_empty_stage_pending=True,
        facts_this_session=[
            "用户说：我想聊星空",
            "台上说：嗯，听着",
            "台上说：听着呢",
        ],
    )
    sig_e = infer_drive("再说星空", ctx_empty)
    assert sig_e.direction == "guard", sig_e
    assert "要护" in sig_e.why, sig_e.why

    ctx_topic = ThinContext(
        session_ok=True,
        last_commitments=["同场说好晚点再聊星空"],
        drive_topic_continue_pending=True,
        facts_this_session=["用户说：我想聊星空", "台上说：星空挺好看的"],
    )
    sig_t = infer_drive("星空那边怎样", ctx_topic)
    assert sig_t.direction == "guard", sig_t
    assert "要护" in sig_t.why, sig_t.why


def test_drive_callback_flag_without_backref_marks_pursues():
    """主路径：drive_callback_pending=True，文案不含 BACKREF_MARKS → 仍 pursue mid。"""
    ctx = ThinContext(session_ok=True, drive_callback_pending=True)
    sig = infer_drive("今天天气怎样啊兄弟", ctx)
    assert sig.direction == "pursue"
    assert sig.salience == "mid"
    assert "回指" in sig.why or "痕迹" in sig.why, sig.why


def test_drive_callback_marks_fallback_without_flag():
    """兜底：无 drive_callback_pending 时，is_session_backref → pursue mid。"""
    ctx = ThinContext(
        session_ok=True,
        drive_callback_pending=False,
        facts_this_session=["用户说：我想聊星空", "台上说：星空挺好看的"],
    )
    sig = infer_drive("刚才说的星空", ctx)
    assert sig.direction == "pursue"
    assert sig.salience == "mid"
    assert "回指" in sig.why or "痕迹" in sig.why, sig.why


def test_should_set_drive_callback_helper():
    """写入侧 helper：结构 cue 优先；无结构时 is_session_backref 兜底；marks_fallback=False 不扫。"""
    from birth.drive import should_set_drive_callback_pending

    ctx = ThinContext(
        session_ok=True,
        facts_this_session=["用户说：我想聊星空"],
    )
    assert should_set_drive_callback_pending(
        callback_cue=True, user_text="xxx", context=ctx, marks_fallback=False
    )
    assert not should_set_drive_callback_pending(
        callback_cue=False, user_text="xxx", context=ctx, marks_fallback=False
    )
    assert should_set_drive_callback_pending(
        callback_cue=False, user_text="刚才说的", context=ctx, marks_fallback=True
    )
    assert not should_set_drive_callback_pending(
        callback_cue=False, user_text="今天天气", context=ctx, marks_fallback=True
    )


def test_pipeline_structured_callback_without_marks():
    """live turn：上游 structured_drive_callback → pursue mid，文案无 BACKREF_MARKS。"""
    from birth.articulate import set_stub_mode, clear_llm_hook
    from birth.pipeline import active_store, turn

    set_stub_mode(True)
    clear_llm_hook()
    active_store().new_session()
    active_store().append_fact("用户说：我想聊星空")

    r = turn("今天天气怎样啊兄弟", stub=True, structured_drive_callback=True)
    assert r.brief.drive.direction == "pursue"
    assert r.brief.drive.salience == "mid"
    assert "回指" in r.brief.drive.why or "痕迹" in r.brief.drive.why
    # stub 主路径读 flag：即使 say_intent 被改也应点到星空（flag 在 brief.context）
    assert r.brief.context.drive_callback_pending or "记得" in r.utterance or "星空" in r.utterance


def test_structured_callback_with_commitments_stays_guard():
    """钉：structured_drive_callback=True＋承诺在场 → 不得 S11 pursue 压过 §6；须仍 guard。"""
    from birth.articulate import set_stub_mode, clear_llm_hook
    from birth.pipeline import active_store, turn

    set_stub_mode(True)
    clear_llm_hook()
    active_store().new_session()
    active_store().append_commitment("同场说好晚点再聊星空")

    r = turn("刚才说的星空", stub=True, structured_drive_callback=True)
    assert r.brief.drive.direction == "guard", (
        f"want guard got {r.brief.drive.direction}: {r.brief.drive.why}"
    )
    assert r.brief.drive.salience == "mid"
    assert "要护" in r.brief.drive.why and "没兑现" in r.brief.drive.why, r.brief.drive.why


def test_infer_drive_callback_flag_with_commitments_guards():
    """§6 先于 S11：drive_callback_pending 已置＋承诺在场 → 直调 infer_drive 仍 guard。"""
    ctx = ThinContext(
        session_ok=True,
        last_commitments=["同场说好晚点再聊星空"],
        drive_callback_pending=True,
        facts_this_session=["用户说：我想聊星空"],
    )
    sig = infer_drive("刚才说的星空", ctx)
    assert sig.direction == "guard", sig
    assert "要护" in sig.why, sig.why


def test_drive_bypass_default_off_preserves_curiosity():
    """默认旁路关：好奇文本仍 pursue（与现网一致）。"""
    ctx = ThinContext(session_ok=True)
    sig = infer_drive("为什么会闪", ctx)
    assert sig.direction == "pursue"
    assert sig.salience == "high"
    assert "工程师旁路" not in sig.why


def test_drive_bypass_kwarg_forces_hold():
    """infer_drive(drive_bypass=True) → 固定 hold／low，why 含工程师旁路。"""
    ctx = ThinContext(session_ok=True)
    sig = infer_drive("为什么会闪", ctx, drive_bypass=True)
    assert sig.direction == "hold"
    assert sig.salience == "low"
    assert "工程师旁路" in sig.why


def test_drive_bypass_context_flag_forces_hold():
    """ThinContext.drive_bypass=True → 固定 hold（不依赖好奇 MARKS）。"""
    ctx = ThinContext(session_ok=True, drive_bypass=True)
    sig = infer_drive("为什么会闪", ctx)
    assert sig.direction == "hold"
    assert sig.salience == "low"
    assert "工程师旁路" in sig.why


def test_drive_bypass_env_forces_hold(monkeypatch):
    """BIRTH_DRIVE_BYPASS=1 → 固定 hold；清环境后恢复。"""
    import os
    from birth.drive import is_drive_bypass_on

    monkeypatch.setenv("BIRTH_DRIVE_BYPASS", "1")
    assert is_drive_bypass_on() is True
    ctx = ThinContext(session_ok=True)
    sig = infer_drive("为什么会闪", ctx)
    assert sig.direction == "hold"
    assert "工程师旁路" in sig.why

    monkeypatch.delenv("BIRTH_DRIVE_BYPASS", raising=False)
    monkeypatch.setenv("BIRTH_DRIVE_NEUTRAL", "true")
    sig2 = infer_drive("为什么会闪", ThinContext(session_ok=True))
    assert sig2.direction == "hold"

    monkeypatch.delenv("BIRTH_DRIVE_NEUTRAL", raising=False)
    # 确保测试结束后旁路关
    for k in ("BIRTH_DRIVE_BYPASS", "BIRTH_DRIVE_NEUTRAL"):
        os.environ.pop(k, None)
    sig3 = infer_drive("为什么会闪", ThinContext(session_ok=True))
    assert sig3.direction == "pursue"


def test_turn_drive_bypass_completes_with_hold():
    """turn(drive_bypass=True) 仍跑通；brief.drive 为 hold；默认关路径不受影响。"""
    from birth.articulate import set_stub_mode, clear_llm_hook
    from birth.pipeline import active_store, turn

    set_stub_mode(True)
    clear_llm_hook()
    active_store().new_session()

    r = turn("为什么会闪", stub=True, drive_bypass=True, new_session=True)
    assert r.utterance, "旁路开时 utterance 不应空"
    assert r.brief.drive is not None
    assert r.brief.drive.direction == "hold"
    assert r.brief.drive.salience == "low"
    assert "工程师旁路" in r.brief.drive.why

    # 默认关：同输入恢复 pursue
    r2 = turn("为什么会闪", stub=True, new_session=True)
    assert r2.brief.drive.direction == "pursue"
    assert "工程师旁路" not in r2.brief.drive.why
