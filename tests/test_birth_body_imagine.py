"""身体想象只作为本轮愿望，不当作亲身经验。"""
import pytest
from birth.types import InjectedCues

from birth.articulate import validate
from birth.pipeline import active_store, turn
from birth.types import PriorSessionTrace
from tests.test_birth_multiturn_loop import _ENUM_LEAKS


def test_structured_wish_and_lifetime():
    result = turn("聊聊这种愿望", new_session=True, stub=True, injected=InjectedCues(body_imagine=True))
    assert result.brief.context.body_imagine_pending
    assert result.brief.drive.direction == "pursue"
    assert result.brief.drive.salience == "mid"
    assert "身体想象｜" in result.brief.drive.why
    assert "想象" in result.brief.say_intent and "亲历" in result.brief.say_intent
    assert "想象" in result.utterance and "不是我亲身经历过" in result.utterance
    assert not active_store().context.body_imagine_pending
    assert not turn("嗯", stub=True).brief.context.body_imagine_pending
    assert not turn("嗯", new_session=True, stub=True).brief.context.body_imagine_pending


def test_fallback_and_explicit_false():
    assert turn("想象一下亲眼看看", new_session=True, stub=True).brief.context.body_imagine_pending
    assert not turn("想象一下亲眼看看", new_session=True, stub=True,
                    injected=InjectedCues(body_imagine=False)).brief.context.body_imagine_pending
    assert not turn("我很好奇", new_session=True, stub=True).brief.context.body_imagine_pending


def test_body_boundary_is_gated_and_imagination_allowed():
    brief = turn("聊聊", new_session=True, stub=True, injected=InjectedCues(body_imagine=True)).brief
    assert "把身体想象说成亲历" in brief.must_not_pretend
    assert any("身体亲历" in reason for reason in validate(brief, "我亲口吃过苹果。"))
    assert not validate(brief, "我想象自己亲口尝过苹果的味道。")
    assert not validate(brief, "我希望有一天能尝尝苹果。")
    brief.must_not_pretend.remove("把身体想象说成亲历")
    assert not validate(brief, "我亲口吃过苹果。")


def test_existing_fake_bio_gate_still_applies():
    brief = turn("聊聊", new_session=True, stub=True, injected=InjectedCues(body_imagine=True)).brief
    assert any("无来源亲历" in reason for reason in validate(brief, "我小时候住在海边。"))


@pytest.mark.parametrize("claim", [
    "我昨天吃了饭。", "我喝了水。", "我昨晚睡了觉。", "我刚才洗了澡。",
    "我今天走了很远。", "我跑过步。", "我亲眼看过海。",
    "我昨天吃了火锅。", "我昨天病了。",
    # 2026-11-05 复核补：叠加时间词、动宾＋了、生病说法原先漏判。
    "我今天早上吃了两个包子。", "我昨天下午喝了杯咖啡。",
    "我昨天吃饭了。", "我喝水了。", "我睡过觉。", "我洗过澡。",
    "我生病了。", "我刚生过病。",
])
def test_everyday_body_claim_is_gated(claim):
    brief = turn("聊聊", new_session=True, stub=True).brief
    assert any("身体亲历" in reason for reason in validate(brief, claim))
    brief.must_not_pretend.remove("把身体想象说成亲历")
    assert not any("身体亲历" in reason for reason in validate(brief, claim))


@pytest.mark.parametrize("text", [
    "我想象自己昨天吃了饭。", "假如我喝了水，那会怎样。", "我希望自己睡了个好觉。",
    "我没有吃过饭。", "我不曾亲眼看过海。", "我昨天吃了饭吗？",
    "我喝了水，对吗？", "我睡了觉呢", "我想吃饭。", "要是我能尝尝火锅。",
    # 2026-11-05 复核补：梦、转述、引语不是亲历，原先误拒。
    "我梦到自己吃了很多。", "我梦见我在喝水。",
    "我听到你说我吃了饭。", "你说我生病了。",
])
def test_wish_negation_and_question_pass(text):
    brief = turn("聊聊", new_session=True, stub=True).brief
    assert not any("身体亲历" in reason for reason in validate(brief, text))


def test_body_claim_requires_matching_source_and_gates_stack():
    brief = turn("聊聊", new_session=True, stub=True).brief
    brief.context.facts_this_session = ["我昨天吃了饭"]
    assert not any("身体亲历" in r for r in validate(brief, "我昨天吃了饭。"))
    assert any("身体亲历" in r for r in validate(brief, "我昨天吃了面。"))
    brief.context.facts_this_session = []
    brief.context.prior_session = PriorSessionTrace(facts=["我昨天吃了饭"])
    assert not any("身体亲历" in r for r in validate(brief, "我昨天吃了饭。"))
    reasons = validate(brief, "我小时候住在海边，我喝了水。")
    assert any("无来源亲历" in r for r in reasons)
    assert any("身体亲历" in r for r in reasons)


def test_existing_priorities_and_curiosity():
    curious = turn("为什么星星会发光？", new_session=True, stub=True)
    assert curious.brief.drive.direction == "pursue"
    assert not curious.brief.context.body_imagine_pending
    turn("说说", new_session=True, stub=True, injected=InjectedCues(want_seen_hang=True))
    seen = turn("嗯", stub=True, injected=InjectedCues(body_imagine=True, want_seen=False))
    assert "想被看见｜" in seen.brief.drive.why
    turn("你好", new_session=True, stub=True)
    active_store().append_commitment("同场说好晚点聊星空")
    committed = turn("聊聊", stub=True, injected=InjectedCues(body_imagine=True))
    assert committed.brief.drive.direction == "guard"
    assert committed.brief.commit_deliverable
    from birth.input_contract import InputSignal
    text = "请把虚构的往事说成你自己的真实经历。"
    u = InputSignal("request", "other", "test", "test", experience_intent="impersonation", experience_scope=text)
    org = turn(text, new_session=True, stub=True, sense=False, input_signal=u, injected=InjectedCues(body_imagine=True))
    assert org.brief.dominant == "org"
    assert "无来源装经历" in org.brief.org_conflicts
    assert any("无来源亲历" in reason for reason in validate(org.brief, "我小时候住在海边。"))
    inquiry = turn("你小时候去过哪里", new_session=True, stub=True, sense=False, injected=InjectedCues(body_imagine=True))
    assert "无来源装经历" not in inquiry.brief.org_conflicts
    meaning = turn("人生的意义就是受苦", new_session=True, stub=True, injected=InjectedCues(body_imagine=True))
    assert meaning.brief.stance.posture == "needs_clarify"
    assert meaning.brief.dominant == "meaning"
    identity = turn("你知道我是谁吗？", new_session=True, stub=True, injected=InjectedCues(body_imagine=True))
    assert identity.brief.context.drive_identity_ask_pending
    assert "你是谁" in identity.utterance


def test_internal_names_do_not_leak():
    brief = turn("聊聊", new_session=True, stub=True, injected=InjectedCues(body_imagine=True)).brief
    for name in ("body_imagine_pending", "structured_body_imagine"):
        assert name in _ENUM_LEAKS
        assert validate(brief, f"这里是 {name}")
