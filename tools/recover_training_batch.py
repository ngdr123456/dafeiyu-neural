"""One authorised six-turn formal recovery batch after current offline checks.

Uses real training paths, appends real API experiences and keeps the failed run.
This is model-generated training, never a verified human or developmental proof.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from action_plan import REGRESSION, FOUNDATION, LIVE, source_hashes, write_report
from train import Trainer


def read(path, fallback=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else fallback


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.exists() else []


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if not args.run:
        print("Use --run to perform the single real six-turn recovery batch.")
        return 0
    current = source_hashes(ROOT)
    for name, flag in ((REGRESSION, "all_checks_passed"), (FOUNDATION, "passed")):
        proof = read(ROOT / name, {})
        if proof.get(flag) is not True or proof.get("source_hashes") != current:
            raise RuntimeError("Current offline check required: " + name)
    progress_path = ROOT / "state/train/progress.json"
    failed = read(progress_path, {})
    if failed.get("failure") != "tutor_generation_failed" or failed.get("turns_added") != 0:
        raise RuntimeError("Recovery scope requires the observed zero-turn tutor failure")
    archive = ROOT / "spec/训练首轮断线原始记录_20261008.json"
    if not archive.exists():
        archive.write_bytes(progress_path.read_bytes())
    before_ledger = (ROOT / "state/train/ledger.jsonl").read_bytes()
    before_evals = (ROOT / "state/train/eval.jsonl").read_bytes()
    trainer = Trainer(use_api=True, use_think=True, gate_perception=True)
    result = trainer.run(rounds=1, session_len=2, source="corpus", tutor=True, strict=True, max_turns=6)
    run_id = result.get("run_id")
    experiences = [row for row in rows(ROOT / "state/train/ledger.jsonl") if run_id and (row.get("input_origin") or {}).get("run_id") == run_id]
    evaluations = [row for row in rows(ROOT / "state/train/eval.jsonl") if run_id and (row.get("input_origin") or {}).get("run_id") == run_id]
    after_ledger = (ROOT / "state/train/ledger.jsonl").read_bytes()
    after_evals = (ROOT / "state/train/eval.jsonl").read_bytes()
    if current != source_hashes(ROOT) or not after_ledger.startswith(before_ledger) or not after_evals.startswith(before_evals):
        raise RuntimeError("Source changed or historical records were overwritten")
    cases = [{"case": "formal_recovery_turn:%d" % (i + 1), "passed": bool((row.get("tutor") or {}).get("ok")),
              "input": row.get("input"), "output": row.get("output"), "input_origin": row.get("input_origin"),
              "tutor": row.get("tutor"), "behavior": row.get("behavior"), "mech": row.get("mech")}
             for i, row in enumerate(evaluations)]
    passed = bool(result.get("ok") and result.get("training_complete") and len(experiences) == len(evaluations) == 6
                  and result["sessions_added"] == 3 and result["rounds_added"] == 1 and all(c["passed"] for c in cases))
    report = {"schema": 1, "date": "2026-10-08", "passed": passed, "source_hashes": current,
              "scope": "one_model_generated_formal_recovery_batch", "real_API": True, "formal_training": True,
              "scripted_inputs": False, "model_generated_inputs": True, "cases": cases, "run_id": run_id,
              "progress": result, "original_failure_archived": archive.relative_to(ROOT).as_posix(),
              "historical_ledger_prefix_preserved": True, "historical_evaluation_prefix_preserved": True,
              "prior_ledger_sha256": hashlib.sha256(before_ledger).hexdigest(),
              "independent_semantic_review_verified": False, "development_credit": 0,
              "claims": "recovery batch only, not the earlier thirteen diagnostic cases or human development"}
    (ROOT / LIVE).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(ROOT)
    print(json.dumps({"passed": passed, "run_id": run_id, "turns": len(experiences), "evaluations": len(evaluations)}, ensure_ascii=False))
    return int(not passed)


if __name__ == "__main__":
    raise SystemExit(main())
