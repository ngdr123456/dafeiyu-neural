"""Regression for restart-driven growth; actual Pipeline plus isolated state."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from devlevel import DevLevel, ERROR_HIGH, ERROR_LOW
from pipeline import Pipeline
from markers import MarkerEngine


def state_hashes():
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (ROOT / "state").rglob("*") if p.is_file()}


class ContinuityTests(unittest.TestCase):
    def setUp(self):
        self.before = state_hashes()
        self.temp = tempfile.TemporaryDirectory(prefix="ego-continuity-")
        self.root = Path(self.temp.name)
        self.path = str(self.root / "devlevel.json")

    def tearDown(self):
        self.temp.cleanup()
        self.assertEqual(self.before, state_hashes(), "Real state changed")

    def pipeline(self):
        return Pipeline(ledger_path=str(self.root / "ledger.jsonl"),
                        character_path=str(self.root / "character.json"),
                        devlevel_path=self.path, carry_root=str(self.root),
                        gate_perception=True, use_api=False, use_render=False,
                        use_think=False, auto_audit=False)

    def test_real_pipeline_restart_does_not_grow(self):
        first = self.pipeline()
        for _ in range(24):
            first.turn("大家都这样，我也没办法。", "T08")
        self.assertTrue(first.devlevel.failed, "Actual mechanism must first fail")
        count = first.devlevel.equilibration
        level = first.devlevel.level
        for _ in range(3):
            restarted = self.pipeline()
            restarted.turn("大家都这样，我也没办法。", "T08")
            self.assertLessEqual(restarted.mech.e, ERROR_LOW)
            self.assertEqual(restarted.devlevel.equilibration, count)
            self.assertEqual(restarted.devlevel.level, level)
            self.assertTrue(restarted.devlevel.failed)

    def test_same_lifecycle_pressure_recovery_still_counts(self):
        dev = DevLevel(self.path, rules=[])
        dev.update({"e": ERROR_HIGH, "tension": 8, "tension_measured": True})
        dev.update({"e": ERROR_LOW, "tension": 8, "tension_measured": True})
        self.assertEqual(dev.equilibration, 1)

    def test_reobserved_failure_uses_current_tension(self):
        old = DevLevel(self.path, rules=[])
        old.update({"e": ERROR_HIGH, "tension": 8, "tension_measured": True})
        new = DevLevel(self.path, rules=[])
        new.update({"e": ERROR_LOW, "tension": 8, "tension_measured": True})
        self.assertEqual(new.equilibration, 0)
        new.update({"e": ERROR_HIGH, "tension": 0, "tension_measured": True})
        new.update({"e": ERROR_LOW, "tension": 8, "tension_measured": True})
        self.assertEqual(new.equilibration, 0)
        self.assertEqual(new.not_grown, 1)
        self.assertEqual(new.pending, 1)

    def test_legacy_state_and_history_are_preserved(self):
        legacy = ROOT / "state/development_legacy_20261006/devlevel.json"
        source = legacy if legacy.exists() else ROOT / "state/devlevel.json"
        data = json.loads(source.read_text(encoding="utf-8"))
        Path(self.path).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        dev = DevLevel(self.path, rules=[])
        dev.update({"e": ERROR_LOW, "tension": 8, "tension_measured": True})
        self.assertEqual(dev.level, data["level"])
        self.assertEqual(dev.equilibration, data["equilibration"])
        self.assertEqual(dev.history, data["history"])
        self.assertEqual(dev.failed, data["failed"])

    def test_meta_fallback_reports_no_invented_cause(self):
        rid, text = MarkerEngine().meta_response("你能解释这个陌生问题吗？")
        self.assertEqual(rid, "ASKED_ME_SOMETHING_I_LACK")
        self.assertEqual(text, "这个问题，我暂时没能给出可靠的回答。")


if __name__ == "__main__":
    unittest.main()
