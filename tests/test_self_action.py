"""Own failure must change a later real Pipeline attempt without certifying meaning."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from pipeline import Pipeline
from think import Thinker
from test_content_fidelity import Reader, verdict
from input_provenance import digest
from self_action import fingerprint, prior_tasks, receipt, basis

RAW = "押金还没退，我前面说由谁收着？"
BAD = "我这边没有任何可依据的东西。"
GOOD = "按你之前说的，押金由李老师收着。"


def origin(raw, **extra):
    return dict(schema=1, kind="interactive_input", input_sha256=digest(raw),
                topic_id=None, independent_human_input_verified=False, **extra)


def pipe(root, reader=None, *, enabled=True):
    p = Pipeline(ledger_path=str(root / "state/ledger.jsonl"),
                 character_path=str(root / "state/character.json"),
                 carry_root=str(root), auto_audit=False, gate_perception=False,
                 use_self_action=enabled)
    if reader is not None:
        p.thinker = Thinker(reader)
    return p


def failed_history(root):
    p = pipe(root)
    raw = "押金由李老师收着。"
    p.turn(raw, input_origin=origin(raw))
    p.thinker = Thinker(Reader([BAD, BAD], [
        verdict("REJECT", problem="ignoring_evidence", text=BAD)] * 2))
    result = p.turn(RAW, input_origin=origin(RAW))
    return p, result


class OwnAction(unittest.TestCase):
    def test_expectation_precedes_generation_real_operations_do_not_certify_semantics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p, failed = failed_history(root)
            reader = Reader([BAD, GOOD], [verdict("PASS")])
            p = pipe(root, reader)
            result = p.turn(RAW, input_origin=origin(RAW))
            trace = result.self_action
            self.assertEqual(trace["plan"], "REVISE_OWN_BLOCKED_RESPONSE")
            self.assertEqual(trace["prior"][0]["goal_id"], failed.self_action["goal"]["id"])
            self.assertEqual(trace["attempts"][0]["prior_retry"]["text"], BAD)
            self.assertFalse(trace["attempts"][0]["accepted"])
            self.assertEqual(result.output, GOOD)
            self.assertEqual(trace["procedure_status"], "PERMITTED")
            self.assertEqual(trace["outcome"]["semantic_goal_fit"], "UNKNOWN")
            self.assertEqual(trace["speech_action"]["actual"], "UNCLASSIFIED")
            self.assertTrue(trace["expectation"]["declared_before_generation"])
            self.assertEqual(sum(is_json for is_json, _ in reader.messages), 1)
            self.assertIn("REVISE_OWN_BLOCKED_RESPONSE", reader.messages[0][1][1]["content"])
            self.assertEqual(p.ledger.effective_entries[-1].self_action, trace)
            self.assertEqual(trace["receipt_sha256"], receipt(trace))
            self.assertEqual(trace["development_credit"], 0)
            self.assertFalse(trace["subjective_reward_verified"])
            selected = next(op for op in trace["operations"] if op["operation"] == "SELECT_PIPELINE_RETURN_TEXT")
            self.assertFalse(selected["external_delivery_verified"])

    def test_ablation_changes_actual_selected_output_with_identical_committed_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            failed_history(root)
            enabled = pipe(root, Reader([BAD, GOOD], [verdict("PASS")]))
            disabled = pipe(root, Reader([BAD], [verdict("PASS")]), enabled=False)
            # Both instances load exactly the same on-disk history before either acts.
            self.assertEqual(enabled.ledger.entries[-1].to_dict(), disabled.ledger.entries[-1].to_dict())
            active = enabled.turn(RAW, input_origin=origin(RAW))
            absent = disabled.turn(RAW, input_origin=origin(RAW))
            self.assertEqual(active.output, GOOD)
            self.assertEqual(absent.output, BAD)
            self.assertIsNone(absent.self_action)

    def test_second_attempt_can_reconsider_old_opinion_then_retires_retry_pressure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            failed_history(root)
            p = pipe(root, Reader([BAD, BAD], [verdict("PASS")]))
            reconsidered = p.turn(RAW, input_origin=origin(RAW))
            self.assertEqual(reconsidered.output, BAD)
            self.assertEqual(reconsidered.self_action["procedure_status"], "PERMITTED")
            p = pipe(root, Reader([BAD], [verdict("PASS")]))
            later = p.turn(RAW, input_origin=origin(RAW))
            self.assertEqual(later.self_action["plan"], "RESPOND_TO_CURRENT_INPUT")
            self.assertEqual(len(later.self_action["attempts"]), 1)
            self.assertEqual(later.self_action["outcome"]["semantic_goal_fit"], "UNKNOWN")

    def test_new_sources_and_distinct_input_reopen_instead_of_blacklisting_words(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p, _ = failed_history(root)
            fresh = "更正：押金由周老师收着。"
            p.thinker = None
            p.turn(fresh, input_origin=origin(fresh))
            p = pipe(root, Reader([BAD], [verdict("PASS")]))
            result = p.turn(RAW, input_origin=origin(RAW))
            self.assertEqual(result.self_action["plan"], "RESPOND_TO_CURRENT_INPUT")
            other = RAW + "另外文件在哪里？"
            p = pipe(root, Reader([BAD], [verdict("PASS")]))
            result = p.turn(other, input_origin=origin(other))
            self.assertEqual(result.self_action["plan"], "RESPOND_TO_CURRENT_INPUT")

    def test_domain_session_void_and_tampered_trace_are_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            p, failed = failed_history(Path(tmp))
            rows = [e.to_dict() for e in p.ledger.entries]
            context = prior_tasks(rows, RAW, origin(RAW), failed.self_action["evidence_basis"])
            self.assertTrue(context["first_attempt_avoid"])
            for transform in (
                    lambda row: row.update(void="fixture"),
                    lambda row: row["self_action"].update(evidence_basis="tampered"),
                    lambda row: row["self_action"]["attempts"][0].update(text="tampered"),
                    lambda row: row.update(output="tampered"),
                    lambda row: row.update(input_origin=dict(row["input_origin"], run_id="run-a", session_id=1))):
                modified = copy.deepcopy(rows)
                transform(modified[-1])
                self.assertFalse(prior_tasks(modified, RAW, origin(RAW),
                                            failed.self_action["evidence_basis"])["first_attempt_avoid"])
            training = copy.deepcopy(rows)
            training[-1]["input_origin"].update(run_id="run-a", session_id=1)
            self.assertFalse(prior_tasks(training, RAW, dict(origin(RAW), run_id="run-a", session_id=2),
                                        failed.self_action["evidence_basis"])["first_attempt_avoid"])

    def test_changed_relation_role_reopens_but_duplicate_source_ids_do_not(self):
        from think import Frame
        frame = Frame(raw=RAW, dialogue_sources=[{"user_text": "押金由李老师收着。", "source_id": "a"}],
                      relational_context={"version": "test", "groups": [{"subject": "押金",
                          "predicate": "custodian", "status": "reported", "reported_values": ["李老师"],
                          "claims": [{"value": "李老师", "role": "ASSERTED", "node_id": "a"}]}]})
        initial = basis(frame, "fixture")
        frame.dialogue_sources.append({"user_text": "押金由李老师收着。", "source_id": "b"})
        frame.relational_context["groups"][0]["claims"].append(
            {"value": "李老师", "role": "ASSERTED", "node_id": "b"})
        self.assertEqual(basis(frame, "fixture"), initial)
        frame.relational_context["groups"][0]["claims"][0]["role"] = "QUOTED"
        self.assertNotEqual(basis(frame, "fixture"), initial)

    def test_unknown_or_transport_failure_does_not_erase_prior_unresolved_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            failed_history(root)
            p = pipe(root, Reader([GOOD, GOOD], [verdict("UNKNOWN")] * 2))
            p.turn(RAW, input_origin=origin(RAW))
            p = pipe(root, Reader([OSError("fixture")], []))
            p.turn(RAW, input_origin=origin(RAW))
            p = pipe(root, Reader([BAD, GOOD], [verdict("PASS")]))
            result = p.turn(RAW, input_origin=origin(RAW))
            self.assertEqual(result.output, GOOD)
            self.assertEqual(result.self_action["plan"], "REVISE_OWN_BLOCKED_RESPONSE")
            self.assertTrue(result.self_action["attempts"][0]["prior_retry"])

    def test_unknown_review_transport_failure_and_template_never_manufacture_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = pipe(root, Reader([GOOD, GOOD], [verdict("UNKNOWN")] * 2))
            unknown = p.turn(RAW, input_origin=origin(RAW))
            self.assertEqual(unknown.self_action["procedure_status"], "WITHHELD")
            self.assertEqual(unknown.self_action["outcome"]["semantic_goal_fit"], "UNKNOWN")
            p = pipe(root, Reader([OSError("fixture")], []))
            failed = p.turn(RAW, input_origin=origin(RAW))
            self.assertTrue(any(op["operation"] == "GENERATION_FAILED" for op in failed.self_action["operations"]))
            self.assertFalse(any(op["operation"] == "GENERATE_CANDIDATE" for op in failed.self_action["operations"]))
            p = pipe(root)
            template = p.turn(RAW, input_origin=origin(RAW))
            self.assertEqual(template.self_action["procedure_status"], "TEMPLATE_ONLY")
            self.assertFalse(template.self_action["expectation"]["declared_before_generation"])
            self.assertEqual(template.self_action["outcome"]["semantic_goal_fit"], "UNKNOWN")

    def test_incomplete_external_thinker_record_keeps_response_but_does_not_certify_execution(self):
        from render import Speech
        class Partial:
            last_attempts = [{"accepted": True, "source": "declared_fixture"}]
            def think(self, frame):
                return Speech("那件事后来怎么样了？", True, "fixture")
        with tempfile.TemporaryDirectory() as tmp:
            p = pipe(Path(tmp))
            p.thinker = Partial()
            result = p.turn(RAW, input_origin=origin(RAW))
            self.assertEqual(result.output, "那件事后来怎么样了？")
            self.assertEqual(result.self_action["procedure_status"], "RETURNED_WITHOUT_CHECK_TRACE")
            self.assertTrue(any(op["operation"] == "ATTEMPT_TRACE_INCOMPLETE" for op in result.self_action["operations"]))
            self.assertFalse(any(op["operation"] == "GENERATE_CANDIDATE" for op in result.self_action["operations"]))


if __name__ == "__main__":
    unittest.main()
