"""Constructed conflicts, temporary memories, no network or real training."""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.relation_learning import RelationLearning
from engine.structure_evidence import report
from tools.structure_scope_trial import state_hashes


def main():
    before = state_hashes()
    reports = {}
    with tempfile.TemporaryDirectory(prefix="ego-conflicts-") as tmp:
        for scenario in ("same_occurrence", "different_inputs", "different_occurrences"):
            learner = RelationLearning(Path(tmp) / (scenario + ".json"), offline=True)
            def observe(raw, role, observer="synthetic_author", last=False):
                start = raw.rindex("都是他们") if last else raw.index("都是他们")
                return learner.observe(raw, start, start + 4, "blame_external", {"blame_external"},
                                       role, source="offline_fixture", observer=observer, turn=1)
            if scenario == "different_occurrences":
                raw = "都是他们说的都是他们做的。"
                observe(raw, "QUOTED")
                observe(raw, "ASSERTED", last=True)
            else:
                for i in range(5):
                    observe("不要说，都是他们害了项目%d。" % i, "PROHIBITED")
                raw = ("不要说，都是他们害了项目0。" if scenario == "same_occurrence"
                       else "不要说，都是他们害了另一份合同。")
                observe(raw, "ASSERTED", observer="synthetic_second_author")
            reports[scenario] = report(learner.learner.data)
    assert before == state_hashes(), "Real state changed"
    result = {"simulated": True, "feedback_is_constructed_not_human_gold": True,
              "state_files_unchanged": len(before), "development_credit": 0, "scenarios": reports}
    (ROOT / "spec/结构冲突隔离试验_20261006.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Three constructed conflicts verified; real state unchanged:", len(before))


if __name__ == "__main__":
    main()
