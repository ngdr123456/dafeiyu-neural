import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.relation_learning import RelationLearning
from tools.structure_scope_trial import state_hashes

MARKER = "blame_external"
PHRASE = "都是他们"


def span(raw):
    start = raw.index(PHRASE)
    return start, start + len(PHRASE)


class RelationTests(unittest.TestCase):
    def setUp(self):
        self.before = state_hashes()
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "relations.json"
        self.learning = RelationLearning(self.path, offline=True)

    def tearDown(self):
        self.temp.cleanup()
        self.assertEqual(self.before, state_hashes())

    def observe(self, raw, role="PROHIBITED", source="offline_fixture", observer="fixture_author"):
        return self.learning.observe(raw, *span(raw), MARKER, {MARKER}, role,
                                     source=source, observer=observer, turn=1)

    def test_formation_validation_restart_and_reward_prediction_error(self):
        for i in range(5):
            raw = f"不要说，都是他们害了项目{i}。"
            event = self.observe(raw)
            if i == 0:
                self.assertIsNone(event["feedback"]["prediction_error"])
            else:
                self.assertGreater(event["feedback"]["prediction_error"], 0)
            self.assertEqual(event["status"], "active" if i == 4 else "candidate")
        resumed = RelationLearning(self.path, offline=True)
        raw = "不要说，都是他们害了另一项工作。"
        self.assertEqual(resumed.predict(raw, *span(raw), MARKER, {MARKER})["role"], "PROHIBITED")
        event = self.observe(raw, "ASSERTED")
        self.assertTrue(event["feedback"]["weakened"])
        self.assertLess(event["feedback"]["prediction_error"], 0)
        self.assertEqual(event["revision"], 2)
        self.assertEqual(event["status"], "candidate")
        self.assertEqual(next(iter(resumed.learner.data["rules"].values()))["revision"], 1)
        events = json.loads(self.path.read_text(encoding="utf-8"))["events"]
        self.assertTrue(any(e["kind"] == "retired" for e in events))
        self.assertTrue(all(e["feedback"]["development_credit"] == 0 for e in events))

    def test_duplicate_and_self_feedback_do_not_consolidate(self):
        raw = "不要说，都是他们害的。"
        self.observe(raw)
        self.assertEqual(self.observe(raw)["kind"], "duplicate")
        original = self.path.read_bytes()
        self.assertEqual(self.observe(raw + " 新情境", "UNKNOWN")["kind"], "undetermined")
        self.assertEqual(self.path.read_bytes(), original)
        with self.assertRaises(ValueError):
            self.observe(raw, observer="self")
        self.assertEqual(self.learning.predict(raw, *span(raw), MARKER, {MARKER})["role"], "UNKNOWN")

    def test_visibility_precedes_learning_and_unknown_is_not_assertion(self):
        raw = "都是他们害的。"
        before = self.path.exists()
        result = self.learning.observe(raw, *span(raw), MARKER, set(), "ASSERTED",
                                       source="offline_fixture", observer="test", turn=1)
        self.assertEqual(result["kind"], "blocked")
        self.assertEqual(self.path.exists(), before)
        self.assertIsNone(self.learning.predict(raw, *span(raw), MARKER, set())["evidence"])

    def test_simulation_cannot_be_used_as_live_consolidation(self):
        raw = "不要说，都是他们害的。"
        for i in range(5):
            self.observe(raw + str(i))
        live = RelationLearning(self.path)
        self.assertEqual(live.predict(raw, *span(raw), MARKER, {MARKER})["role"], "UNKNOWN")
        with self.assertRaises(ValueError):
            live.observe(raw, *span(raw), MARKER, {MARKER}, "PROHIBITED",
                         source="offline_fixture", observer="test", turn=1)
        unrelated = Path(self.temp.name) / "behavior_rules.json"
        original = '{"schema":1,"kind":"realization_fallback_habits_not_development","rules":{},"events":[]}'
        unrelated.write_text(original, encoding="utf-8")
        with self.assertRaises(ValueError):
            RelationLearning(unrelated)
        self.assertEqual(unrelated.read_text(encoding="utf-8"), original)

    def test_context_is_relation_not_whole_sentence_and_feedback_is_traceable(self):
        raw = "不要说，都是他们害了这份合同。"
        event = self.observe(raw)
        other = "不要说，都是他们害了那场比赛。"
        self.assertEqual(self.learning.context(raw, *span(raw), MARKER, {MARKER}),
                         self.learning.context(other, *span(other), MARKER, {MARKER}))
        feedback = event["feedback"]
        self.assertEqual(raw[slice(*feedback["span"])], feedback["evidence"])
        with self.assertRaises(ValueError):
            self.learning.context(raw, 0, 3, MARKER, {MARKER})

    def test_live_intake_accepts_explicit_corrections_without_inventing_them(self):
        live = RelationLearning(self.path)
        # Synthetic interface test: these are NOT actual human corrections.
        for i in range(5):
            raw = f"不能说，都是他们害了计划{i}。"
            live.observe(raw, *span(raw), MARKER, {MARKER}, "PROHIBITED",
                         source="user_correction", observer="synthetic_interface_test", turn=i)
        raw = "不能说，都是他们害了新计划。"
        self.assertEqual(live.predict(raw, *span(raw), MARKER, {MARKER})["role"], "PROHIBITED")

    def test_failed_commit_does_not_leave_rule_without_feedback_or_memory_ahead(self):
        self.observe("不要说，都是他们害了旧项目。")
        original = self.path.read_bytes()
        original_memory = json.loads(json.dumps(self.learning.learner.data))
        with patch("engine.relation_learning.atomic_json", side_effect=OSError("simulated disk failure")):
            with self.assertRaises(OSError):
                self.observe("不要说，都是他们害了新项目。")
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.learning.learner.data, original_memory)
        self.assertTrue(all("feedback" in e for e in self.learning.learner.data["events"]))


if __name__ == "__main__":
    unittest.main()
