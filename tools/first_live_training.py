"""Explicit small live acceptance run. Calls configured API; never prints credentials."""
import argparse
import hashlib
import json
import os
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))


def hashes():
    return {str(p.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (ROOT / "state").rglob("*") if p.is_file()}


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] \
        if path.exists() else []


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Make real API calls and record up to six turns")
    parser.add_argument("--turns", type=int, default=6, choices=range(1, 7))
    parser.add_argument("--source", choices=["corpus", "topics"], default="corpus")
    args = parser.parse_args()
    if not args.run:
        parser.print_help()
        return 0
    os.environ["EGO_ROOT"] = str(ROOT)
    os.environ["EGO_GATE_PERCEPTION"] = "1"
    from understand import ApiReader
    from devlevel import DevLevel
    from markers import load_marker_rules
    from train import Trainer, TrainingControl
    from input_provenance import digest
    stamp = time.strftime("%Y%m%d_%H%M%S")
    report_path = ROOT / "spec" / ("首批真实训练验收_" + stamp + ".json")
    before = hashes()
    backup = ROOT / "build" / "training_backups" / ("before_" + stamp + ".zip")
    backup.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(backup, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in before:
            archive.write(ROOT / name, name)
    baseline_before = json.loads((ROOT / "state/devlevel_verified.json").read_text(encoding="utf-8"))
    report = {"run_id": stamp, "requested_turns": args.turns, "gate_perception": True,
              "input_kind": "tutor_generated", "independent_human_input_verified": False,
              "independent_semantic_review_verified": False,
              "backup": str(backup), "state_before": before, "turns": []}
    train_dir = ROOT / "state/train"
    ledger_before = rows(train_dir / "ledger.jsonl")
    eval_before = rows(train_dir / "eval.jsonl")
    try:
        reader = ApiReader(timeout=45, retries=0)
        if not reader.available:
            report.update(ok=False, reason="api_key_unavailable", preflight_calls=0)
        else:
            visible = DevLevel().visible()
            spec = [rule for rule in load_marker_rules()["markers"] if rule["id"] in visible]
            probe = reader.read("我还没想清楚这件事。", None, spec)
            report["preflight"] = {"ok": probe.ok, "calls": reader.calls,
                                   "error": probe.error, "usage": reader.last_usage}
            print("API preflight:", "passed" if probe.ok else "failed", flush=True)
            if not probe.ok:
                report.update(ok=False, reason="api_preflight_failed")
            else:
                control = TrainingControl()
                def completed(rec):
                    report["turns"].append(rec)
                    print("Completed:", rec["n"], "API:", rec["api_ok"],
                          "source:", rec["input_origin"]["kind"], "topic:", rec["topic_id"], flush=True)
                control.on_turn = completed
                trainer = Trainer(gate_perception=True, use_api=True, use_think=True)
                result = trainer.run(rounds=1, session_len=2, source=args.source, tutor=True,
                                     seed=20261006 + args.turns, control=control, strict=True, max_turns=args.turns)
                report["training"] = result
                new_rows = rows(train_dir / "ledger.jsonl")[len(ledger_before):]
                new_evals = rows(train_dir / "eval.jsonl")[len(eval_before):]
                checks = {"requested_ledger_rows": len(new_rows) == args.turns,
                          "requested_evaluation_rows": len(new_evals) == args.turns,
                          "all_api_readings_ok": bool(report["turns"]) and all(r["api_ok"] for r in report["turns"]),
                          "tutor_evaluations_ok": bool(new_evals) and all(r["tutor"].get("ok") for r in new_evals),
                          "evaluation_internals_present": bool(new_evals) and all(r["tutor"].get("saw_internals") for r in new_evals),
                          "provenance_matches": len(new_rows) == len(new_evals) and all(
                              r.get("input_origin") == e.get("input_origin") and
                              r["input_origin"]["input_sha256"] == digest(r["raw_input"]) and
                              r["topic_id"] == r["input_origin"]["topic_id"] and
                              e["input_source"] == "tutor_generated"
                              for r, e in zip(new_rows, new_evals))}
                report.update(checks=checks, ok=bool(result["ok"] and all(checks.values())))
                report["new_ledger_rows"] = len(new_rows)
                report["new_evaluation_rows"] = len(new_evals)
    except Exception as exc:
        report.update(ok=False, reason="exception:" + type(exc).__name__)
    finally:
        after = hashes()
        report["state_after"] = after
        report["changed_state_files"] = [name for name in sorted(set(before) | set(after))
                                         if before.get(name) != after.get(name)]
        report["interactive_ledger_unchanged"] = before.get("state/ledger.jsonl") == after.get("state/ledger.jsonl")
        report["legacy_archive_unchanged"] = all(before[name] == after.get(name) for name in before
                                                if name.startswith("state/development_legacy_20261006/"))
        baseline_after = json.loads((ROOT / "state/devlevel_verified.json").read_text(encoding="utf-8"))
        report["development"] = {"before_level": baseline_before["level"], "after_level": baseline_after["level"],
                                 "before_equilibration": baseline_before["equilibration"],
                                 "after_equilibration": baseline_after["equilibration"]}
        report["ok"] = bool(report.get("ok") and report["interactive_ledger_unchanged"]
                            and report["legacy_archive_unchanged"])
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Acceptance:", report["ok"], "Report:", str(report_path), flush=True)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
