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
        result = SimpleNamespace(
            utterance=f"U{len(calls)}:{user_text}",
            articulate_source="stub",
            brief=SimpleNamespace(),  # debug 路径另测；默认不用 asdict
        )
        kwargs["output"](result)
        return result

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


@pytest.mark.parametrize("failure", [KeyboardInterrupt, OSError])
@pytest.mark.parametrize("phase", ["write", "flush"])
def test_real_cli_output_failure_saves_only_confirmed_turns(failure, phase, tmp_path, monkeypatch, capsys):
    """真 main→turn→stdout；中断走 finish，I/O 失败后显式保存也不能污染记忆。"""
    import sys
    from birth.memory import BirthMemoryStore
    from birth.pipeline import active_store, end_session

    first = "我答应晚点再聊月亮。你想聊什么？"
    unheard = "我答应回头再聊星空。你想看哪里？"
    stdout = sys.stdout
    before = []

    class Output:
        failing = False

        def write(self, text):
            if text == unheard:
                before.append(active_store().snapshot())
                self.failing = True
                if phase == "write":
                    raise failure()
            return stdout.write(text)

        def flush(self):
            if self.failing:
                self.failing = False
                raise failure()
            return stdout.flush()

    monkeypatch.setattr(sys, "stdout", Output())
    with patch("birth.pipeline.articulate", side_effect=[first, unheard]), patch(
        "builtins.input", side_effect=["你好", "接着说", "q"]
    ):
        if failure is KeyboardInterrupt:
            assert main(["--stub"]) == 0
        else:
            with pytest.raises(OSError):
                main(["--stub"])
            assert end_session() is True
    assert len(before) == 1
    ctx = active_store().snapshot()
    assert ctx.last_commitments == before[0].last_commitments
    assert ctx.open_questions == before[0].open_questions
    assert ctx.her_questions == before[0].her_questions
    assert ctx.stance_traces == before[0].stance_traces
    assert ctx.want_seen_pending == before[0].want_seen_pending
    assert ctx.last_commitments and ctx.her_questions
    prior = BirthMemoryStore(path=tmp_path / "memory.json").latest_prior()
    assert "台上说：" + first in prior.facts
    assert "台上说：" + unheard not in prior.facts
    assert "星空" not in str(prior)
    assert "月亮" in str(prior.commitments_pending)
    assert first in prior.her_questions
    if phase == "write":
        assert unheard not in capsys.readouterr().out


def test_real_cli_confirmation_precedes_debug_and_survives_new_session(monkeypatch, tmp_path):
    import sys
    from birth.memory import BirthMemoryStore
    from birth.pipeline import active_store

    line = "我答应晚点再聊月亮。你想聊什么？"
    stdout = sys.stdout
    snapshots = []

    class Output:
        def write(self, text):
            if text == line:
                snapshots.append(active_store().snapshot())
            return stdout.write(text)

        def flush(self):
            assert not active_store().context.last_commitments
            return stdout.flush()

    # 单轮实际输出成功后才可见承诺／悬问；debug 不参与确认。
    monkeypatch.setattr(sys, "stdout", Output())
    with patch("birth.pipeline.articulate", return_value=line):
        assert main(["你好", "--stub", "--debug"]) == 0
    assert snapshots[0].last_commitments == []
    assert snapshots[0].open_questions == []
    monkeypatch.setattr(sys, "stdout", stdout)
    seen = []
    def sense(text, *, context):
        seen.append(context)
        return None
    monkeypatch.setattr("birth.pipeline.sense_input", sense)
    from birth.pipeline import turn
    from birth.memory import configure_memory
    configure_memory(enabled=True, path=tmp_path / "confirmed.json")
    turn("接着说", stub=True, sense=True)
    assert "台上说：" + line in seen[-1].facts_this_session
    turn("新场", new_session=True, stub=True, sense=True)
    assert "台上说：" + line in seen[-1].prior_session.facts
    assert "月亮" in str(seen[-1].prior_session.commitments_pending)
    assert line in BirthMemoryStore(path=tmp_path / "confirmed.json").latest_prior().her_questions


def test_debug_failure_keeps_already_printed_experience(tmp_path, capsys):
    from birth.memory import BirthMemoryStore
    from birth.pipeline import active_store, end_session
    line = "我答应晚点再聊月亮。"
    with patch("birth.pipeline.articulate", return_value=line), patch(
        "birth.__main__._print_debug", side_effect=KeyboardInterrupt
    ), patch("builtins.input", side_effect=["你好"]):
        with pytest.raises(KeyboardInterrupt):
            main(["--stub", "--debug"])
    assert line in capsys.readouterr().out
    assert active_store().pending_commitments() == [line]
    assert end_session() is True
    assert "台上说：" + line in BirthMemoryStore(path=tmp_path / "memory.json").latest_prior().facts
