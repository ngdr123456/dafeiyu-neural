"""The synthetic probe writes a verifiable UTF-8 report without a model call."""
import json
import socket
import sys

from tools import probe_self_recall_bounded as probe


def test_dry_run_writes_utf8_json(tmp_path, monkeypatch, capsys):
    output = tmp_path / "回看.json"
    monkeypatch.setattr(sys, "argv", ["probe", "--output", str(output)])
    def no_network(*args, **kwargs):
        raise AssertionError("the dry run must not access the network")
    monkeypatch.setattr(socket, "socket", no_network)
    probe.main()
    raw = output.read_bytes()
    report = json.loads(raw.decode("utf-8"))
    assert probe.QUESTION.encode("utf-8") in raw
    assert report["question"] == probe.QUESTION
    assert report["synthetic_history"] == probe.HISTORY
    assert report["cases"]["unique"]["evidence"]["text"] == probe.HISTORY
    assert report["model_calls_attempted"] == 0
    assert set(report["cases"]) == {"unique", "no_match", "multiple"}
    assert not capsys.readouterr().out
