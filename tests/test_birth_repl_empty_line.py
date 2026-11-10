"""Empty REPL lines must skip, not end the session."""

from birth.__main__ import repl_line_action


def test_empty_and_whitespace_skip():
    assert repl_line_action("") == "skip"
    assert repl_line_action("   ") == "skip"
    assert repl_line_action("\t") == "skip"
    assert repl_line_action("\n") == "skip"


def test_exit_words_still_exit():
    assert repl_line_action("exit") == "exit"
    assert repl_line_action("quit") == "exit"
    assert repl_line_action("q") == "exit"
    assert repl_line_action("  exit  ") == "exit"


def test_new_and_turn_unchanged():
    assert repl_line_action("/new") == "new"
    assert repl_line_action("嗯") == "turn"
    assert repl_line_action("上次的尝试对下一步有帮助。") == "turn"
    # Uppercase was not an exit before this knife; do not expand the set.
    assert repl_line_action("Exit") == "turn"


def test_repl_loop_empty_lines_do_not_end_or_pause(monkeypatch):
    """Empty lines must not finish the session; only an exit word should."""
    from types import SimpleNamespace
    from birth import __main__ as main

    calls = {"pause": 0, "turn": []}

    def fake_pause():
        calls["pause"] += 1

    def fake_turn(text, **kwargs):
        calls["turn"].append(text)
        return SimpleNamespace(
            utterance="ok",
            articulate_source="stub",
            input_signal=None,
            brief=SimpleNamespace(dominant_why=""),
        )

    monkeypatch.setattr(main, "pause_session", fake_pause)
    monkeypatch.setattr(main, "resume_open_session", lambda: False)
    monkeypatch.setattr(main, "turn", fake_turn)
    lines = iter(["", "   ", "嗯", "", "exit"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(lines))
    args = main._build_parser().parse_args(["--stub", "--no-memory"])
    assert main._run_repl(args) == 0
    assert calls["turn"] == ["嗯"]
    assert calls["pause"] == 1
