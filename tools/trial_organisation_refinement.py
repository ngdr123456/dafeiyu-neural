"""Constructed experience-selected organisation, no live enable or API calls."""
import copy
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
    with tempfile.TemporaryDirectory(prefix="ego-organisation-") as tmp:
        learner = RelationLearning(Path(tmp) / "relations.json", offline=True)
        def observe(quoted, tail, role=None):
            raw = ('他写下“不要说”，' if quoted else '不要说，') + '都是他们害了' + tail + '。'
            start = raw.index("都是他们")
            return learner.observe(raw, start, start + 4, "blame_external", {"blame_external"},
                                   role or ("ASSERTED" if quoted else "PROHIBITED"),
                                   source="offline_fixture", observer="synthetic_author", turn=1)
        for i in range(5):
            observe(False, "旧项目%d" % i)
        old = copy.deepcopy(report(learner.learner.data))
        for i in range(3):
            observe(True, "形成合同%d" % i)
        formed = copy.deepcopy(report(learner.learner.data)["organisation_candidates"])
        for quoted in (False, True):
            for tail in ("后续比赛", "后续租约"):
                observe(quoted, tail)
        validated = copy.deepcopy(report(learner.learner.data)["organisation_candidates"])
        observe(True, "反例材料", "NEGATED")  # Deliberate counterlabel, not a linguistic claim.
        rejected = report(learner.learner.data)["organisation_candidates"]
    assert before == state_hashes()
    assert formed[0]["old_competence_losses"] == []
    assert validated[0]["status"] == "locally_validated_candidate"
    assert rejected[0]["status"] == "rejected"
    assert formed[0]["fingerprint"] == validated[0]["fingerprint"] == rejected[0]["fingerprint"]
    result = {"simulated": True, "labels_constructed_not_independent_review": True,
              "feature_library_engineered": True, "enabled_in_pipeline": False,
              "development_credit": 0, "state_files_unchanged": len(before),
              "old": old, "formed": formed, "later_validation": validated,
              "counterevidence_rejection": rejected}
    (ROOT / "spec/组织表示细化隔离试验_20261006.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Candidate formed, tested on later inputs, and falsified; real state unchanged:", len(before))


if __name__ == "__main__":
    main()
