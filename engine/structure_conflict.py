"""Trace a relation mismatch without inventing its cause or a new principle.

E p71-77: a change in labels is not itself a change in organizing laws.
ENG: distinguish conflicting feedback on one occurrence from collisions between
occurrences compressed into one representation. Neither certifies a reviewer.
"""
import copy


def diagnose(previous_data, *, sid, incoming):
    rule = previous_data.get("rules", {}).get(sid)
    if not rule or rule["target"] == incoming["role"]:
        return None
    # Prefer the canonical case sequence; older memories may have events only.
    evidence = previous_data.get("structure_evidence", {})
    cases = evidence.get("cases", [])
    if not cases:
        cases = [dict(event.get("feedback", {}), sid=event.get("sid"))
                 for event in previous_data.get("events", [])
                 if event.get("feedback")]
    prior = []
    seen = set()
    for case in cases:
        if case.get("sid") != sid or case.get("role") != rule["target"]:
            continue
        key = (case.get("raw_sha256"), tuple(case.get("span", [])),
               case.get("source"), case.get("observer"), case.get("role"))
        if key in seen:
            continue
        seen.add(key)
        prior.append({key: copy.deepcopy(case.get(key)) for key in
                      ("seq", "raw_sha256", "span", "literal_evidence", "role",
                       "source", "observer", "topic_id", "input_origin")})
    same_input = [case for case in prior
                  if case["raw_sha256"] == incoming["raw_sha256"]]
    same_occurrence = [case for case in same_input if case["span"] == incoming["span"]]
    if same_occurrence:
        observation = "same_occurrence_conflicting_feedback"
        next_check = "review_feedback_consistency_before_refining_representation"
    elif same_input:
        observation = "different_occurrences_same_input_same_context"
        next_check = "inspect_occurrence_scope_and_feedback_consistency"
    elif prior:
        observation = "different_inputs_same_context_conflicting_feedback"
        next_check = "inspect_missing_relations_background_and_feedback_consistency"
    else:
        observation = "prior_rule_without_comparable_feedback"
        next_check = "recover_prior_evidence_before_explaining_conflict"
    return {"schema": 1, "sid": sid, "observation": observation,
            "cause": "unresolved", "next_check": next_check,
            "old_rule": copy.deepcopy(rule), "prior_evidence": prior,
            "incoming": copy.deepcopy(incoming),
            "source_or_observer_differs": any(
                (case["source"], case["observer"]) !=
                (incoming["source"], incoming["observer"]) for case in prior),
            "topic_label_differs": any(case["topic_id"] != incoming.get("topic_id")
                                      for case in prior),
            "independent_semantic_review_verified": False,
            "new_organizing_principle_formed": False, "development_credit": 0}
