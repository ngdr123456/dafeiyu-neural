"""Small current-source API checks; no formal training or natural failure claim."""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "engine")]
from action_plan import LIVE, source_hashes, write_report
from tools.structure_scope_trial import state_hashes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    if not parser.parse_args().run:
        print("Use --run for disposable API checks; no calls made.")
        return 0
    before, initial = state_hashes(), source_hashes(ROOT)
    paths = ["spec/自身作答闭环模型诊断_20261008.json", "spec/自身作答闭环组织诊断_20261008.json",
             "spec/自身作答闭环记忆诊断_20261008.json"]
    commands = [["tools/trial_self_action.py", "--api", "--report", paths[0]],
                ["tools/trial_organisation_runtime.py", "--api", "--report", paths[1]],
                ["tools/verify_goal_live.py", "--run", "--relations", "--report", paths[2]]]
    parts, cases = [], []
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    for command, path in zip(commands, paths):
        completed = subprocess.run([sys.executable, "-B", *command], cwd=ROOT, env=env, timeout=900)
        report = json.loads((ROOT / path).read_text(encoding="utf-8")) if (ROOT / path).exists() else {}
        valid = completed.returncode == 0 and report.get("passed") is True and report.get("source_hashes") == initial
        parts.append({"path": path, "exit_code": completed.returncode, "current_source_passed": valid})
        cases.extend(dict(case, component=path) for case in report.get("cases", []))
        if not valid:
            cases.append({"case": "component_not_passed:" + path, "passed": False})
            break
    if state_hashes() != before or source_hashes(ROOT) != initial:
        raise RuntimeError("Real state/source changed during live verification")
    result = {"schema": 1, "scope": "scripted_memory_rule_execution_and_own_revision",
              "passed": len(parts) == 3 and all(p["current_source_passed"] for p in parts),
              "source_hashes": initial, "parts": parts, "cases": cases, "real_API": True,
              "formal_training": False, "scripted_inputs": True, "independent_semantics_verified": False,
              "real_state_files_unchanged": len(before), "development_credit": 0,
              "claims": "Engineered failure injection and correlated opinions; own operation evidence, not autonomous human goals."}
    (ROOT / LIVE).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(ROOT)
    print(json.dumps({"passed": result["passed"], "cases": len(cases), "state_unchanged": len(before)}, ensure_ascii=False))
    return int(not result["passed"])


if __name__ == "__main__":
    raise SystemExit(main())
