"""Actual Pipeline learning in temp roots; structured reviewer is simulated."""
import json
import re
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
sys.path.insert(0, str(ROOT))
from pipeline import Pipeline
from understand import ApiReader
from tools.structure_scope_trial import state_hashes


class Reviewer:
    available = True
    model = "synthetic_test_reviewer"
    def __init__(self, role="PROHIBITED", assert_marker=False):
        self.role, self.assert_marker = role, assert_marker
        self.last_spec = []

    def read(self, raw, stem, spec):
        self.last_spec = [r["id"] for r in spec]
        items = [{"id": "blame_external", "start": m.start(), "end": m.end(),
                  "evidence": m.group(), "role": self.role}
                 for rule in spec if rule["id"] == "blame_external"
                 for phrase in rule["patterns"] for m in re.finditer(re.escape(phrase), raw)]
        return ApiReader(api_key="")._parse_obj(
            {"intent": "ANSWER", "markers": [{"id": "blame_external", "evidence": ["都是他们"]}]
             if self.assert_marker else [], "relations": items}, raw, spec, 0, {})


class PipelineRelationTests(unittest.TestCase):
    def setUp(self):
        self.before = state_hashes()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "state").mkdir()

    def tearDown(self):
        self.temp.cleanup()
        self.assertEqual(self.before, state_hashes())

    def pipeline(self):
        return Pipeline(ledger_path=str(self.root / "state/ledger.jsonl"),
                        character_path=str(self.root / "state/character.json"),
                        devlevel_path=str(self.root / "state/devlevel_verified.json"),
                        carry_root=str(self.root), gate_perception=True,
                        use_api=False, use_render=False, use_think=False, auto_audit=False)

    def trained(self):
        pipeline = self.pipeline()
        pipeline.reader = Reviewer()
        for i in range(5):
            pipeline.turn(f"不要说了，都是他们害了项目{i}。")
        return pipeline

    def test_real_pipeline_consolidation_restart_and_trace(self):
        pipeline = self.trained()
        resumed = self.pipeline()
        result = resumed.turn("不要说了，都是他们害了另一份工作。")
        self.assertNotIn("blame_external", result.markers)
        trace = next(n for n in result.notes if n.startswith("关系学习="))
        self.assertTrue(json.loads(trace.split("=", 1)[1])["suppressed"])
        baseline = json.loads((self.root / "state/devlevel_verified.json").read_text(encoding="utf-8"))
        self.assertEqual(baseline["equilibration"], 0)
        self.assertEqual(baseline["level"], "I-3")
        ledger = (self.root / "state/ledger.jsonl").read_text(encoding="utf-8")
        self.assertIn("关系学习=", ledger)

    def test_current_contradiction_retires_before_this_turn_filter(self):
        pipeline = self.trained()
        pipeline.reader = Reviewer("ASSERTED", assert_marker=True)
        result = pipeline.turn("不要说了，都是他们害了新的合同。")
        self.assertIn("blame_external", result.markers)
        self.assertTrue(any(e["kind"] == "retired" for e in pipeline.relation_learning.learner.data["events"]))

    def test_unknown_occurrence_and_api_silence_cannot_train_or_veto(self):
        pipeline = self.pipeline()
        result = pipeline.turn("都是他们害的。")
        self.assertIn("blame_external", result.markers)
        self.assertFalse((self.root / "state/relation_rules.json").exists())
        pipeline = self.trained()
        pipeline.reader = None
        result = pipeline.turn("不要说了，都是他们害的。但是都是他们害了别的事。")
        self.assertIn("blame_external", result.markers)

    def test_exact_span_and_conflicting_role_rejected_and_visibility_is_sent(self):
        parser = ApiReader(api_key="")
        spec = self.pipeline().markers.rules["markers"]
        raw = "都是他们害的。"
        valid = {"id": "blame_external", "start": 0, "end": 4,
                 "evidence": "都是他们", "role": "ASSERTED"}
        result = parser._parse_obj({"relations": [valid, dict(valid, role="QUOTED"),
                                                  dict(valid, start=True),
                                                  dict(valid, evidence="伪造原话")]}, raw, spec, 0, {})
        self.assertEqual(result.relations, [])
        self.assertIn("关系结论冲突", result.dropped)
        pipeline = self.pipeline()
        pipeline.reader = Reviewer()
        pipeline.markers.visible = set()
        result = pipeline.turn(raw)
        self.assertEqual(pipeline.reader.last_spec, [])
        self.assertNotIn("blame_external", result.markers)
        self.assertFalse((self.root / "state/relation_rules.json").exists())

    def test_prior_sentence_cue_does_not_suppress_current_assertion(self):
        pipeline = self.trained()
        pipeline.reader = None
        result = pipeline.turn("不要说了。这份合同就是都是他们害的。")
        self.assertIn("blame_external", result.markers)

    def test_api_position_manifest_keeps_overlaps_separate_without_prejudging_roles(self):
        reader=ApiReader(api_key='fixture');captured=[]
        raw='不要说，这种话：都是他们害了合同。'
        spec=self.pipeline().markers.rules['markers']
        def reply(messages):
            captured.extend(messages)
            return {'choices':[{'message':{'content':json.dumps({'intent':'ANSWER','markers':[],'relations':[]})}}]},0
        with patch.object(reader,'_post',side_effect=reply):
            reading=reader.read(raw,'',spec)
        self.assertTrue(reading.ok)
        user=captured[1]['content']
        block=user.split('【逐字关系位置清单：仅定位，不含角色】\n',1)[1].split('\n',1)[0]
        positions=json.loads(block)
        self.assertGreater(len(positions),1)
        self.assertEqual({(p['start'],p['end']) for p in positions},
                         {(m.start(),m.end()) for rule in spec if rule['id']=='blame_external'
                          for phrase in rule['patterns'] for m in re.finditer(re.escape(phrase),raw)})
        for position in positions:
            self.assertEqual(raw[position['start']:position['end']],position['evidence'])
            self.assertNotIn('role',position)
        # Supplying positions alone still cannot create feedback or a verdict.
        self.assertEqual(reading.relations,[])

    def test_consolidated_assertion_does_not_create_missing_marker(self):
        pipeline = self.pipeline()
        pipeline.reader = Reviewer("ASSERTED")
        for i in range(5):
            pipeline.turn(f"不能说，都是他们害了项目{i}。")
        pipeline.reader = None
        raw = "不能说，都是他们害了另一项任务。"
        self.assertNotIn("blame_external", pipeline.markers.parse(raw).markers)
        self.assertNotIn("blame_external", pipeline.turn(raw).markers)

    def test_memory_write_failure_preserves_original_judgment_and_reports_degradation(self):
        pipeline = self.pipeline()
        pipeline.reader = Reviewer()
        with patch.object(pipeline.relation_learning, "observe", side_effect=OSError("simulated failure")):
            result = pipeline.turn("不要说了，都是他们害了合同。")
        self.assertIn("blame_external", result.markers)
        self.assertTrue(any("关系学习降级" in n for n in result.notes))

    def test_structure_versions_keep_formation_out_and_capture_future_topics(self):
        from structure_evidence import report
        pipeline = self.pipeline()
        pipeline.reader = Reviewer()
        for i in range(5):
            pipeline.turn(f"不要说了，都是他们害了项目{i}，也是都是他们害了另一件事{i}。")
        initial = report(pipeline.relation_learning.learner.data)
        self.assertTrue(initial["comparisons"])
        self.assertTrue(all(c["future_input_count"] == 0 for c in initial["comparisons"]))
        pipeline.turn("不要说了，都是他们害了那份合同。", "T01")
        pipeline.turn("不要说了，都是他们害了那场比赛。", "T02")
        result = report(pipeline.relation_learning.learner.data)
        self.assertTrue(any(c["cross_topic_labels_observed"] for c in result["comparisons"]))
        self.assertTrue(all(c["development_credit"] == 0 for c in result["comparisons"]))
        self.assertTrue(all(c["losses"] == 0 for c in result["comparisons"]))


if __name__ == "__main__":
    unittest.main()
