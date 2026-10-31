"""Read-only goal audit with isolated, synthetic probes; never calls an API."""
import ast
import argparse
import hashlib
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
sys.path.insert(0, str(ROOT))


def hashes():
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (ROOT / "state").rglob("*") if p.is_file()}


def rows(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines()
            if line.strip()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default="spec/目标修正复查_20261007.json")
    args = parser.parse_args()
    before = hashes()
    def network_guard(event, args):
        if event == "socket.connect":
            raise RuntimeError("Goal audit forbids network access")
    sys.addaudithook(network_guard)
    from pipeline import Pipeline
    from render import Speech
    from think import Thinker
    from mechanism import Mechanism
    from relation_learning import RelationLearning
    from structure_evidence import report as structure_report
    from organisation_refinement import predict as refinement_predict

    class CaptureThinker:
        def __init__(self):
            self.frames = []
        def think(self, frame):
            self.frames.append(frame.user_text())
            return Speech("那笔押金现在由谁收着？", True, "synthetic_capture_no_API")

    # Actual Pipeline call, isolated files, identical current question after
    # different named contacts. This checks the data delivered to the brain,
    # not an opinion about how a real model would answer.
    contexts = []
    with tempfile.TemporaryDirectory(prefix="ego-goal-audit-") as tmp:
        for i, name in enumerate(("李老师", "周老师")):
            workspace = Path(tmp) / str(i)
            workspace.mkdir()
            p = Pipeline(ledger_path=str(workspace / "state/ledger.jsonl"),
                         character_path=str(workspace / "state/character.json"),
                         devlevel_path=str(workspace / "state/devlevel_verified.json"),
                         carry_root=str(workspace), gate_perception=True,
                         use_api=False, use_think=False, use_render=False, auto_audit=False)
            first = "押金由%s收着，我要先联系%s。" % (name, name)
            p.turn(first)
            capture = CaptureThinker()
            p.thinker = capture
            current_result = p.turn("那我现在该联系谁？")
            frame = capture.frames[-1]
            contexts.append({"prior_input": first, "current_input": "那我现在该联系谁？",
                             "prior_fact_in_ledger": first in (workspace / "state/ledger.jsonl").read_text(encoding="utf-8"),
                             "prior_contact_in_brain_frame": name in frame,
                             "ledger_behavior_after_brain_output": current_result.behavior,
                             "brain_output": current_result.output,
                             "frame_sha256": hashlib.sha256(frame.encode()).hexdigest()})
        memory_probe = {"synthetic": True, "real_pipeline": True, "API_called": False,
                        "cases": contexts,
                        "different_histories_produce_identical_brain_frame":
                            contexts[0]["frame_sha256"] == contexts[1]["frame_sha256"]}
        refinement = RelationLearning(Path(tmp) / "refinement.json", offline=True)
        def feedback(raw, role):
            start = raw.index("都是他们")
            return refinement.observe(raw, start, start + 4, "blame_external", {"blame_external"},
                                      role, source="offline_fixture", observer="synthetic_author", turn=1)
        for i in range(5):
            feedback("不能说，都是他们害了背景项目%d。" % i, "NEGATED")
            feedback("不要说，都是他们害了形成项目%d。" % i, "PROHIBITED")
        for i in range(3):
            feedback("他写下“不要说”，都是他们害了形成合同%d。" % i, "ASSERTED")
        for i in range(2):
            feedback("不要说，都是他们害了后续项目%d。" % i, "PROHIBITED")
            feedback("他写下“不要说”，都是他们害了后续合同%d。" % i, "ASSERTED")
        candidates = structure_report(refinement.learner.data)["organisation_candidates"]
        assert len(candidates) == 1 and candidates[0]["status"] == "locally_validated_candidate"
        feedback("不能说，都是他们害了后续背景反例。", "ASSERTED")
        candidate = structure_report(refinement.learner.data)["organisation_candidates"][0]
        latest_case = refinement.learner.data["structure_evidence"]["cases"][-1]
        cross_context_probe = {"synthetic": True, "counterlabel_is_deliberate_not_a_semantic_claim": True,
                               "candidate_status_after_other_context_counterexample": candidate["status"],
                               "candidate_prediction": refinement_predict(candidate, latest_case),
                               "feedback_role": latest_case["role"],
                               "cross_context_counterexample_ignored":
                                   refinement_predict(candidate, latest_case) != latest_case["role"]
                                   and candidate["status"] == "locally_validated_candidate",
                               "enabled_in_pipeline": candidate["enabled_in_pipeline"]}
        workspace = Path(tmp) / "action"
        workspace.mkdir()
        action_pipe = Pipeline(ledger_path=str(workspace / "state/ledger.jsonl"),
                               character_path=str(workspace / "state/character.json"),
                               devlevel_path=str(workspace / "state/devlevel_verified.json"),
                               carry_root=str(workspace), gate_perception=True,
                               use_api=False, use_think=False, use_render=False, auto_audit=False)
        capture = CaptureThinker()
        action_pipe.thinker = capture
        result = action_pipe.turn("我站在那里闻了半小时桂花。")
        action_probe = {"synthetic_brain": True, "real_pipeline": True,
                        "brain_output": result.output, "recorded_behavior": result.behavior,
                        "output_is_an_explicit_question": result.output.endswith("？"),
                        "output_passes_existing_gate": not Thinker.check(result.output, "我站在那里闻了半小时桂花。"),
                        "planned_behavior": result.planned_behavior,
                        "action_observation": result.action_observation}

    # The error function receives channels, not the input's proposition or the
    # model's response correctness. Equal channel histories yield equal e.
    error_traces = []
    for inputs in (("这件事仍然如此。", "前面的说法没有改变。"),
                   ("这件事不是如此。", "我明确反驳前面的说法。")):
        mechanism = Mechanism()
        trace = []
        for i in range(16):
            state = mechanism.step(markers=[], raw=inputs[i % 2], channel="B",
                                   context_key="synthetic_same_context", stem_level=None,
                                   engaged=True)
            trace.append(state.to_dict()["e"])
        error_traces.append(trace)
    error_probe = {"synthetic": True, "real_mechanism": True,
                   "same_channel_different_content_same_e": error_traces[0] == error_traces[1],
                   "e_trace": error_traces[0],
                   "interpretation": "channel pressure proxy does not measure semantic correctness"}

    gate_examples = [
        {"raw": "我站在那里闻了半小时桂花。", "candidate": "那半小时里没人在看表。",
         "issue": "unsupported_added_detail"},
        {"raw": "押金还没有退，那我现在该联系谁？",
         "candidate": "模型和架构是别人定的，我左右不了。", "issue": "off_topic"}]
    for example in gate_examples:
        example["violations"] = Thinker.check(example["candidate"], example["raw"])
        example["accepted_by_mechanical_gate"] = not example["violations"]

    progress_path = ROOT / "state/train/progress.json"
    progress = json.loads(progress_path.read_text(encoding="utf-8")) if progress_path.exists() else {}
    ledger = rows(ROOT / "state/train/ledger.jsonl")
    evaluations = rows(ROOT / "state/train/eval.jsonl")
    run_id = progress.get("run_id")
    current = [r for r in ledger if (r.get("input_origin") or {}).get("run_id") == run_id]
    current_evals = [r for r in evaluations if (r.get("input_origin") or {}).get("run_id") == run_id]
    baseline = json.loads((ROOT / "state/devlevel_verified.json").read_text(encoding="utf-8"))
    from devlevel import DevLevel
    development = DevLevel(str(ROOT / "state/devlevel_verified.json"))
    memory_paths = ["state/behavior_rules.json", "state/relation_rules.json",
                    "state/train/behavior_rules.json", "state/train/relation_rules.json"]
    memory = {}
    for relative in memory_paths:
        path = ROOT / relative
        entry = {"exists": path.exists()}
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            entry["rule_status_counts"] = dict(Counter(r.get("status") for r in data.get("rules", {}).values()))
        memory[relative] = entry
    claims = {}
    for book in ("DB", "E", "M"):
        table = rows(ROOT / ("spec/观点总表/" + book + ".jsonl"))
        claims[book] = {"total": len(table), "historical_status_counts": dict(Counter(r.get("status") for r in table)),
                        "note": "historical labels, not revalidated capability coverage"}
    source_locations = {}
    targets = {"pipeline.py": {"_build_frame", "turn"}, "think.py": {"check", "think"},
               "mechanism.py": {"_observe", "_layer1", "_layer2", "_layer3"},
               "train.py": {"run", "_pipe", "_record_eval", "_regrow"},
               "devlevel.py": {"update"}, "organisation_refinement.py": {"derive", "predict"}}
    for file, names in targets.items():
        path = ROOT / "engine" / file
        source_locations[file] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                  "functions": {n.name: n.lineno for n in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig")))
                                                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names}}
    after = hashes()
    if before != after:
        raise RuntimeError("Real state changed during audit; refusing an unchanged-state claim")
    result = {"audit_date": "2026-10-07", "network_forbidden": True,
              "state_files_unchanged": len(before), "state_hashes": before,
              "brain_context_probe": memory_probe, "semantic_error_probe": error_probe,
              "refinement_cross_context_probe": cross_context_probe,
              "realized_behavior_probe": action_probe,
              "mechanical_gate_probe": {"synthetic": True, "cases": gate_examples},
              "latest_training": {"run_id": run_id, "last_run": progress.get("last_run"),
                                  "turns": len(current), "evals": len(current_evals),
                                  "META_turns": sum(r.get("channel") == "META" for r in current),
                                  "carried_mechanism_turns": sum(bool((r.get("mech") or {}).get("_carried")) for r in current),
                                  "evaluation_problem_counts": dict(Counter((r.get("tutor") or {}).get("problem") for r in current_evals))},
              "development": dict({key: baseline.get(key) for key in ("level", "equilibration", "history", "evidence_policy")},
                                  allowed_self_rules=sorted(development.self_rules()),
                                  visible_marker_count=len(development.visible())),
              "learning_memories": memory, "historical_claim_inventory": claims,
              "source_locations": source_locations}
    (ROOT / args.report).write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"real_state_files_unchanged": len(before),
                      "different_histories_same_frame": memory_probe["different_histories_produce_identical_brain_frame"],
                      "same_channels_same_e": error_probe["same_channel_different_content_same_e"],
                      "unsafe_examples_passing_gate": sum(x["accepted_by_mechanical_gate"] for x in gate_examples),
                      "latest_training": result["latest_training"], "memories": memory,
                      "historical_claim_inventory": claims}, ensure_ascii=False))


if __name__ == "__main__":
    main()
