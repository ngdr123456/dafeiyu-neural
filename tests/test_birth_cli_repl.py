"""CLI REPL 多轮入口：工程师通道测，非听感。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from birth.__main__ import main


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
