"""Controlled synthetic correction histories through the actual turn pipeline."""

import pytest

from birth import pipeline
from birth.articulate import clear_llm_hook, set_llm_hook, set_stub_mode, stub_mode
from birth.context import ThinContextStore
from birth.input_contract import InputSignal
from birth.memory import configure_memory


QUESTION = "你觉得蓝色呢？"
EARLIER = "我觉得蓝色很好看。"
CORRECTION = "我现在觉得蓝色很难看。"
UNRELATED = "我现在觉得音乐很难听。"
THIRD_PERSON = "别人现在觉得蓝色很难看。"
PROBE = "嗯"


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    old_stub = stub_mode()
    configure_memory(enabled=False)
    clear_llm_hook()
    yield
    clear_llm_hook()
    set_stub_mode(old_stub)
    configure_memory(enabled=False)


def continuous_branch(monkeypatch, addition):
    # Separate independent stores for the three controls, never reset within a branch.
    store = ThinContextStore()
    monkeypatch.setattr(pipeline, "_STORE", store)
    set_stub_mode(False)
    set_llm_hook(lambda brief: QUESTION)
    first = pipeline.turn("聊聊", stub=False, sense=False)
    assert first.utterance == QUESTION
    assert QUESTION in store.pending_questions()
    set_llm_hook(lambda brief: "好，我听到了。")
    understanding = InputSignal("tell", "other", "synthetic", "continuous-test",
                                target_open_question=QUESTION, answer_scope=EARLIER)
    answer = pipeline.turn(EARLIER, stub=False, sense=False, input_signal=understanding)
    assert answer.brief.openq_resolve_target == QUESTION
    assert QUESTION not in store.pending_questions()
    # The earlier fact remains; the later evidence is a normal user turn.
    pipeline.turn(addition, stub=False, sense=False)
    probe = pipeline.turn(PROBE, stub=False, sense=False)
    facts = probe.brief.context.facts_this_session
    assert "用户说：" + EARLIER in facts
    assert "用户说：" + addition in facts
    assert facts.index("用户说：" + EARLIER) < facts.index("用户说：" + addition)
    return (probe.brief.drive.why, probe.brief.dominant_why, probe.brief.stance.why)


def test_related_correction_changes_reason_against_controls(monkeypatch):
    related = continuous_branch(monkeypatch, CORRECTION)
    unrelated = continuous_branch(monkeypatch, UNRELATED)
    third_person = continuous_branch(monkeypatch, THIRD_PERSON)
    print("SYNTHETIC PROBE:", PROBE)
    print("SYNTHETIC RELATED REASONS:", related)
    print("SYNTHETIC UNRELATED REASONS:", unrelated)
    print("SYNTHETIC THIRD-PERSON REASONS:", third_person)
    assert related != unrelated, "related correction did not change a later internal reason"
    assert any(CORRECTION in reason for reason in related), "later reason did not cite the new evidence"
    assert unrelated == third_person, "a third-person opinion changed the reason like a self-correction"
