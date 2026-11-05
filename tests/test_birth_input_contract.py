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


def test_commitment_precedes_input():
    store = active_store()
    store.new_session()
    store.append_commitment("同场里说好这轮先补月亮的事")
    result = turn("你还记得吗？", stub=True, input_signal=signal())
    assert result.brief.drive.direction == "guard"


def test_curiosity_precedes_input():
    result = turn("为什么星星会发光？", new_session=True, stub=True, input_signal=signal())
    assert (result.brief.drive.direction, result.brief.drive.salience) == ("pursue", "high")


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
