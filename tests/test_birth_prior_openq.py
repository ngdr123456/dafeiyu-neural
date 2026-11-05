"""上场她问出去的问题：管线记录、跨场参考和消账。"""

import pytest

from birth.articulate import clear_llm_hook, set_stub_mode
from birth.memory import configure_memory
from birth.pipeline import active_store, turn


@pytest.fixture(autouse=True)
def clean_session():
    configure_memory(enabled=False)
    active_store().new_session()
    set_stub_mode(True)
    clear_llm_hook()
    try:
        yield
    finally:
        configure_memory(enabled=False)
        active_store().new_session()
        clear_llm_hook()
        set_stub_mode(True)


def establish_prior(tmp_path):
    configure_memory(enabled=True, path=tmp_path / "mem.json")
    first = turn("你记得我是谁吗", new_session=True, stub=True)
    current = active_store().snapshot()
    assert "？" in first.utterance or "?" in first.utterance
    assert current.her_questions
    assert set(current.her_questions) <= set(current.open_questions)
    turn("嗯", new_session=True, stub=True)
    prior = active_store().context.prior_session
    assert prior is not None and prior.her_questions
    return prior


def test_t1_record_and_persist(tmp_path):
    establish_prior(tmp_path)


def test_t2_prior_backref(tmp_path):
    establish_prior(tmp_path)
    result = turn("上次我说过的那个呢", stub=True)
    assert result.brief.drive.direction == "pursue"
    assert "上场她问出去的一句" in result.brief.drive.why
    assert "问出去" in result.brief.say_intent


def test_t3_no_forced_callback(tmp_path):
    establish_prior(tmp_path)
    result = turn("今天天气不错", stub=True)
    assert "上场她问出去的一句" not in result.brief.drive.why


def test_t4_answer_clears_prior(tmp_path):
    establish_prior(tmp_path)
    turn("我告诉你，我叫Mark", stub=True)
    assert not active_store().context.prior_session.her_questions


def test_t5_user_question_source():
    turn("为什么天是蓝的", new_session=True, stub=True)
    context = active_store().snapshot()
    assert "为什么天是蓝的" in context.open_questions
    assert "为什么天是蓝的" not in context.her_questions


def test_t6_prior_question_in_prompt(tmp_path):
    from birth.llm_opencode import brief_to_prompt

    configure_memory(enabled=True, path=tmp_path / "mem.json")
    turn("你记得我是谁吗", new_session=True, stub=True)
    question = active_store().snapshot().her_questions[0]
    result = turn("嗯", new_session=True, stub=True)
    assert result.brief.drive.prior_her_question is True
    prompt = brief_to_prompt(result.brief)
    assert question in prompt
    assert "prior_her_question" not in prompt
    assert "her_questions" not in prompt

    result = turn("今天天气不错", stub=True)
    assert result.brief.drive.prior_her_question is False
    prompt = brief_to_prompt(result.brief)
    assert question not in prompt
    assert "上场你问出去、还没被接住的一句" not in prompt


def test_t7_used_suppresses_filler_but_not_backref(tmp_path):
    configure_memory(enabled=True, path=tmp_path / "mem.json")
    turn("你记得我是谁吗", new_session=True, stub=True)
    assert active_store().snapshot().her_questions

    result = turn("嗯", new_session=True, stub=True)
    assert result.brief.drive.prior_her_question is True
    result = turn("嗯", stub=True)
    assert result.brief.drive.prior_her_question is False
    result = turn("上次我说过的那个呢", stub=True)
    assert result.brief.drive.prior_her_question is True
