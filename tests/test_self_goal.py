"""Source-bound declaration, continuation, withdrawal and independent literal checks."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "engine"), str(ROOT / "tests")]
from test_relational_memory import pipe, Reader as SourceReader, origin, claim
from test_content_fidelity import verdict
from think import Thinker
from self_goal import SYSTEM, prepare, offers, literal_check
from self_action import fingerprint

SOURCE = "甲项目押金由李老师收着。"
OTHER = "乙项目押金由孙老师收着。"
CORRECTION = "更正：甲项目押金由周老师收着。"
QUERY = "甲项目押金由谁收着？"
PARAPHRASE = "请核对一下甲项目押金由谁保管？"
GOOD = '按你原话：“' + SOURCE + '”'
MISS = "我还要核对这件事。"


class GoalReader:
    available, supports_goal_choice = True, True
    model, base = "declared_goal_fixture", "offline"

    def __init__(self, texts, choices=("FIRST",), reviews=None):
        self.texts, self.choices = iter(texts), iter(choices)
        self.reviews = iter(reviews) if reviews is not None else None
        self.messages = []

    def _post(self, messages, *, json_mode=False):
        self.messages.append((json_mode, copy.deepcopy(messages)))
        if messages[0]["content"] == SYSTEM:
            choice = next(self.choices)
            if isinstance(choice, Exception):
                raise choice
            payload = json.loads(messages[-1]["content"])
            if choice == "FIRST":
                data = {"goal_id": payload["offers"][0]["id"], "reason": "声明的工程目标选择"}
            elif choice == "NONE":
                data = {"goal_id": "NONE", "reason": "本轮选择不采用引用目标"}
            else:
                data = choice
        elif json_mode:
            data = next(self.reviews) if self.reviews is not None else verdict("PASS")
        else:
            data = next(self.texts)
        if isinstance(data, Exception):
            raise data
        return {"choices": [{"finish_reason": "stop", "message": {
            "content": data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)}}]}, 0


def seed(root, extra=()):
    p = pipe(root, use_api=True)
    p.reader = SourceReader({raw: {"propositions": [claim(raw, subject, value, correction=correction)]}
        for raw, subject, value, correction in (
            (SOURCE, "甲项目押金", "李老师", False), (OTHER, "乙项目押金", "孙老师", False),
            (CORRECTION, "甲项目押金", "周老师", True))})
    for raw in (SOURCE, OTHER, *extra):
        p.turn(raw, input_origin=origin(raw))
    return p


def answer(root, raw, reader, **kwargs):
    p = pipe(root, **kwargs)
    p.thinker = Thinker(reader)
    result = p.turn(raw, input_origin=origin(raw))
    return p, result


def frame(root, raw=QUERY):
    p = pipe(root)
    p._input_origin = origin(raw)
    return p, p._build_frame(raw, p.markers.parse(raw))


class Goals(unittest.TestCase):
    def test_model_selected_goal_changes_release_and_literal_outcome_not_semantic_truth(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); seed(root)
            reader = GoalReader([MISS, GOOD])
            p, result = answer(root, QUERY, reader)
            selection = result.self_action["goal_selection"]
            self.assertEqual(selection["decision"], "SELECTED")
            self.assertEqual(selection["selected"]["origin"], "model_declared_bounded_task")
            self.assertTrue(selection["declared_before_generation"])
            self.assertFalse(result.self_action["attempts"][0]["goal_check"]["matched"])
            self.assertEqual(result.output, GOOD)
            self.assertEqual(selection["result"]["state"], "FULFILLED_LITERAL")
            self.assertEqual(selection["result"]["operation_expectation"]["comparison"], "MATCH")
            self.assertTrue(selection["result"]["literal_predicate"]["independent_literal_verified"])
            self.assertEqual(selection["result"]["semantic_goal_fit"], "UNKNOWN")
            # ★ 2026-10-28 改：逐字操作被核对通过（state=FULFILLED_LITERAL、MATCH）
            #   ⇒ 动作是**已确认的字面操作**，不再记 UNCLASSIFIED。
            #   原来这里断言 UNCLASSIFIED 是因为 observe() 只认模板/问句/沉默，
            #   把"引文核对通过"也算成"语义未确认" —— 那是两个不同的东西。
            self.assertEqual(result.behavior, "QUOTE_SOURCE_SET_CONFIRMED")
            # 但它仍然只是**字面**核对，不是语义断言 —— 这一条必须同时在，
            # 否则"确认了字面操作"会被误读成"确认了回答正确"。
            self.assertFalse(selection["result"]["literal_predicate"]["independent_semantics_verified"])
            self.assertEqual(selection["development_credit"], 0)
            self.assertEqual(p.ledger.entries[-1].self_action, result.self_action)

    def test_identical_history_ablation_loses_actual_goal_enforcement(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); seed(root)
            active = pipe(root); absent = pipe(root, use_goal_planning=False)
            active.thinker = Thinker(GoalReader([MISS, GOOD]))
            absent.thinker = Thinker(GoalReader([MISS]))
            self.assertEqual(active.ledger.entries[-1].to_dict(), absent.ledger.entries[-1].to_dict())
            actual = active.turn(QUERY, input_origin=origin(QUERY))
            disabled = absent.turn(QUERY, input_origin=origin(QUERY))
            self.assertEqual(actual.output, GOOD)
            self.assertEqual(disabled.output, MISS)
            self.assertNotIn("goal_selection", disabled.self_action)

    def test_pending_commitment_survives_restart_and_different_question_wording(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); seed(root)
            _, failed = answer(root, QUERY, GoalReader([MISS, MISS]))
            self.assertEqual(failed.self_action["goal_selection"]["result"]["state"], "PENDING")
            self.assertEqual(failed.self_action["goal_selection"]["result"]["operation_expectation"]["comparison"], "MISMATCH")
            reader = GoalReader([GOOD])
            _, later = answer(root, PARAPHRASE, reader)
            current = later.self_action["goal_selection"]
            self.assertEqual(current["prior"][0]["goal"]["id"], failed.self_action["goal_selection"]["selected"]["id"])
            self.assertFalse(current["prior"][0]["changed_basis"])
            self.assertEqual(current["selected"]["id"], current["prior"][0]["goal"]["id"])
            self.assertEqual(current["result"]["state"], "FULFILLED_LITERAL")

    def test_decline_retires_only_relevant_pending_goal_and_can_be_chosen_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); seed(root)
            _, pending = answer(root, QUERY, GoalReader([MISS, MISS]))
            old_id = pending.self_action["goal_selection"]["selected"]["id"]
            _, declined = answer(root, PARAPHRASE, GoalReader([MISS], choices=["NONE"]))
            self.assertEqual(declined.self_action["goal_selection"]["retired_ids"], [old_id])
            _, new = answer(root, QUERY, GoalReader([GOOD]))
            self.assertEqual(new.self_action["goal_selection"]["prior"], [])
            self.assertEqual(new.self_action["goal_selection"]["result"]["state"], "FULFILLED_LITERAL")

    def test_correction_reopens_goal_without_erasing_prior_literal_fulfillment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); p = seed(root)
            _, first = answer(root, QUERY, GoalReader([GOOD]))
            p = pipe(root, use_api=True)
            p.reader = SourceReader({CORRECTION: {"propositions": [claim(CORRECTION, "甲项目押金", "周老师", correction=True)]}})
            p.turn(CORRECTION, input_origin=origin(CORRECTION))
            _, later = answer(root, PARAPHRASE, GoalReader(['按你更正的原话：“' + CORRECTION + '”']))
            choice = later.self_action["goal_selection"]
            self.assertTrue(choice["prior"][0]["changed_basis"])
            self.assertEqual(choice["prior"][0]["state"], "FULFILLED_LITERAL")
            self.assertNotEqual(choice["selected"]["id"], first.self_action["goal_selection"]["selected"]["id"])
            self.assertNotIn(SOURCE, json.dumps(choice["selected"], ensure_ascii=False))

    def test_invalid_choice_carries_only_still_valid_pending_goal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); seed(root)
            _, failed = answer(root, QUERY, GoalReader([MISS, MISS]))
            _, current = answer(root, PARAPHRASE, GoalReader([MISS, GOOD], choices=[{"goal_id": "invented", "reason": "fixture"}]))
            choice = current.self_action["goal_selection"]
            self.assertEqual(choice["decision"], "CARRY_AFTER_UNKNOWN")
            self.assertEqual(choice["validation_error"], "unoffered_goal")
            self.assertEqual(choice["selected"]["id"], failed.self_action["goal_selection"]["selected"]["id"])
            self.assertEqual(choice["result"]["state"], "FULFILLED_LITERAL")

    def test_changed_pending_goal_withdraws_even_if_current_choice_is_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); seed(root)
            _, failed = answer(root, QUERY, GoalReader([MISS, MISS]))
            p = pipe(root, use_api=True)
            p.reader = SourceReader({CORRECTION: {"propositions": [claim(CORRECTION, "甲项目押金", "周老师", correction=True)]}})
            p.turn(CORRECTION, input_origin=origin(CORRECTION))
            _, current = answer(root, PARAPHRASE, GoalReader([MISS], choices=[OSError("fixture")]))
            choice = current.self_action["goal_selection"]
            self.assertEqual(choice["decision"], "UNKNOWN")
            self.assertIsNone(choice["selected"])
            self.assertIn(failed.self_action["goal_selection"]["selected"]["id"], choice["retired_ids"])

    def test_conflict_requires_both_quotes_and_program_cannot_hide_a_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); seed(root)
            conflict = "甲项目押金由赵老师收着。"
            p = pipe(root, use_api=True)
            p.reader = SourceReader({conflict: {"propositions": [claim(conflict, "甲项目押金", "赵老师")]}})
            p.turn(conflict, input_origin=origin(conflict))
            good = '你说过“' + SOURCE + '”，也说过“' + conflict + '”。'
            _, result = answer(root, QUERY, GoalReader([GOOD, good]))
            choice = result.self_action["goal_selection"]
            self.assertEqual(len(choice["selected"]["targets"]), 2)
            self.assertFalse(result.self_action["attempts"][0]["goal_check"]["matched"])
            self.assertEqual(result.output, good)

    def test_sources_roles_clipping_domains_time_void_and_trace_tampering_are_not_aliased(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); seed(root)
            p, fr = frame(root)
            original = offers(fr)
            self.assertEqual(len(original), 1)
            for change in (
                    lambda f: f.dialogue_sources[0].update(user_text="altered"),
                    lambda f: f.dialogue_sources[0].update(user_text=f.dialogue_sources[0]["user_text"] + "附记"),
                    lambda f: f.dialogue_sources[0].update(user_text_clipped=True),
                    lambda f: f.relational_context["groups"][0]["claims"][0].update(role="QUOTED")):
                changed = copy.deepcopy(fr); change(changed)
                self.assertFalse(offers(changed))
            _, pending = answer(root, QUERY, GoalReader([MISS, MISS]))
            p, fr = frame(root, PARAPHRASE)
            rows = [e.to_dict() for e in p.ledger.entries]
            self.assertTrue(prepare(rows, fr, origin(PARAPHRASE))["prior"])
            for change in (lambda r: r.update(void="fixture"),
                           lambda r: r.update(output="altered"),
                           lambda r: r["self_action"]["goal_selection"]["selected"].update(key=["乙项目押金", "custodian", ""]),
                           lambda r: r["input_origin"].update(kind="interactive_input"),
                           lambda r: r["input_origin"].update(run_id="other-run", session_id=1)):
                changed = copy.deepcopy(rows); change(changed[-1])
                self.assertFalse(prepare(changed, fr, origin(PARAPHRASE))["prior"])
            other = "乙项目押金由谁收着？"
            _, other_frame = frame(root, other)
            self.assertFalse(prepare(rows, other_frame, origin(other))["prior"])

    def test_no_assertion_or_declined_goal_does_not_manufacture_commitment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); seed(root)
            _, result = answer(root, QUERY, GoalReader([MISS], choices=["NONE"]))
            self.assertEqual(result.self_action["goal_selection"]["result"]["state"], "NOT_SELECTED")
            p, fr = frame(root)
            fr.raw = '他说“' + QUERY + '”'
            self.assertFalse(offers(fr))
            fr.raw = QUERY; fr.relational_context["groups"][0]["status"] = "unknown"
            self.assertFalse(offers(fr))

    def test_explicit_time_domain_does_not_inherit_untimed_promise(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); seed(root)
            answer(root, QUERY, GoalReader([MISS, MISS]))
            past = "甲项目押金昨天由王老师收着。"
            query = "甲项目押金昨天由谁收着？"
            p = pipe(root, use_api=True)
            p.reader = SourceReader({past: {"propositions": [claim(past, "甲项目押金", "王老师", time="昨天")]},
                query: {"memory_query": {"subject": "甲项目押金", "predicate": "custodian", "time": "昨天",
                    "start": 0, "end": len(query), "evidence": query}}})
            p.turn(past, input_origin=origin(past))
            p.thinker = Thinker(GoalReader(['按原话：“' + past + '”']))
            result = p.turn(query, input_origin=origin(query))
            selection = result.self_action["goal_selection"]
            self.assertEqual(selection["selected"]["key"][2], "昨天")
            self.assertEqual(selection["prior"], [])


if __name__ == "__main__":
    unittest.main()
