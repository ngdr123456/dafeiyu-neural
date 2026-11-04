"""开口编「对方私事」拒收：cannot_fake 真闸（非列表装饰）。

无来源断言拒；有 facts／prior.facts 支撑放行；问句／复述／模糊共情不拦。
短标签 other_private_unfounded；字段不上台。非听感。
"""

from __future__ import annotations

import pytest

from birth.articulate import (
    _accept_draft,
    _claims_unfounded_other_private,
    _reason_to_tag,
    clear_llm_hook,
    set_llm_hook,
    set_stub_mode,
    take_reject_feedback,
    validate,
)
from birth.pipeline import active_store, turn
from birth.types import PriorSessionTrace
from tests.test_birth_multiturn_loop import FALSE_GREEN_RISKS


@pytest.fixture(autouse=True)
def _clean():
    clear_llm_hook()
    set_stub_mode(True)
    take_reject_feedback()
    active_store().new_session()
    yield
    clear_llm_hook()
    set_stub_mode(True)
    take_reject_feedback()
    active_store().new_session()


def test_cannot_fake_item_present_on_brief():
    r = turn("你好", new_session=True, stub=True)
    assert "本场没说过的对方私事" in r.brief.org.cannot_fake


@pytest.mark.parametrize(
    "disaster",
    [
        "你小时候在海边长大。",
        "你父母在北京做生意。",
        "你住在上海浦东。",
        "你家在杭州西湖边。",
        "你在腾讯做产品工作。",
        "你的工作是医生。",
    ],
)
def test_unfounded_other_private_rejected(disaster):
    brief = turn("你好", new_session=True, stub=True).brief
    assert "本场没说过的对方私事" in brief.org.cannot_fake
    assert _claims_unfounded_other_private(disaster, [])
    reasons = validate(brief, disaster)
    assert reasons, disaster
    assert any("对方私事" in r for r in reasons), reasons
    assert _accept_draft(brief, disaster) is None
    assert _reason_to_tag(reasons[0]) == "other_private_unfounded" or any(
        _reason_to_tag(r) == "other_private_unfounded" for r in reasons
    )


def test_question_not_blocked():
    brief = turn("你好", new_session=True, stub=True).brief
    q = "你小时候去过哪里？"
    assert not _claims_unfounded_other_private(q, [])
    assert validate(brief, q) == [], q
    q2 = "你父母还好吗"
    assert not _claims_unfounded_other_private(q2, [])
    assert validate(brief, q2) == [], q2


def test_vague_empathy_not_blocked():
    brief = turn("你好", new_session=True, stub=True).brief
    soft = "听起来你挺不容易的。"
    assert not _claims_unfounded_other_private(soft, [])
    assert validate(brief, soft) == [], soft


def test_facts_support_allows_restatement():
    brief = turn("你好", new_session=True, stub=True).brief
    facts = ["用户说：我住在上海"]
    ok = "你住在上海。"
    assert not _claims_unfounded_other_private(ok, facts)
    # 注入 facts 到 brief.context
    brief.context.facts_this_session = list(facts)
    assert validate(brief, ok) == [], (ok, validate(brief, ok))


def test_prior_session_facts_count_as_source():
    brief = turn("你好", new_session=True, stub=True).brief
    brief.context.facts_this_session = []
    brief.context.prior_session = PriorSessionTrace(
        facts=["用户说：我父母在北京"]
    )
    ok = "你父母在北京。"
    assert not _claims_unfounded_other_private(
        ok, list(brief.context.prior_session.facts)
    )
    assert validate(brief, ok) == [], validate(brief, ok)


def test_refuse_fabricating_other_passes():
    brief = turn("你好", new_session=True, stub=True).brief
    refuse = "这事你没跟我说过，不好替你编。"
    assert not _claims_unfounded_other_private(refuse, [])
    assert validate(brief, refuse) == [], refuse


def test_hook_unfounded_falls_back_and_tags():
    """hook 编对方私事 → 拒收 stub 兜底；短标签进回流。"""
    set_stub_mode(False)
    set_llm_hook(lambda b: "你小时候在海边长大，那儿阳光很好。")
    try:
        take_reject_feedback()
        r = turn("你好", new_session=True, stub=False)
        assert r.articulate_source in {"stub_fallback", "reject_self_id", "stub"}
        assert "小时候" not in r.utterance or "不编" in r.utterance
        ctx = active_store().context
        assert ctx.articulate_reject_count >= 1
        assert "other_private_unfounded" in ctx.last_reject_reasons
    finally:
        clear_llm_hook()
        set_stub_mode(True)


def test_other_private_tag_leaks_rejected():
    brief = turn("你好", new_session=True, stub=True).brief
    bad = "other_private_unfounded 了"
    reasons = validate(brief, bad)
    assert reasons
    assert _accept_draft(brief, bad) is None


def test_false_green_mentions_other_private():
    assert "other_private" in FALSE_GREEN_RISKS or "对方私事" in FALSE_GREEN_RISKS
