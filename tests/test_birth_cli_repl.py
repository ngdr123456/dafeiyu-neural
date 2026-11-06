"""CLI REPL 多轮入口：工程师通道测，非听感。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from birth.__main__ import main


@pytest.fixture(autouse=True)
def _isolate_repl_memory(monkeypatch, tmp_path):
    from birth.articulate import clear_llm_hook, set_stub_mode
    from birth.memory import configure_memory
    from birth.pipeline import active_store
    monkeypatch.setenv("BIRTH_MEMORY_PATH", str(tmp_path / "memory.json"))
    configure_memory(enabled=False)
    active_store().new_session()
    clear_llm_hook()
    yield
    configure_memory(enabled=False)
    active_store().new_session()
    clear_llm_hook()
    set_stub_mode(True)


def _fake_turn_factory():
    calls: list[dict] = []

    def _fake_turn(user_text, *, new_session=False, debug=False, stub=None, **kwargs):
        calls.append(
            {
                "user_text": user_text,
                "new_session": new_session,
                "debug": debug,
                "stub": stub,
            }
        )
        return SimpleNamespace(
            utterance=f"U{len(calls)}:{user_text}",
            articulate_source="stub",
            brief=SimpleNamespace(),  # debug 路径另测；默认不用 asdict
        )

    return calls, _fake_turn


def test_no_args_enters_repl_not_default_nihao():
    calls, fake = _fake_turn_factory()
    with patch("birth.__main__.turn", fake), patch("builtins.input", side_effect=["q"]):
        assert main([]) == 0
    assert calls == []


def test_repl_empty_line_exits():
    calls, fake = _fake_turn_factory()
    with patch("birth.__main__.turn", fake), patch("builtins.input", side_effect=[""]):
        assert main(["--stub"]) == 0
    assert calls == []


@pytest.mark.parametrize("word", ["exit", "quit", "q"])
def test_repl_quit_aliases(word: str):
    calls, fake = _fake_turn_factory()
    with patch("birth.__main__.turn", fake), patch("builtins.input", side_effect=[word]):
        assert main(["--stub"]) == 0
    assert calls == []


def test_repl_multiturn_keeps_session(capsys):
    calls, fake = _fake_turn_factory()
    with patch("birth.__main__.turn", fake), patch(
        "builtins.input", side_effect=["你好", "还在吗", "exit"]
    ):
        assert main(["--stub"]) == 0
    assert len(calls) == 2
    assert calls[0]["new_session"] is True
    assert calls[0]["user_text"] == "你好"
    assert calls[0]["stub"] is True
    assert calls[1]["new_session"] is False
    assert calls[1]["user_text"] == "还在吗"
    out = capsys.readouterr().out
    assert "U1:你好" in out
    assert "U2:还在吗" in out


def test_repl_slash_new_starts_new_session(capsys):
    calls, fake = _fake_turn_factory()
    with patch("birth.__main__.turn", fake), patch(
        "builtins.input", side_effect=["你好", "/new", "嗨", "q"]
    ):
        assert main(["--stub"]) == 0
    assert len(calls) == 2
    assert calls[0]["new_session"] is True
    assert calls[0]["user_text"] == "你好"
    assert calls[1]["new_session"] is True
    assert calls[1]["user_text"] == "嗨"
    assert "[新场]" in capsys.readouterr().out


def test_repl_eof_exits_cleanly():
    calls, fake = _fake_turn_factory()
    with patch("birth.__main__.turn", fake), patch(
        "builtins.input", side_effect=EOFError
    ):
        assert main(["--stub"]) == 0
    assert calls == []


def test_single_shot_still_works():
    """单句路径仍走真 stub turn（不 mock）。"""
    rc = main(["你好", "--stub"])
    assert rc == 0


def test_single_shot_with_debug_prints_brief(capsys):
    rc = main(["你好", "--stub", "--debug"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "ThoughtBrief" in out
    assert "开口来源" in out


@pytest.mark.parametrize("ending", ["quit", "exit", "q", "", EOFError, KeyboardInterrupt])
def test_real_repl_exit_persists_final_utterance(ending, tmp_path, capsys):
    from birth.memory import BirthMemoryStore
    from birth.pipeline import active_store
    with patch("builtins.input", side_effect=["你好", ending]):
        assert main(["--stub"]) == 0
    path = tmp_path / "memory.json"
    assert path.exists()
    final_facts = [f for f in active_store().context.facts_this_session if f.startswith("台上说：")]
    assert len(final_facts) == 1
    assert final_facts[0] in BirthMemoryStore(path=path).latest_prior().facts
    assert final_facts[0][len("台上说："):] in capsys.readouterr().out


def test_repl_exit_capacity_error_is_reported(capsys):
    from birth.memory import PendingCommitmentCapacityError
    with patch("builtins.input", side_effect=["q"]), patch(
        "birth.__main__.end_session", side_effect=PendingCommitmentCapacityError("full")
    ):
        assert main(["--stub"]) == 0
    assert "[记忆容量不足]" in capsys.readouterr().out
