"""Semantic review is fallible; verify its enforcement and unknown handling."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))
from think import Thinker, Frame


class Reader:
    available = True
    model = "synthetic_same_provider"

    def __init__(self, texts, reviews):
        self.texts, self.reviews, self.messages = iter(texts), iter(reviews), []

    def _post(self, messages, *, json_mode=False):
        self.messages.append((json_mode, messages))
        content = next(self.reviews) if json_mode else next(self.texts)
        if isinstance(content, Exception):
            raise content
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False)
        return {"choices": [{"finish_reason": "stop", "message": {"content": content}}]}, 0


def verdict(value, reason="人工构造接口反馈", problem=None, text=None):
    return {"verdict": value, "reason": reason,
            "evidence": [{"problem": problem, "text": text}] if problem else []}


class Fidelity(unittest.TestCase):
    def test_known_history_cannot_be_replaced_with_false_ignorance(self):
        denied = "我这边没有任何可依据的东西。"
        sources = [{"source_id": "dialogue:1", "user_text": "押金由李老师收着。", "system_output": ""}]
        reader = Reader([denied, "按你之前说的，押金由李老师收着。"],
                        [verdict("REJECT", problem="ignoring_evidence", text=denied), verdict("PASS")])
        thinker = Thinker(reader)
        result = thinker.think(Frame(raw="那我现在该联系谁？", dialogue_sources=sources))
        self.assertTrue(result.rendered)
        self.assertIn("李老师", result.text)
        self.assertEqual(thinker.last_attempts[0]["content_review"]["evidence"][0]["problem"], "ignoring_evidence")

    def test_audit_counterexamples_are_rejected_then_repaired_with_original_context(self):
        for raw, bad, problem in (
                ("我站在那里闻了半小时桂花。", "那半小时里没人在看表。", "unsupported_fact"),
                ("押金还没有退，那我现在该联系谁？", "模型和架构是别人定的，我左右不了。", "off_topic")):
            self.assertFalse(Thinker.check(bad, raw))  # old gate alone remains insufficient
            reader = Reader([bad, "这件事我还不能确定。"],
                            [verdict("REJECT", problem=problem, text=bad), verdict("PASS")])
            thinker = Thinker(reader)
            result = thinker.think(Frame(raw=raw))
            self.assertTrue(result.rendered)
            self.assertNotEqual(result.text, bad)
            self.assertFalse(thinker.last_attempts[0]["accepted"])
            self.assertEqual(thinker.last_attempts[0]["content_review"]["verdict"], "REJECT")
            self.assertFalse(thinker.last_attempts[1]["content_review"]["independent_semantic_review_verified"])
            self.assertEqual(sum(is_json for is_json, _ in reader.messages), 2)

    def test_unknown_malformed_network_and_nonliteral_feedback_cannot_release(self):
        reviews = [verdict("UNKNOWN"), "{}", OSError("synthetic"),
                   verdict("REJECT", problem="unsupported_fact", text="候选里没有这几个字")]
        for review in reviews:
            reader = Reader(["这件事我还不能确定。"] * 2, [review] * 2)
            thinker = Thinker(reader)
            self.assertFalse(thinker.think(Frame(raw="押金还没退。")).rendered)
            self.assertEqual(len(thinker.last_attempts), 2)
            self.assertTrue(all(not a["accepted"] for a in thinker.last_attempts))

    def test_prior_user_quote_allowed_assistant_fabrication_not_allowed(self):
        sources = [{"source_id": "dialogue:1", "user_text": "押金由李老师收着。",
                    "system_output": "押金由周老师收着。"}]
        reader = Reader(["你之前说“押金由李老师收着”。"], [verdict("PASS")])
        result = Thinker(reader).think(Frame(raw="我前面说谁收着？", dialogue_sources=sources))
        self.assertTrue(result.rendered)
        payload = json.loads(reader.messages[-1][1][-1]["content"])
        self.assertEqual(payload["history"], sources)
        reader = Reader(["你之前说“押金由周老师收着”。"] * 2, [])
        self.assertFalse(Thinker(reader).think(Frame(raw="我前面说谁收着？", dialogue_sources=sources)).rendered)
        self.assertFalse(any(is_json for is_json, _ in reader.messages))


if __name__ == "__main__":
    unittest.main()
