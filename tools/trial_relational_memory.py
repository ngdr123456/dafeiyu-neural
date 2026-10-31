"""Freeze and ablate the engineered relation representation through Pipeline.

This diagnostic establishes a useful substrate, NOT experience-learned rules.
Fixtures declare extraction labels; no semantic independence is claimed.
"""
import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "engine"), str(ROOT / "tests")]
from test_relational_memory import origin, claim, pipe, Reader, Capture
from action_plan import source_hashes, FOUNDATION
from relational_memory import VERSION


def state_hashes():
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (ROOT / "state").rglob("*") if p.is_file()}


def main():
    before = state_hashes()
    initial_sources = source_hashes(ROOT)
    cases = []
    with tempfile.TemporaryDirectory(prefix="ego-relation-causal-") as tmp:
        for i, (predicate, verb) in enumerate((("custodian", "由%s收着"),
                                               ("contact", "要联系%s"), ("location", "在%s"))):
            root = Path(tmp) / str(i)
            a, b = "甲项目文件", "乙项目文件"
            first, other, corrected = a + verb % "东七" + "。", b + verb % "西九" + "。", "更正：" + a + verb % "南三" + "。"
            readings = {raw: {"propositions": [claim(raw, subject, value, predicate=predicate, correction=correction)]}
                        for raw, subject, value, correction in ((first, a, "东七", False),
                            (other, b, "西九", False), (corrected, a, "南三", True))}
            p = pipe(root)
            p.reader = Reader(readings)
            for raw in (first, other, corrected):
                p.turn(raw, input_origin=origin(raw))
            query = a + {"custodian": "由谁收着？", "contact": "要联系谁？", "location": "在哪里？"}[predicate]
            for j in range(18):
                raw = query + "此问先放着，编号%d。" % j
                p.turn(raw, input_origin=origin(raw))

            def frame(enabled, text):
                capture = Capture()
                run = pipe(root, use_relational_memory=enabled)
                run.thinker = capture
                # Only assemble the frame: comparisons cannot contaminate history.
                run._input_origin = origin(text)
                return run._build_frame(text, run.markers.parse(text))

            enabled, reloaded, disabled = frame(True, query), frame(True, query), frame(False, query)
            query_b = b + query[len(a):]
            retained = frame(True, query_b)
            selected = enabled.relational_context["groups"]
            passed = (len(selected) == 1 and selected[0]["reported_values"] == ["南三"]
                      and any(n["superseded_by"] for n in selected[0]["claims"]))
            result = {"case": predicate, "passed": passed,
                      "ablation_loses_selected_relation": "南三" not in disabled.user_text(),
                      "unaffected_object_retained": retained.relational_context["groups"][0]["reported_values"] == ["西九"],
                      "restart_equal": enabled.relational_context == reloaded.relational_context,
                      "enabled_context": enabled.relational_context,
                      "unaffected_context": retained.relational_context,
                      "old_frame_sha256": hashlib.sha256(disabled.user_text().encode()).hexdigest(),
                      "new_frame_sha256": hashlib.sha256(enabled.user_text().encode()).hexdigest()}
            cases.append(result)
    if before != state_hashes() or initial_sources != source_hashes(ROOT):
        raise RuntimeError("State or source changed during diagnostic")
    passed = all(c["passed"] and c["ablation_loses_selected_relation"] and c["unaffected_object_retained"]
                 and c["restart_equal"] for c in cases)
    report = {"schema": 1, "date": "2026-10-08", "passed": passed, "version": VERSION,
              "rule_origin": "engineered", "learned_rule_change": False, "cases": cases,
              "source_hashes": initial_sources, "real_state_files_unchanged": len(before),
              "network_used": False, "scripted_inputs": True, "independent_semantics_verified": False,
              "development_credit": 0, "claim": "causal effect of engineered representation, not autonomous structural growth"}
    (ROOT / FOUNDATION).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": passed, "cases": len(cases), "state_unchanged": len(before)}, ensure_ascii=False))
    return int(not passed)


if __name__ == "__main__":
    raise SystemExit(main())
