"""Execute one bounded, feedback-selected relation law, with atomic withdrawal.

E p71/73/77 motivates changing laws between parts and retaining useful material.
The quote-ownership operator and 3+2 criteria are engineering choices. This is
local linguistic rule execution, never developmental or subjective credit.
No natural-language proposal is executable, and no historical memory migrates
to a live rule merely because somebody wrote 'active' in its snapshot.
"""
import copy
import hashlib
import json

try:
    from .organisation_refinement import FEATURE, derive, observe_ownership
except ImportError:
    from organisation_refinement import FEATURE, derive, observe_ownership

VERSION = "bounded_quote_owner_split_v1"
ROLES = frozenset({"ASSERTED", "NEGATED", "PROHIBITED", "QUOTED"})


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def _program(candidate, evidence):
    context = evidence.get("contexts", {}).get(candidate["sid"])
    if (not context or context.get("marker") != "blame_external"
            or context.get("representation") != "literal_scope_relations_v2"
            or type(context.get("offline")) is not bool
            or candidate.get("feature") != FEATURE
            or set(candidate.get("branches", {})) != {"False", "True"}
            or any(role not in ROLES for role in candidate["branches"].values())):
        raise ValueError("Unsupported organisation program")
    if _hash(context)[:24] != candidate["sid"]:
        raise ValueError("Organisation guard does not match its source context")
    return {"operator": VERSION, "guard": copy.deepcopy(context),
            "feature": FEATURE, "branches": copy.deepcopy(candidate["branches"]),
            "unsupported_observation": "UNKNOWN", "effect": "role_prediction_only"}


def _proof(candidate, evidence):
    return {"candidate_fingerprint": candidate["fingerprint"],
            "program": _program(candidate, evidence),
            "formed_at": candidate["created_at_case"],
            "formation_inputs": candidate["formation_inputs"],
            "formation_cases": candidate["formation_cases"],
            "base_version": candidate["base_version"],
            "old_mapping": candidate["old_mapping"],
            "formation_source_sha256": _hash(evidence["cases"][:candidate["created_at_case"]])}


def _sources_verified(candidate, evidence):
    """Recompute literal ownership from source bytes, including later cases.

    Old annotations without their original text remain historical candidates;
    missing text is never filled by inference or by a new model completion.
    """
    covered = set(candidate["old_mapping"]) | {candidate["sid"]}
    for case in evidence["cases"]:
        if case["sid"] not in covered:
            continue
        raw = case.get("raw_text")
        span = case.get("span") or []
        context = evidence.get("contexts", {}).get(case["sid"], {})
        allowed = {"offline_fixture"} if context.get("offline") is True else {"user_correction", "external_reviewer"}
        if (not isinstance(raw, str) or hashlib.sha256(raw.encode()).hexdigest() != case["raw_sha256"]
                or len(span) != 2 or any(type(pos) is not int for pos in span)
                or not 0 <= span[0] < span[1] <= len(raw)
                or raw[slice(*span)] != case["literal_evidence"]
                or case.get("source") not in allowed or not case.get("observer")
                or case["observer"] in {"self", "candidate"}
                or observe_ownership(raw, span[0]) != case.get("organisation_observation")):
            return False
    return True


def synchronise(data):
    """Called inside the relation feedback's existing single atomic commit.

    The freeze, later validation and whole-candidate refutation are replayed
    from original evidence. Persisted status alone never proves eligibility.
    """
    evidence = data.get("structure_evidence")
    if not evidence:
        return []
    candidates = derive(evidence)
    if not candidates and "organisation_runtime" not in data:
        return []
    runtime = data.setdefault("organisation_runtime", {
        "schema": 1, "operator": VERSION, "versions": [], "events": [],
        "independent_semantics_verified": False, "development_credit": 0})
    if runtime.get("schema") != 1 or runtime.get("operator") != VERSION:
        raise ValueError("Unknown organisation runtime")
    seq = len(evidence["cases"])
    changes, present = [], set()
    for candidate in candidates:
        proof = _proof(candidate, evidence)
        key = _hash(proof)
        present.add(key)
        record = next((v for v in runtime["versions"] if v["proof_sha256"] == key), None)
        if record is None:
            record = {"version": len(runtime["versions"]) + 1, "sid": candidate["sid"],
                      "proof_sha256": key, "proof": copy.deepcopy(proof), "status": "candidate",
                      "activated_at": None, "withdrawn_at": None, "development_credit": 0}
            runtime["versions"].append(record)
            changes.append({"kind": "formed", "version": record["version"], "case": seq})
        if record["proof"] != proof:
            raise ValueError("Executable organisation version was altered")
        if candidate["status"] == "rejected" and record["status"] != "withdrawn":
            record["status"] = "withdrawn"
            record["withdrawn_at"] = seq
            changes.append({"kind": "withdrawn", "version": record["version"], "case": seq,
                            "counterevidence": list(candidate["counterevidence"]),
                            "old_competence_losses": list(candidate["old_competence_losses"])})
        elif record["status"] == "active" and not _sources_verified(candidate, evidence):
            record["status"], record["withdrawn_at"] = "withdrawn", seq
            changes.append({"kind": "withdrawn", "version": record["version"], "case": seq,
                            "reason": "original_sources_not_verified"})
        elif (candidate["status"] == "locally_validated_candidate" and record["status"] == "candidate"
              and _sources_verified(candidate, evidence)):
            record["status"] = "active"
            record["activated_at"] = seq
            changes.append({"kind": "activated", "version": record["version"], "case": seq,
                            "validation_inputs": copy.deepcopy(candidate["validation_inputs"])})
    # Evidence removed or changed cannot leave an executable orphan behind.
    for record in runtime["versions"]:
        if record["proof_sha256"] not in present and record["status"] != "withdrawn":
            record["status"], record["withdrawn_at"] = "withdrawn", seq
            changes.append({"kind": "withdrawn", "version": record["version"], "case": seq,
                            "reason": "formation_proof_no_longer_available"})
    runtime["events"].extend(changes)
    return changes


def select(data, context, raw, start, end):
    """Interpret a saved rule only after checking its full current evidence.

    Return None for the unchanged literal-context learner. Return UNKNOWN on a
    withdrawn or unsupported refined slot, rather than reviving its old alias.
    Other slots always use their CURRENT learner, never a frozen old mapping.
    """
    runtime = data.get("organisation_runtime")
    if not runtime:
        return None
    if runtime.get("schema") != 1 or runtime.get("operator") != VERSION:
        raise ValueError("Unknown organisation runtime")
    sid = _hash(context)[:24]
    records = [v for v in runtime["versions"] if v["sid"] == sid]
    if not records:
        return None
    record = records[-1]
    if record["proof_sha256"] != _hash(record["proof"]):
        raise ValueError("Organisation program fingerprint mismatch")
    if record["proof"]["program"]["guard"] != context:
        raise ValueError("Organisation guard mismatch")
    if record["status"] == "candidate":
        return None
    evidence = data.get("structure_evidence", {})
    candidates = {c["fingerprint"]: c for c in derive(evidence)}
    candidate = candidates.get(record["proof"]["candidate_fingerprint"])
    eligible = bool(candidate and candidate["status"] == "locally_validated_candidate"
                    and _proof(candidate, evidence) == record["proof"]
                    and _sources_verified(candidate, evidence))
    if record["status"] == "withdrawn" or not eligible:
        return {"role": "UNKNOWN", "reason": "organisation_withdrawn_or_unproved",
                "execution": {"version": record["version"], "status": "abstained",
                              "reason": "whole_candidate_refuted_or_proof_missing"}}
    if record["status"] != "active" or not record.get("activated_at"):
        raise ValueError("Invalid organisation activation")
    # Only this exact supported operator is evaluated. There is no eval/exec.
    program = record["proof"]["program"]
    observation = observe_ownership(raw, start)
    supported = observation.get("supported") and type(observation.get("features", {}).get(FEATURE)) is bool
    role = program["branches"][str(observation["features"][FEATURE])] if supported else "UNKNOWN"
    return {"role": role, "reason": "organisation_rule_active" if supported else "organisation_observation_unknown",
            "execution": {"operation": "RESOLVE_PROPOSITION_ROLE", "version": record["version"],
                          "program_sha256": _hash(program), "input_sha256": hashlib.sha256(raw.encode()).hexdigest(),
                          "span": [start, end], "observation": observation, "result": role,
                          "basis": "executed_bounded_operator_not_generated_speech_classification",
                          "development_credit": 0}}
