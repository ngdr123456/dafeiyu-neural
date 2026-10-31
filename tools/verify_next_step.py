"""Run offline regressions and mutation checks in a disposable project copy."""
import hashlib
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def hashes():
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (ROOT / "state").rglob("*") if p.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default="spec/下一步验证_20261006.json")
    args = parser.parse_args()
    before = hashes()
    results = []
    with tempfile.TemporaryDirectory(prefix="ego-verification-") as tmp:
        copy = Path(tmp) / "验收副本"
        copy.mkdir()
        for folder in ("engine", "tests", "rules", "corpus", "spec", "tools", "state"):
            shutil.copytree(ROOT / folder, copy / folder,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        for source in ROOT.glob("*.md"):
            shutil.copy2(source, copy / source.name)
        # Fail any real network connect in this process and inherited child processes.
        guard = Path(tmp) / "network_guard"
        guard.mkdir()
        (guard / "sitecustomize.py").write_text(
            "import sys\ndef guard(event, args):\n"
            "    if event == 'socket.connect':\n"
            "        raise RuntimeError('Offline verification: network forbidden')\n"
            "sys.addaudithook(guard)\n", encoding="utf-8")
        env = dict(os.environ, EGO_ROOT=str(copy), PYTHONIOENCODING="utf-8",
                   PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(guard))

        def run(file, label):
            p = subprocess.run([sys.executable, "-B", str(copy / file)],
                               cwd=copy, env=env, capture_output=True, text=True,
                               encoding="utf-8", timeout=60)
            result = {"label": label, "file": file, "exit_code": p.returncode,
                      "stdout": p.stdout, "stderr": p.stderr}
            results.append(result)
            print(label, file, p.returncode, flush=True)
            return p.returncode

        for gate in ("0", "1"):
            env["EGO_GATE_PERCEPTION"] = gate
            for test in sorted((copy / "tests").glob("test_*.py")):
                run("tests/" + test.name, "gate=" + gate)
        run("tools/audit_growth_handoff.py", "historical-replay")
        run("tools/structure_scope_trial.py", "structure-counterfactual")

        source = copy / "engine/devlevel.py"
        original = source.read_text(encoding="utf-8")
        mutation = original.replace(
            "not self.verified and self.failed and self._failure_observed_here",
            "not self.verified and self.failed")
        assert mutation != original
        source.write_text(mutation, encoding="utf-8")
        caught = run("tests/test_growth_continuity.py", "mutation:remove-continuity-guard") != 0
        source.write_text(original, encoding="utf-8")
        learner_source = copy / "engine/behavior_learning.py"
        learner_original = learner_source.read_text(encoding="utf-8")
        learner_mutation = learner_original.replace(
            'if rule and rule["status"] == "active" and rule["target"] in self.actions:',
            'if rule and rule["target"] in self.actions:')
        assert learner_mutation != learner_original
        learner_source.write_text(learner_mutation, encoding="utf-8")
        learner_caught = run("tests/test_behavior_learning.py", "mutation:use-unvalidated-rule") != 0
        learner_source.write_text(learner_original, encoding="utf-8")
        scope_source = copy / "tools/structure_scope_trial.py"
        scope_original = scope_source.read_text(encoding="utf-8")
        scope_mutation = scope_original.replace("or regressions or errors or not all(",
                                                "or regressions or not all(")
        assert scope_mutation != scope_original
        scope_source.write_text(scope_mutation, encoding="utf-8")
        scope_caught = run("tests/test_structure_scope_trial.py", "mutation:ignore-structural-counterexamples") != 0
        scope_source.write_text(scope_original, encoding="utf-8")
        relation_source = copy / "engine/relation_learning.py"
        relation_original = relation_source.read_text(encoding="utf-8")
        relation_mutation = relation_original.replace(
            'or observer in {"self", "candidate"}', '')
        assert relation_mutation != relation_original
        relation_source.write_text(relation_mutation, encoding="utf-8")
        relation_caught = run("tests/test_relation_learning.py", "mutation:accept-self-feedback") != 0
        relation_source.write_text(relation_original, encoding="utf-8")
        bridge_source = copy / "engine/relation_bridge.py"
        bridge_original = bridge_source.read_text(encoding="utf-8")
        bridge_mutation = bridge_original.replace(
            'all(p["role"] in {"NEGATED", "PROHIBITED", "QUOTED"} for p in after.values())',
            'any(p["role"] in {"NEGATED", "PROHIBITED", "QUOTED"} for p in after.values())')
        assert bridge_mutation != bridge_original
        bridge_source.write_text(bridge_mutation, encoding="utf-8")
        bridge_caught = run("tests/test_relation_pipeline.py", "mutation:veto-unreviewed-occurrences") != 0
        bridge_source.write_text(bridge_original, encoding="utf-8")
        evidence_source = copy / "engine/structure_evidence.py"
        evidence_original = evidence_source.read_text(encoding="utf-8")
        evidence_mutation = evidence_original.replace(' or case["raw_sha256"] in excluded', '')
        assert evidence_mutation != evidence_original
        evidence_source.write_text(evidence_mutation, encoding="utf-8")
        evidence_caught = run("tests/test_relation_pipeline.py", "mutation:count-formation-as-transfer") != 0
        evidence_source.write_text(evidence_original, encoding="utf-8")
        organisation_source = copy / "engine/organisation_refinement.py"
        organisation_original = organisation_source.read_text(encoding="utf-8")
        organisation_mutation = organisation_original.replace(
            'if digest in candidate["formation_inputs"]:', 'if False:')
        assert organisation_mutation != organisation_original
        organisation_source.write_text(organisation_mutation, encoding="utf-8")
        organisation_isolation_caught = run("tests/test_organisation_refinement.py",
                                          "mutation:reuse-organisation-formation-input") != 0
        organisation_source.write_text(organisation_original, encoding="utf-8")
        repair_mutations = [
            ("engine/pipeline.py", "tests/test_goal_repairs.py", "erase-dialogue-retrieval",
             'sources = retrieve(self.ledger.effective_entries, raw, getattr(self, "_input_origin", None))',
             'sources = []'),
            ("engine/pipeline.py", "tests/test_goal_repairs.py", "keep-plan-as-actual-action",
             'ren.behavior = action["actual"]', 'ren.behavior = planned_behavior'),
            ("engine/think.py", "tests/test_content_fidelity.py", "bypass-content-review",
             'if not bad and self.verify_content and text !=', 'if False and text !='),
            ("engine/organisation_refinement.py", "tests/test_organisation_refinement.py", "ignore-other-context-counterexample",
             'if case["sid"] != sid and case["sid"] not in candidate["old_mapping"]:',
             'if case["sid"] != sid:'),
            ("engine/behavior_learning.py", "tests/test_atomic_persistence.py", "drop-transient-lock-retry",
             'for attempt in range(4):', 'for attempt in range(1):'),
            ("engine/pipeline.py", "tests/test_relational_memory.py", "disconnect-relational-memory",
             'if self.use_relational_memory:', 'if False:'),
            ("engine/relational_memory.py", "tests/test_relational_memory.py", "forget-entity-in-correction-key",
             'key = (item["subject"], item["predicate"], item["time"])',
             'key = ("", item["predicate"], item["time"])'),
            ("engine/relational_memory.py", "tests/test_relational_memory.py", "overwrite-unresolved-conflict",
             'active.extend(asserted)', 'active[:] = asserted'),
            ("engine/relational_memory.py", "tests/test_relational_memory.py", "treat-quoted-relation-as-fact",
             'if n["role"] == "ASSERTED"]', 'if n["role"] in {"ASSERTED", "QUOTED"}]'),
            ("engine/understand.py", "tests/test_training_interruptions.py", "remove-disconnect-retry",
             'for attempt in range(2):', 'for attempt in range(1):'),
            ("engine/train.py", "tests/test_training_interruptions.py", "credit-empty-session",
             'if session_turns == session_len:', 'if True:'),
            ("engine/action_plan.py", "tests/test_adaptive_action_plan.py", "ignore-latest-training-failure",
             'if signals.get("training_run_failed"):', 'if False:'),
            ("engine/relation_learning.py", "tests/test_organisation_runtime.py", "disconnect-organisation-execution",
             'if self.use_organisation:', 'if False:'),
            ("engine/organisation_runtime.py", "tests/test_organisation_runtime.py", "revive-withdrawn-organisation",
             'if record["status"] == "withdrawn" or not eligible:', 'if not eligible and record["status"] != "withdrawn":'),
            ("engine/organisation_runtime.py", "tests/test_organisation_runtime.py", "trust-untraced-validation",
             'and _sources_verified(candidate, evidence))', ')'),
            ("engine/understand.py", "tests/test_relation_pipeline.py", "omit-overlapping-position-manifest",
             'if positions:', 'if False:'),
            ("engine/pipeline.py", "tests/test_self_action.py", "disconnect-own-task-memory",
             'fr.own_task = prior_tasks(self.ledger.effective_entries, raw, self._input_origin, evidence_basis)',
             'fr.own_task = {}'),
            ("engine/think.py", "tests/test_self_action.py", "ignore-prior-own-failure",
             'if previous["text"] == text:', 'if False:'),
            ("engine/think.py", "tests/test_self_action.py", "permanently-ban-rejected-candidate",
             'if attempt == 0:', 'if True:'),
            ("engine/self_action.py", "tests/test_self_action.py", "mistake-permission-for-goal-fulfillment",
             '"semantic_goal_fit": "UNKNOWN"', '"semantic_goal_fit": "CONFIRMED"'),
            ("engine/pipeline.py", "tests/test_self_goal.py", "disconnect-goal-planning",
             'if self.use_goal_planning:', 'if False:'),
            ("engine/think.py", "tests/test_self_goal.py", "bypass-chosen-goal-check",
             'if goal_check and not goal_check["matched"]:', 'if False:'),
            ("engine/self_goal.py", "tests/test_self_goal.py", "reuse-other-object-commitment",
             'if key in relevant:', 'if True:'),
            ("engine/self_goal.py", "tests/test_self_goal.py", "ignore-goal-retirement",
             'for retired in packet.get("retired_ids", []):', 'for retired in []:'),
            ("engine/self_goal.py", "tests/test_self_goal.py", "carry-source-invalidated-goal",
             'and item["goal"]["id"] in allowed]', ']'),
            ("engine/self_goal.py", "tests/test_self_goal.py", "mistake-literal-outcome-for-semantic-fit",
             '"semantic_goal_fit": "UNKNOWN"', '"semantic_goal_fit": "CONFIRMED"'),
            ("engine/self_goal.py", "tests/test_self_goal.py", "skip-goal-source-hash-proof",
             'or fingerprint(raw) != node.get("raw_sha256")', ''),
            ("engine/pipeline.py", "tests/test_memory_scope.py", "forget-positive-history-witness",
             'memory_scope=memory_scope)', 'memory_scope={})'),
            ("engine/think.py", "tests/test_memory_scope.py", "bypass-positive-history-scope-check",
             'bad.extend(check_memory_scope(frame, text))', 'pass')]
        repair_mutations_caught = {}
        for file, test, name, old, replacement in repair_mutations:
            target = copy / file
            saved = target.read_text(encoding="utf-8")
            modified = saved.replace(old, replacement)
            assert modified != saved
            target.write_text(modified, encoding="utf-8")
            repair_mutations_caught[name] = run(test, "mutation:" + name) != 0
            target.write_text(saved, encoding="utf-8")
        organisation_mutation = organisation_original.replace(
            'candidate["status"] = "rejected"', 'candidate["status"] = "candidate"')
        assert organisation_mutation != organisation_original
        organisation_source.write_text(organisation_mutation, encoding="utf-8")
        organisation_counterexample_caught = run("tests/test_organisation_refinement.py",
                                                "mutation:ignore-organisation-counterexample") != 0
        organisation_source.write_text(organisation_original, encoding="utf-8")
    if before != hashes():
        raise RuntimeError("Real state changed")
    report = {"state_files_unchanged": len(before), "network_forbidden": True,
              "mutation_caught": caught, "learner_mutation_caught": learner_caught,
              "structure_mutation_caught": scope_caught,
              "relation_mutation_caught": relation_caught,
              "bridge_mutation_caught": bridge_caught,
              "evidence_mutation_caught": evidence_caught, "results": results}
    report.update(organisation_isolation_mutation_caught=organisation_isolation_caught,
                  organisation_counterexample_mutation_caught=organisation_counterexample_caught,
                  repair_mutations_caught=repair_mutations_caught)
    failures = [r for r in results if not r["label"].startswith("mutation:")
                and r["exit_code"] != 0]
    sys.path.insert(0, str(ROOT / "engine"))
    from action_plan import source_hashes
    report["source_hashes"] = source_hashes(ROOT)
    report["all_checks_passed"] = not bool(failures) and all([
        caught, learner_caught, scope_caught, relation_caught, bridge_caught,
        evidence_caught, organisation_isolation_caught, organisation_counterexample_caught,
        *repair_mutations_caught.values()])
    (ROOT / args.report).write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Summary:", len(failures), "failures; mutation caught:", caught,
          "; state unchanged:", len(before))
    return int(not report["all_checks_passed"])


if __name__ == "__main__":
    raise SystemExit(main())
