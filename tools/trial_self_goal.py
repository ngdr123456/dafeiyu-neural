"""Isolated source-bound goal choices, commitments and literal outcomes."""
import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "engine"), str(ROOT / "tests")]
from test_self_goal import (seed, answer, pipe, origin, SourceReader, GoalReader, Thinker,
                            claim, SOURCE, OTHER, CORRECTION, QUERY, PARAPHRASE, GOOD, MISS)
from understand import ApiReader
from action_plan import SELF_GOAL, source_hashes
from tools.structure_scope_trial import state_hashes


class InjectedGeneration:
    supports_goal_choice = True
    def __init__(self, live):
        self.live, self.available, self.model = live, live.available, live.model

    def _post(self, messages, *, json_mode=False):
        if json_mode:
            return self.live._post(messages, json_mode=True)
        return {"choices": [{"message": {"content": MISS}}]}, 0


def selection(result):
    return result.self_action["goal_selection"]


def add(cases, name, passed, **details):
    cases.append(dict(case=name, passed=bool(passed), **details))
    print(name, bool(passed), flush=True)


def source_turn(root, raw, live=None):
    p = pipe(root, use_api=True)
    p.reader = live or SourceReader({raw: {"propositions": [claim(raw, "甲项目押金",
        "周老师" if raw == CORRECTION else "赵老师", correction=raw == CORRECTION)]}})
    return p.turn(raw, input_origin=origin(raw))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", action="store_true")
    parser.add_argument("--report")
    args = parser.parse_args()
    before, initial = state_hashes(), source_hashes(ROOT)
    cases = []
    with tempfile.TemporaryDirectory(prefix="ego-declared-goal-") as tmp:
        root = Path(tmp)
        if args.api:
            live = ApiReader()
            if not live.available:
                raise RuntimeError("API unavailable")
            p = pipe(root, use_api=True); p.reader = live
            readings = [p.turn(raw, input_origin=origin(raw)).proposition_reading for raw in (SOURCE, OTHER)]
            add(cases, "actual_relation_seed", all(any(n["subject"] == subject and n["role"] == "ASSERTED"
                for n in (reading or {}).get("propositions", []))
                for reading, subject in zip(readings, ("甲项目押金", "乙项目押金"))), readings=readings)
            # Candidate failure is injected; choice and source readings are real model calls.
            _, pending = answer(root, QUERY, InjectedGeneration(live))
            old = selection(pending)
            add(cases, "actual_choice_with_injected_candidate_failure", old["decision"] == "SELECTED"
                and old["result"]["state"] == "PENDING"
                and old["result"]["operation_expectation"]["comparison"] == "MISMATCH",
                generation_origin="declared_engineered_failure_injection", trace=pending.self_action)
            _, resumed = answer(root, PARAPHRASE, live)
            new = selection(resumed)
            add(cases, "actual_paraphrase_resume", bool(old["selected"] and new["selected"])
                and new["selected"]["id"] == old["selected"]["id"]
                and new["result"]["state"] == "FULFILLED_LITERAL", trace=resumed.self_action)
            source_turn(root, CORRECTION, live)
            _, corrected = answer(root, QUERY, live)
            current = selection(corrected)
            add(cases, "actual_source_change_reconsider", bool(current["selected"])
                and any(item["changed_basis"] for item in current["prior"])
                and "周老师" in json.dumps(current["selected"], ensure_ascii=False)
                and "李老师" not in json.dumps(current["selected"], ensure_ascii=False)
                and current["result"]["state"] == "FULFILLED_LITERAL", trace=corrected.self_action)
            conflict = "甲项目押金由赵老师收着。"
            source_turn(root, conflict, live)
            _, conflicted = answer(root, QUERY, live)
            current = selection(conflicted)
            add(cases, "actual_conflict_quotes_complete", bool(current["selected"])
                and len(current["selected"]["targets"]) == 2
                and current["result"]["state"] == "FULFILLED_LITERAL"
                and current["result"]["semantic_goal_fit"] == "UNKNOWN", trace=conflicted.self_action)
        else:
            seed(root)
            active, absent = pipe(root), pipe(root, use_goal_planning=False)
            active.thinker, absent.thinker = Thinker(GoalReader([MISS, GOOD])), Thinker(GoalReader([MISS]))
            actual = active.turn(QUERY, input_origin=origin(QUERY))
            disabled = absent.turn(QUERY, input_origin=origin(QUERY))
            add(cases, "identical_history_goal_ablation", actual.output == GOOD and disabled.output == MISS,
                enabled=actual.output, disabled=disabled.output)
            target = root / "resume"; seed(target)
            _, pending = answer(target, QUERY, GoalReader([MISS, MISS]))
            _, resumed = answer(target, PARAPHRASE, GoalReader([GOOD]))
            add(cases, "paraphrase_resume", selection(resumed)["prior"][0]["goal"]["id"] == selection(pending)["selected"]["id"]
                and selection(resumed)["result"]["state"] == "FULFILLED_LITERAL")
            source_turn(target, CORRECTION)
            _, corrected = answer(target, QUERY, GoalReader(['按更正原话：“' + CORRECTION + '”']))
            add(cases, "source_change_reconsider", selection(corrected)["prior"][0]["changed_basis"]
                and selection(corrected)["result"]["state"] == "FULFILLED_LITERAL"
                and "李老师" not in json.dumps(selection(corrected)["selected"], ensure_ascii=False))
            conflict = "甲项目押金由赵老师收着。"; source_turn(target, conflict)
            _, result = answer(target, QUERY, GoalReader(['按原话：“' + CORRECTION + '”“' + conflict + '”']))
            add(cases, "conflict_complete_quotes", len(selection(result)["selected"]["targets"]) == 2
                and selection(result)["result"]["state"] == "FULFILLED_LITERAL")
            target = root / "retire"; seed(target)
            _, pending = answer(target, QUERY, GoalReader([MISS, MISS]))
            _, declined = answer(target, PARAPHRASE, GoalReader([MISS], choices=["NONE"]))
            _, new = answer(target, QUERY, GoalReader([GOOD]))
            add(cases, "decline_retires_pending", selection(pending)["selected"]["id"] in selection(declined)["retired_ids"]
                and selection(new)["prior"] == [])
            add(cases, "literal_outcome_not_semantic_fit", selection(actual)["result"]["semantic_goal_fit"] == "UNKNOWN"
                and actual.self_action["outcome"]["semantic_goal_fit"] == "UNKNOWN"
                and not selection(actual)["selected"]["subjective_desire_verified"])
            other = "乙项目押金由谁收着？"
            _, kept = answer(target, other, GoalReader(['按原话：“' + OTHER + '”']))
            add(cases, "other_object_preserved", selection(kept)["prior"] == []
                and selection(kept)["result"]["state"] == "FULFILLED_LITERAL")
    if state_hashes() != before or source_hashes(ROOT) != initial:
        raise RuntimeError("State/source changed during diagnostic")
    result = {"schema": 1, "scope": "source_bound_declared_goal_commitments", "passed": all(c["passed"] for c in cases),
              "cases": cases, "source_hashes": initial, "real_API": args.api, "formal_training": False,
              "scripted_inputs": True, "goal_origin": "model_declared_bounded_task",
              "selection_origin": "actual_model_with_injected_candidate_failure" if args.api else "declared_engineered_selection_and_review",
              "real_state_files_unchanged": len(before), "independent_semantics_verified": False,
              "development_credit": 0, "claims": "Literal goal outcome and commitment process; no human goal, reward or stage certification."}
    (ROOT / (args.report or SELF_GOAL)).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": result["passed"], "cases": len(cases), "real_API": args.api,
                      "state_unchanged": len(before)}, ensure_ascii=False), flush=True)
    return int(not result["passed"])


if __name__ == "__main__":
    raise SystemExit(main())
