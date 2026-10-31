"""Exercise actual training records using a simulated API, never network."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from train import Trainer, load_topics
from pipeline import Pipeline
from input_provenance import training_origin, normalize
from understand import ApiReader


class Reviewer:
    available = True
    model = "offline_fixture"
    def read(self, raw, stem, spec):
        return ApiReader(api_key="")._parse_obj(
            {"intent": "ANSWER", "markers": [], "relations": []}, raw, spec, 0, {})


class FakeTutor:
    errors = []
    def __init__(self, *args):
        self._ad = type("Admin", (), {"reader": Reviewer()})()
    def speak(self, prompt, last):
        return "我还没想清楚这件事。"
    def judge(self, *args):
        return {"ok": True, "problem": "none"}


class Tests(unittest.TestCase):
    def test_authorship_and_tamper(self):
        item = {"text": "题面", "source": "topic_stem", "topic_id": "T01"}
        origin = training_origin(item, "生成的话", generated=True, model="fixture")
        self.assertEqual(origin["kind"], "tutor_generated")
        self.assertFalse(origin["independent_human_input_verified"])
        with self.assertRaises(ValueError):
            normalize(origin, "另一句话", "T01")
        with self.assertRaises(ValueError):
            normalize(origin, "生成的话", "T02")

    def test_actual_training_ledger_eval_and_session_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trainer = Trainer(out_dir=tmp, use_api=False, use_think=False, gate_perception=True)
            def pipe():
                p = Pipeline(ledger_path=trainer.ledger, character_path=trainer.character,
                             devlevel_path=str(root / "devlevel.json"), carry_root=tmp,
                             auto_audit=False, use_api=False, gate_perception=True)
                p.reader = Reviewer()
                return p
            with patch.object(trainer, "_pipe", pipe), patch("train.Tutor", FakeTutor), \
                    patch("understand.ApiReader.available", new_callable=lambda: True):
                result = trainer.run(rounds=1, session_len=2, source="topics", tutor=True,
                                     seed=1, strict=True)
            self.assertTrue(result["ok"])
            self.assertEqual(result["turns_added"], 6)
            rows = [json.loads(x) for x in Path(trainer.ledger).read_text(encoding="utf-8").splitlines()]
            evals = [json.loads(x) for x in Path(trainer.eval_file).read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(rows), 6)
            for row, ev in zip(rows, evals):
                self.assertEqual(row["input_origin"], ev["input_origin"])
                self.assertEqual(row["topic_id"], row["input_origin"]["topic_id"])
                self.assertEqual(ev["input_source"], "tutor_generated")
                self.assertEqual(ev["mech"], row["mech"])
                self.assertEqual(row["input_origin"]["run_id"], result["run_id"])
            run = json.loads((root / "runs.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(run["turns_added"], 6)
            self.assertEqual(run["sessions"], 3)

    def test_strict_unavailable_stops_before_any_turn(self):
        with tempfile.TemporaryDirectory() as tmp:
            trainer = Trainer(out_dir=tmp, use_api=False, use_think=False, gate_perception=False)
            p = type("Pipe", (), {"api_enabled": False, "thinker": None})()
            with patch.object(trainer, "_pipe", return_value=p):
                result = trainer.run(session_len=2, source="topics", strict=True)
            self.assertFalse(result["ok"])
            self.assertEqual(result["turns_added"], 0)
            self.assertEqual(result["failure"], "pipeline_api_unavailable")

    def test_relation_feedback_keeps_input_origin(self):
        from relation_learning import RelationLearning
        with tempfile.TemporaryDirectory() as tmp:
            raw = "不要说了，都是他们害的。"
            origin = training_origin({"text": "题面", "source": "topic_stem", "topic_id": "T01"},
                                     raw, generated=True, model="fixture")
            learner = RelationLearning(str(Path(tmp) / "relations.json"))
            start = raw.index("都是他们")
            learner.observe(raw, start, start + 4, "blame_external", {"blame_external"},
                            "PROHIBITED", source="external_reviewer", observer="fixture_reviewer",
                            turn=1, topic_id="T01", input_origin=origin)
            case = learner.learner.data["structure_evidence"]["cases"][0]
            self.assertEqual(case["input_origin"], origin)
            self.assertEqual(case["source"], "external_reviewer")
            self.assertEqual(case["input_origin"]["kind"], "tutor_generated")

    def test_empty_judge_response_is_failure_with_cause(self):
        from train import Tutor
        reader = type("Reader", (), {"available": True,
            "_post": lambda *_args, **_kwargs: ({"choices": [{"finish_reason": "length",
                "message": {"content": ""}}], "usage": {"completion_tokens": 4096}}, 0)})()
        result = Tutor(reader).judge("输入", "输出", {"w": 1})
        self.assertFalse(result["ok"])
        self.assertIn("JSONDecodeError", result["error"])
        self.assertEqual(result["api_diagnostic"]["finish_reason"], "length")
        self.assertEqual(result["api_diagnostic"]["content_chars"], 0)

    def test_desktop_failed_evaluation_is_not_a_clean_judgment(self):
        import training_studio
        from train import EVAL_SCHEMA
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "state/train"
            destination.mkdir(parents=True)
            records = [{"eval_schema": EVAL_SCHEMA, "tutor": {"ok": True, "problem": "none"}},
                       {"eval_schema": EVAL_SCHEMA, "tutor": {"ok": False, "problem": "none"}}]
            (destination / "eval.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
            studio = training_studio.Studio.__new__(training_studio.Studio)
            with patch.object(training_studio, "_ROOT", tmp):
                page = studio._tutor_page()
            self.assertIn("有效判定 1 条｜失败或无判定 1 条", page)

    def test_topic_ids_kept(self):
        self.assertTrue(all(item.get("topic_id") for item in load_topics()))


if __name__ == "__main__":
    unittest.main()
