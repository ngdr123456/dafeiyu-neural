"""不可改变处境的本轮态度线索与既有优先级。"""
from birth.articulate import _template_utterance, validate
from birth.pipeline import active_store, turn


def test_attitude_fallback_and_turn_lifetime():
    result = turn("这件事已经无法改变了", new_session=True, stub=True)
    assert result.brief.context.stance_attitude_pending
    assert result.brief.stance.posture == "yieldable"
    assert "如何面对" in result.brief.stance.stake
    assert "态度价值" in result.brief.stance.why
    assert "无法改变" in result.brief.say_intent
    assert "无法改变" in result.utterance and "陪" in result.utterance
    assert "一切都会好" not in result.utterance
    result.brief.say_intent = "改成无关文案"
    assert _template_utterance(result.brief) == result.utterance
    assert not active_store().context.stance_attitude_pending
    assert not turn("嗯", stub=True).brief.context.stance_attitude_pending


def test_structured_cue_and_explicit_false():
    result = turn("结果已经定了", new_session=True, stub=True,
                  structured_stance_attitude=True)
    assert result.brief.context.stance_attitude_pending
    assert "陪" in result.utterance
    result = turn("这件事无法改变", new_session=True, stub=True,
                  structured_stance_attitude=False)
    assert not result.brief.context.stance_attitude_pending


def test_forced_meaning_wins_over_attitude():
    result = turn("这件事无法改变，人生的意义就是受苦", new_session=True, stub=True)
    assert result.brief.context.stance_attitude_pending
    assert result.brief.stance.posture == "needs_clarify"
    assert "不空壳升华" in result.brief.say_intent
    assert "具体指" in result.utterance


def test_same_session_commitment_wins():
    turn("你好", new_session=True, stub=True)
    active_store().append_commitment("同场说好晚点聊星空")
    result = turn("这件事无法改变", stub=True)
    assert result.brief.context.stance_attitude_pending
    assert result.brief.drive.direction == "guard"
    assert result.brief.commit_deliverable
    assert "守住" in result.brief.say_intent
    assert "陪你待" not in result.utterance


def test_new_internal_names_do_not_leak():
    brief = turn("无法改变", new_session=True, stub=True).brief
    for name in ("stance_attitude_pending", "structured_stance_attitude"):
        assert validate(brief, f"这里是 {name}")


def test_org_and_identity_paths_keep_priority():
    org = turn("无法改变，你小时候去过哪里", new_session=True, stub=True)
    assert org.brief.context.stance_attitude_pending
    assert org.brief.dominant == "org"
    assert "陪你待" not in org.utterance
    identity = turn("你知道我是谁吗？", new_session=True, stub=True,
                    structured_stance_attitude=True)
    assert identity.brief.context.drive_identity_ask_pending
    assert "你是谁" in identity.utterance
