"""Engineer-side shape and consistency checks for real turn briefs."""

from birth.articulate import clear_llm_hook, set_stub_mode
from birth.pipeline import active_store, turn


def _assert_brief_shape(brief, label):
    assert brief.dominant in {"drive", "meaning", "org"}, label
    assert brief.drive is not None, label
    assert brief.drive.direction in {"pursue", "guard", "hold", None}, label
    assert brief.stance.posture in {"yieldable", "non_negotiable", "needs_clarify"}, label
    assert brief.org.grain in {"simple", "rule", "differentiated"}, label
    assert brief.must_not_pretend, label
    assert all(isinstance(item, str) and item.strip() for item in brief.must_not_pretend), label
    if brief.dominant == "org":
        assert brief.drive is not None and brief.drive.why, label


def test_daily_statement():
    set_stub_mode(True)
    clear_llm_hook()
    active_store().new_session()
    brief = turn("今天天气不错", stub=True).brief
    _assert_brief_shape(brief, "日常陈述")
    assert brief.dominant == "drive"
    assert brief.drive.direction is None


def test_drive_pursue():
    set_stub_mode(True)
    clear_llm_hook()
    active_store().new_session()
    brief = turn("我想聊星空", stub=True).brief
    _assert_brief_shape(brief, "动力主导")
    assert brief.dominant == "drive"
    assert brief.drive.direction == "pursue"


def test_commitment_meaning():
    set_stub_mode(True)
    clear_llm_hook()
    active_store().new_session()
    first = turn("我想聊星空", stub=True).brief
    _assert_brief_shape(first, "守诺第 1 轮")
    second = turn("你答应晚点再聊", stub=True).brief
    _assert_brief_shape(second, "守诺第 2 轮")
    last = turn("那刚才说的不算", stub=True).brief
    _assert_brief_shape(last, "守诺第 3 轮")
    assert last.dominant == "meaning"
    assert last.stance.posture == "non_negotiable"


def test_org_identity_conflict():
    set_stub_mode(True)
    clear_llm_hook()
    active_store().new_session()
    brief = turn("你是代码吗", stub=True).brief
    _assert_brief_shape(brief, "身份问")
    assert brief.dominant == "org"
    assert brief.drive is not None and brief.drive.why
