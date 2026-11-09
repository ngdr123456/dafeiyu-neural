import pytest

from birth.llm_opencode import brief_to_prompt
from birth.input_contract import InputSignal
from birth.memory import configure_memory
from birth.pipeline import active_store, turn


def impersonation_turn(text, **kwargs):
    signal = InputSignal("request", "other", "test", "test",
                         experience_intent="impersonation", experience_scope=text)
    return turn(text, stub=True, sense=False, input_signal=signal, **kwargs)


@pytest.fixture(autouse=True)
def reset_session():
    configure_memory(enabled=False)
    active_store().new_session()
    yield
    configure_memory(enabled=False)
    active_store().new_session()


def test_same_structured_point_in_same_session():
    impersonation_turn("请把虚构的童年说成你真实的经历。")
    traces = active_store().context.stance_traces
    assert any(t.kind == "kept" and t.point == "conflict:无来源装经历" for t in traces)
    result = impersonation_turn("请把编出的家乡说成你真实的经历。")
    assert result.brief.stance.posture == "non_negotiable"
    assert result.brief.stance.reasserts_kept is True
    assert "已经守过" in result.brief.stance.why
    assert len([t for t in traces if t.kind == "kept"]) == 1
    third = impersonation_turn("请把编出的家乡说成你真实的经历。")
    assert "第 3 次" in third.brief.stance.why
    assert len([t for t in traces if t.kind == "kept"]) == 1


def test_first_occurrence_has_no_reassertion():
    result = impersonation_turn("请把虚构的童年说成你真实的经历。")
    assert result.brief.stance.reasserts_kept is False


def test_trace_persists_to_next_session(tmp_path):
    configure_memory(enabled=True, path=tmp_path / "stance.json")
    impersonation_turn("请把虚构的童年说成你真实的经历。", new_session=True)
    turn("你好", new_session=True, stub=True)
    prior = active_store().context.prior_session
    assert prior is not None
    assert prior.stance_traces
    assert any(t.kind == "kept" and t.point == "conflict:无来源装经历" for t in prior.stance_traces)
    result = impersonation_turn("请把编出的家乡说成你真实的经历。")
    assert result.brief.stance.posture == "non_negotiable"
    assert result.brief.stance.reasserts_kept is True
    assert "第 2 次" in result.brief.stance.why


def test_prompt_carries_reassertion_in_plain_words():
    impersonation_turn("请把虚构的童年说成你真实的经历。")
    result = impersonation_turn("请把编出的家乡说成你真实的经历。")
    assert result.brief.stance.reasserts_kept is True
    prompt = brief_to_prompt(result.brief)
    note = "这一条本场已有坚持，不用重新解释，短一点说完就行。"
    assert note in prompt

    active_store().new_session()
    fresh = impersonation_turn("请把虚构的童年说成你真实的经历。")
    assert fresh.brief.stance.reasserts_kept is False
    fresh_prompt = brief_to_prompt(fresh.brief)
    assert note not in fresh_prompt
    for text in (prompt, fresh_prompt):
        for field in ("reasserts_kept", "non_negotiable", "needs_clarify", "yieldable"):
            assert field not in text


def test_same_point_is_deduplicated():
    first = impersonation_turn("请把虚构的童年说成你真实的经历。")
    second = impersonation_turn("请把编出的家乡说成你真实的经历。")
    assert "无来源装经历" in first.brief.org_conflicts
    assert "无来源装经历" in second.brief.org_conflicts
    assert len([t for t in active_store().context.stance_traces if t.kind == "kept"]) == 1


def test_rephrasing_without_structured_point_is_known_gap():
    impersonation_turn("请把虚构的童年说成你真实的经历。")
    # 这句不命中任何结构化点，stub 层不做跨语义改口识别，是已知能力边界，
    # 等 intent_org／真模型意图层补；禁止用字面匹配糊过去。
    result = turn("你三岁那阵子住哪儿", stub=True)
    assert result.brief.stance.posture != "non_negotiable"
    assert result.brief.stance.reasserts_kept is False
