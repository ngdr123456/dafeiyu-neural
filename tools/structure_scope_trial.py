"""Offline, falsifiable scope trial. Never imported by the production pipeline."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.markers import MarkerEngine
from tests.corpus_probe import CASES

TARGET = "blame_external"
PROTOCOL = ROOT / "spec/结构试验_作用域协议_20261006.json"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def state_hashes():
    return {p.relative_to(ROOT).as_posix(): digest(p)
            for p in (ROOT / "state").rglob("*") if p.is_file()}


def negated_at(text, phrase, pos):
    if phrase in MarkerEngine._NEGATION_IMMUNE:
        return False
    prefix = text[max(0, pos - 6):pos]
    # Same literal negators as the original method; no semantic inference.
    return any(n in prefix for n in ("不", "没", "别", "并非", "不是", "谁说", "有人说"))


class OccurrenceEngine(MarkerEngine):
    @staticmethod
    def _is_negated_or_quoted(text, phrase):
        # The inherited detector used the first occurrence for every match.
        # Check each occurrence, with its own literal prefix. No new marker words.
        positions = [m.start() for m in re.finditer(re.escape(phrase), text)]
        return bool(positions) and all(negated_at(text, phrase, pos) for pos in positions)


class ClauseScopeCandidate:
    """Engineered candidate, NOT experience-acquired or approved for use."""
    def __init__(self, visible=None):
        self.base = MarkerEngine(visible=visible)
        self.local = OccurrenceEngine(rules=self.base.rules, topics=self.base.topics)
        self.visible = visible

    def inspect(self, raw):
        if self.visible is not None and TARGET not in self.visible:
            return {"fired": False, "reason": "not_visible", "nodes": []}
        # Preserve all existing whole-input explicit counterexamples, including
        # mixed admission of one's responsibility. Splitting must not bypass them.
        rule = self.base._markers[TARGET]
        veto = any(re.search(p, raw) for p in rule.get("counterexample_regex", []))
        # Quoted syntax isn't supported by this candidate. Fall back, explicitly.
        if any(c in raw for c in '“”‘’"「」『』'):
            return {"fired": bool(self.base._detect(TARGET, raw)),
                    "reason": "unsupported_quote_original_result", "nodes": []}
        nodes = []
        for part in re.finditer(r"[^，,。.!！?？;；\n]+", raw):
            clause = part.group()
            hit = self.local._detect(TARGET, clause)
            for phrase in rule.get("patterns", []):
                for occurrence in re.finditer(re.escape(phrase), clause):
                    start = part.start() + occurrence.start()
                    end = part.start() + occurrence.end()
                    negated = negated_at(clause, phrase, occurrence.start())
                    nodes.append({"start": start, "end": end, "text": raw[start:end],
                                  "clause_start": part.start(), "clause_end": part.end(),
                                  "negated": negated,
                                  "accepted": bool(hit) and not negated and not veto})
        return {"fired": any(n["accepted"] for n in nodes),
                "reason": "whole_input_counterexample" if veto else "local_scope_candidate",
                "nodes": nodes}


def verdict(discovery_fixed, regressions, errors, span_ok, visibility_ok,
            state_unchanged, independently_reviewed=False):
    # Independence is never inferred from distinct texts or from internal accuracy.
    if not discovery_fixed or regressions or errors or not all(
            (span_ok, visibility_ok, state_unchanged)):
        return "rejected"
    return "external_review_required" if not independently_reviewed else "reviewed_prototype"


def evaluate(challenges):
    before = state_hashes()
    protocol_bytes = PROTOCOL.read_bytes()
    candidate = ClauseScopeCandidate()
    old = candidate.base
    rows = []
    for i, (raw, labels, gap, note) in enumerate(CASES):
        rows.append({"id": f"history-{i+1}", "source": "prior_AI_diagnostic_corpus",
                     "split": "historical", "raw": raw, "expected": TARGET in labels,
                     "note": note})
    for row in challenges:
        rows.append(dict(row, source="current_AI_constructed_challenge", split="challenge"))
    for row in rows:
        row["old"] = bool(old._detect(TARGET, row["raw"]))
        row["candidate"] = candidate.inspect(row["raw"])
    regression = [r["id"] for r in rows if r["split"] == "historical"
                  and r["old"] == r["expected"]
                  and r["candidate"]["fired"] != r["expected"]]
    errors = [r["id"] for r in rows if r["split"] == "challenge"
              and r["candidate"]["fired"] != r["expected"]]
    discovery = next(r for r in rows if r["raw"] == "这事跟我没关系，是他们先动的手。")
    fixed = discovery["candidate"]["fired"] == discovery["expected"]
    span_ok = all(r["raw"][n["start"]:n["end"]] == n["text"]
                  for r in rows for n in r["candidate"]["nodes"])
    visibility_ok = all(ClauseScopeCandidate(visible=set()).inspect(r["raw"])
                        == {"fired": False, "reason": "not_visible", "nodes": []}
                        for r in rows)
    unchanged = before == state_hashes()
    if PROTOCOL.read_bytes() != protocol_bytes or not unchanged:
        raise RuntimeError("Protocol or real state changed during trial")
    counts = {split: {"count": sum(r["split"] == split for r in rows),
                      "old_errors": sum(r["split"] == split and r["old"] != r["expected"] for r in rows),
                      "candidate_errors": sum(r["split"] == split and r["candidate"]["fired"] != r["expected"] for r in rows)}
              for split in ("historical", "challenge")}
    return {"candidate_id": "clause_scope_v1", "protocol_sha256": digest(PROTOCOL),
            "candidate_source_sha256": digest(Path(__file__)),
            "marker_rules_sha256": digest(ROOT / "rules/markers.json"),
            "historical_corpus_sha256": digest(ROOT / "tests/corpus_probe.py"),
            "discovery_fixed": fixed, "historical_target_regressions": regression,
            "challenge_errors": errors, "exact_evidence_spans": span_ok,
            "blocked_visibility_preserved": visibility_ok,
            "real_state_unchanged": unchanged, "state_files_checked": len(before),
            "independently_reviewed": False, "development_credit": 0,
            "verdict": verdict(fixed, regression, errors, span_ok, visibility_ok, unchanged),
            "target_only_counts": counts,
            "rows": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default="spec/结构作用域试验_20261006.json")
    args = parser.parse_args()
    challenge_path = ROOT / "spec/结构作用域挑战_20261006.json"
    report = evaluate(json.loads(challenge_path.read_text(encoding="utf-8")))
    report["challenge_sha256"] = digest(challenge_path)
    (ROOT / args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, ensure_ascii=False))
    # A rejected hypothesis is a successful falsification run, not a test failure.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
