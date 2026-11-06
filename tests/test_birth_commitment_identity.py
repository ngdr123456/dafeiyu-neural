import pytest

from birth.input_contract import InputSignal
from birth.memory import configure_memory
from birth.pipeline import active_store, turn
from birth.stance_org import commitment_point


A = "我答应你明天聊月亮"
B = "我答应你后天讲星星"


@pytest.fixture(autouse=True)
def reset_session():
    configure_memory(enabled=False)
    active_store().new_session()
    yield
    configure_memory(enabled=False)
    active_store().new_session()


def seed(*commitments):
    for commitment in commitments:
        active_store().append_commitment(commitment)


def signal(act="tell", **kwargs):
    return InputSignal(act, "other", "upstream:test", "turn:1", **kwargs)


def assert_kept_only(target, count=1):
    ctx = active_store().snapshot()
    point = commitment_point(target)
    assert [t.point for t in ctx.stance_traces if t.kind == "kept"] == [point]
    assert ctx.stance_kept_counts == {point: count}


def assert_no_commitment_kept(brief):
    assert brief.hold_same_field is True
    assert brief.stance.held_commitment == ""
    assert brief.stance.reasserts_kept is False
    ctx = active_store().snapshot()
    assert not any(t.kind == "kept" and t.point.startswith("commitment:")
                   for t in ctx.stance_traces)
    assert not any(p.startswith("commitment:") for p in ctx.stance_kept_counts)


def test_named_second_commitment_keeps_its_identity_on_repeat():
    seed(A, B)
    first = turn("星星那件事不算", stub=True).brief
    assert first.stance.held_commitment == B
    assert (first.focus, first.focus_source) == ("星星", "同场承诺")
    assert first.stance.reasserts_kept is False
    assert_kept_only(B)
    second = turn("星星那件事不算", stub=True).brief
    assert second.stance.held_commitment == B
    assert (second.focus, second.focus_source) == ("星星", "同场承诺")
    assert second.stance.reasserts_kept is True
    assert "第 2 次" in second.stance.why
    assert_kept_only(B, 2)
    assert commitment_point(A) not in active_store().snapshot().stance_kept_counts


def test_ambiguous_deny_does_not_keep_first_commitment():
    seed(A, B)
    brief = turn("那件事不算", stub=True).brief
    assert_no_commitment_kept(brief)
    assert (brief.focus, brief.focus_source) == ("那件事不算", "本轮原话")


@pytest.mark.parametrize("commitments", [(B,), (A, B)])
def test_quoted_deny_does_not_keep_commitment(commitments):
    seed(*commitments)
    brief = turn("我朋友说星星那件事不算", stub=True,
                 input_signal=signal(quoted_or_negated=True)).brief
    assert_no_commitment_kept(brief)


def test_time_only_does_not_identify_commitment():
    seed(A, B)
    brief = turn("后天那件事不算", stub=True).brief
    assert_no_commitment_kept(brief)


def test_time_and_content_identify_commitment():
    seed(A, B)
    brief = turn("后天和星星那件事不算", stub=True).brief
    assert brief.stance.held_commitment == B
    assert_kept_only(B)


@pytest.mark.parametrize("kwargs", [
    {"confidence": "low"},
    {"degraded": True},
    {"quoted_or_negated": True},
])
def test_untrusted_target_does_not_resolve_ambiguous_deny(kwargs):
    seed(A, B)
    brief = turn("那件事不算", stub=True,
                 input_signal=signal(target_commitment=B, **kwargs)).brief
    assert_no_commitment_kept(brief)


def test_credible_target_selects_second_commitment():
    seed(A, B)
    brief = turn("那件事不算", stub=True,
                 input_signal=signal(target_commitment=B, confidence="high")).brief
    assert brief.stance.held_commitment == B
    assert (brief.focus, brief.focus_source) == ("星星", "同场承诺")
    assert_kept_only(B)


def test_single_commitment_falls_back_to_unique_target():
    seed(B)
    brief = turn("那件事不算", stub=True).brief
    assert brief.stance.held_commitment == B
    assert (brief.focus, brief.focus_source) == ("星星", "同场承诺")
    assert_kept_only(B)


def test_stop_priority_with_ambiguous_commitments():
    seed(A, B)
    brief = turn("别说了，那件事不算", stub=True,
                 input_signal=signal("stop", scope="conversation")).brief
    assert brief.say_intent.startswith("对方在收束这场：")
    assert_no_commitment_kept(brief)


def test_credible_outside_target_does_not_rematch_raw_text():
    seed(A, B)
    brief = turn("星星那件事不算", stub=True,
                 input_signal=signal(target_commitment="我答应你周末讲故事")).brief
    assert_no_commitment_kept(brief)
    assert (brief.focus, brief.focus_source) == ("星星那件事不算", "本轮原话")


def test_tied_raw_targets_do_not_keep_either_commitment():
    seed(A, B)
    brief = turn("月亮和星星那件事不算", stub=True).brief
    assert_no_commitment_kept(brief)


def test_prompt_selects_held_commitment_and_falls_back():
    from birth.llm_opencode import brief_to_prompt

    seed(A, B)
    brief = turn("\u661f\u661f\u90a3\u4ef6\u4e8b\u4e0d\u7b97", stub=True).brief
    assert brief.context.last_commitments == [A, B]
    assert brief.stance.held_commitment == B
    label = "\u540c\u573a\u8bf4\u8fc7\u8981\u505a\u7684\uff1a"
    assert label + B in brief_to_prompt(brief)
    assert label + A not in brief_to_prompt(brief)
    brief.stance.held_commitment = ""
    brief.context.last_commitments = [B]
    assert label + B in brief_to_prompt(brief)
    brief.context.last_commitments = [A, B]
    brief.focus = "\u661f\u661f"
    assert label + B in brief_to_prompt(brief)
    assert label + A not in brief_to_prompt(brief)
    for focus in ("\u65e0\u5173\u8bdd\u9898", "\u6708\u4eae\u548c\u661f\u661f"):
        brief.focus = focus
        assert label not in brief_to_prompt(brief)
