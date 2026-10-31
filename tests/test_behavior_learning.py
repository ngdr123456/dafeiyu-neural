import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from behavior_learning import BehaviorLearning
from development_baseline import initialize
from devlevel import DevLevel, ERROR_HIGH, ERROR_LOW
from pipeline import Pipeline


def hashes():
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (ROOT / "state").rglob("*") if p.is_file()}


class LearningTests(unittest.TestCase):
    def setUp(self):
        self.before = hashes()
        self.tmp = tempfile.TemporaryDirectory(prefix="ego-learning-")
        self.root = Path(self.tmp.name)
        self.state = self.root / "state"
        self.state.mkdir()

    def tearDown(self):
        self.tmp.cleanup()
        self.assertEqual(self.before, hashes())

    def learner(self):
        return BehaviorLearning(self.state / "behavior_rules.json",
                                {"ASK_MUST", "ASK_DETAIL", "REFLECT"})

    def test_distinct_future_validation_and_revision(self):
        learner = self.learner()
        context = learner.context(["over_intention"], "ASK_MUST")
        for _ in range(20):
            learner.observe(context, "REFLECT", "同一条输入", 1)
        self.assertIsNone(learner.predict(context))
        for i in range(4):
            learner.observe(context, "REFLECT", "新的输入%d" % i, i + 2)
        self.assertEqual(learner.predict(context), "REFLECT")
        old_events = json.loads(json.dumps(learner.data["events"]))
        learner.observe(context, "ASK_DETAIL", "反例", 7)
        self.assertIsNone(learner.predict(context), "Counterexample must withdraw active rule")
        self.assertEqual(learner.data["rules"][learner.sid(context)]["revision"], 2)
        self.assertEqual(learner.data["events"][:len(old_events)], old_events)
        self.assertTrue(any(e["kind"] == "retired" for e in learner.data["events"]))
        self.assertIsNone(self.learner().predict(context))

    def test_unknown_action_cannot_enter_library(self):
        learner = self.learner()
        with self.assertRaises(ValueError):
            learner.observe(learner.context([], "ASK_MUST"), "DIAGNOSE_PERSON", "输入", 1)
        self.assertFalse(learner.path.exists())

    def test_baseline_preserves_bytes_and_never_uses_pressure_as_growth(self):
        archive = ROOT / "state/development_legacy_20261006/devlevel.json"
        legacy = (archive if archive.exists() else ROOT / "state/devlevel.json").read_bytes()
        (self.state / "devlevel.json").write_bytes(legacy)
        initialized = initialize(self.root)
        self.assertEqual(initialized["level"], "I-3")
        self.assertEqual(initialized["equilibration"], 0)
        self.assertEqual((self.state / "development_legacy_20261006/devlevel.json").read_bytes(), legacy)
        dev = DevLevel(str(self.state / "devlevel_verified.json"), rules=[])
        for _ in range(10):
            dev.update({"e": ERROR_HIGH, "tension": 8, "tension_measured": True})
            dev.update({"e": ERROR_LOW, "tension": 8, "tension_measured": True})
        self.assertEqual(dev.equilibration, 0)
        self.assertEqual(dev.level, "I-3")
        canonical = (self.state / "devlevel_verified.json").read_bytes()
        initialize(self.root)
        self.assertEqual(canonical, (self.state / "devlevel_verified.json").read_bytes())
        self.assertTrue(json.loads((self.state / "devlevel.json").read_text(encoding="utf-8"))["display_projection"])
        via_display = DevLevel(str(self.state / "devlevel.json"), rules=[])
        self.assertTrue(via_display.verified)
        self.assertEqual(via_display.path, str(self.state / "devlevel_verified.json"))

    def test_corrupt_baseline_fails_without_legacy_fallback(self):
        (self.state / "devlevel_verified.json").write_text("{", encoding="utf-8")
        with self.assertRaises(ValueError):
            DevLevel(str(self.state / "devlevel_verified.json"), rules=[])
        (self.state / "devlevel_verified.json").unlink()
        (self.state / "devlevel.json").write_text(
            json.dumps({"display_projection": True, "level": "I-3/4"}), encoding="utf-8")
        with self.assertRaises(ValueError):
            DevLevel(str(self.state / "devlevel_verified.json"), rules=[])

    def test_historical_seed_cannot_restore_unverified_level(self):
        # Select an actual archived-level row, rather than the live ledger tail.
        # New verified experiences are expected to change that tail.
        rows = [json.loads(line) for line in (ROOT / "state/train/ledger.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        historical = [row for row in rows if (row.get("mech") or {}).get("dev", {}).get("level") == "I-3/4"]
        self.assertTrue(historical, "Missing historical fixture")
        (self.state / "ledger.jsonl").write_text(json.dumps(historical[-1], ensure_ascii=False) + "\n", encoding="utf-8")
        pipeline = Pipeline(ledger_path=str(self.state / "ledger.jsonl"),
                            character_path=str(self.state / "character.json"),
                            devlevel_path=str(self.state / "devlevel_verified.json"),
                            carry_root=str(self.root), gate_perception=True,
                            use_api=False, use_think=False, use_render=False, auto_audit=False)
        self.assertEqual(pipeline._last_mech["dev"]["level"], "I-3")
        self.assertEqual(pipeline._last_mech["dev"]["equil"], 0)
        self.assertEqual(pipeline._last_mech["historical_dev"]["level"], "I-3/4")
        self.assertEqual(pipeline.devlevel.self_rules(), {"R1"})

    def test_real_pipeline_learns_and_carries_across_sessions(self):
        def pipeline():
            return Pipeline(ledger_path=str(self.state / "ledger.jsonl"),
                            character_path=str(self.state / "character.json"),
                            devlevel_path=str(self.state / "devlevel_verified.json"),
                            carry_root=str(self.root), gate_perception=True,
                            use_api=False, use_think=False, use_render=False, auto_audit=False)
        pipeline_one = pipeline()
        for noun in ("项目", "合同", "冠军", "资格", "机会"):
            pipeline_one.turn("我非拿下这个%s不可。" % noun, "T08")
        self.assertTrue(any(r["status"] == "active"
                            for r in pipeline_one.behavior_learning.data["rules"].values()),
                        pipeline_one.behavior_learning.data)
        restarted = pipeline()
        outcome = restarted.turn("我非拿下这个奖项不可。", "T08")
        rows = [json.loads(line) for line in (self.state / "ledger.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertTrue(any("经历规则：" in note for note in rows[-1]["notes"]),
                        (rows[-1]["notes"], restarted.behavior_learning.data["rules"]))
        self.assertEqual(outcome.behavior, "REFLECT")
        self.assertEqual(restarted.devlevel.equilibration, 0)
        self.assertEqual(restarted.devlevel.level, "I-3")

    def test_learned_action_cannot_override_over_intention_boundary(self):
        pipeline = Pipeline(ledger_path=str(self.state / "ledger.jsonl"),
                            character_path=str(self.state / "character.json"),
                            devlevel_path=str(self.state / "devlevel_verified.json"),
                            carry_root=str(self.root), gate_perception=True,
                            use_api=False, use_think=False, use_render=False, auto_audit=False)
        learner = pipeline.behavior_learning
        context = learner.context(["over_intention"], "ASK_MUST")
        for i in range(5):
            learner.observe(context, "ASK_DETAIL", "测试反例%d" % i, i)
        self.assertEqual(learner.predict(context), "ASK_DETAIL")
        result = pipeline.turn("我非拿下这个奖项不可。", "T08")
        self.assertEqual(result.behavior, "REFLECT")
        self.assertIsNone(learner.predict(context))
        self.assertTrue(any(event["kind"] == "retired" for event in learner.data["events"]))


if __name__ == "__main__":
    unittest.main()
