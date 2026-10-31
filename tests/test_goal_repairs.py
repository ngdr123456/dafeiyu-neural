"""Counterfactual memory and actual-action tests through the real Pipeline."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from pipeline import Pipeline
from render import Speech
from dialogue_memory import retrieve
from action_observation import observe, learning_action
from association import Association
from experience import derive
from experience import _outcome_of
from runtime_profile import paths
from input_provenance import digest


class Capture:
    def __init__(self, text="那笔押金现在由谁收着？"):
        self.frames, self.text = [], text

    def think(self, frame):
        self.frames.append(frame)
        return Speech(self.text, True, "synthetic_capture")


class Repairs(unittest.TestCase):
    def pipe(self, root):
        return Pipeline(ledger_path=str(root / "state/ledger.jsonl"),
                        character_path=str(root / "state/character.json"),
                        devlevel_path=str(root / "state/devlevel_verified.json"),
                        carry_root=str(root), gate_perception=True, auto_audit=False)

    def test_history_changes_frame_correction_and_restart_preserve_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            frames = []
            for name in ("李老师", "周老师"):
                root = Path(tmp) / name
                p = self.pipe(root)
                first = "押金由%s收着，我要先联系%s。" % (name, name)
                p.turn(first)
                p = self.pipe(root)  # actual on-disk reload
                capture = Capture()
                p.thinker = capture
                p.turn("那我现在该联系谁？")
                frame = capture.frames[-1]
                self.assertIn(name, frame.user_text())
                self.assertEqual(frame.dialogue_sources[0]["user_text"], first)
                self.assertFalse(frame.self_facts)  # irrelevant architecture does not occupy this turn
                frames.append(frame.user_text())
                p.thinker = None
                p.turn("更正：押金现在由赵老师收着，前面联系人说错了。")
                p = self.pipe(root)
                capture = Capture()
                p.thinker = capture
                p.turn("那我现在该联系谁？")
                sources = capture.frames[-1].dialogue_sources
                self.assertIn("赵老师", sources[-1]["user_text"])
                self.assertEqual(sources[0]["user_text"], first)  # correction does not erase history
                self.assertIn("更正", capture.frames[-1].user_text())
            self.assertNotEqual(frames[0], frames[1])

    def test_actual_question_is_not_reflection_and_unknown_does_not_shape_character(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = self.pipe(root)
            p.thinker = Capture()
            result = p.turn("我站在那里闻了半小时桂花。")
            self.assertEqual(result.planned_behavior, "REFLECT")
            self.assertEqual(result.behavior, "QUESTION")
            self.assertTrue(result.action_observation["confirmed"])
            p.thinker = Capture("这件事我还不能确定。")
            unknown = p.turn("押金还没退。")
            self.assertEqual(unknown.behavior, "UNCLASSIFIED")
            self.assertIsNone(learning_action(p.ledger.effective_entries[-1].to_dict()))
            p.thinker = None
            p.turn("我想先问清楚是谁收着。")
            pairs = Association.derive_from_ledger(str(root / "state/ledger.jsonl"),
                                                   str(root / "unused.jsonl")).pairs
            self.assertTrue(any(pair.mine == "QUESTION" and pair.my_kind == "问" for pair in pairs))
            self.assertFalse(any(pair.mine == "UNCLASSIFIED" for pair in pairs))
            events = derive([e.to_dict() for e in p.ledger.effective_entries])
            self.assertFalse(any(e.actor == "SELF" and e.turn == unknown.turn_id
                                 and e.kind != "SELF_WRONG" for e in events))
            self.assertFalse(result.mech["signal_basis"]["development_evidence"])

    def test_domains_run_and_session_are_not_invented_shared_biography(self):
        def row(raw, **origin):
            return {"raw_input": raw, "input_origin": origin, "output": "", "ts": "test"}
        entries = [row("模拟人物的李老师", kind="tutor_generated", run_id="r1", session_id=0),
                   row("另场的周老师", kind="tutor_generated", run_id="r1", session_id=1),
                   row("实际界面输入赵老师", kind="interactive_input"),
                   dict(row("已作废的王老师", kind="interactive_input"), void="test")]
        human = retrieve(entries, "老师", {"kind": "interactive_input"})
        self.assertEqual([s["user_text"] for s in human], ["实际界面输入赵老师"])
        training = retrieve(entries, "老师", {"run_id": "r1", "session_id": 0})
        self.assertEqual([s["user_text"] for s in training], ["模拟人物的李老师"])
        self.assertEqual(retrieve(entries, "老师", {"run_id": "r2", "session_id": 0}), [])
        crowded = [row("某事%d" % i, kind="interactive_input") for i in range(60)]
        self.assertLessEqual(len(retrieve(crowded, "某事", {"kind": "interactive_input"})), 10)

    def test_profiles_share_training_paths_without_merging_old_ledgers(self):
        train = paths(ROOT)
        self.assertEqual(Path(train["ledger"]), ROOT / "state/train/ledger.jsonl")
        self.assertEqual(Path(train["character"]), ROOT / "state/train/character.json")
        self.assertEqual(Path(paths(ROOT, "legacy")["ledger"]), ROOT / "state/ledger.jsonl")
        self.assertEqual(Path(paths(ROOT, ledger="X:/custom/log.jsonl")["character"]),
                         Path("X:/custom/character.json"))
        # ★ 2026-10-28（改动 ③）：期望从 UNCLASSIFIED 改成 QUESTION。
        #   原来的断言钉住的正是 Gemini 指出的那个 bug ——「甲是乙。你同意？」
        #   是一句**两句式追问**（先接半句再发问），旧判据要求"全文不许有句号"，
        #   于是把它踢进 UNCLASSIFIED。那不叫"不猜标签"，那叫把真问句判丢了。
        self.assertEqual(observe("甲是乙。你同意？", "REFLECT", "brain")["actual"], "QUESTION")
        # 反向仍然守着：陈述句不许被误判成问句
        self.assertEqual(observe("甲是乙。我同意。", "REFLECT", "brain")["actual"],
                         "UNCLASSIFIED")
        a = {"turn_id": 1, "input_origin": {"run_id": "r", "session_id": 0}}
        b = {"turn_id": 2, "input_origin": {"run_id": "r", "session_id": 1}}
        self.assertFalse(Association._same_session(a, b))
        self.assertEqual(_outcome_of([a, b], 0), "对话结束")


if __name__ == "__main__":
    unittest.main()
