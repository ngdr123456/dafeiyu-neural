import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from studio_status import development_path, learning_line


class StatusTests(unittest.TestCase):
    def test_canonical_does_not_fall_back_to_old_level(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "state").mkdir()
            legacy = root / "state/devlevel.json"
            legacy.write_text(json.dumps({"display_projection": True}), encoding="utf-8")
            self.assertEqual(development_path(root), root / "state/devlevel_verified.json")
            (root / "state/devlevel_verified.json").write_text("corrupt", encoding="utf-8")
            self.assertEqual(development_path(root), root / "state/devlevel_verified.json")

    def test_generic_future_memory_is_visible_read_only_and_errors_not_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "state/train").mkdir(parents=True)
            path = root / "state/train/future_rules.json"
            data = {"kind": "future_relation", "rules": {"a": {"status": "active"}, "b": {"status": "candidate"}},
                    "events": [{"kind": "retired"}]}
            path.write_text(json.dumps(data), encoding="utf-8")
            before = path.read_bytes()
            line = learning_line(root)
            self.assertIn("固化1/候选1/退出1", line)
            self.assertEqual(path.read_bytes(), before)
            path.write_text("broken", encoding="utf-8")
            self.assertIn("读取失败", learning_line(root))

    def test_organisation_versions_are_visible_without_migrating_or_writing_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'state/train').mkdir(parents=True)
            path=root/'state/train/relation_rules.json'
            path.write_text(json.dumps({'kind':'proposition_relation_habits_not_stage_development','rules':{},'events':[],
                'organisation_runtime':{'schema':1,'versions':[{'status':s} for s in ['active','candidate','withdrawn']]}}))
            before=path.read_bytes()
            self.assertIn('启用1/候选1/撤回1',learning_line(root))
            self.assertEqual(path.read_bytes(),before)

    def test_own_operation_is_not_displayed_as_completed_semantic_goal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / 'state/train').mkdir(parents=True)
            path = root / 'state/train/ledger.jsonl'
            path.write_text(json.dumps({'self_action': {'schema': 1, 'procedure_status': 'PERMITTED'}}), encoding='utf-8')
            before = path.read_bytes()
            line = learning_line(root)
            self.assertIn('闸门放行／语义结果待核验', line)
            self.assertEqual(path.read_bytes(), before)
            path.write_text('broken', encoding='utf-8')
            self.assertIn('自身作答记录读取失败', learning_line(root))

    def test_literal_goal_fulfillment_never_displays_as_semantic_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'state/train').mkdir(parents=True)
            path=root/'state/train/ledger.jsonl'
            path.write_text(json.dumps({'self_action':{'goal_selection':{
                'selected':{'id':'saved_fixture'},'result':{'state':'FULFILLED_LITERAL'}}}}),encoding='utf-8')
            before=path.read_bytes()
            self.assertIn('逐字操作已核对／语义结果待核验',learning_line(root))
            self.assertEqual(path.read_bytes(),before)


if __name__ == "__main__":
    unittest.main()
