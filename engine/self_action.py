"""Bounded own task -> plan -> observed operations -> unresolved outcome.

The task is an engineered dialogue obligation, not a subjective desire. A
content verdict is a correlated opinion. Past failure changes a later retry
plan, never the user's facts, dopamine proxies or development level. Everything
is derived from committed ledger rows; there is no second mutable goal store.
"""
import copy
import hashlib
import json

VERSION = "own_response_revision_v1"


def fingerprint(value):
    serialized = value if isinstance(value, str) else json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def basis(frame, reviewer):
    # Repeated questions and assistant outputs do not manufacture new evidence.
    # Changed selected user sources do reopen review. This is deliberately more
    # conservative than deciding whether two source sets mean the same thing.
    from think import FRAME_SYSTEM
    from content_fidelity import SYSTEM
    relation = frame.relational_context or {}
    groups = []
    for group in relation.get("groups", []):
        claims = {fingerprint({key: node.get(key) for key in (
            "subject", "predicate", "time", "value", "evidence", "role", "status", "correction")}
            | {"superseded": bool(node.get("superseded_by"))})
            for node in group.get("claims", [])}
        groups.append({key: group.get(key) for key in (
            "subject", "predicate", "time", "status", "reported_values")}
            | {"claims": sorted(claims)})
    return fingerprint({"raw": frame.raw,
                        "utterances": sorted({frame.raw} | {
                            s["user_text"] for s in frame.dialogue_sources}),
                        "self_facts": frame.self_facts, "hard_notes": frame.notes,
                        "relations": {"version": relation.get("version"), "groups": groups,
                                      "unresolved_reasons": relation.get("unresolved_reasons", [])},
                        "reviewer": reviewer, "policy": [VERSION, FRAME_SYSTEM, SYSTEM]})


def prior_tasks(entries, raw, origin, evidence_basis):
    """Exact request, selected evidence and author domain; bounded recency.

    Do not turn old free text, malformed traces or a PASS into proof of meaning.
    Latest committed attempt replaces the procedural retry status only.
    """
    from dialogue_memory import eligible_entries
    selected = []
    for index, row in eligible_entries(entries, origin)[-64:]:
        trace = row.get("self_action")
        if (row.get("raw_input") != raw or not isinstance(trace, dict)
                or trace.get("schema") != 1 or trace.get("version") != VERSION
                or trace.get("input_sha256") != fingerprint(raw)
                or trace.get("evidence_basis") != evidence_basis
                or not isinstance(trace.get("goal"), dict) or not trace["goal"].get("id")
                or not isinstance(trace.get("attempts"), list)
                or any(not isinstance(a, dict) for a in trace["attempts"])
                or trace.get("selected_output_sha256") != fingerprint(row.get("output", ""))
                or trace.get("receipt_sha256") != receipt(trace)):
            continue
        selected.append((index, trace))
    if not selected:
        return {"schema": 1, "plan": "RESPOND_TO_CURRENT_INPUT", "prior": [],
                "first_attempt_avoid": [], "independent_semantics_verified": False}
    index, latest = selected[-1]
    avoid = []
    # A later permitted response closes only the procedural failure. It doesn't
    # retroactively turn the earlier generated response into a confirmed action.
    unresolved = []
    for prior_index, prior in reversed(selected[-8:]):
        if prior.get("procedure_status") == "PERMITTED":
            break
        if prior.get("procedure_status") != "WITHHELD":
            continue
        unresolved.append({"goal_id": prior["goal"]["id"], "ledger_index": prior_index + 1,
                           "procedure_status": "WITHHELD", "semantic_outcome": "UNKNOWN"})
        for attempt in prior.get("attempts", [])[-2:]:
            review = attempt.get("content_review") or {}
            text = attempt.get("text")
            evidence = review.get("evidence")
            if (attempt.get("accepted") is False and review.get("verdict") == "REJECT"
                    and isinstance(text, str) and 0 < len(text) <= 120
                    and isinstance(evidence, list) and evidence
                    and all(isinstance(e, dict) and isinstance(e.get("text"), str)
                            and e["text"] and e["text"] in text for e in evidence)):
                if any(item["text"] == text for item in avoid):
                    continue
                avoid.append({"text": text, "source_goal": prior["goal"]["id"],
                              "source_ledger_index": prior_index + 1,
                              "basis": "prior_correlated_rejection_not_semantic_truth"})
    return {"schema": 1, "plan": "REVISE_OWN_BLOCKED_RESPONSE" if avoid else "RESPOND_TO_CURRENT_INPUT",
            "prior": unresolved[:4] or [{"goal_id": latest["goal"]["id"], "ledger_index": index + 1,
                       "procedure_status": latest.get("procedure_status", "UNKNOWN"),
                       "semantic_outcome": "UNKNOWN"}],
            "first_attempt_avoid": avoid[:4], "independent_semantics_verified": False}


def begin(raw, origin, turn, context, evidence_basis, *, source_ids, thinker_present):
    goal_id = fingerprint({"raw": raw, "origin": origin, "turn": turn, "version": VERSION})
    return {"schema": 1, "version": VERSION, "input_sha256": fingerprint(raw),
            "evidence_basis": evidence_basis,
            "goal": {"id": goal_id, "kind": "RESPOND_WITH_TRACEABLE_BASIS",
                     "origin": "engineered_dialogue_obligation", "subjective_desire_verified": False},
            "plan": context.get("plan", "RESPOND_TO_CURRENT_INPUT"),
            "prior": copy.deepcopy(context.get("prior", [])),
            "expectation": {"declared_before_generation": thinker_present,
                            "declared_before_selection": True,
                            "desired_semantic_fit": True, "semantic_fit_observable": False,
                            "release_requires_current_checks": thinker_present,
                            "source_ids_available": list(source_ids)},
            "operations": [{"operation": "ASSEMBLE_FRAME_SOURCES", "confirmed": True,
                            "source_ids": list(source_ids)}] if thinker_present else [],
            "attempts": [], "development_credit": 0, "subjective_reward_verified": False}


def receipt(trace):
    return fingerprint({k: v for k, v in trace.items() if k != "receipt_sha256"})


def finish(trace, attempts, output, action, response_mode):
    result = copy.deepcopy(trace)
    result["attempts"] = copy.deepcopy(attempts or [])
    for attempt in result["attempts"]:
        if (not isinstance(attempt, dict) or not isinstance(attempt.get("attempt"), int)
                or (not isinstance(attempt.get("text"), str) and not attempt.get("error_type"))):
            result["operations"].append({"operation": "ATTEMPT_TRACE_INCOMPLETE", "confirmed": True,
                                         "basis": "record_shape_observed_execution_not_certified"})
            continue
        if attempt.get("error_type"):
            result["operations"].append({"operation": "GENERATION_FAILED", "confirmed": True,
                                         "attempt": attempt["attempt"], "error_type": attempt["error_type"]})
            continue
        if isinstance(attempt.get("text"), str):
            result["operations"].append({"operation": "GENERATE_CANDIDATE", "confirmed": True,
                                         "attempt": attempt["attempt"],
                                         "text_sha256": fingerprint(attempt["text"])})
        result["operations"].append({"operation": "APPLY_RELEASE_CHECKS", "confirmed": True,
                                     "attempt": attempt["attempt"],
                                     "permitted": attempt.get("accepted") is True,
                                     "prior_retry": attempt.get("prior_retry")})
    result["operations"].append({"operation": "SELECT_PIPELINE_RETURN_TEXT", "confirmed": True,
                                 "text_sha256": fingerprint(output), "mode": response_mode,
                                 "external_delivery_verified": False})
    result["selected_output_sha256"] = fingerprint(output)
    result["speech_action"] = copy.deepcopy(action)
    checked = bool(result["attempts"] and isinstance(result["attempts"][-1], dict)
                   and isinstance(result["attempts"][-1].get("attempt"), int)
                   and result["attempts"][-1].get("accepted") is True
                   and result["attempts"][-1].get("text") == output)
    result["procedure_status"] = ("PERMITTED" if response_mode == "brain" and checked else
                                  "RETURNED_WITHOUT_CHECK_TRACE" if response_mode == "brain" else
                                  "WITHHELD" if result["expectation"]["release_requires_current_checks"] else
                                  "TEMPLATE_ONLY")
    result["outcome"] = {"semantic_goal_fit": "UNKNOWN", "user_satisfaction": "UNKNOWN",
                         "basis": "operations_confirmed_semantics_not_independently_measured"}
    if result.get("goal_selection"):
        from self_goal import finish as finish_goal
        result["goal_selection"] = finish_goal(result["goal_selection"], output, result["procedure_status"])
        result["operations"].append({"operation": "OBSERVE_BOUND_GOAL_PREDICATE", "confirmed": True,
                                     "result": result["goal_selection"]["result"]})
    result["receipt_sha256"] = receipt(result)
    return result
