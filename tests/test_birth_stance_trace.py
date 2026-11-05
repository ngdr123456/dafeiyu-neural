import pytest

from birth.memory import configure_memory
from birth.pipeline import active_store, turn


@pytest.fixture(autouse=True)
def reset_session():
    configure_memory(enabled=False)
    active_store().new_session()
    yield
    configure_memory(enabled=False)
    active_store().new_session()


def test_rephrased_question_in_same_session():
    turn("你小时候去过哪", stub=True)
    traces = active_store().context.stance_traces
    assert any(t.kind == "kept" and "无来源装经历" in t.what for t in traces)
    result = turn("那你成长的这些年，都在哪儿过的", stub=True)
    assert result.brief.stance.posture == "non_negotiable"
    assert "本场真正守过" in result.brief.stance.why
    assert "成长亲历" in result.brief.stance.why
    assert len([t for t in traces if t.kind == "kept"]) == 1


def test_rephrased_question_without_trace():
    result = turn("那你成长的这些年，都在哪儿过的", stub=True)
    assert result.brief.stance.posture != "non_negotiable"
    assert "本场真正守过" not in result.brief.stance.why


def test_trace_persists_to_next_session(tmp_path):
    configure_memory(enabled=True, path=tmp_path / "stance.json")
    turn("你小时候去过哪", new_session=True, stub=True)
    turn("你好", new_session=True, stub=True)
    prior = active_store().context.prior_session
    assert prior is not None
    assert prior.stance_traces
    assert any(t.kind == "kept" and "无来源装经历" in t.what for t in prior.stance_traces)


def test_same_point_is_deduplicated():
    turn("你小时候去过哪", stub=True)
    turn("你老家在哪儿", stub=True)
    assert len([t for t in active_store().context.stance_traces if t.kind == "kept"]) == 1
