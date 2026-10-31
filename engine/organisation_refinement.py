"""Bounded, experience-selected candidate organisation; never a live override.

E p71-77 motivates relations governing parts, mismatch and continuity.
ENG: the available feature and 3 formation + 2 later cases per branch are
explicit engineering choices. Labels come from feedback, not quotation syntax.
"""
import copy
import hashlib
import json
import re

FEATURE = "cue_in_completed_quote"
CUES = r"不能说|不要说|没有说|没说|不是|并非|不|没|别"


def observe_ownership(raw, start):
    """Literal spans only; unsupported quotation is unknown, not false."""
    prefix = raw[:start]
    cues = list(re.finditer(CUES, prefix))
    cue = cues[-1] if cues else None
    stack, quotes = [], []
    for pos, char in enumerate(prefix):
        if char in "‘’「」『』":
            return {"supported": False, "reason": "unsupported_quote_syntax"}
        if char == '“':
            stack.append(('”', pos))
        elif char == '”':
            if not stack or stack[-1][0] != char:
                return {"supported": False, "reason": "unmatched_quote"}
            _, opened = stack.pop()
            quotes.append((opened, pos + 1))
        elif char == '"':
            if stack and stack[-1][0] == char:
                _, opened = stack.pop()
                quotes.append((opened, pos + 1))
            else:
                stack.append((char, pos))
    if stack:
        return {"supported": False, "reason": "quote_not_completed_before_occurrence"}
    owners = [(a, b) for a, b in quotes
              if cue and a < cue.start() and cue.end() < b]
    owner = min(owners, key=lambda pair: pair[1] - pair[0]) if owners else None
    return {"supported": True, "features": {FEATURE: bool(owner)},
            "cue_span": list(cue.span()) if cue else None,
            "cue_text": cue.group() if cue else None,
            "quote_span": list(owner) if owner else None,
            "quote_text": raw[slice(*owner)] if owner else None}


def predict(candidate, case):
    if case.get("sid") != candidate["sid"]:
        return candidate["old_mapping"].get(case.get("sid"), "UNKNOWN")
    observation = case.get("organisation_observation", {})
    value = observation.get("features", {}).get(candidate["feature"])
    if not observation.get("supported") or type(value) is not bool:
        return "UNKNOWN"
    return candidate["branches"].get(str(value), "UNKNOWN")


def derive(evidence, formation=3, validation=2):
    """Replay chronologically: freeze at formation, validate only later input.

    No majority vote, training on validation, raw-text memorisation, live enable,
    or stage credit. Existing memories lacking observations stay unrefined.
    """
    candidates = []
    for sid in sorted({c["sid"] for c in evidence["cases"]}):
        cases = evidence["cases"]
        conflicts = [c for c in cases if c["sid"] == sid and c.get("structural_conflict")]
        if not conflicts:
            continue
        accumulated = {"False": [], "True": []}
        candidate = None
        for case in cases:
            if candidate is None and case["sid"] != sid:
                continue
            observation = case.get("organisation_observation", {})
            value = observation.get("features", {}).get(FEATURE)
            if candidate is None and (not observation.get("supported") or type(value) is not bool):
                continue
            if candidate is None:
                accumulated[str(value)].append(case)
                if not all(len({c["raw_sha256"] for c in bucket}) >= formation
                           for bucket in accumulated.values()):
                    continue
                roles = {key: {c["role"] for c in bucket} for key, bucket in accumulated.items()}
                # Exactly identical occurrences have identical feature values.
                # Inconsistent labels block formation; after freezing they are
                # retained as counterevidence, never erased by a new fit.
                if any(len(labels) != 1 for labels in roles.values()):
                    continue
                branches = {key: next(iter(labels)) for key, labels in roles.items()}
                if len(set(branches.values())) < 2:
                    continue
                if not any(c["seq"] <= case["seq"] for c in conflicts):
                    continue
                prior_versions = [v for v in evidence["versions"]
                                  if v["created_at_case"] < case["seq"] and sid in v["mapping"]]
                if not prior_versions:
                    continue
                latest = max((v for v in evidence["versions"] if v["created_at_case"] < case["seq"]),
                             key=lambda v: v["created_at_case"])
                old_mapping = copy.deepcopy(latest["mapping"])
                # Only the reorganised slot uses its latest pre-conflict target.
                # Other slots must not resurrect previously withdrawn mappings.
                old_mapping[sid] = prior_versions[-1]["mapping"][sid]
                prior_cases = [c for c in evidence["cases"] if c["seq"] <= case["seq"]]
                candidate = {"schema": 1, "sid": sid, "feature": FEATURE,
                             "representation": "cue_quote_ownership_v1", "branches": branches,
                             "created_at_case": case["seq"], "old_mapping": old_mapping,
                             "base_version": latest["version"],
                             "reorganised_slot_prior_version": prior_versions[-1]["version"],
                             "formation_inputs": sorted({c["raw_sha256"] for c in prior_cases}),
                             "formation_cases": [c["seq"] for bucket in accumulated.values() for c in bucket],
                             "validation_inputs": {"False": [], "True": []},
                             "counterevidence": [], "old_competence_losses": [],
                             "status": "candidate", "enabled_in_pipeline": False,
                             "feature_library_engineered": True,
                             "independent_semantic_review_verified": False, "development_credit": 0}
                candidate["fingerprint"] = hashlib.sha256(json.dumps(
                    {"sid": sid, "feature": FEATURE, "branches": branches, "old_mapping": old_mapping},
                    sort_keys=True).encode()).hexdigest()
                for old_case in prior_cases:
                    if old_mapping.get(old_case["sid"], "UNKNOWN") == old_case["role"]:
                        if predict(candidate, old_case) != old_case["role"]:
                            candidate["old_competence_losses"].append(old_case["seq"])
                if candidate["old_competence_losses"]:
                    candidate["status"] = "rejected"
                continue
            # Once frozen, the candidate is not changed to fit later feedback.
            if case["sid"] != sid and case["sid"] not in candidate["old_mapping"]:
                continue  # outside this candidate's executable coverage
            if predict(candidate, case) != case["role"]:
                candidate["counterevidence"].append(case["seq"])
                candidate["status"] = "rejected"
                continue
            if case["sid"] != sid:
                continue  # retention evidence is not validation of the new split
            digest = case["raw_sha256"]
            if digest in candidate["formation_inputs"]:
                continue
            if digest in set(candidate["validation_inputs"]["False"] + candidate["validation_inputs"]["True"]):
                continue
            candidate["validation_inputs"][str(value)].append(digest)
            if (candidate["status"] != "rejected" and
                    all(len(bucket) >= validation for bucket in candidate["validation_inputs"].values())):
                candidate["status"] = "locally_validated_candidate"
        if candidate:
            candidates.append(candidate)
    return candidates
