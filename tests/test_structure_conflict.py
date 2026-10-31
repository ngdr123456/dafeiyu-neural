"""Synthetic conflict evidence; no human corrections or real state writes."""
import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.relation_learning import RelationLearning
from engine.structure_evidence import report
from tools.structure_scope_trial import state_hashes


class ConflictTests(unittest.TestCase):
    def setUp(self):
        self.before = state_hashes()
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "relations.json"
        self.learner = RelationLearning(self.path, offline=True)

    def tearDown(self):
        self.tmp.cleanup()
        self.assertEqual(self.before, state_hashes())

    def observe(self, raw, role="PROHIBITED", observer="fixture_author", occurrence=0, topic="T01"):
        start = raw.index("都是他们") if occurrence == 0 else raw.rindex("都是他们")
        return self.learner.observe(raw, start, start + 4, "blame_external", {"blame_external"},
                                    role, source="offline_fixture", observer=observer,
                                    turn=1, topic_id=topic)

    def form(self):
        for i in range(5):
            self.observe("不要说，都是他们害了项目%d。" % i)

    def test_identical_occurrence_disagreement_is_not_invented_as_new_structure(self):
        self.form()
        old = copy.deepcopy(self.learner.learner.data["structure_evidence"]["versions"][1])
        result = self.observe("不要说，都是他们害了项目0。", "ASSERTED", observer="other_fixture")
        conflict = result["feedback"]["structural_conflict"]
        self.assertEqual(conflict["observation"], "same_occurrence_conflicting_feedback")
        self.assertTrue(conflict["source_or_observer_differs"])
        self.assertEqual(conflict["old_rule"]["status"], "active")
        self.assertEqual(conflict["cause"], "unresolved")
        self.assertFalse(conflict["new_organizing_principle_formed"])
        self.assertEqual(result["status"], "candidate")
        self.assertEqual(report(self.learner.learner.data)["versions"][1], old)
        restarted = RelationLearning(self.path, offline=True)
        self.assertEqual(report(restarted.learner.data)["conflicts"], [conflict])
        self.assertEqual(report(restarted.learner.data)["comparisons"][-1]["verdict"], "counterevidence")

    def test_different_inputs_do_not_prove_context_or_observer_is_wrong(self):
        self.form()
        result = self.observe("不要说，都是他们害了新合同。", "ASSERTED", topic="T02")
        conflict = result["feedback"]["structural_conflict"]
        self.assertEqual(conflict["observation"], "different_inputs_same_context_conflicting_feedback")
        self.assertTrue(conflict["topic_label_differs"])
        self.assertFalse(conflict["source_or_observer_differs"])
        self.assertFalse(conflict["independent_semantic_review_verified"])
        self.assertEqual(conflict["development_credit"], 0)

    def test_one_input_two_occurrences_are_not_one_feedback_disagreement(self):
        # No extra cue or punctuation before occurrence 2, so the existing
        # representation merges the two spans despite their different positions.
        raw = "都是他们说的都是他们做的。"
        self.observe(raw, "QUOTED")
        result = self.observe(raw, "ASSERTED", occurrence=1)
        conflict = result["feedback"]["structural_conflict"]
        self.assertEqual(conflict["observation"], "different_occurrences_same_input_same_context")
        self.assertNotEqual(conflict["prior_evidence"][0]["span"], conflict["incoming"]["span"])

    def test_confirmation_replay_unknown_and_failed_save_do_not_make_false_conflicts(self):
        self.form()
        self.observe("不要说，都是他们害了项目0。")
        self.observe("不要说，都是他们害了新合同。", "UNKNOWN")
        self.assertEqual(report(self.learner.learner.data)["conflicts"], [])
        original = self.path.read_bytes()
        memory = copy.deepcopy(self.learner.learner.data)
        with patch("engine.relation_learning.atomic_json", side_effect=OSError("fixture disk failure")):
            with self.assertRaises(OSError):
                self.observe("不要说，都是他们害了新合同。", "ASSERTED")
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.learner.learner.data, memory)


if __name__ == "__main__":
    unittest.main()
