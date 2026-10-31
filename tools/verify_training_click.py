"""Click the actual exe's start button in a disposable, network-blocked fixture."""
import hashlib
import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DRIVER = r'''
# Acceptance-only driver: this appendix never modifies production UI source.
def main():
    import sys, json, time, faulthandler
    from pathlib import Path
    trace_file = open(Path(_ROOT) / "click_trace.txt", "w", encoding="utf-8")
    faulthandler.dump_traceback_later(20, file=trace_file)
    stage_file = Path(_ROOT) / "click_stage.json"
    def stage(name):
        stage_file.write_text(json.dumps({"stage": name}), encoding="utf-8")
    stage("driver_entered")
    import train, understand
    from pipeline import Pipeline
    from render import Speech
    def forbid_network(event, args):
        if event == "socket.connect":
            raise RuntimeError("Click acceptance forbids real network")
    sys.addaudithook(forbid_network)
    class FixtureReader:
        available = True
        model = "offline_click_fixture"
        base = "offline_fixture"
        def read(self, raw, stem, spec):
            return understand.ApiReader(api_key="")._parse_obj(
                {"intent": "ANSWER", "markers": [], "relations": []}, raw, spec, 0, {})
    class FixtureThinker:
        available = True
        last_attempts = [{"accepted": True, "source": "offline_fixture"}]
        def think(self, frame):
            return Speech("那件事后来怎么样了？", True, "offline_fixture")
    class FixtureTutor:
        errors = []
        def __init__(self, *args):
            self.n = 0
            self._ad = type("AdminFixture", (), {"reader": FixtureReader()})()
        def speak(self, *args):
            self.n += 1
            return "我今天想起了那件事%d。" % self.n
        def judge(self, *args):
            return {"ok": True, "problem": "none", "why": "offline fixture", "severity": 0,
                    "saw_internals": True}
    def fixture_pipe(self):
        p = Pipeline(ledger_path=self.ledger, character_path=self.character, auto_audit=False,
                     use_api=False, use_think=False, gate_perception=self.gate_perception)
        assert p.devlevel is not None, "Desktop start failed to activate the gate"
        p.reader, p.thinker = FixtureReader(), FixtureThinker()
        return p
    train.Tutor = FixtureTutor
    train.Trainer._pipe = fixture_pipe
    understand.ApiReader.available = property(lambda self: True)
    window = tk.Tk()
    window.withdraw()
    destination = Path(_ROOT) / "click_result.json"
    try:
        _setup_styles(window)
        stage("before_studio")
        app = Studio(window)
        stage("studio_created")
        app._probe_api = lambda: (True, "offline_click_fixture")
        def widget_texts(widget):
            result = []
            try:
                result.append(str(widget.cget("text")))
            except tk.TclError:
                pass
            for child in widget.winfo_children():
                result.extend(widget_texts(child))
            return result
        labels = widget_texts(window)
        assert "批准全部提案" not in labels and "全部驳回" not in labels
        assert "重审" in labels
        assert app.var_rounds.get() == "1" and app.var_len.get() == "2"
        before = len(Path(TRAIN_DIR, "ledger.jsonl").read_text(encoding="utf-8").splitlines())
        stage("before_start")
        app.btn_start.invoke()
        stage("start_invoked")
        deadline = time.time() + 30
        while time.time() < deadline:
            window.update()
            if app.worker is not None and not app.worker.is_alive() and not getattr(app, "_running", False):
                break
            time.sleep(.02)
        else:
            raise RuntimeError("UI did not complete within 30 seconds")
        after = len(Path(TRAIN_DIR, "ledger.jsonl").read_text(encoding="utf-8").splitlines())
        result = {"simulated_api": True, "network_forbidden": True, "actual_exe_button_invoked": True,
                  "bulk_proposal_decision_removed": True, "review_button_retained": True,
                  "default_rounds": app.var_rounds.get(), "default_session_length": app.var_len.get(),
                  "gate_default_on": desktop_training_gate(), "turns_added": after - before,
                  "ui_turn_count": app.counts["turns"], "status": app.lbl_state.cget("text"),
                  "start_button_state": str(app.btn_start.cget("state")), "progress": app.pbar["value"]}
        result["run_progress"] = json.loads(Path(TRAIN_DIR, "progress.json").read_text(encoding="utf-8"))
        result["last_notes"] = app.turns[-1].get("notes", []) if app.turns else []
        destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        assert result["turns_added"] == result["ui_turn_count"] == 6, result
        assert result["status"] == "完成" and result["start_button_state"] == "normal", result
        destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        stage("passed")
        return 0
    except Exception as exc:
        import traceback
        diagnosis = json.loads(destination.read_text(encoding="utf-8")) if destination.exists() else {}
        diagnosis.update(error=str(exc), traceback=traceback.format_exc())
        destination.write_text(json.dumps(diagnosis,
                                          ensure_ascii=False, indent=2), encoding="utf-8")
        return 1
    finally:
        faulthandler.cancel_dump_traceback_later()
        trace_file.close()
        window.destroy()
'''


def hashes():
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (ROOT / "state").rglob("*") if p.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default="spec/目标修正训练按钮验收_20261007.json")
    args = parser.parse_args()
    before = hashes()
    with tempfile.TemporaryDirectory(prefix="ego-click-") as temporary:
        root = Path(temporary) / "点击验收副本"
        root.mkdir()
        for name in ("engine", "rules", "corpus", "spec", "state", "tests"):
            shutil.copytree(ROOT / name, root / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        for source in ROOT.glob("*.md"):
            shutil.copy2(source, root / source.name)
        executable = root / "启动训练台.exe"
        shutil.copy2(ROOT / "启动训练台.exe", executable)
        source = root / "engine/training_studio.py"
        source.write_text(source.read_text(encoding="utf-8") + DRIVER, encoding="utf-8")
        env = dict(os.environ, EGO_ROOT=str(root))
        env.pop("EGO_GATE_PERCEPTION", None)
        process = subprocess.Popen([str(executable)], env=env)
        try:
            process.wait(timeout=45)
        except subprocess.TimeoutExpired:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
            diagnosis = {"timeout": True}
            for filename in ("click_stage.json", "click_trace.txt", "click_result.json"):
                if (root / filename).exists():
                    diagnosis[filename] = (root / filename).read_text(encoding="utf-8")
            (ROOT / args.report).write_text(json.dumps(diagnosis, ensure_ascii=False, indent=2), encoding="utf-8")
            raise RuntimeError("Owned exe test timed out; diagnostics preserved")
        result = json.loads((root / "click_result.json").read_text(encoding="utf-8"))
        (ROOT / args.report).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        assert process.returncode == 0, result
    assert hashes() == before, "Real state changed during isolated button verification"
    result["real_state_files_unchanged"] = len(before)
    (ROOT / args.report).write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Actual exe start button verified; network blocked; real state unchanged", len(before))


if __name__ == "__main__":
    main()
