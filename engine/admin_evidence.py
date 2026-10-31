"""Read-only evidence packet: latest training and source-bound engineering checks.

The reviewer sees the scope and age of each piece. This does not independently
certify model semantics, developmental stages, or execute proposed changes.
"""
import json
import hashlib
from pathlib import Path


def _read(path, fallback):
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else fallback


def source_fingerprint(root):
    from action_plan import source_hashes
    return hashlib.sha256(json.dumps(source_hashes(root), sort_keys=True).encode()).hexdigest()


def snapshot(root):
    from action_plan import REGRESSION, LIVE, FOUNDATION, ORGANISATION, SELF_ACTION, SELF_GOAL, source_hashes
    from train import EVAL_SCHEMA
    root = Path(root)
    current = source_hashes(root)
    progress = _read(root / "state/train/progress.json", {})
    latest = {key: progress.get(key) for key in ("run_id", "last_run", "turns_added", "requested_turns",
              "evals", "failure", "training_complete", "outcome", "eval_schema", "gate_perception",
              "gate_observed_in_turn", "failure_diagnostic", "source_fingerprint", "source_unchanged_during_run")}
    latest["source_matches_current"] = progress.get("source_fingerprint") == source_fingerprint(root)
    latest["failure_observed"] = bool(progress.get("failure") and progress.get("failure") != "user_stopped")
    latest["metadata_is_current_schema"] = progress.get("eval_schema") == EVAL_SCHEMA
    counts = {}
    latest_evals = 0
    path = root / "state/train/eval.jsonl"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            schema = str(row.get("eval_schema", "unknown"))
            counts[schema] = counts.get(schema, 0) + 1
            if (row.get("input_origin") or {}).get("run_id") == latest["run_id"]:
                latest_evals += 1
    artefacts = []
    for label, name in (("regression", REGRESSION), ("live_diagnostic", LIVE), ("relation_foundation", FOUNDATION),
                        ("bounded_rule_execution", ORGANISATION), ("own_response_revision", SELF_ACTION),
                        ("declared_goal_process", SELF_GOAL)):
        report = _read(root / name, {})
        fresh = bool(report.get("source_hashes") == current and report)
        result = report.get("all_checks_passed") if label == "regression" else report.get("passed")
        artefacts.append({"kind": label, "path": name, "exists": bool(report), "source_matches": fresh,
                          "passed_for_current_source": result if fresh else None,
                          "historical_passed": result, "cases": len(report.get("cases", [])),
                          "scope": report.get("scope") or ("engineering_tests" if label == "regression" else "scripted_local_cases"),
                          "independent_semantics_verified": False, "development_credit": 0})
    return {"schema": 1, "latest_training": latest, "latest_run_evaluations": latest_evals,
            "has_material": bool(latest["run_id"] or any(item["exists"] for item in artefacts)),
            "evaluation_schema_counts": counts, "current_eval_schema": EVAL_SCHEMA,
            "current_schema_evaluations": counts.get(str(EVAL_SCHEMA), 0), "artefacts": artefacts,
            "development_credit": 0, "independent_review_verified": False}
