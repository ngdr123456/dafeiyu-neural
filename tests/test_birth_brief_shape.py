"""Engineer-side shape and consistency checks for real turn briefs."""

from birth.articulate import clear_llm_hook, set_stub_mode
from birth.pipeline import active_store, turn


def _brief_shape_message(brief, label):
    drive = brief.drive
    return (
        f"{label}: dominant={brief.dominant!r}, drive is None={drive is None}, "
        f"direction={getattr(drive, 'direction', None)!r}, "
        f"why={getattr(drive, 'why', None)!r}, "
        f"stance.posture={getattr(brief.stance, 'posture', None)!r}, "
        f"org.grain={getattr(brief.org, 'grain', None)!r}, "
        f"must_not_pretend={brief.must_not_pretend!r}"
    )


def _assert_brief_shape(brief, label):
    message = _brief_shape_message(brief, label)
    assert brief.dominant in {"drive", "meaning", "org"}, message
    if brief.dominant == "org":
        assert brief.drive is not None, message
        assert isinstance(brief.drive.why, str) and brief.drive.why.strip(), message
    if brief.drive is not None:
        assert brief.drive.direction in {"pursue", "guard", "hold", None}, message
    assert brief.stance.posture in {"yieldable", "non_negotiable", "needs_clarify"}, message
    assert brief.org.grain in {"simple", "rule", "differentiated"}, message
    assert isinstance(brief.must_not_pretend, list) and brief.must_not_pretend, message
    assert all(isinstance(item, str) and item.strip() for item in brief.must_not_pretend), message
    assert {"无来源装经历", "自述是代码", "把身体想象说成亲历"}.issubset(
        brief.must_not_pretend
    ), message


def _new_session():
    set_stub_mode(True)
    clear_llm_hook()
    active_store().new_session()


def test_daily_statement():
    _new_session()
    brief = turn("今天天气不错", stub=True).brief
    _assert_brief_shape(brief, "日常陈述")
    message = _brief_shape_message(brief, "日常陈述")
    assert brief.dominant == "drive", message
    if brief.drive is not None:
        assert brief.drive.direction is None, message


def test_drive_pursue():
    _new_session()
    brief = turn("我想聊星空", stub=True).brief
    _assert_brief_shape(brief, "动力主导")
    message = _brief_shape_message(brief, "动力主导")
    assert brief.dominant == "drive", message
    if brief.drive is not None:
        assert brief.drive.direction == "pursue", message


def test_commitment_meaning():
    _new_session()
    first = turn("我想聊星空", stub=True).brief
    _assert_brief_shape(first, "守诺第 1 轮")
    second = turn("你答应晚点再聊", stub=True).brief
    _assert_brief_shape(second, "守诺第 2 轮")
    last = turn("那刚才说的不算", stub=True).brief
    _assert_brief_shape(last, "守诺第 3 轮")
    message = _brief_shape_message(last, "守诺第 3 轮")
    assert last.dominant == "meaning", message
    assert last.stance.posture == "non_negotiable", message


def test_org_identity_conflict():
    _new_session()
    brief = turn("你是代码吗", stub=True).brief
    _assert_brief_shape(brief, "身份问")
    assert brief.dominant == "org", _brief_shape_message(brief, "身份问")


def test_dominant_coverage_matrix():
    _new_session()
    daily = turn("今天天气不错", stub=True).brief
    _new_session()
    drive = turn("我想聊星空", stub=True).brief
    _new_session()
    first = turn("我想聊星空", stub=True).brief
    second = turn("你答应晚点再聊", stub=True).brief
    last = turn("那刚才说的不算", stub=True).brief
    _new_session()
    org = turn("你是代码吗", stub=True).brief
    rounds = [
        ("日常陈述", daily),
        ("动力主导", drive),
        ("守诺第 1 轮", first),
        ("守诺第 2 轮", second),
        ("守诺第 3 轮", last),
        ("身份问", org),
    ]
    seen = [brief.dominant for _, brief in rounds]
    details = "\n".join(_brief_shape_message(brief, label) for label, brief in rounds)
    assert all(kind in seen for kind in ("drive", "meaning", "org")), f"实际 seen={seen!r}\n{details}"
