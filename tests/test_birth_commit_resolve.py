"""承诺兑现／放下：store API + pipeline 薄接线（非听感）。"""

from __future__ import annotations
from birth.types import InjectedCues

from birth.articulate import clear_llm_hook, set_llm_hook, set_stub_mode
from birth.pipeline import active_store, turn


def test_store_resolve_commitment_pops_first():
    store = active_store()
    store.new_session()
    store.append_commitment("我晚点再跟你聊星空。")
    store.append_commitment("下次补月亮")
    assert store.resolve_commitment() == "我晚点再跟你聊星空。"
    assert store.pending_commitments() == ["下次补月亮"]
    store.clear_commitments()
    assert store.pending_commitments() == []
    assert store.resolve_commitment() is None


def test_commitment_stays_until_fulfilled():
    set_stub_mode(True)
    clear_llm_hook()
    active_store().new_session()
    turn("我想聊星空", stub=True)
    turn("你答应晚点再聊", stub=True)
    before = active_store().pending_commitments()
    assert before, before
    # 误触发：闲聊不清空
    turn("今天天气怎么样", stub=True)
    assert active_store().pending_commitments() == before


def test_user_fulfill_mark_resolves_commitment():
    set_stub_mode(True)
    clear_llm_hook()
    active_store().new_session()
    turn("我想聊星空", stub=True)
    turn("你答应晚点再聊", stub=True)
    assert active_store().pending_commitments()
    turn("那件事你兑现了", stub=True)
    assert active_store().pending_commitments() == []


def test_utterance_cover_resolves_commitment():
    """用户点到主题 + 台上可检验接上 → resolve。"""
    set_stub_mode(False)
    set_llm_hook(lambda _b: "行，接着聊星空。你想从哪头起？")
    try:
        active_store().new_session()
        turn("我想聊星空", stub=True)
        active_store().append_commitment("我晚点再跟你聊星空。")
        assert active_store().pending_commitments()
        set_stub_mode(False)
        set_llm_hook(lambda _b: "行，接着聊星空。你想从哪头起？")
        turn("那就星空继续", stub=False)  # 用户点到主题 → deliver_intent
        assert active_store().pending_commitments() == []
    finally:
        clear_llm_hook()
        set_stub_mode(True)


def test_deny_commitment_does_not_resolve():
    """改口否定 ≠ 兑现；承诺应仍在。"""
    set_stub_mode(True)
    clear_llm_hook()
    store = active_store()
    store.new_session()
    store.append_commitment("同场里说好这轮先补月亮的事")
    turn("那刚才说的不算", stub=True)
    assert store.pending_commitments(), store.pending_commitments()


def test_commitment_deny_flag_used_then_cleared_no_leak():
    """pipeline 薄接线：有 pending＋改口 → 本轮 drive 走 guard（经 flag 主路径）；
    回合末 flag 清 False，不漏到下一轮；无 pending 时写入侧不置位。"""
    set_stub_mode(True)
    clear_llm_hook()
    store = active_store()
    store.new_session()
    store.append_commitment("同场里说好这轮先补月亮的事")
    r = turn("那刚才说的不算", stub=True)
    assert r.brief.drive is not None and r.brief.drive.direction == "guard"
    assert r.brief.commit_deny is True  # arbitrate 从 stance 守诺结构置 Brief 标记
    assert store.context.commitment_deny_pending is False  # 回合末已清，不漏
    # 无 pending：即使命中改口词表也不置 flag
    store.new_session()
    turn("那刚才说的不算", stub=True)
    assert store.context.commitment_deny_pending is False


def test_should_set_deny_structured_without_marks():
    """主路径：结构化 commit_deny=True，文案无 COMMIT_DENY_MARKS → 仍应置位。"""
    from birth.commit_extract import should_set_commitment_deny_pending

    text = "够了先这样"  # SATISFIED 收束词；不含不算/忘掉/改口/收回/作废等
    assert should_set_commitment_deny_pending(
        commit_deny=True, user_text=text, has_pending=True
    )
    assert not should_set_commitment_deny_pending(
        commit_deny=False, user_text=text, has_pending=True
    )


def test_should_set_deny_marks_fallback_without_structured():
    """兜底：无结构化时 COMMIT_DENY_MARKS 仍探出；无 pending 即使有词也不置。"""
    from birth.commit_extract import should_set_commitment_deny_pending

    assert should_set_commitment_deny_pending(
        commit_deny=False, user_text="那刚才说的不算", has_pending=True
    )
    assert not should_set_commitment_deny_pending(
        commit_deny=False, user_text="那刚才说的不算", has_pending=False
    )


def test_structured_commit_deny_kwarg_sets_flag_drive_guards():
    """turn(structured_commit_deny=True)+无改口词表文案 -> drive guard + stance 守诺。

    结构化写入服务 store flag/drive/stance；Brief.commit_deny 由 arbitrate 从 stance 守诺结构置 True。
    """
    set_stub_mode(True)
    clear_llm_hook()
    store = active_store()
    store.new_session()
    store.append_commitment("同场说好晚点再聊星空")
    r = turn("够了先这样", stub=True, injected=InjectedCues(commit_deny=True))
    assert r.brief.drive is not None and r.brief.drive.direction == "guard"
    assert "要护" in (r.brief.drive.why or "") or "没兑现" in (r.brief.drive.why or "")
    assert r.brief.stance.posture == "non_negotiable"
    assert "同场说过的话仍然有效" in (r.brief.stance.stake or "")
    assert r.brief.commit_deny is True
    assert store.context.commitment_deny_pending is False  # 回合末清
    # 有词表的改口轮：Brief.commit_deny 由 arbitrate 从 stance 守诺结构置 True
    store.new_session()
    store.append_commitment("同场说好晚点再聊星空")
    r2 = turn("那刚才说的不算", stub=True)
    assert r2.brief.commit_deny is True
    assert r2.brief.drive is not None and r2.brief.drive.direction == "guard"


def test_brief_commit_deny_defaults_false():
    from birth.types import ThoughtBrief

    assert ThoughtBrief(dominant="drive").commit_deny is False


def test_resolve_uses_brief_flags_not_loose_marks():
    """有 commit_resolve／可检验交付才 resolve；无标记即使闲话也不清。"""
    from birth.commit_extract import should_resolve_commitment
    from birth.types import DriveSignal, ThoughtBrief, ThinContext

    pending = "我晚点再跟你聊星空。"
    brief_resolve = ThoughtBrief(
        dominant="meaning",
        drive=DriveSignal(direction="guard", salience="mid", why="x"),
        say_intent="文案已改，不含兑现字样",
        commit_resolve=True,
        context=ThinContext(),
    )
    assert should_resolve_commitment(
        brief=brief_resolve, utterance="随便", pending_first=pending
    )

    brief_deliver = ThoughtBrief(
        dominant="meaning",
        drive=DriveSignal(direction="guard", salience="mid", why="x"),
        say_intent="先守住同场说过的话",
        commit_deliverable=True,
        commit_deliver_intent=True,
        context=ThinContext(),
    )
    assert should_resolve_commitment(
        brief=brief_deliver, utterance="行，接着聊星空。", pending_first=pending
    )
    assert not should_resolve_commitment(
        brief=brief_deliver, utterance="今天天气怎么样", pending_first=pending
    )

    brief_none = ThoughtBrief(
        dominant="drive",
        drive=DriveSignal(direction=None, salience="low", why="x"),
        say_intent="那件事你兑现了",  # 仅子串，无标记
        context=ThinContext(),
    )
    assert not should_resolve_commitment(
        brief=brief_none, utterance="那件事你兑现了", pending_first=pending
    )


def test_guard_utterance_with_topic_keeps_commitment():
    """守诺口径只提主题词未接上 → 承诺仍在。"""
    from birth.commit_extract import should_resolve_commitment
    from birth.types import DriveSignal, ThoughtBrief, ThinContext

    pending = "我晚点再跟你聊星空。"
    brief = ThoughtBrief(
        dominant="meaning",
        drive=DriveSignal(direction="guard", salience="mid", why="x"),
        say_intent="先守住同场说过的话",
        commit_deliverable=True,
        commit_deliver_intent=True,
        context=ThinContext(),
    )
    guard = "同场里说过的还在，我先守着那句，星空那事也还在，再接你眼前这句。"
    assert not should_resolve_commitment(
        brief=brief, utterance=guard, pending_first=pending
    )

    # 仅 pending＋主题重叠、无 deliver_intent → 也不清
    brief2 = ThoughtBrief(
        dominant="meaning",
        drive=DriveSignal(direction="guard", salience="mid", why="x"),
        commit_deliverable=True,
        commit_deliver_intent=False,
        context=ThinContext(),
    )
    assert not should_resolve_commitment(
        brief=brief2, utterance="行，接着聊星空。", pending_first=pending
    )


def test_stance_structured_deny_without_marks():
    """主路径：commitment_deny_pending=True+承诺在场，文案无 COMMIT_DENY_MARKS -> 守诺。"""
    from birth.stance_org import STAKE_HOLD_SAME_FIELD, default_stance
    from birth.types import ThinContext

    text = "够了先这样"  # SATISFIED 收束；不含不算/忘掉/改口等
    ctx = ThinContext(
        last_commitments=["同场说好晚点再聊星空"],
        commitment_deny_pending=True,
    )
    st = default_stance(text, ctx)
    assert st.posture == "non_negotiable"
    assert st.hold_same_field is True
    assert STAKE_HOLD_SAME_FIELD in (st.stake or "")


def test_stance_marks_fallback_without_structured_flag():
    """兜底：无 commitment_deny_pending 时 COMMIT_DENY_MARKS 仍探出守诺。"""
    from birth.stance_org import STAKE_HOLD_SAME_FIELD, default_stance
    from birth.types import ThinContext

    ctx = ThinContext(
        last_commitments=["同场说好晚点再聊星空"],
        commitment_deny_pending=False,
    )
    st = default_stance("那刚才说的不算", ctx)
    assert st.posture == "non_negotiable"
    assert st.hold_same_field is True
    assert STAKE_HOLD_SAME_FIELD in (st.stake or "")


def test_stance_no_false_hold_without_deny():
    """承诺在场但无 deny flag／无改口词 → 不走守诺 non_negotiable。"""
    from birth.stance_org import STAKE_HOLD_SAME_FIELD, default_stance
    from birth.types import ThinContext

    ctx = ThinContext(
        last_commitments=["同场说好晚点再聊星空"],
        commitment_deny_pending=False,
    )
    st = default_stance("今天怎么样", ctx)
    assert STAKE_HOLD_SAME_FIELD not in (st.stake or "")


def test_stance_deny_words_without_commitments_not_hold():
    """无承诺时即使改口词在场，也不经 step2 进守诺 stake。"""
    from birth.stance_org import STAKE_HOLD_SAME_FIELD, default_stance
    from birth.types import ThinContext

    st = default_stance("那刚才说的不算", ThinContext(commitment_deny_pending=False))
    assert STAKE_HOLD_SAME_FIELD not in (st.stake or "")

def test_structured_deny_from_stance_unit():
    """structured_deny_from_stance 与 Brief.commit_deny 同条件；不扫词表。"""
    from birth.commit_extract import structured_deny_from_stance
    from birth.stance_org import STAKE_HOLD_SAME_FIELD
    from birth.types import StanceSignal

    hold = StanceSignal(
        posture="non_negotiable",
        stake=STAKE_HOLD_SAME_FIELD,
        why="x",
    )
    assert structured_deny_from_stance(hold, has_commitments=True)
    assert not structured_deny_from_stance(hold, has_commitments=False)
    assert not structured_deny_from_stance(
        StanceSignal(posture="non_negotiable", stake="别的不可交", why="x"),
        has_commitments=True,
    )
    assert not structured_deny_from_stance(
        StanceSignal(posture="yieldable", stake=STAKE_HOLD_SAME_FIELD, why="x"),
        has_commitments=True,
    )
    # 结构优先：hold_same_field=True 即使 stake 文案改掉／缺省仍 True
    assert structured_deny_from_stance(
        StanceSignal(
            posture="non_negotiable",
            stake="改口后的stake文案",
            hold_same_field=True,
            why="x",
        ),
        has_commitments=True,
    )
    assert structured_deny_from_stance(
        StanceSignal(
            posture="non_negotiable",
            stake="",
            hold_same_field=True,
            why="x",
        ),
        has_commitments=True,
    )


def test_live_early_stance_structure_sets_flag_without_write_marks():
    """live 本轮：early stance 守诺结构在写入前可用 → flag 置位 → drive/stance 走结构。

    有 pending＋改口词时，写入主路径经 commit_deny=True（结构），不应调用
    user_marks_commitment_deny（词表兜底）。stance／drive 层内兜底仍可扫词表。
    """
    from birth import commit_extract
    from birth.articulate import clear_llm_hook, set_stub_mode
    from birth.pipeline import active_store, turn
    import birth.pipeline as pipe

    set_stub_mode(True)
    clear_llm_hook()
    store = active_store()
    store.new_session()
    store.append_commitment("同场里说好这轮先补月亮的事")

    calls: list[dict] = []
    real_should = commit_extract.should_set_commitment_deny_pending
    real_marks = commit_extract.user_marks_commitment_deny
    marks_from_should = {"n": 0}

    def spy_should(**kwargs):
        calls.append(dict(kwargs))
        return real_should(**kwargs)

    def spy_marks(user_text: str) -> bool:
        # should_set 词表兜底会调到这里；结构路径不得走进来
        marks_from_should["n"] += 1
        raise AssertionError(
            "write-side marks fallback must not run when early stance structure exists"
        )

    commit_extract.should_set_commitment_deny_pending = spy_should
    commit_extract.user_marks_commitment_deny = spy_marks
    pipe.should_set_commitment_deny_pending = spy_should
    try:
        r = turn("那刚才说的不算", stub=True)
    finally:
        commit_extract.should_set_commitment_deny_pending = real_should
        commit_extract.user_marks_commitment_deny = real_marks
        pipe.should_set_commitment_deny_pending = real_should

    assert r.brief.drive is not None and r.brief.drive.direction == "guard"
    assert r.brief.stance.posture == "non_negotiable"
    assert r.brief.commit_deny is True
    assert any(c.get("commit_deny") is True for c in calls), calls
    assert marks_from_should["n"] == 0


def test_should_set_marks_fallback_flag_respected():
    """marks_fallback=False 时即使文案含 COMMIT_DENY_MARKS 也不靠词表置位。"""
    from birth.commit_extract import should_set_commitment_deny_pending

    assert not should_set_commitment_deny_pending(
        commit_deny=False,
        user_text="那刚才说的不算",
        has_pending=True,
        marks_fallback=False,
    )
    assert should_set_commitment_deny_pending(
        commit_deny=True,
        user_text="够了先这样",
        has_pending=True,
        marks_fallback=False,
    )


def test_arbitrate_hold_same_field_without_stake_chinese():
    """有 stance.hold_same_field＋承诺在场 → Brief.commit_deny／hold_same_field，
    即使 stake 不含「先守同场说过的话」。"""
    from birth.arbitrate import arbitrate
    from birth.types import DriveSignal, OrgConstraint, StanceSignal, ThinContext

    ctx = ThinContext(last_commitments=["同场说好晚点再聊星空"])
    stance = StanceSignal(
        posture="non_negotiable",
        stake="完全改过的stake文案",
        hold_same_field=True,
        why="守诺",
    )
    brief = arbitrate(
        DriveSignal(direction="hold", salience="low", why="x"),
        stance,
        OrgConstraint(),
        ctx,
        user_text="够了先这样",
    )
    assert brief.commit_deny is True
    assert brief.hold_same_field is True
    assert "同场说过的话仍然有效" not in (brief.stance.stake or "")


def test_articulate_structure_without_stake_chinese():
    """Brief.commit_deny／hold_same_field／stance.hold_same_field 时 stub 守诺，
    即使 stake 无「先守同场说过的话」；无结构时 stake 缺省不守诺。"""
    from birth.articulate import _template_utterance
    from birth.types import StanceSignal, ThinContext, ThoughtBrief

    def _out(**kw):
        base = dict(
            dominant="meaning",
            say_intent="无关改口文案xyz",
            stance=StanceSignal(posture="yieldable"),
            context=ThinContext(),
        )
        base.update(kw)
        return _template_utterance(ThoughtBrief(**base))

    # Brief.commit_deny 结构
    out1 = _out(commit_deny=True, stance=StanceSignal(posture="non_negotiable", stake=""))
    assert "不当没说过" in out1 or "不跟着改口" in out1, out1

    # Brief.hold_same_field 结构
    out2 = _out(
        hold_same_field=True,
        stance=StanceSignal(posture="non_negotiable", stake="别的文案"),
    )
    assert "不当没说过" in out2 or "不跟着改口" in out2, out2

    # stance.hold_same_field＋posture，stake 改文案
    out3 = _out(
        stance=StanceSignal(
            posture="non_negotiable",
            stake="改过的",
            hold_same_field=True,
        ),
    )
    assert "不当没说过" in out3 or "不跟着改口" in out3, out3

    # 无结构、无承诺、stake 也不含常量 → 不走守诺
    out4 = _out(
        stance=StanceSignal(posture="non_negotiable", stake="别的不可交"),
    )
    assert "不当没说过" not in out4 and "不跟着改口" not in out4, out4
