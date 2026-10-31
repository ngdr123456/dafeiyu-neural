import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.relation_learning import RelationLearning
from engine.structure_evidence import report, fingerprint
from tools.structure_scope_trial import state_hashes


class StructureEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.before = state_hashes()
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "relations.json"
        self.learning = RelationLearning(self.path, offline=True)

    def tearDown(self):
        self.temp.cleanup()
        self.assertEqual(self.before, state_hashes())

    def observe(self, text, role="PROHIBITED", topic="training"):
        raw = "不要说，都是他们害了" + text + "。"
        start = raw.index("都是他们")
        return self.learning.observe(raw, start, start + 4, "blame_external", {"blame_external"},
                                     role, source="offline_fixture", observer="synthetic_fixture_author",
                                     turn=1, topic_id=topic)

    def consolidate(self):
        for i in range(5):
            self.observe("项目" + str(i))

    def test_candidates_counts_restart_and_pressure_do_not_change_version(self):
        for i in range(4):
            self.observe("项目" + str(i))
        self.assertEqual(len(self.learning.learner.data["structure_evidence"]["versions"]), 1)
        self.observe("项目4")
        versions = copy.deepcopy(self.learning.learner.data["structure_evidence"]["versions"])
        resumed = RelationLearning(self.path, offline=True)
        resumed.learner.data["pressure"] = 0.01
        resumed.learner.data["stable_channel_count"] = 10000
        self.assertEqual(resumed.learner.data["structure_evidence"]["versions"], versions)
        self.observe("新输入")
        self.assertEqual(self.learning.learner.data["structure_evidence"]["versions"], versions)

    def test_formation_excluded_future_transfer_and_provenance_not_independence(self):
        self.consolidate()
        first = report(self.learning.learner.data)["comparisons"][0]
        self.assertEqual(first["verdict"], "no_future_evidence")
        self.assertEqual(first["future_input_count"], 0)
        self.observe("合同", topic="T01")
        self.observe("比赛", topic="T02")
        result = report(self.learning.learner.data)["comparisons"][0]
        self.assertEqual(result["future_input_count"], 2)
        self.assertEqual(result["improvements"], 2)
        self.assertTrue(result["cross_topic_labels_observed"])
        self.assertFalse(result["independent_semantic_review_verified"])
        self.assertEqual(result["development_credit"], 0)
        self.assertEqual(result["source_declarations"], ["offline_fixture"])
        self.assertTrue(all(c["old_prediction"] == "UNKNOWN" for c in result["future"]))

    def test_withdrawal_preserves_old_snapshot_and_reports_lost_competence(self):
        self.consolidate()
        old = copy.deepcopy(self.learning.learner.data["structure_evidence"]["versions"][1])
        self.observe("新合同", role="ASSERTED", topic="T03")
        result = report(self.learning.learner.data)
        self.assertEqual(result["versions"][1], old)
        comparison = result["comparisons"][-1]
        self.assertEqual(comparison["verdict"], "counterevidence")
        self.assertGreater(comparison["losses"], 0)
        self.assertTrue(any(not c["retained"] for c in comparison["retention"]))
        for version in result["versions"]:
            self.assertEqual(version["fingerprint"], fingerprint(version["mapping"]))

    def test_replay_and_same_original_in_different_topic_are_not_transfer(self):
        self.consolidate()
        self.observe("项目0", topic="new_topic")
        result = report(self.learning.learner.data)["comparisons"][0]
        self.assertEqual(result["future_input_count"], 0)
        self.assertFalse(result["cross_topic_labels_observed"])

    def test_frozen_comparison_does_not_train_or_change_memory(self):
        self.consolidate()
        self.observe("另一个项目", topic="T01")
        before = self.path.read_bytes()
        memory = copy.deepcopy(self.learning.learner.data)
        self.assertEqual(report(memory), report(memory))
        self.assertEqual(memory, self.learning.learner.data)
        self.assertEqual(before, self.path.read_bytes())
        tampered = copy.deepcopy(memory)
        tampered["structure_evidence"]["versions"][1]["mapping"]["fake"] = "ASSERTED"
        with self.assertRaises(ValueError):
            report(tampered)


if __name__ == "__main__":
    unittest.main()
