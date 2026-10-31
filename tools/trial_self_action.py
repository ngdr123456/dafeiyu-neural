"""Own revision contrast; optional real review of explicitly injected candidates."""
import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "engine"), str(ROOT / "tests")]
from test_self_action import pipe, origin, failed_history, RAW, BAD, GOOD
from test_content_fidelity import Reader, verdict
from think import Thinker
from understand import ApiReader
from action_plan import SELF_ACTION, source_hashes
from tools.structure_scope_trial import state_hashes


class InjectedGeneration:
    """The candidate is engineered; only its content review uses the real API."""
    def __init__(self, live):
        self.live = live
        self.available, self.model = live.available, live.model

    def _post(self, messages, *, json_mode=False):
        if json_mode:
            return self.live._post(messages, json_mode=True)
        return {"choices": [{"message": {"content": BAD}}]}, 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", action="store_true")
    parser.add_argument("--report")
    args = parser.parse_args()
    before, initial = state_hashes(), source_hashes(ROOT)
    cases = []
    with tempfile.TemporaryDirectory(prefix="ego-own-task-") as tmp:
        root = Path(tmp)
        if args.api:
            live = ApiReader()
            if not live.available:
                raise RuntimeError("API unavailable")
            p = pipe(root)
            seed = "押金由李老师收着。"
            p.turn(seed, input_origin=origin(seed))
            p.thinker = Thinker(InjectedGeneration(live))
            failed = p.turn(RAW, input_origin=origin(RAW))
            cases.append({"case": "actual_review_of_injected_failure",
                          "passed": failed.self_action["procedure_status"] == "WITHHELD"
                            and len(failed.self_action["attempts"]) == 2
                            and all((a.get("content_review") or {}).get("verdict") == "REJECT"
                                    for a in failed.self_action["attempts"]),
                          "generation_origin": "declared_engineered_candidate",
                          "reviews": failed.self_action["attempts"]})
            # Don't promote an injection to a real model's spontaneously failed reply.
            p = pipe(root, live)
            result = p.turn(RAW, input_origin=origin(RAW))
            cases.append({"case": "actual_model_receives_restarted_own_task",
                          "passed": result.self_action["plan"] == "REVISE_OWN_BLOCKED_RESPONSE"
                            and result.self_action["prior"][0]["goal_id"] == failed.self_action["goal"]["id"],
                          "trace": result.self_action})
            cases.append({"case": "actual_model_return_keeps_unmeasured_goal_unknown",
                          "passed": result.self_action["procedure_status"] == "PERMITTED"
                            and result.self_action["outcome"]["semantic_goal_fit"] == "UNKNOWN"
                            and "李老师" in result.output,
                          "output": result.output, "action_observation": result.action_observation})
        else:
            _, failed = failed_history(root)
            enabled = pipe(root, Reader([BAD, GOOD], [verdict("PASS")]))
            disabled = pipe(root, Reader([BAD], [verdict("PASS")]), enabled=False)
            active = enabled.turn(RAW, input_origin=origin(RAW))
            absent = disabled.turn(RAW, input_origin=origin(RAW))
            cases.extend([
                {"case": "identical_history_enable_disable", "passed": active.output == GOOD and absent.output == BAD,
                 "enabled_output": active.output, "disabled_output": absent.output},
                {"case": "restart_resumes_committed_failure", "passed": active.self_action["plan"] == "REVISE_OWN_BLOCKED_RESPONSE"
                    and active.self_action["prior"][0]["goal_id"] == failed.self_action["goal"]["id"]},
                {"case": "permission_not_semantic_fulfillment", "passed": active.self_action["outcome"]["semantic_goal_fit"] == "UNKNOWN"
                    and active.action_observation["actual"] == "UNCLASSIFIED"}])
            # Reset to the genuine failed row, ignoring newly appended contrast outputs.
            for directory in ("reconsider", "changed"):
                target = root / directory
                failed_history(target)
                if directory == "reconsider":
                    current = pipe(target, Reader([BAD, BAD], [verdict("PASS")]))
                    result = current.turn(RAW, input_origin=origin(RAW))
                    cases.append({"case": "fresh_second_review_can_reconsider",
                                  "passed": result.output == BAD and result.self_action["procedure_status"] == "PERMITTED"})
                else:
                    current = pipe(target)
                    correction = "更正：押金现在由周老师收着。"
                    current.turn(correction, input_origin=origin(correction))
                    current = pipe(target, Reader([BAD], [verdict("PASS")]))
                    result = current.turn(RAW, input_origin=origin(RAW))
                    cases.append({"case": "changed_evidence_reopens", "passed": result.self_action["plan"] == "RESPOND_TO_CURRENT_INPUT"})
    if state_hashes() != before or source_hashes(ROOT) != initial:
        raise RuntimeError("State/source changed during diagnostic")
    report = {"schema": 1, "scope": "bounded_own_response_revision", "passed": all(c["passed"] for c in cases),
              "cases": cases, "source_hashes": initial, "real_state_files_unchanged": len(before),
              "goal_origin": "engineered_dialogue_obligation", "real_API": args.api,
              "formal_training": False, "scripted_inputs": True,
              "independent_semantics_verified": False, "development_credit": 0}
    (ROOT / (args.report or SELF_ACTION)).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "cases": len(cases), "real_API": args.api,
                      "state_unchanged": len(before)}, ensure_ascii=False), flush=True)
    return int(not report["passed"])


if __name__ == "__main__":
    raise SystemExit(main())
