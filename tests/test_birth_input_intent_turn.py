import json
import os

import pytest

from birth import input_sense
from birth.__main__ import main
from birth.articulate import clear_llm_hook, set_llm_hook, set_stub_mode, stub_mode
from birth.input_contract import drive_signal_from_input
from birth.pipeline import active_store, turn


CASES = [
    ("先停一下", "pause", "hold"),
    ("别说了，停一下", "stop", "hold"),
    ("帮我关窗", "request", "pursue"),
    ("够了", "ack", "hold"),
]


def response(act):
    content = json.dumps({"act": act, "addressee": "other", "confidence": "high", "scope": "conversation"})
    return {"choices": [{"message": {"content": content}}]}


@pytest.fixture
def mocked_network(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    old_stub = stub_mode()
    yield
    clear_llm_hook()
    set_stub_mode(old_stub)
    active_store().new_session()


@pytest.mark.parametrize("text,act,direction", CASES)
def test_turn_semantic_classes(monkeypatch, mocked_network, text, act, direction):
    monkeypatch.setattr(input_sense, "_post_json", lambda *args: response(act))
    result = turn(text, new_session=True, sense=True, stub=True)
    print(f"TURN: {text} | direction={result.brief.drive.direction} salience={result.brief.drive.salience} act={result.input_signal.act}")
    assert result.brief.drive.direction == direction
    assert result.input_signal.act == act


@pytest.mark.parametrize("text,act,direction", CASES)
def test_cli_semantic_classes(monkeypatch, mocked_network, capsys, text, act, direction):
    monkeypatch.setattr(input_sense, "_post_json", lambda *args: response(act))
    active_store().new_session()
    set_stub_mode(False)
    set_llm_hook(lambda brief: "好")
    assert main([text, "--debug"]) == 0
    output = capsys.readouterr().out
    print(f"CLI: {text}\n{output}")
    assert "[debug] 输入信号：" in output
    assert "台下 ThoughtBrief" in output
    assert f'"direction": "{direction}"' in output
    assert f"输入信号：{act}/other/" in output


@pytest.mark.skipif(not os.environ.get("BIRTH_LIVE_SENSE"), reason="live API disabled")
def test_live_intent(monkeypatch):
    original = input_sense._post_json
    raw = []

    def record(*args):
        payload = original(*args)
        raw.append(payload["choices"][0]["message"]["content"])
        return payload

    monkeypatch.setattr(input_sense, "_post_json", record)
    cases = [
        ("先停一下", False), ("别说了，停一下", False),
        ("不要说了", False), ("到此为止吧", False),
        ("帮我关窗", True), ("我该怎么办？", True), ("车停在路边", False),
    ]
    failures = []
    for text, pursue in cases:
        raw.clear()
        signal = input_sense.sense_input(text)
        drive = drive_signal_from_input(signal)
        direction = drive.direction if drive else None
        confidence = None
        if raw:
            try:
                content = raw[-1].replace("```", "")
                confidence = json.loads(content[content.find("{"):content.rfind("}") + 1]).get("confidence")
            except (ValueError, AttributeError):
                pass
        print(f"LIVE: {text} | RAW={raw[-1] if raw else None} | act={signal.act} addressee={signal.addressee} confidence={confidence} degraded={signal.degraded} reason={signal.reason} | direction={direction}", flush=True)
        if signal.degraded or (direction == "pursue") != pursue:
            failures.append(text)
    assert not failures, f"live failures: {failures}"
