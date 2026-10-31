"""A real ledger witness prevents unqualified denial; ablation must not leak names."""
import copy
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "engine"), str(ROOT / "tests")]
from test_self_goal import seed, pipe, origin, GoalReader, Thinker, QUERY, SOURCE
from test_relational_memory import row
from think import Frame
from memory_scope import describe, check

BAD = "我不知道押金现在由谁收着——这件事我这儿没有记录。"
GOOD = "当前能查到的这批原话里，我还不能确定是谁收着。"


class Scope(unittest.TestCase):
    def test_pipeline_ablated_view_still_knows_existence_and_blocks_false_denial(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); seed(root); p = pipe(root)
            for i in range(18):
                raw = QUERY + "此问暂放编号%d。" % i
                p.turn(raw, input_origin=origin(raw))
            p = pipe(root, use_relational_memory=False)
            reader = GoalReader([BAD, GOOD])
            p.thinker = Thinker(reader)
            result = p.turn(QUERY, input_origin=origin(QUERY))
            self.assertEqual(result.output, GOOD)
            self.assertTrue(result.self_action["memory_scope"]["matching_relation_utterance_known"])
            self.assertFalse(result.self_action["attempts"][0]["accepted"])
            self.assertTrue(any("全局未记录" in bad for bad in result.self_action["attempts"][0]["violations"]))
            generator = next(messages for mode, messages in reader.messages if not mode)
            self.assertNotIn("李老师", generator[1]["content"])
            self.assertNotIn("孙老师", generator[1]["content"])
            self.assertEqual(result.self_action["outcome"]["semantic_goal_fit"], "UNKNOWN")

    def test_nonassertions_and_qualified_view_keep_their_language_scope(self):
        f = Frame(raw=QUERY, memory_scope={"matching_relation_utterance_known": True})
        self.assertTrue(check(f, BAD))
        self.assertTrue(check(f, "我这儿没有记录。"))
        for text in (GOOD, "当前这批片段里，我没有看到相关记录。", '你说“我这儿没有记录”。',
                     "不是没记录过，我只是还没核对。", "不能说我这儿没有记录。", "你以前有没有记录过？"):
            self.assertFalse(check(f, text), text)

    def test_positive_witness_is_source_scoped_and_absence_is_never_inferred(self):
        entry = row(SOURCE, "甲项目押金", "李老师")
        current = describe([entry], QUERY, origin(QUERY))
        self.assertTrue(current["matching_relation_utterance_known"])
        for change in (lambda r: r.update(void="fixture"),
                       lambda r: r["input_origin"].update(kind="interactive_input"),
                       lambda r: r["input_origin"].update(run_id="elsewhere", session_id=1),
                       lambda r: r.update(raw_input=r["raw_input"] + "altered")):
            altered = copy.deepcopy(entry); change(altered)
            self.assertFalse(describe([altered], QUERY, origin(QUERY))["matching_relation_utterance_known"])
        empty = describe([], QUERY, origin(QUERY))
        self.assertFalse(empty["record_absence_verified"])
        self.assertFalse(empty["external_fact_verified"])
        self.assertNotIn("李老师", str(current))


if __name__ == "__main__":
    unittest.main()
