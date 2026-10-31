"""Frozen executable relation versions and out-of-formation counterfactuals.

This records local structural evidence; it NEVER awards development credit.
"""
import copy
import hashlib
import json


def profile(data):
    return {sid: rule["target"] for sid, rule in sorted(data.get("rules", {}).items())
            if rule.get("status") == "active"}


def fingerprint(mapping):
    return hashlib.sha256(json.dumps(mapping, sort_keys=True).encode()).hexdigest()


def used_inputs(data):
    return sorted({digest for rule in data.get("rules", {}).values()
                   for digest in rule.get("training", []) + rule.get("validation", [])}
                  | {e["case"] for e in data.get("events", []) if e.get("case")})


def record(data, previous_data, *, sid, feedback, topic_id, turn):
    evidence = data.setdefault("structure_evidence", {
        "schema": 1, "versions": [{"version": 0, "fingerprint": fingerprint(profile(previous_data)),
                                   "mapping": profile(previous_data), "created_at_case": 0,
                                   "formation_inputs": used_inputs(previous_data),
                                   "origin": "oldest_observed_snapshot"}], "cases": []})
    if evidence.get("schema") != 1:
        raise ValueError("Unknown structure evidence schema")
    catalog = evidence.setdefault("contexts", {})
    for key, rule in previous_data.get("rules", {}).items():
        catalog.setdefault(key, copy.deepcopy(rule["context"]))
    catalog[sid] = copy.deepcopy(data["rules"][sid]["context"])
    case = {"seq": len(evidence["cases"]) + 1, "sid": sid,
            "raw_sha256": feedback["raw_sha256"], "span": feedback["span"],
            "literal_evidence": feedback["evidence"], "role": feedback["role"],
            "source": feedback["source"], "observer": feedback["observer"],
            "topic_id": topic_id, "turn": turn,
            "input_origin": copy.deepcopy(feedback.get("input_origin"))}
    if feedback.get("structural_conflict"):
        case["structural_conflict"] = copy.deepcopy(feedback["structural_conflict"])
    if feedback.get("organisation_observation"):
        case["organisation_observation"] = copy.deepcopy(feedback["organisation_observation"])
    if "raw_text" in feedback:
        case["raw_text"] = feedback["raw_text"]
    evidence["cases"].append(case)
    current = profile(data)
    latest = evidence["versions"][-1]
    if current != latest["mapping"]:
        evidence["versions"].append({
            "version": latest["version"] + 1, "fingerprint": fingerprint(current),
            "mapping": copy.deepcopy(current), "created_at_case": case["seq"],
            "formation_inputs": used_inputs(data), "origin": "relation_activation_or_withdrawal",
            "cause": copy.deepcopy(case)})


def compare_versions(evidence, old_number, new_number):
    versions = {v["version"]: v for v in evidence["versions"]}
    old, new = versions[old_number], versions[new_number]
    if old_number >= new_number:
        raise ValueError("Compare earlier to later structure")
    excluded = set(new["formation_inputs"])
    future = []
    seen = set()
    for case in evidence["cases"]:
        key = (case["raw_sha256"], case["sid"])
        if case["seq"] <= new["created_at_case"] or case["raw_sha256"] in excluded or key in seen:
            continue
        seen.add(key)
        before = old["mapping"].get(case["sid"], "UNKNOWN")
        after = new["mapping"].get(case["sid"], "UNKNOWN")
        future.append(dict(case, old_prediction=before, new_prediction=after,
                           improved=before != case["role"] and after == case["role"],
                           regression=before == case["role"] and after != case["role"],
                           contradicted=after not in ("UNKNOWN", case["role"])))
    # Old competence cases are examined separately, never counted as new transfer.
    retention = []
    for case in evidence["cases"]:
        if case["seq"] > new["created_at_case"]:
            continue
        if old["mapping"].get(case["sid"], "UNKNOWN") == case["role"]:
            after = new["mapping"].get(case["sid"], "UNKNOWN")
            retention.append(dict(case, new_prediction=after, retained=after == case["role"]))
    topics = sorted({c["topic_id"] for c in future if c["topic_id"] and c["improved"]})
    improvements = sum(c["improved"] for c in future)
    losses = sum(c["regression"] or c["contradicted"] for c in future) + sum(not c["retained"] for c in retention)
    verdict = ("counterevidence" if losses else "no_future_evidence" if not future
               else "local_transfer_observed" if improvements else "no_improvement_observed")
    return {"old_version": old_number, "new_version": new_number,
            "old_fingerprint": old["fingerprint"], "new_fingerprint": new["fingerprint"],
            "future": future, "retention": retention, "improvements": improvements,
            "future_input_count": len({c["raw_sha256"] for c in future}),
            "losses": losses, "topic_ids": topics, "cross_topic_labels_observed": len(topics) >= 2,
            "observers": sorted({c["observer"] for c in future}),
            "source_declarations": sorted({c["source"] for c in future}),
            "independent_semantic_review_verified": False,
            "verdict": verdict, "development_credit": 0}


def report(data):
    evidence = data.get("structure_evidence")
    if not evidence:
        return {"verdict": "no_structure_history", "development_credit": 0}
    versions = evidence["versions"]
    for number, version in enumerate(versions):
        if version["version"] != number or version["fingerprint"] != fingerprint(version["mapping"]):
            raise ValueError("Structure version order or fingerprint mismatch")
    if any(case["seq"] != number for number, case in enumerate(evidence["cases"], 1)):
        raise ValueError("Structure case sequence mismatch")
    try:
        from .organisation_refinement import derive
    except ImportError:
        from organisation_refinement import derive
    return {"schema": 1, "kind": "local_relation_structure_evidence",
            "contexts": copy.deepcopy(evidence.get("contexts", {})),
            "versions": copy.deepcopy(versions), "case_count": len(evidence["cases"]),
            "conflicts": [copy.deepcopy(case["structural_conflict"])
                          for case in evidence["cases"] if case.get("structural_conflict")],
            "organisation_candidates": derive(evidence),
            "comparisons": [compare_versions(evidence, a["version"], b["version"])
                            for a, b in zip(versions, versions[1:])],
            "development_credit": 0}
