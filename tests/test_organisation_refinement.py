"""Executable candidate formation, preservation and falsification, all synthetic."""
import copy
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.relation_learning import RelationLearning
from engine.structure_evidence import report
from engine.organisation_refinement import observe_ownership, predict
from tools.structure_scope_trial import state_hashes


class RefinementTests(unittest.TestCase):
    def setUp(self):
        self.before = state_hashes()
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "relations.json"
        self.learner = RelationLearning(self.path, offline=True)

    def tearDown(self):
        self.tmp.cleanup()
        self.assertEqual(self.before, state_hashes())

    def raw(self, quoted, tail):
        return ('他写下“不要说”，' if quoted else '不要说，') + '都是他们害了' + tail + '。'

    def observe(self, quoted, tail, role=None):
        raw = self.raw(quoted, tail)
        start = raw.index("都是他们")
        return self.learner.observe(raw, start, start + 4, "blame_external", {"blame_external"},
                                    role or ("ASSERTED" if quoted else "PROHIBITED"),
                                    source="offline_fixture", observer="synthetic_author", turn=1)

    def form(self):
        for i in range(5):
            self.observe(False, "项目%d" % i)
        for i in range(3):
            self.observe(True, "合同%d" % i)
        return report(self.learner.learner.data)["organisation_candidates"][0]

    def test_old_collision_new_ownership_graph_and_experience_selected_labels(self):
        left, right = self.raw(False, "计划"), self.raw(True, "计划")
        contexts = [self.learner.context(raw, raw.index("都是他们"), raw.index("都是他们") + 4,
                                         "blame_external", {"blame_external"}) for raw in (left, right)]
        self.assertEqual(contexts[0], contexts[1])
        graph = observe_ownership(right, right.index("都是他们"))
        self.assertEqual(right[slice(*graph["cue_span"])], graph["cue_text"])
        self.assertEqual(right[slice(*graph["quote_span"])], graph["quote_text"])
        candidate = self.form()
        self.assertEqual(candidate["branches"], {"False": "PROHIBITED", "True": "ASSERTED"})
        self.assertEqual(candidate["status"], "candidate")
        self.assertEqual(candidate["old_competence_losses"], [])
        for raw, role in ((left, "PROHIBITED"), (right, "ASSERTED")):
            case = {"sid": candidate["sid"], "organisation_observation": observe_ownership(raw, raw.index("都是他们"))}
            self.assertEqual(predict(candidate, case), role)
        # Syntax is observation only: reversing supplied labels reverses the
        # candidate, instead of silently hardcoding 'quote means assertion'.
        other = RelationLearning(Path(self.tmp.name) / "other.json", offline=True)
        for quoted, count in ((False, 5), (True, 3)):
            for i in range(count):
                raw = self.raw(quoted, "另项目%d" % i)
                start = raw.index("都是他们")
                other.observe(raw, start, start + 4, "blame_external", {"blame_external"},
                              "NEGATED" if quoted else "QUOTED", source="offline_fixture",
                              observer="synthetic_author", turn=1)
        self.assertEqual(report(other.learner.data)["organisation_candidates"][0]["branches"],
                         {"False": "QUOTED", "True": "NEGATED"})

    def test_unseen_validation_restart_and_no_live_override(self):
        candidate = self.form()
        original = copy.deepcopy(candidate)
        for quoted in (False, True):
            for i in range(2):
                self.observe(quoted, "后续比赛%d" % i)
        restarted = RelationLearning(self.path, offline=True)
        new = report(restarted.learner.data)["organisation_candidates"][0]
        self.assertEqual(new["status"], "locally_validated_candidate")
        self.assertEqual(new["branches"], original["branches"])
        self.assertEqual(new["fingerprint"], original["fingerprint"])
        self.assertTrue(all(len(x) == 2 for x in new["validation_inputs"].values()))
        self.assertTrue(set(new["formation_inputs"]).isdisjoint(
            new["validation_inputs"]["False"] + new["validation_inputs"]["True"]))
        self.assertFalse(new["enabled_in_pipeline"])
        self.assertFalse(new["independent_semantic_review_verified"])
        self.assertEqual(new["development_credit"], 0)

    def test_later_counterexample_rejects_without_refitting_or_erasing(self):
        old = self.form()
        self.observe(True, "新合同", role="NEGATED")
        new = report(self.learner.learner.data)["organisation_candidates"][0]
        self.assertEqual(new["status"], "rejected")
        self.assertEqual(new["branches"], old["branches"])
        self.assertEqual(new["fingerprint"], old["fingerprint"])
        self.assertEqual(len(new["counterevidence"]), 1)

    def test_replays_unsupported_quotes_and_conflicting_annotation_cannot_validate(self):
        self.form()
        self.observe(True, "合同0")
        self.observe(False, "项目0")
        self.assertEqual(report(self.learner.learner.data)["organisation_candidates"][0]["validation_inputs"],
                         {"False": [], "True": []})
        unsupported = "他写下「不要说」，都是他们害了合同。"
        self.assertFalse(observe_ownership(unsupported, unsupported.index("都是他们"))["supported"])
        self.observe(False, "项目0", role="ASSERTED")
        candidate = report(self.learner.learner.data)["organisation_candidates"][0]
        self.assertEqual(candidate["status"], "rejected")
        self.assertTrue(candidate["counterevidence"])

    def test_old_memory_without_new_observation_cannot_be_migrated_by_guessing(self):
        self.form()
        memory = copy.deepcopy(self.learner.learner.data)
        for case in memory["structure_evidence"]["cases"]:
            case.pop("organisation_observation", None)
        self.assertEqual(report(memory)["organisation_candidates"], [])

    def test_quote_variants_nested_owner_and_no_cue(self):
        for raw in ('他说"不要说"，都是他们害的。', '他说“她写了“不要说””，都是他们害的。'):
            graph = observe_ownership(raw, raw.index("都是他们"))
            self.assertTrue(graph["supported"])
            self.assertTrue(graph["features"]["cue_in_completed_quote"])
            self.assertEqual(raw[slice(*graph["cue_span"])], "不要说")
        raw = '他说“不要说，都是他们害的。'
        self.assertFalse(observe_ownership(raw, raw.index("都是他们"))["supported"])
        raw = '都是他们害的。'
        graph = observe_ownership(raw, 0)
        self.assertFalse(graph["features"]["cue_in_completed_quote"])
        self.assertIsNone(graph["cue_span"])

    def test_counterexample_elsewhere_in_frozen_mapping_withdraws_entire_candidate(self):
        for i in range(5):
            raw = "不能说，都是他们害了背景%d。" % i
            start = raw.index("都是他们")
            self.learner.observe(raw, start, start + 4, "blame_external", {"blame_external"},
                                 "NEGATED", source="offline_fixture", observer="synthetic_author", turn=1)
        formed = self.form()
        self.assertEqual(len(formed["old_mapping"]), 2)
        for quoted in (False, True):
            for i in range(2):
                self.observe(quoted, "后来%d" % i)
        before = report(self.learner.learner.data)["organisation_candidates"][0]
        self.assertEqual(before["status"], "locally_validated_candidate")
        raw = "不能说，都是他们害了另情境反例。"
        start = raw.index("都是他们")
        self.learner.observe(raw, start, start + 4, "blame_external", {"blame_external"},
                             "ASSERTED", source="offline_fixture", observer="synthetic_author", turn=1)
        after = report(self.learner.learner.data)["organisation_candidates"][0]
        self.assertEqual(after["status"], "rejected")
        self.assertEqual(after["fingerprint"], before["fingerprint"])
        self.assertEqual(after["counterevidence"], [len(self.learner.learner.data["structure_evidence"]["cases"])])

    def test_latest_base_does_not_resurrect_withdrawn_other_context(self):
        def background(tail, role):
            raw = "不能说，都是他们害了" + tail + "。"
            start = raw.index("都是他们")
            return self.learner.observe(raw, start, start + 4, "blame_external", {"blame_external"},
                                        role, source="offline_fixture", observer="synthetic_author", turn=1)
        for i in range(5):
            background("旧能力%d" % i, "NEGATED")
        background("撤回旧能力", "ASSERTED")
        candidate = self.form()
        self.assertEqual(len(candidate["old_mapping"]), 1)
        self.assertGreater(candidate["base_version"], 0)


if __name__ == "__main__":
    unittest.main()
