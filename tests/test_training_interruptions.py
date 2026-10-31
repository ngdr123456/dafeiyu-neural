"""Replay actual disconnect class, zero/partial completion and reviewer scope."""
import contextlib
import http.client
import io
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from understand import ApiReader
from train import Trainer, Tutor, TrainingControl, EVAL_SCHEMA
from admin_evidence import snapshot
from action_plan import source_hashes, REGISTRY, REGRESSION, LIVE, FOUNDATION


class Response(io.BytesIO):
    def __enter__(self):
        return self
    def __exit__(self, *args):
        self.close()


class Pipe:
    api_enabled, thinker, devlevel = True, True, True
    def __init__(self, trainer, fail_at=None):
        self.trainer, self.calls, self.fail_at = trainer, 0, fail_at
    def turn(self, raw, topic, **kwargs):
        self.calls += 1
        if self.calls == self.fail_at:
            raise ValueError("offline fixture turn failure")
        with open(self.trainer.ledger, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({"raw_input": raw}) + "\n")
        return SimpleNamespace(output="那件事后来怎么样了？", behavior="QUESTION", character_note=None,
                               mech={}, api_ok=True, notes=[], markers=[], turn_id=self.calls)


class EmptyTutor:
    available, errors = True, []
    def __init__(self, *args):
        self.last_generation_diagnostic = {"error_type": "RemoteDisconnected", "transport_attempts": [
                {"attempt": 1, "ok": False}, {"attempt": 2, "ok": False}]}
    def speak(self, *args):
        return ""


class Interruptions(unittest.TestCase):
    def test_one_transport_disconnect_then_success_reuses_request_and_preserves_failure(self):
        payload = json.dumps({"choices": [{"message": {"content": "测试输入"}}]}).encode()
        reader = ApiReader(api_key="fixture-secret")
        with patch("urllib.request.urlopen", side_effect=[http.client.RemoteDisconnected("fixture"), Response(payload)]) as opened, \
                patch("understand.time.sleep"):
            text, _ = reader._post([{"role": "user", "content": "输入"}], json_mode=False)
        self.assertEqual(text["choices"][0]["message"]["content"], "测试输入")
        self.assertEqual(opened.call_count, 2)
        self.assertEqual(opened.call_args_list[0].args[0].data, opened.call_args_list[1].args[0].data)
        self.assertEqual([a["ok"] for a in reader.last_transport_attempts], [False, True])
        self.assertNotIn("fixture-secret", json.dumps(reader.last_transport_attempts))

    def test_persistent_transport_failure_is_bounded_and_authentication_never_retries(self):
        for error, attempts in ((http.client.RemoteDisconnected("fixture"), 2),
                                (urllib.error.HTTPError("fixture", 401, "auth", {}, None), 1),
                                (ValueError("invalid schema"), 1)):
            reader = ApiReader(api_key="fixture")
            with patch("urllib.request.urlopen", side_effect=error) as opened, patch("understand.time.sleep"):
                with self.assertRaises(type(error)):
                    reader._post([], json_mode=False)
            self.assertEqual(opened.call_count, attempts)
            self.assertEqual(len(reader.last_transport_attempts), attempts)

    def test_shared_tutor_recovers_at_transport_layer_and_retains_audit_trace(self):
        payload = json.dumps({"choices": [{"message": {"content": "我想先问清楚。"}}]}).encode()
        tutor = Tutor(ApiReader(api_key="fixture"))
        with patch("urllib.request.urlopen", side_effect=[http.client.RemoteDisconnected("fixture"), Response(payload)]), \
                patch("understand.time.sleep"):
            self.assertEqual(tutor.speak("题面"), "我想先问清楚。")
        self.assertEqual(len(tutor.last_generation_diagnostic["transport_attempts"]), 2)

    def run_fixture(self, directory, *, fail_at=None, tutor=False, max_turns=None, stopped=False):
        trainer = Trainer(out_dir=str(directory), use_api=False, use_think=False, gate_perception=True)
        control = TrainingControl()
        if stopped:
            control.stop()
        with patch.object(trainer, "_pipe", side_effect=lambda: Pipe(trainer, fail_at)), \
                patch.object(trainer, "_regrow", return_value={"summary": "offline fixture"}) as regrow, \
                patch("train.Tutor", EmptyTutor), patch("understand.ApiReader.available", new_callable=lambda: True), \
                contextlib.redirect_stdout(io.StringIO()):
            result = trainer.run(rounds=2, session_len=2, source="topics", strict=True, tutor=tutor,
                                 max_turns=max_turns, control=control)
        return result, regrow.call_count

    def test_zero_turn_failure_adds_no_sessions_rounds_or_growth_and_keeps_gate_truth(self):
        with tempfile.TemporaryDirectory() as tmp:
            result, grown = self.run_fixture(Path(tmp), tutor=True)
            self.assertFalse(result["ok"])
            self.assertEqual(result["turns_added"], 0)
            self.assertEqual(result["sessions_added"], 0)
            self.assertEqual(result["rounds_added"], 0)
            self.assertEqual(grown, 0)
            self.assertTrue(result["gate_perception"])
            self.assertIsNone(result["gate_observed_in_turn"])
            self.assertEqual(result["failure_diagnostic"]["stage"], "tutor_generation")

    def test_partial_session_counts_recorded_turn_without_claiming_completed_unit(self):
        with tempfile.TemporaryDirectory() as tmp:
            result, _ = self.run_fixture(Path(tmp), fail_at=2)
            self.assertEqual(result["turns_added"], 1)
            self.assertEqual(result["sessions_with_turns"], 1)
            self.assertEqual(result["sessions_added"], 0)
            self.assertEqual(result["rounds_added"], 0)
            self.assertFalse(result["training_complete"])

    def test_target_cap_and_early_user_stop_do_not_credit_requested_rounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            result, _ = self.run_fixture(Path(tmp), max_turns=6)
            self.assertEqual((result["turns_added"], result["sessions_added"], result["rounds_added"]), (6, 3, 1))
            self.assertTrue(result["ok"])
            result, grown = self.run_fixture(Path(tmp) / "stopped", stopped=True)
            self.assertFalse(result["ok"])
            self.assertEqual(result["failure"], "user_stopped")
            self.assertEqual((result["turns_added"], result["sessions_added"], result["rounds_added"], grown), (0, 0, 0, 0))

    def test_legacy_zero_credit_corrected_once_without_rewriting_original_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old = {"run_schema": 2, "run_id": "old_failure", "turns_added": 0, "failure": "tutor_generation_failed",
                   "sessions": 1, "rounds": 1}
            raw = json.dumps(old) + "\n"
            (root / "runs.jsonl").write_text(raw, encoding="utf-8")
            (root / "progress.json").write_text(json.dumps({"turns": 0, "sessions": 1, "rounds": 1}), encoding="utf-8")
            result, _ = self.run_fixture(root, max_turns=6)
            self.assertEqual((result["sessions"], result["rounds"]), (3, 1))
            self.assertTrue((root / "runs.jsonl").read_text(encoding="utf-8").startswith(raw))
            second, _ = self.run_fixture(root, max_turns=6)
            self.assertEqual((second["sessions"], second["rounds"]), (6, 2))
            self.assertEqual(len(second["legacy_zero_turn_corrections"]), 1)

    def test_reviewer_packet_separates_current_run_versions_and_stale_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "state/train").mkdir(parents=True)
            (root / "spec").mkdir()
            (root / "engine").mkdir()
            source = root / "engine/fixture.py"
            source.write_text("v1")
            (root / REGISTRY).write_text(json.dumps({"schema": 1, "issues": []}), encoding="utf-8")
            (root / "state/train/progress.json").write_text(json.dumps({"run_id": "new", "turns_added": 0,
                "requested_turns": 6, "failure": "tutor_generation_failed", "eval_schema": EVAL_SCHEMA}), encoding="utf-8")
            (root / "state/train/eval.jsonl").write_text(json.dumps({"eval_schema": EVAL_SCHEMA - 1,
                    "input_origin": {"run_id": "old"}}) + "\n", encoding="utf-8")
            (root / LIVE).write_text(json.dumps({"passed": True, "source_hashes": source_hashes(root), "cases": []}), encoding="utf-8")
            first = snapshot(root)
            self.assertEqual(first["current_schema_evaluations"], 0)
            self.assertEqual(first["latest_run_evaluations"], 0)
            self.assertTrue(first["latest_training"]["failure_observed"])
            self.assertTrue(first["artefacts"][1]["passed_for_current_source"])
            source.write_text("v2")
            self.assertIsNone(snapshot(root)["artefacts"][1]["passed_for_current_source"])
            self.assertEqual(first["development_credit"], 0)


if __name__ == "__main__":
    unittest.main()
