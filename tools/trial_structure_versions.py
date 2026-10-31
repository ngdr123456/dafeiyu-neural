"""Constructed offline trial; records are never written to real relation memory."""
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
    with tempfile.TemporaryDirectory(prefix="ego-structure-trial-") as tmp:
        learning = RelationLearning(Path(tmp) / "relations.json", offline=True)
        def observe(tail, role="PROHIBITED", topic="formation"):
            raw = "不要说，都是他们害了" + tail + "。"
            start = raw.index("都是他们")
            learning.observe(raw, start, start + 4, "blame_external", {"blame_external"}, role,
                             source="offline_fixture", observer="current_AI_fixture_author", turn=1, topic_id=topic)
        for i in range(5):
            observe("项目" + str(i))
        formed = report(learning.learner.data)
        observe("这份合同", topic="T01")
        observe("那场比赛", topic="T02")
        transferred = report(learning.learner.data)
        observe("另一个项目", role="ASSERTED", topic="T03")
        contradicted = report(learning.learner.data)
    assert before == state_hashes()
    result = {"simulated": True, "independent_observer": False,
              "state_files_unchanged": len(before), "development_credit": 0,
              "formed": formed, "later_examples": transferred, "contradicted": contradicted}
    (ROOT / "spec/结构版本隔离试验_20261006.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Isolated structure trial recorded; real state unchanged:", len(before))


if __name__ == "__main__":
    main()
