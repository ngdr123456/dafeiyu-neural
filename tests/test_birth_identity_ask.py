"""Identity questions use sourced clues and a turn-local structured flag."""
import pytest
from birth.types import InjectedCues

from birth.articulate import validate
from birth.drive import drive_cues_from_context, infer_drive, is_identity_ask
from birth.memory import configure_memory
from birth.pipeline import active_store, turn
from birth.types import PriorSessionTrace
from tests.test_birth_multiturn_loop import _ENUM_LEAKS


@pytest.fixture(autouse=True)
def clean_store():
    configure_memory(enabled=False)
    active_store().new_session()
    yield
    active_store().new_session()


@pytest.mark.parametrize("question", [
    "你知道我是谁吗？", "知道我是谁吗", "知道我是谁",
    "认识我吗", "记得我吗", "记得我是谁吗",
])
def test_no_clue(question):
    result = turn(question, new_session=True, stub=True)
    assert result.brief.context.drive_identity_ask_pending
    assert drive_cues_from_context(result.brief.context).drive_identity_ask_pending
    assert result.brief.drive.direction == "hold"
    assert "不确定" in result.utterance and "你是谁" in result.utterance
    assert "这句我接" not in result.utterance
    assert "你想让接几句" not in result.utterance
    assert "我叫" not in result.utterance
    assert not active_store().snapshot().drive_identity_ask_pending


@pytest.mark.parametrize("source", ["session", "prior"])
def test_sourced_clue(source):
    if source == "session":
        active_store().append_fact("用户说：我叫小林")
    else:
        active_store().context.prior_session = PriorSessionTrace(facts=["用户说：我叫小林"])
    result = turn("你认识我吗？", stub=True)
    assert result.brief.drive.direction == "pursue"
    assert "我叫小林" in result.utterance


def test_irrelevant_facts_are_not_identity_clues():
    active_store().append_fact("用户说：我想聊星空")
    active_store().append_fact("台上说：我是小王")
    result = turn("你记得我是谁吗？", stub=True)
    assert result.brief.drive.direction == "hold"
    assert "小王" not in result.utterance


def test_commitment_records_flag_but_guard_wins():
    active_store().append_commitment("晚点补一句月亮的事")
    result = turn("你知道我是谁吗？", stub=True)
    assert result.brief.context.drive_identity_ask_pending
    assert result.brief.drive.direction == "guard"
    assert "不确定" in result.utterance


def test_identity_leak_is_rejected():
    result = turn("你认识我吗", stub=True)
    flag = "drive_identity_ask_pending"
    assert flag in _ENUM_LEAKS
    assert validate(result.brief, f"{flag} 真")
    assert not validate(result.brief, result.utterance)


def test_detection_is_narrow():
    assert is_identity_ask("你还记得我吗？")
    assert not is_identity_ask("你知道我想聊星空吗？")


def test_structured_flag_without_matching_words():
    result = turn("认出对面的人了吗", injected=InjectedCues(drive_identity_ask=True), stub=True)
    assert result.brief.context.drive_identity_ask_pending
    assert result.brief.drive.direction == "hold"
    assert infer_drive("其他", result.brief.context).direction == "hold"


def test_answer_received_in_same_turn():
    first = turn("你知道我是谁吗？", new_session=True, stub=True)
    assert first.brief.context.drive_identity_ask_pending
    result = turn("我叫Mark", stub=True)
    assert result.brief.context.identity_ask_awaiting_answer
    assert result.brief.context.drive_identity_answer_pending
    assert drive_cues_from_context(result.brief.context).drive_identity_answer_pending
    assert result.brief.drive.direction == "pursue"
    assert "Mark" in result.utterance
    assert "你想让接几句" not in result.utterance
    assert "这句我接" not in result.utterance
    for flag in ("identity_ask_awaiting_answer", "drive_identity_answer_pending", "identity_answer_text"):
        assert flag in _ENUM_LEAKS
        assert validate(result.brief, f"{flag} 真")
    assert not validate(result.brief, result.utterance)
    assert not active_store().snapshot().drive_identity_answer_pending


def test_answer_requires_immediately_preceding_ask_and_same_session():
    assert not turn("我叫Mark", new_session=True, stub=True).brief.context.drive_identity_answer_pending
    turn("你认识我吗", stub=True)
    turn("嗯", stub=True)
    assert not turn("我叫Mark", stub=True).brief.context.drive_identity_answer_pending
    turn("你认识我吗", stub=True)
    assert not turn("我叫Mark", new_session=True, stub=True).brief.context.drive_identity_answer_pending


def test_identity_answer_respects_commitment_guard():
    turn("你认识我吗", new_session=True, stub=True)
    active_store().append_commitment("晚点补一句月亮的事")
    result = turn("我叫Mark", stub=True)
    assert result.brief.context.drive_identity_answer_pending
    assert result.brief.drive.direction == "guard"


def test_question_is_not_an_introduction():
    turn("你认识我吗", new_session=True, stub=True)
    assert not turn("我叫Mark吗？", stub=True).brief.context.drive_identity_answer_pending
