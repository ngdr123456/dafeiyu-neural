"""Test evidence integrity and rejection, NOT assert a good psychological model."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.structure_scope_trial import ClauseScopeCandidate, evaluate, state_hashes, verdict


class TrialTests(unittest.TestCase):
    def test_occurrences_have_exact_offsets_and_independent_negation(self):
        raw = "我没说都是他们害的，但是都是他们害的。"
        result = ClauseScopeCandidate().inspect(raw)
        self.assertTrue(result["fired"])
        nodes = [n for n in result["nodes"] if n["text"] == "都是他们"]
        self.assertEqual([n["negated"] for n in nodes], [True, False])
        for node in result["nodes"]:
            self.assertEqual(raw[node["start"]:node["end"]], node["text"])

    def test_hard_visibility_and_counterexample_preserved(self):
        self.assertEqual(ClauseScopeCandidate(set()).inspect("都是他们害的。")["nodes"], [])
        for raw in ("都怪我，都是他们害的。", "都怪他们。我也有责任。"):
            result = ClauseScopeCandidate().inspect(raw)
            self.assertFalse(result["fired"])
            self.assertEqual(result["reason"], "whole_input_counterexample")

    def test_failure_and_missing_independence_block_acceptance(self):
        self.assertEqual(verdict(True, [], ["counterexample"], True, True, True), "rejected")
        self.assertEqual(verdict(True, [], [], True, True, True), "external_review_required")
        self.assertEqual(verdict(True, [], [], True, False, True, True), "rejected")

    def test_reproducible_falsification_and_no_real_state_write(self):
        before = state_hashes()
        challenges = json.loads((ROOT / "spec/结构作用域挑战_20261006.json").read_text(encoding="utf-8"))
        result = evaluate(challenges)
        self.assertTrue(result["discovery_fixed"])
        self.assertEqual(result["historical_target_regressions"], [])
        self.assertEqual(result["challenge_errors"], ["C06", "C07"])
        self.assertEqual(result["verdict"], "rejected")
        self.assertEqual(result["development_credit"], 0)
        self.assertFalse(result["independently_reviewed"])
        self.assertEqual(before, state_hashes())


if __name__ == "__main__":
    unittest.main()
