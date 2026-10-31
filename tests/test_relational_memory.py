"""Causal wiring and adversarial source/correction tests for reported relations."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from relational_memory import parse, project
from dialogue_memory import retrieve
from input_provenance import digest
from pipeline import Pipeline
from understand import ApiReader
from render import Speech


def origin(raw, **extra):
    return dict(schema=1, kind="scripted_diagnostic", input_sha256=digest(raw), topic_id=None,
                independent_human_input_verified=False, **extra)


def claim(raw, subject, value, *, time="", correction=False, role="ASSERTED", predicate="custodian"):
    return {"subject": subject, "predicate": predicate, "value": value, "time": time,
            "start": 0, "end": len(raw), "evidence": raw, "role": role, "correction": correction}


def row(raw, subject, value, **kwargs):
    return {"raw_input": raw, "input_origin": origin(raw), "output": "", "ts": "fixture",
            "proposition_reading": parse(raw, {"propositions": [claim(raw, subject, value, **kwargs)]},
                                         extractor="offline_fixture")}


class Reader:
    available = True
    model, base = "offline_fixture", "offline"

    def __init__(self, readings):
        self.readings = readings

    def read(self, raw, stem, spec):
        return ApiReader(api_key="")._parse_obj(dict(intent="ANSWER", markers=[],
                                                     **self.readings.get(raw, {})), raw, spec, 0, {})


class Capture:
    def __init__(self):
        self.frames = []

    def think(self, frame):
        self.frames.append(frame)
        return Speech("这件事我还不能确定。", True, "offline_fixture")


def pipe(root, **kwargs):
    return Pipeline(ledger_path=str(root / "state/ledger.jsonl"),
                    character_path=str(root / "state/character.json"),
                    devlevel_path=str(root / "state/devlevel_verified.json"),
                    carry_root=str(root), gate_perception=True, auto_audit=False, **kwargs)


class Relations(unittest.TestCase):
    def test_long_gap_restart_and_ablation_change_actual_pipeline_frame(self):
        first = "甲项目押金由李老师收着。"
        other = "乙项目押金由周老师收着。"
        corrected = "更正：甲项目押金由赵老师收着。"
        readings = {raw: {"propositions": [claim(raw, subject, value, correction=correction)]}
                    for raw, subject, value, correction in (
                        (first, "甲项目押金", "李老师", False),
                        (other, "乙项目押金", "周老师", False),
                        (corrected, "甲项目押金", "赵老师", True))}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = pipe(root)
            p.reader = Reader(readings)
            for raw in (first, other, corrected):
                p.turn(raw, input_origin=origin(raw))
            # The lexical window is deliberately crowded with unrelated chat.
            for i in range(18):
                raw = "甲项目押金现在由谁收着？这个问题暂放第%d次。" % i
                p.turn(raw, input_origin=origin(raw))
            query = "甲项目押金现在由谁收着？"
            flat = retrieve(p.ledger.effective_entries, query, origin(query))
            self.assertFalse(any("赵老师" in s["user_text"] for s in flat))
            enabled = pipe(root)
            capture = Capture()
            enabled.thinker = capture
            enabled.turn(query, input_origin=origin(query))
            frame = capture.frames[-1]
            group = frame.relational_context["groups"][0]
            self.assertEqual(group["reported_values"], ["赵老师"])
            self.assertTrue(any("李老师" in n["value"] and n["superseded_by"] for n in group["claims"]))
            self.assertTrue(any("赵老师" in s["user_text"] for s in frame.dialogue_sources))
            self.assertFalse(any(n["value"] == "周老师" for n in group["claims"]))
            disabled = pipe(root, use_relational_memory=False)
            disabled.thinker = capture
            disabled.turn(query, input_origin=origin(query))
            self.assertFalse(capture.frames[-1].relational_context)
            self.assertNotIn("赵老师", capture.frames[-1].user_text())
            stored = json.loads((root / "state/ledger.jsonl").read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(stored["proposition_reading"]["raw_sha256"], digest(first))
            self.assertFalse(group["claims"][0]["speaker"] == "system")
            self.assertFalse(frame.relational_context["rule_learned_from_experience"])

    def test_correction_never_crosses_entity_time_or_authorship(self):
        rows = [row("甲押金由李老师收着。", "甲押金", "李老师"),
                row("乙押金由周老师收着。", "乙押金", "周老师"),
                row("甲押金昨天由孙老师收着。", "甲押金", "孙老师", time="昨天"),
                row("更正：甲押金由赵老师收着。", "甲押金", "赵老师", correction=True)]
        ctx, _ = project(rows, "乙押金由谁收着？", origin("乙押金由谁收着？"))
        self.assertEqual(ctx["groups"][0]["reported_values"], ["周老师"])
        query = "甲押金昨天由谁收着？"
        reading = parse(query, {"memory_query": dict(subject="甲押金", predicate="custodian", time="昨天",
                        start=0, end=len(query), evidence=query)})
        ctx, _ = project(rows, query, origin(query), reading)
        timed = next(g for g in ctx["groups"] if g["time"] == "昨天")
        self.assertEqual(len(ctx["groups"]), 1)
        self.assertEqual(timed["reported_values"], ["孙老师"])
        self.assertFalse(timed["claims"][0]["superseded_by"])
        ctx, sources = project(rows, query, dict(origin(query), kind="interactive_input"), reading)
        self.assertFalse(ctx["groups"])
        self.assertFalse(sources)

    def test_disagreement_is_not_silently_overwritten_and_void_correction_replays(self):
        rows = [row("甲押金由李老师收着。", "甲押金", "李老师"),
                row("甲押金由周老师收着。", "甲押金", "周老师")]
        raw = "甲押金由谁收着？"
        ctx, _ = project(rows, raw, origin(raw))
        self.assertEqual(ctx["groups"][0]["status"], "conflict")
        self.assertEqual(ctx["groups"][0]["reported_values"], ["周老师", "李老师"])
        rows.append(dict(row("更正：甲押金由赵老师收着。", "甲押金", "赵老师", correction=True), void="撤销"))
        self.assertEqual(project(rows, raw, origin(raw))[0]["groups"][0]["status"], "conflict")
        rows[-1].pop("void")
        ctx, _ = project(rows, raw, origin(raw))
        self.assertEqual(ctx["groups"][0]["reported_values"], ["赵老师"])
        self.assertEqual(len(ctx["groups"][0]["claims"][-1]["corrects"]), 2)

    def test_custodian_correction_does_not_change_a_contact_plan(self):
        rows = [row("甲押金由李老师收着。", "甲押金", "李老师"),
                row("甲押金要联系周老师。", "甲押金", "周老师", predicate="contact"),
                row("更正：甲押金由赵老师收着。", "甲押金", "赵老师", correction=True)]
        raw = "甲押金要联系谁？"
        context = project(rows, raw, origin(raw))[0]
        self.assertEqual(context["groups"][0]["reported_values"], ["周老师"])
        self.assertFalse(context["groups"][0]["claims"][0]["superseded_by"])

    def test_quotes_negation_questions_hypotheses_cannot_become_positive_facts(self):
        for raw, role in (("他说：“甲押金由李老师收着。”", "QUOTED"),
                          ("甲押金不由李老师收着。", "NEGATED"),
                          ("不要说甲押金由李老师收着。", "PROHIBITED"),
                          ("甲押金由李老师收着？", "UNKNOWN"),
                          ("如果甲押金由李老师收着，我就放心。", "UNKNOWN")):
            rows = [row(raw, "甲押金", "李老师", role=role)]
            context = project(rows, "甲押金由谁收着？", origin("甲押金由谁收着？"))[0]
            self.assertEqual(context["groups"][0]["status"], "unknown")
            self.assertFalse(context["groups"][0]["reported_values"])
            # Even an erroneous ASSERTED extraction hits the local veto here.
            bad = row(raw, "甲押金", "李老师")
            self.assertEqual(bad["proposition_reading"]["propositions"][0]["role"], "UNKNOWN")

    def test_hash_malformed_and_contradictory_extraction_are_unusable(self):
        raw = "甲押金由李老师收着。"
        for patch in ({"subject": "乙押金"}, {"value": "王老师"}, {"end": 1}, {"role": "positive"}):
            item = dict(claim(raw, "甲押金", "李老师"), **patch)
            self.assertFalse(parse(raw, {"propositions": [item]})["propositions"])
        rows = [row(raw, "甲押金", "李老师")]
        rows[0]["raw_input"] = raw.replace("李", "赵")
        self.assertFalse(project(rows, "甲押金", origin("甲押金"))[0]["groups"])
        item = claim(raw, "甲押金", "李老师")
        reading = parse(raw, {"propositions": [item, dict(item, role="QUOTED")]})
        self.assertEqual(reading["propositions"][0]["role"], "UNKNOWN")
        raw = "前面那句没说错，甲押金由李老师收着。"
        self.assertFalse(row(raw, "甲押金", "李老师", correction=True)["proposition_reading"]
                         ["propositions"][0]["correction"])

    def test_ambiguous_objects_and_times_remain_explicit_and_context_is_bounded(self):
        rows = [row("甲押金由李老师收着。", "甲押金", "李老师"),
                row("乙押金由周老师收着。", "乙押金", "周老师")]
        ctx, _ = project(rows, "谁收着？", origin("谁收着？"))
        self.assertIn("ambiguous_subject", ctx["unresolved_reasons"])
        rows.append(row("甲押金昨天由孙老师收着。", "甲押金", "孙老师", time="昨天"))
        self.assertIn("ambiguous_time", project(rows, "甲押金由谁收着？", origin("甲押金由谁收着？"))
                      [0]["unresolved_reasons"])
        rows.extend(row("第%d押金由李老师收着。" % i, "第%d押金" % i, "李老师") for i in range(30))
        ctx, sources = project(rows, "谁收着？", origin("谁收着？"))
        self.assertLessEqual(len(ctx["groups"]), 4)
        self.assertLessEqual(len(sources), 8)
        self.assertIn("context_limit", ctx["unresolved_reasons"])
        self.assertFalse(project(rows, "今天很冷。", origin("今天很冷。"))[0]["groups"])

    def test_training_personas_are_not_merged_across_sessions_or_runs(self):
        rows = [row("甲押金由李老师收着。", "甲押金", "李老师")]
        rows[0]["input_origin"].update(kind="tutor_generated", run_id="a", session_id=0)
        raw = "甲押金由谁收着？"
        for run, session in (("b", 0), ("a", 1)):
            ctx, _ = project(rows, raw, dict(origin(raw), kind="tutor_generated", run_id=run, session_id=session))
            self.assertFalse(ctx["groups"])
        ctx, _ = project(rows, raw, dict(origin(raw), kind="tutor_generated", run_id="a", session_id=0))
        self.assertEqual(ctx["groups"][0]["reported_values"], ["李老师"])

    def test_long_correction_chains_are_bounded_without_losing_current_value(self):
        rows = [row("甲押金由李老师收着。", "甲押金", "李老师") for _ in range(100)]
        rows.append(row("更正：甲押金由赵老师收着。", "甲押金", "赵老师", correction=True))
        raw = "甲押金由谁收着？"
        context, sources = project(rows, raw, origin(raw))
        group = context["groups"][0]
        self.assertEqual(group["reported_values"], ["赵老师"])
        correction = next(n for n in group["claims"] if n["value"] == "赵老师")
        self.assertEqual(correction["corrects_total"], 100)
        self.assertTrue(correction["corrects_clipped"])
        self.assertEqual(len(correction["corrects"]), 8)
        self.assertLessEqual(len(group["claims"]), 12)
        self.assertLessEqual(len(sources), 8)

    def test_content_review_receives_the_same_relation_graph(self):
        from content_fidelity import review
        from think import Frame
        class ReviewReader:
            model = "fixture"
            def _post(self, messages, json_mode=True):
                self.payload = json.loads(messages[-1]["content"])
                return {"choices": [{"message": {"content": json.dumps({"verdict": "PASS", "reason": "fixture", "evidence": []})}}]}, 0
        reader = ReviewReader()
        raw = "甲押金由谁收着？"
        context, sources = project([row("甲押金由李老师收着。", "甲押金", "李老师")], raw, origin(raw))
        review(reader, Frame(raw=raw, dialogue_sources=sources, relational_context=context), "按你说过的，是李老师。")
        self.assertEqual(reader.payload["relational_context"], context)


if __name__ == "__main__":
    unittest.main()
