import json
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest

from birth import input_sense, llm_deepseek
from birth.articulate import (clear_llm_hook, set_llm_hook, set_stub_mode,
                              stub_mode)
from birth.__main__ import main
from birth.input_contract import InputSignal, drive_signal_from_input
from birth.pipeline import active_store, turn


def response(act="ask", addressee="other", confidence="high", scope="conversation"):
    return {"choices": [{"message": {"content": json.dumps(dict(
        act=act, addressee=addressee, confidence=confidence, scope=scope))}}]}


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    old_stub = stub_mode()
    monkeypatch.setattr(llm_deepseek, "load_api_key", lambda: "test-key")
    monkeypatch.delenv("BIRTH_INPUT_SENSE", raising=False)
    active_store().new_session()
    yield
    clear_llm_hook()
    set_stub_mode(old_stub)
    active_store().new_session()


@pytest.mark.parametrize("act,label", [("ask", "问句"), ("request", "请求")])
def test_positive(monkeypatch, act, label):
    monkeypatch.setattr(input_sense, "_post_json", lambda *args: response(act))
    signal = input_sense.sense_input("这件事")
    drive = drive_signal_from_input(signal)
    assert (drive.direction, drive.salience) == ("pursue", "mid")
    assert drive.why.startswith(f"输入信号｜{label}｜model:")


@pytest.mark.parametrize("act,addressee", [("ask", "self"), ("request", "unclear"),
                                          ("ack", "other"), ("tell", "other"), ("unknown", "other")])
def test_no_drive(monkeypatch, act, addressee):
    monkeypatch.setattr(input_sense, "_post_json", lambda *args: response(act, addressee))
    signal = input_sense.sense_input("这件事")
    assert not signal.degraded
    assert drive_signal_from_input(signal) is None
    assert turn("这件事", new_session=True, stub=True, input_signal=signal).brief.drive.direction is None


def test_low(monkeypatch):
    monkeypatch.setattr(input_sense, "_post_json", lambda *args: response(confidence="low"))
    signal = input_sense.sense_input("这件事")
    assert (signal.act, signal.addressee, signal.degraded, signal.reason) == ("ask", "other", True, "low_confidence")
    assert drive_signal_from_input(signal) is None


def test_no_key(monkeypatch):
    monkeypatch.setattr(llm_deepseek, "load_api_key", lambda: None)
    signal = input_sense.sense_input("这件事")
    assert signal.degraded and signal.reason == "no_key" and signal.source and signal.provenance


@pytest.mark.parametrize("error,reason", [(URLError("offline"), "network"),
                                          (TimeoutError(), "timeout"),
                                          (URLError(TimeoutError()), "timeout"),
                                          (HTTPError("url", 503, "error", {}, None), "http_503"),
                                          (RuntimeError("unexpected"), "network")])
def test_network_errors(monkeypatch, error, reason):
    def fail(*args):
        raise error
    monkeypatch.setattr(input_sense, "_post_json", fail)
    signal = input_sense.sense_input("这件事")
    assert signal.degraded and signal.reason == reason
    assert drive_signal_from_input(signal) is None


@pytest.mark.parametrize("content,reason", [("{oops}", "invalid_json"),
    ('{"act":"bad","addressee":"other","confidence":"high"}', "invalid_output"),
    ('{"act":"ask","addressee":"other"}', "invalid_output")])
def test_invalid(monkeypatch, content, reason):
    monkeypatch.setattr(input_sense, "_post_json", lambda *args: {"choices": [{"message": {"content": content}}]})
    signal = input_sense.sense_input("这件事")
    assert signal.degraded and signal.reason == reason


def test_cli(monkeypatch, capsys):
    calls = []
    def post(*args):
        calls.append(args)
        return response()
    monkeypatch.setattr(input_sense, "_post_json", post)
    set_stub_mode(False)
    set_llm_hook(lambda brief: "好")
    assert main(["你觉得呢？", "--debug"]) == 0
    output = capsys.readouterr().out
    assert len(calls) == 1
    assert '"direction": "pursue"' in output
    assert '输入信号｜问句｜model:' in output
    assert '[debug] 输入信号：ask/other/model:' in output
    assert '降级：' not in output


def test_cli_low_confidence(monkeypatch, capsys):
    monkeypatch.setattr(input_sense, "_post_json", lambda *args: response(confidence="low"))
    set_stub_mode(False)
    set_llm_hook(lambda brief: "好")
    assert main(["你觉得呢？", "--debug"]) == 0
    output = capsys.readouterr().out
    assert '降级：low_confidence' in output
    assert '"direction": null' in output


@pytest.mark.parametrize("flag", ["--stub", "--no-sense"])
def test_cli_off(monkeypatch, capsys, flag):
    def fail(*args):
        pytest.fail("unexpected model call")
    monkeypatch.setattr(input_sense, "_post_json", fail)
    set_stub_mode(False)
    set_llm_hook(lambda brief: "好")
    assert main(["你觉得呢？", flag, "--debug"]) == 0
    assert '"direction": null' in capsys.readouterr().out


def test_priority(monkeypatch):
    calls = []
    def post(*args):
        calls.append(1)
        return response()
    monkeypatch.setattr(input_sense, "_post_json", post)
    active_store().append_commitment("同场里说好这轮先补月亮的事")
    assert turn("你还记得吗？", sense=True, stub=True).brief.drive.direction == "guard"
    drive = turn("为什么星星会发光？", new_session=True, sense=True, stub=True).brief.drive
    assert (drive.direction, drive.salience) == ("pursue", "high")
    assert len(calls) == 2


def test_empty_and_fences(monkeypatch):
    calls = []
    def post(*args):
        calls.append(args)
        return {"choices": [{"message": {"content": '```json\n{"act":"ask","addressee":"other","confidence":"medium"}\n```'}}]}
    monkeypatch.setattr(input_sense, "_post_json", post)
    assert input_sense.sense_input("  ") is None
    assert input_sense.sense_input("话").act == "ask"
    assert len(calls) == 1
    assert calls[0][1]["thinking"] == {"type": "disabled"}


def test_turn_opt_in_and_bypass(monkeypatch):
    calls = []
    def post(*args):
        calls.append(1)
        return response()
    monkeypatch.setattr(input_sense, "_post_json", post)
    assert turn("这件事", new_session=True, stub=True).input_signal is None
    monkeypatch.setenv("BIRTH_INPUT_SENSE", "YES")
    assert turn("这件事", new_session=True, stub=True).brief.drive.direction == "pursue"
    assert turn("这件事", new_session=True, stub=True, sense=False).input_signal is None
    assert turn("这件事", new_session=True, stub=True, sense=True, drive_bypass=True).input_signal is None
    explicit = InputSignal("tell", "other", "test", "test")
    assert turn("这件事", new_session=True, stub=True, sense=True, input_signal=explicit).input_signal is explicit
    assert len(calls) == 1


def test_static():
    source = (Path(__file__).parents[1] / "birth" / "input_sense.py").read_text(encoding="utf-8")
    for forbidden in ("_MARKS", "GREETINGS", "is_neutral_filler", "similarity", "retrieval", "cosine"):
        assert forbidden not in source


@pytest.mark.parametrize("text,act,expected", [
    ("先停一下", "pause", "hold"),
    ("别说了，停一下", "stop", "hold"),
    ("不要说了", "stop", "hold"),
    ("到此为止吧", "stop", "hold"),
    ("帮我关窗", "request", "pursue"),
    ("我该怎么办？", "ask", "pursue"),
])
def test_semantic_classes(monkeypatch, text, act, expected):
    monkeypatch.setattr(input_sense, "_post_json", lambda *args: response(act))
    signal = input_sense.sense_input(text)
    assert not signal.degraded
    assert drive_signal_from_input(signal).direction == expected


@pytest.mark.parametrize("text", ["够了", "先这样", "不用了"])
def test_ack_closure(monkeypatch, text):
    monkeypatch.setattr(input_sense, "_post_json", lambda *args: response("ack"))
    result = turn(text, new_session=True, sense=True, stub=True)
    assert result.input_signal.act == "ack"
    assert result.brief.drive.direction == "hold"


