"""Bounded recovery keeps failures and never relaxes the original guards."""
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from think import Thinker, Frame
from train import Tutor
from training_studio import desktop_training_gate


class Reader:
    available = True
    max_tokens = 4096
    def __init__(self, replies):
        self.replies, self.calls, self.messages, self.budgets = replies, 0, [], []
    def _post(self, messages, **kwargs):
        self.messages.append(list(messages))
        self.budgets.append(self.max_tokens)
        reply = self.replies[min(self.calls, len(self.replies) - 1)]
        self.calls += 1
        return {"choices": [{"finish_reason": "length" if not reply else "stop",
                             "message": {"content": reply}}], "usage": {}}, 0


class Tests(unittest.TestCase):
    def test_original_failed_quote_then_corrected(self):
        raw = "好像每个人都在等我变回以前那个样子。"
        reader = Reader(['你说“每个人都在等我变回去”。', '你说“每个人都在等我变回以前那个样子”。'])
        thinker = Thinker(reader, verify_content=False)  # isolate the original mechanical retry
        result = thinker.think(Frame(raw=raw, observations="", self_state="", milestones="", last=""))
        self.assertTrue(result.rendered)
        self.assertEqual(reader.calls, 2)
        self.assertFalse(thinker.last_attempts[0]["accepted"])
        self.assertTrue(thinker.last_attempts[1]["accepted"])
        self.assertEqual(Thinker.check(thinker.last_attempts[0]["text"], raw)[0][:2], "引用")
        self.assertIn(raw, reader.messages[1][1]["content"])

    def test_twice_invalid_stays_rejected(self):
        reader = Reader(['你说“每个人都在等我变回去”。'])
        thinker = Thinker(reader, verify_content=False)
        result = thinker.think(Frame(raw="我没说这句话。", observations="", self_state="", milestones="", last=""))
        self.assertFalse(result.rendered)
        self.assertEqual(reader.calls, 2)
        self.assertEqual(len(thinker.last_attempts), 2)
        self.assertEqual(thinker.stats()["pass_rate"], 0)

    def test_evaluation_empty_then_valid_preserves_attempts(self):
        valid = json.dumps({"problem": "none", "why": "测试", "severity": 0, "evidence": ""})
        reader = Reader(["", valid])
        result = Tutor(reader).judge("输入", "输出", {"w": 1})
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["api_attempts"]), 2)
        self.assertFalse(result["api_attempts"][0]["ok"])
        self.assertEqual(reader.budgets, [4096, 8192])
        self.assertEqual(reader.max_tokens, 4096)

    def test_invalid_category_never_becomes_none(self):
        invalid = json.dumps({"problem": "invented", "why": "", "severity": 0, "evidence": ""})
        reader = Reader([invalid])
        result = Tutor(reader).judge("输入", "输出", {})
        self.assertFalse(result["ok"])
        self.assertEqual(reader.calls, 2)

    def test_desktop_on_by_default_with_explicit_rollback(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(desktop_training_gate())
        with patch.dict(os.environ, {"EGO_GATE_PERCEPTION": "0"}):
            self.assertFalse(desktop_training_gate())


if __name__ == "__main__":
    unittest.main()
