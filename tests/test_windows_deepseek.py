"""Real DeepSeek HTTP adapters, mocked transport only; never read credentials."""
import io
import json
import socket
import urllib.error

import pytest

from birth import llm_deepseek, pipeline
from birth.articulate import clear_llm_hook
from birth.memory import configure_memory, BirthMemoryStore
from birth.windows_chat import BackendUnavailable, ChatSession


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    configure_memory(enabled=False)
    pipeline.active_store().new_session()
    monkeypatch.setattr(llm_deepseek, "load_api_key", lambda: "OFFLINE-TEST-ONLY")
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: pytest.fail("Unmocked network"))
    monkeypatch.setattr("birth.llm_opencode.generate_utterance", lambda *a, **k: pytest.fail("OpenCode forbidden"))
    yield
    configure_memory(enabled=False)
    pipeline.active_store().new_session()
    clear_llm_hook()


def response(content):
    return io.BytesIO(json.dumps({"choices": [{"message": {"content": content}}]}).encode())


def sense_response():
    return response(json.dumps({"act": "tell", "addressee": "other", "confidence": "high"}))



def open_snapshot(memory_path):
    from pathlib import Path as _Path
    import json
    path = _Path(memory_path).with_name("birth_session_open.json")
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def test_real_adapters_delivery_new_and_restart(tmp_path, monkeypatch):
    path = tmp_path / "memory.json"
    session = ChatSession(memory_path=path)
    requests = []
    line = "我答应晚点再聊月亮。"
    def transport(req, **kwargs):
        body = json.loads(req.data)
        requests.append(body)
        return sense_response() if len(requests) % 2 else response(line)
    monkeypatch.setattr("urllib.request.urlopen", transport)
    delivered = []
    def display(result):
        assert not pipeline.active_store().pending_commitments()
        delivered.append(result)
    session.send("你好", display)
    assert delivered[0].input_signal.source.startswith("model:")
    assert delivered[0].articulate_source == "hook"
    assert pipeline.active_store().pending_commitments()
    assert len(requests) == 2
    assert requests[0]["temperature"] == 0
    assert requests[0]["model"] == requests[1]["model"]
    session.new()
    assert not pipeline.active_store().context.facts_this_session
    assert "台上说：" + line in BirthMemoryStore(path).latest_prior().facts
    session.send("你好", lambda result: None)
    session.close()
    pipeline.active_store().new_session()  # simulate a fresh process
    restarted = ChatSession(memory_path=path)
    assert restarted
    assert "台上说：" + line in pipeline.active_store().snapshot().prior_session.facts


@pytest.mark.parametrize("stage", ["sense", "utterance"])
@pytest.mark.parametrize("failure,code", [
    ("quota", "quota"), ("auth", "auth"), ("http", "http"),
    ("network", "network"), ("timeout", "network"),
    ("json", "invalid_output"), ("empty", "invalid_output"),
])
def test_transport_failure_never_delivers(tmp_path, monkeypatch, stage, failure, code):
    session = ChatSession(memory_path=tmp_path / "memory.json")
    calls = []
    def transport(req, **kwargs):
        calls.append(True)
        if stage == "utterance" and len(calls) == 1:
            return sense_response()
        if failure in ("quota", "auth", "http"):
            raise urllib.error.HTTPError(req.full_url, {"quota": 402, "auth": 401, "http": 503}[failure], "PRIVATE", {}, None)
        if failure == "network":
            raise urllib.error.URLError("PRIVATE")
        if failure == "timeout":
            raise socket.timeout("PRIVATE")
        if failure == "json":
            return io.BytesIO(b"{bad")
        return response("")
    monkeypatch.setattr("urllib.request.urlopen", transport)
    with pytest.raises(BackendUnavailable) as err:
        session.send("你好", lambda result: pytest.fail("must not deliver"))
    assert err.value.code == code
    assert "PRIVATE" not in str(err.value)
    assert len(calls) == (1 if stage == "sense" else 2)
    assert not any(f.startswith("台上说：") for f in pipeline.active_store().context.facts_this_session)
    assert not pipeline.active_store().pending_commitments()


def test_missing_key_and_legacy_optional_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(llm_deepseek, "load_api_key", lambda: None)
    session = ChatSession(memory_path=tmp_path / "memory.json")
    with pytest.raises(BackendUnavailable, match="no_key"):
        session.send("你好", lambda result: pytest.fail("must not display"))
    assert llm_deepseek.generate_utterance(object()) is None


def test_real_backend_display_failure_not_saved(tmp_path, monkeypatch):
    path = tmp_path / "memory.json"
    session = ChatSession(memory_path=path)
    replies = iter([sense_response(), response("我答应晚点再聊月亮。")])
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: next(replies))
    def broken(result):
        raise OSError("display failure")
    with pytest.raises(OSError):
        session.send("你好", broken)
    session.close()
    assert not pipeline.active_store().pending_commitments()
    prior = BirthMemoryStore(path).latest_prior()
    assert prior is None or not any(f.startswith("台上说：") for f in prior.facts)
    snap = open_snapshot(path) or {}
    facts = (snap.get("context") or {}).get("facts_this_session") or []
    assert not any(f.startswith("台上说：") for f in facts)


def test_acceptance_restart_read_is_offline(tmp_path, capsys):
    from birth.chat_acceptance import main
    path = tmp_path / "memory.json"
    session = ChatSession(memory_path=path, offline=True)
    session.send("我叫离线验收", lambda result: None)
    session.new()  # 结束本场才写入薄摘要；关窗只是暂停。
    pipeline.active_store().new_session()
    assert main(["--memory-path", str(path), "--expect-prior-fact", "离线验收"]) == 0
    assert "PRIOR_FACT_MATCH=True" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        main(["--memory-path", str(path), "--send", "你好"])
