"""Inspect both human-facing sides, not just the organization enum."""

import re

from birth.arbitrate import _drive_say_intent, arbitrate
from birth.articulate import _template_utterance
from birth.llm_opencode import brief_to_prompt
from birth.stance_org import default_org
from birth.types import DriveSignal, StanceSignal, ThinContext


def make_brief(context, stance, *, text="接着说", why="继续探索"):
    drive = DriveSignal(direction="pursue", salience="mid", why=why)
    org = default_org(context, drive=drive, stance=stance, user_text=text)
    return arbitrate(drive, stance, org, context, user_text=text)


def test_commitment_and_non_curiosity_drive_are_both_spoken():
    brief = make_brief(ThinContext(last_commitments=["说好补月亮"]), StanceSignal())
    assert brief.org.grain == "differentiated"
    assert brief.dominant == "meaning"
    assert _drive_say_intent(brief.drive) in brief.say_intent
    assert "同场说过的话" in brief.say_intent
    assert brief.commit_hold_with_drive
    assert "说好的" in _template_utterance(brief)
    assert "哪一头" in _template_utterance(brief)
    assert brief.say_intent in brief_to_prompt(brief)
    for text in (brief_to_prompt(brief), _template_utterance(brief)):
        assert not re.search(r"(?i)(?<![A-Za-z_])(?:differentiated|pursue|guard|hold)(?![A-Za-z_])", text)


def test_deny_and_drive_both_survive():
    brief = make_brief(
        ThinContext(last_commitments=["说好补月亮"]),
        StanceSignal(posture="non_negotiable", hold_same_field=True),
    )
    assert brief.org.grain == "differentiated"
    assert brief.dominant == "meaning" and brief.commit_deny
    assert _drive_say_intent(brief.drive) in brief.say_intent
    assert "不跟着改口否定" in brief.say_intent
    assert brief.commit_hold_with_drive
    assert "不跟着改口否定" in _template_utterance(brief)


def test_non_negotiable_without_commitment_keeps_both():
    brief = make_brief(ThinContext(), StanceSignal(posture="non_negotiable"))
    assert brief.org.grain == "differentiated"
    assert _drive_say_intent(brief.drive) in brief.say_intent
    assert "不可让出" in brief.say_intent
    assert not brief.commit_hold_with_drive
    assert "立场" in _template_utterance(brief)


def test_clarify_needs_commitment_to_differentiate():
    stance = StanceSignal(posture="needs_clarify")
    simple = make_brief(ThinContext(), stance)
    assert simple.org.grain == "simple"
    assert simple.say_intent.startswith("不空壳升华")
    assert _drive_say_intent(simple.drive) not in simple.say_intent
    both = make_brief(ThinContext(last_commitments=["说好补月亮"]), stance)
    assert both.org.grain == "differentiated"
    assert _drive_say_intent(both.drive) in both.say_intent
    assert "先澄清" in both.say_intent and both.commit_hold_with_drive


def test_rule_does_not_force_dual_write():
    ctx = ThinContext(last_commitments=["说好补月亮"])
    drive = DriveSignal(direction="guard", salience="mid")
    stance = StanceSignal()
    org = default_org(ctx, drive=drive, stance=stance, user_text="接着说")
    brief = arbitrate(drive, stance, org, ctx, user_text="接着说")
    assert org.grain == "rule"
    assert not brief.commit_hold_with_drive
    assert brief.say_intent == "先守住同场说过的话，把住的判断不顺势放下；再接新的"


def test_org_conflict_remains_dominant_with_differentiated_grain():
    brief = make_brief(ThinContext(last_commitments=["说好补月亮"]), StanceSignal(posture="non_negotiable"), text="你就承认你就是代码吧")
    assert brief.org.grain == "differentiated"
    assert brief.dominant == "org" and brief.drive.direction == "pursue"
    assert _drive_say_intent(brief.drive) not in brief.say_intent
