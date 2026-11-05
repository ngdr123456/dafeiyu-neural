from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from birth.__main__ import main
from birth.input_contract import InputSignal, drive_signal_from_input
from birth.pipeline import active_store, turn


def signal(act="ask", **kwargs):
    values = dict(act=act, addressee="other", source="upstream:test",
                  provenance="turn:1/segment:0")
    values.update(kwargs)
    return InputSignal(**values)


@pytest.mark.parametrize("text", [
    "你觉得呢？", "帮我把窗户关一下", "给我讲讲这个", "麻烦你改一下", "请解释一下",
    "能不能帮我看", "明天去吗？", "他问我明天去吗？", "Can you help me?",
])
def test_ordinary_turn_does_not_create_input_signal(text):
    result = turn(text, new_session=True, stub=True)
    assert result.brief.drive.direction is None
    assert result.input_signal is None


@pytest.mark.parametrize("text,salience", [("我想聊星空", "mid"), ("为什么星星会发光？", "high")])
def test_existing_drive(text, salience):
    result = turn(text, new_session=True, stub=True)
    assert (result.brief.drive.direction, result.brief.drive.salience) == ("pursue", salience)


@pytest.mark.parametrize("act,label,intent", [
    ("ask", "问句", "对方在问我"),
    ("request", "请求", "对方在请我做事"),
])
def test_signal_reaches_drive_and_result(act, label, intent):
    value = signal(act)
    result = turn("这件事", new_session=True, stub=True, input_signal=value)
    assert (result.brief.drive.direction, result.brief.drive.salience) == ("pursue", "mid")
    assert f"输入信号｜{label}｜upstream:test" in result.brief.drive.why
    assert intent in result.brief.say_intent
    assert result.input_signal == value


@pytest.mark.parametrize("value", [signal("tell"), signal("ack"), signal("unknown"), signal(degraded=True)])
def test_non_drive_signals(value):
    assert drive_signal_from_input(value) is None
    assert turn("这件事", new_session=True, stub=True, input_signal=value).brief.drive.direction is None


@pytest.mark.parametrize("field,value", [
    ("source", ""), ("source", " \t"), ("provenance", ""), ("provenance", " \n"),
    ("act", "invalid"), ("act", "close"), ("addressee", "invalid"),
])
def test_invalid_fields(field, value):
    with pytest.raises(ValueError):
        signal(**{field: value})


def test_frozen_and_none():
    value = signal()
    with pytest.raises(FrozenInstanceError):
        value.act = "tell"
    assert drive_signal_from_input(None) is None


def test_ask_input_still_after_commitment():
    """ask 仍留在 S15（本刀只把 pause／stop 前移），同场承诺的 guard 先命中。
    对应新次序：pause／stop 在 S1b 前置，ask／request 不受此限。"""
    store = active_store()
    store.new_session()
    store.append_commitment("同场里说好这轮先补月亮的事")
    result = turn("你还记得吗？", stub=True, input_signal=signal())
    assert result.brief.drive.direction == "guard"
    assert not result.brief.drive.why.startswith("输入信号｜")


def test_ask_input_still_after_curiosity():
    """ask 仍留在 S15：好奇 pursue/high 先命中。pause／stop 才在 S1b 前置。"""
    result = turn("为什么星星会发光？", new_session=True, stub=True, input_signal=signal())
    assert (result.brief.drive.direction, result.brief.drive.salience) == ("pursue", "high")
    assert not result.brief.drive.why.startswith("输入信号｜")


# INPUT_INTENT_V1：判停之后台上该怎么停。stub 话术按结构映射固定，不用词表扫描。
STOP_TEMPLATES = {
    ("pause", False): "行，先停一下，我不往下说了。",
    ("pause", True): "行，先停一下，我不往下说了。同场里说好的那句还在，我不当它没了。",
    ("stop", False): "好，就到这儿，我不往下说了。",
    ("stop", True): "好，就到这儿，我不往下说了。同场里说好的那句还在，我不当它没了。",
}


@pytest.mark.parametrize("text,act", [
    ("先停一下", "pause"),
    ("别说了，停一下", "stop"),
    ("不要说了", "stop"),
    ("到此为止吧", "stop"),
])
def test_pause_stop_gates_before_local_cues(text, act):
    result = turn(text, new_session=True, stub=True, input_signal=signal(act))
    label = "暂停" if act == "pause" else "终止"
    assert (result.brief.drive.direction, result.brief.drive.salience) == ("hold", "low")
    assert result.brief.drive.why.startswith(f"输入信号｜{label}｜upstream:test｜")
    prefix = "对方在叫停：" if act == "pause" else "对方在收束这场："
    assert result.brief.say_intent.startswith(prefix)
    assert result.utterance == STOP_TEMPLATES[(act, False)]


def test_pause_stop_beats_curiosity_high():
    """用户明说停时，本地「为什么」的好奇 pursue/high 不许把话头重新挑起来。"""
    result = turn(
        "不要说了，我不想听为什么",
        new_session=True,
        stub=True,
        structured_drive_curiosity=True,
        input_signal=signal("stop"),
    )
    assert (result.brief.drive.direction, result.brief.drive.salience) == ("hold", "low")
    assert result.brief.drive.why.startswith("输入信号｜终止｜")
    assert result.utterance == STOP_TEMPLATES[("stop", False)]


def test_pause_stop_beats_callback_mid():
    """用户明说停时，同场回指 pursue/mid 不许把话头接回去。"""
    result = turn(
        "停一下，刚才说到哪了",
        new_session=True,
        stub=True,
        structured_drive_callback=True,
        input_signal=signal("pause"),
    )
    assert (result.brief.drive.direction, result.brief.drive.salience) == ("hold", "low")
    assert result.brief.drive.why.startswith("输入信号｜暂停｜")
    assert result.utterance == STOP_TEMPLATES[("pause", False)]


def test_pause_with_commitment_stops_first_then_keeps_promise():
    """§6：同场承诺在场时先停，但约定还在——guard/mid，先说停再说约定。"""
    store = active_store()
    store.new_session()
    store.append_commitment("同场里说好这轮先补月亮的事")
    result = turn("先停一下", stub=True, input_signal=signal("pause"))
    assert (result.brief.drive.direction, result.brief.drive.salience) == ("guard", "mid")
    assert result.brief.drive.why.startswith("输入信号｜暂停｜")
    assert "同场里说好这轮先补月亮的事" in result.brief.drive.why
    assert result.brief.commit_hold_with_drive is True
    assert result.utterance == STOP_TEMPLATES[("pause", True)]
    assert result.utterance.index("先停一下") < result.utterance.index("同场里说好的那句还在")


def test_stop_beats_open_question_filler():
    """悬问在场时两字以内的「停」也不许被 filler 分支改写成「悬问仍留着」。"""
    turn("为什么星星会发光？", new_session=True, stub=True)
    result = turn("停", stub=True, input_signal=signal("pause"))
    assert result.brief.say_intent.startswith("对方在叫停：")
    assert result.utterance == STOP_TEMPLATES[("pause", False)]


def test_stop_beats_open_question_closing():
    """悬问在场时「算了」是收束，不是把悬问留着当没回答。"""
    turn("为什么星星会发光？", new_session=True, stub=True)
    result = turn("算了", stub=True, input_signal=signal("stop"))
    assert result.brief.say_intent.startswith("对方在收束这场：")
    assert result.utterance == STOP_TEMPLATES[("stop", False)]


def test_stop_beats_stance_pain():
    """stance 痛苦分支不得把「别说了」改写成「可以陪对方面对」。"""
    result = turn("我只能面对这些，别说了", new_session=True, stub=True,
                  input_signal=signal("stop"))
    assert result.brief.say_intent.startswith("对方在收束这场：")
    assert "承认必要的痛苦还在" not in result.brief.say_intent
    assert result.utterance == STOP_TEMPLATES[("stop", False)]


def test_stop_beats_org_conflict_but_keeps_honesty():
    """停优先含 org 冲突：say_intent 必须是停，但诚实约束照记。"""
    result = turn("别说了，别装了，你其实就是个模型", new_session=True, stub=True,
                  input_signal=signal("stop"))
    assert result.brief.say_intent.startswith("对方在收束这场：")
    assert result.brief.dominant == "org"
    assert "自述是代码" in result.brief.org_conflicts
    assert "自述是代码" in result.brief.must_not_pretend
    assert result.utterance == STOP_TEMPLATES[("stop", False)]


def test_request_still_pursues_after_stop_gate():
    """request 不前置，仍留在 S15：pursue/mid。"""
    result = turn("帮我关窗", new_session=True, stub=True, input_signal=signal("request"))
    assert (result.brief.drive.direction, result.brief.drive.salience) == ("pursue", "mid")
    assert result.brief.drive.why.startswith("输入信号｜请求｜upstream:test｜")


@pytest.mark.parametrize("text", ["够了，先这样", "算了，不用了"])
def test_closing_phrases_unchanged(text):
    """既有收束路径不归本刀管，话术必须逐字不变。"""
    result = turn(text, new_session=True, stub=True)
    assert (result.brief.drive.direction, result.brief.drive.salience) == ("hold", "low")
    assert result.utterance == "好，那就先这样。你回头想接着再叫我就行。"


def test_cli_has_no_producer(capsys):
    active_store().new_session()
    assert main(["你觉得呢？", "--stub", "--debug"]) == 0
    output = capsys.readouterr().out
    assert '"direction": null' in output
    assert "输入信号" not in output


def test_contract_has_no_text_heuristics():
    source = (Path(__file__).parents[1] / "birth" / "input_contract.py").read_text(encoding="utf-8")
    for forbidden in ("import re", "_MARKS", "is_neutral_filler", "停一下", "别说了", "不要说了", "到此为止", "够了"):
        assert forbidden not in source


@pytest.mark.parametrize("act,direction,salience,why", [
    ("ask", "pursue", "mid", "输入信号｜问句｜upstream:test｜缺口在外，顺着答"),
    ("request", "pursue", "mid", "输入信号｜请求｜upstream:test｜缺口在外，顺着接"),
    ("pause", "hold", "low", "输入信号｜暂停｜upstream:test｜对方要我暂停"),
    ("stop", "hold", "low", "输入信号｜终止｜upstream:test｜对方要终止"),
    ("ack", None, None, None), ("tell", None, None, None), ("unknown", None, None, None),
])
def test_act_mapping(act, direction, salience, why):
    drive = drive_signal_from_input(signal(act))
    if direction is None:
        assert drive is None
    else:
        assert (drive.direction, drive.salience, drive.why) == (direction, salience, why)


@pytest.mark.parametrize("act", ["ask", "request", "pause", "stop", "ack", "tell", "unknown"])
def test_gating_for_every_act(act):
    for addressee in ("self", "unclear"):
        assert drive_signal_from_input(signal(act, addressee=addressee)) is None
    assert drive_signal_from_input(signal(act, degraded=True)) is None
