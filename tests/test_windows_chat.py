"""OFFLINE: real Tk/main/birth pipeline; all model calls stubbed or mocked."""
import time
import gc
import tkinter as tk
from unittest.mock import patch

import pytest

from birth import pipeline
from birth.articulate import clear_llm_hook
from birth.memory import BirthMemoryStore, configure_memory
from birth.input_contract import InputSignal
from birth.windows_chat import BackendUnavailable, ChatSession, ChatWindow, main


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    # Never inspect local credentials or allow a real network request in this file.
    monkeypatch.setattr("birth.llm_deepseek.load_api_key", lambda: "OFFLINE-TEST-ONLY")
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: pytest.fail("Network forbidden"))
    pipeline.active_store().new_session()
    configure_memory(enabled=False)
    yield
    pipeline.active_store().new_session()
    configure_memory(enabled=False)
    clear_llm_hook()
    # Tcl objects from destroyed test windows must be collected on the UI thread.
    gc.collect()


def pump(root, predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while not predicate():
        root.update()
        if time.monotonic() > deadline:
            pytest.fail("Tk worker did not finish")
        time.sleep(.005)
    root.update()


def window(tmp_path, offline=True):
    root = tk.Tk()
    app = ChatWindow(root, memory_path=tmp_path / "memory.json", offline=offline)
    pump(root, lambda: not app.busy)
    return root, app


def test_actual_main_entry_and_normal_exit(tmp_path, monkeypatch):
    """Actual main event loop, controls, pipeline output, shutdown persistence."""
    real_window = ChatWindow
    evidence = []

    def launch(root, **kwargs):
        app = real_window(root, **kwargs)

        def scenario():
            if app.busy:
                root.after(10, scenario)
                return
            app.entry.insert("1.0", "你好")
            app.send_button.invoke()
            root.after(10, finish)

        def finish():
            if app.busy:
                root.after(10, finish)
                return
            evidence.append(app.history.get("1.0", "end"))
            app.close()
        root.after(10, scenario)
        return app

    monkeypatch.setattr("birth.windows_chat.ChatWindow", launch)
    assert main(["--offline", "--memory-path", str(tmp_path / "main.json")]) == 0
    assert "离线模板（非真实模型）" in evidence[0]
    assert BirthMemoryStore(tmp_path / "main.json").latest_prior().facts


def test_real_pipeline_render_precedes_feedback_and_new_saves(tmp_path):
    root, app = window(tmp_path)
    line = "我答应晚点再聊月亮。你想聊什么？"
    original = app._append
    before = []

    def append(who, text):
        if text == line:
            before.append(pipeline.active_store().snapshot())
        original(who, text)
    app._append = append
    try:
        with patch("birth.pipeline.articulate", return_value=line):
            app.entry.insert("1.0", "你好")
            app.send()
            pump(root, lambda: not app.busy)
        assert before and not before[0].last_commitments
        assert pipeline.active_store().pending_commitments()
        assert line in app.history.get("1.0", "end")
        app.new()
        pump(root, lambda: not app.busy)
        assert not pipeline.active_store().context.facts_this_session
        assert "台上说：" + line in BirthMemoryStore(tmp_path / "memory.json").latest_prior().facts
        assert pipeline.active_store().context.prior_session
    finally:
        root.destroy()


def test_render_failure_does_not_confirm_and_preserves_input(tmp_path):
    root, app = window(tmp_path)
    line = "我答应晚点再聊月亮。"
    original = app._append

    def broken(who, text):
        if text == line:
            raise OSError("OFFLINE display failure")
        original(who, text)
    app._append = broken
    try:
        with patch("birth.pipeline.articulate", return_value=line):
            app.entry.insert("1.0", "你好")
            app.send()
            pump(root, lambda: not app.busy)
        assert not pipeline.active_store().pending_commitments()
        assert app.entry.get("1.0", "end").strip() == "你好"
        app.session.close()
        assert "台上说：" + line not in BirthMemoryStore(tmp_path / "memory.json").latest_prior().facts
    finally:
        root.destroy()


@pytest.mark.parametrize("action", ["new", "close"])
def test_save_failure_keeps_window_and_session(tmp_path, action):
    root, app = window(tmp_path)
    try:
        app.entry.insert("1.0", "你好")
        app.send()
        pump(root, lambda: not app.busy)
        facts = list(pipeline.active_store().context.facts_this_session)
        with patch("birth.pipeline.end_session", side_effect=OSError("OFFLINE disk failure")):
            getattr(app, action)()
            pump(root, lambda: not app.busy)
        assert root.winfo_exists()
        assert pipeline.active_store().context.facts_this_session == facts
        assert "操作失败" in app.status.get()
    finally:
        root.destroy()


def test_default_backend_error_never_delivers_template(tmp_path):
    from birth.input_contract import InputSignal
    session = ChatSession(memory_path=tmp_path / "memory.json")
    with patch("birth.windows_chat.sense_input", return_value=InputSignal(
        "tell", "other", "mock", "mock"
    )), patch("birth.llm_deepseek.generate_utterance", return_value=None), patch(
        "birth.llm_opencode.generate_utterance", side_effect=AssertionError("Forbidden")
    ):
        with pytest.raises(BackendUnavailable):
            session.send("你好", lambda result: pytest.fail("must not display fallback"))
    assert not any(f.startswith("台上说：") for f in pipeline.active_store().context.facts_this_session)


def test_slow_mock_backend_keeps_ui_alive_and_queued_close_saves(tmp_path):
    import threading
    from birth.articulate import set_llm_hook
    root, app = window(tmp_path, offline=False)
    gate = threading.Event()
    def backend(brief):
        assert gate.wait(5)
        return "你好，我在这里听着。"
    set_llm_hook(backend)
    try:
        with patch("birth.windows_chat.sense_input", return_value=InputSignal("tell", "other", "mock", "mock")):
            app.entry.insert("1.0", "你好")
            app.send()
            ticks = []
            root.after(10, lambda: ticks.append(True))
            pump(root, lambda: bool(ticks))
            assert app.busy
            app.close()
            assert app.closing and root.winfo_exists()
            gate.set()
            deadline = time.monotonic() + 5
            while root.winfo_exists():
                root.update()
                if time.monotonic() > deadline:
                    pytest.fail("Close did not complete")
                time.sleep(.005)
    except tk.TclError:
        # Interpreter reports destroyed root after successful queued close.
        pass
    finally:
        gate.set()
        try:
            root.destroy()
        except tk.TclError:
            pass
    assert BirthMemoryStore(tmp_path / "memory.json").latest_prior().facts


def test_corrupt_memory_is_not_overwritten(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{bad", encoding="utf-8")
    with pytest.raises(ValueError):
        ChatSession(memory_path=path)
    assert path.read_text(encoding="utf-8") == "{bad"


def test_opencode_windows_transport_offline(monkeypatch):
    from birth import llm_opencode
    from types import SimpleNamespace
    from pathlib import Path
    calls = []
    monkeypatch.setattr(llm_opencode.shutil, "which", lambda name: "OFFLINE-opencode")
    monkeypatch.setattr(llm_opencode, "brief_to_prompt", lambda brief, **kwargs: "离线测试")
    def run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return SimpleNamespace(returncode=0, stdout='{"type":"text","part":{"text":"你好"}}')
    monkeypatch.setattr(llm_opencode.subprocess, "run", run)
    assert llm_opencode.generate_utterance(object()) == "你好"
    assert calls[0][1]["encoding"] == "utf-8"
    assert Path(calls[0][1]["cwd"]).is_dir()


@pytest.mark.parametrize("failure", ["quota", "display"])
def test_deepseek_gui_failure_no_confirmation_and_retry_input(tmp_path, monkeypatch, failure):
    from birth.llm_deepseek import DeepSeekUnavailable
    root, app = window(tmp_path, offline=False)
    monkeypatch.setattr("birth.windows_chat.sense_input", lambda *a, **k: InputSignal(
        "tell", "other", "model:mock", "mock"
    ))
    line = "我答应晚点再聊月亮。"
    def generate(*args, **kwargs):
        assert kwargs["strict"] is True
        if failure == "quota":
            raise DeepSeekUnavailable("quota")
        return line
    monkeypatch.setattr("birth.llm_deepseek.generate_utterance", generate)
    original = app._append
    def append(who, text):
        if failure == "display" and text == line:
            raise OSError("PRIVATE display failure")
        original(who, text)
    app._append = append
    try:
        app.entry.insert("1.0", "你好")
        app.send()
        pump(root, lambda: not app.busy)
        assert app.entry.get("1.0", "end").strip() == "你好"
        assert not pipeline.active_store().pending_commitments()
        assert "PRIVATE" not in app.status.get()
        assert ("额度不足" if failure == "quota" else "操作失败") in app.status.get()
        app.new()
        pump(root, lambda: not app.busy)
        prior = BirthMemoryStore(tmp_path / "memory.json").latest_prior()
        assert not any(f.startswith("台上说：") for f in prior.facts)
    finally:
        root.destroy()


def test_deepseek_gui_real_adapters_mock_transport(tmp_path, monkeypatch):
    import io
    import json
    root, app = window(tmp_path, offline=False)
    line = "我答应晚点再聊月亮。"
    contents = iter([
        json.dumps({"act": "tell", "addressee": "other", "confidence": "high"}),
        line,
    ])
    def transport(*args, **kwargs):
        return io.BytesIO(json.dumps({"choices": [{"message": {
            "content": next(contents)
        }}]}).encode())
    monkeypatch.setattr("urllib.request.urlopen", transport)
    try:
        app.entry.insert("1.0", "你好")
        app.send()
        pump(root, lambda: not app.busy)
        assert line in app.history.get("1.0", "end")
        assert app.entry.get("1.0", "end").strip() == ""
        assert pipeline.active_store().pending_commitments()
        app.new()
        pump(root, lambda: not app.busy)
        assert "台上说：" + line in pipeline.active_store().snapshot().prior_session.facts
    finally:
        root.destroy()

@pytest.mark.parametrize("size,scaling", [
    ((1000, 720), 4 / 3), ((680, 500), 4 / 3),
    ((1000, 720), 2.0), ((680, 500), 2.0),
    ((1000, 720), 8 / 3), ((680, 500), 8 / 3),
])
def test_layout_and_offline_send_at_window_sizes(tmp_path, size, scaling):
    root = tk.Tk()
    root.tk.call("tk", "scaling", scaling)
    app = ChatWindow(root, memory_path=tmp_path / "layout-memory.json", offline=True)
    root.geometry(f"{size[0]}x{size[1]}")
    try:
        pump(root, lambda: not app.busy)
        for widget in (app.history, app.entry, app.send_button):
            assert widget.winfo_viewable()
            assert widget.winfo_width() > 20 and widget.winfo_height() > 20
            x, y = widget.winfo_rootx(), widget.winfo_rooty()
            parent = widget.master
            while parent is not None:
                assert x >= parent.winfo_rootx() and y >= parent.winfo_rooty()
                assert x + widget.winfo_width() <= parent.winfo_rootx() + parent.winfo_width()
                assert y + widget.winfo_height() <= parent.winfo_rooty() + parent.winfo_height()
                parent = parent.master
        app.entry.insert("1.0", "离线布局测试")
        app.send_button.invoke()
        pump(root, lambda: not app.busy)
        assert "离线布局测试" in app.history.get("1.0", "end")
        assert not app.entry.get("1.0", "end").strip()
    finally:
        root.destroy()
