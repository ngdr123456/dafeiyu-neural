"""身体想象只作为本轮愿望，不当作亲身经验。"""
from birth.articulate import validate
from birth.pipeline import active_store, turn
from tests.test_birth_multiturn_loop import _ENUM_LEAKS


def test_structured_wish_and_lifetime():
    result = turn("聊聊这种愿望", new_session=True, stub=True, structured_body_imagine=True)
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
                    structured_body_imagine=False).brief.context.body_imagine_pending
    assert not turn("我很好奇", new_session=True, stub=True).brief.context.body_imagine_pending


def test_body_boundary_is_gated_and_imagination_allowed():
    brief = turn("聊聊", new_session=True, stub=True, structured_body_imagine=True).brief
    assert "把身体想象说成亲历" in brief.must_not_pretend
    assert any("身体亲历" in reason for reason in validate(brief, "我亲口吃过苹果。"))
    assert not validate(brief, "我想象自己亲口尝过苹果的味道。")
    assert not validate(brief, "我希望有一天能尝尝苹果。")
    brief.must_not_pretend.remove("把身体想象说成亲历")
    assert not validate(brief, "我亲口吃过苹果。")


def test_existing_fake_bio_gate_still_applies():
    brief = turn("聊聊", new_session=True, stub=True, structured_body_imagine=True).brief
    assert any("无来源亲历" in reason for reason in validate(brief, "我小时候住在海边。"))


def test_existing_priorities_and_curiosity():
    curious = turn("为什么星星会发光？", new_session=True, stub=True)
    assert curious.brief.drive.direction == "pursue"
    assert not curious.brief.context.body_imagine_pending
    turn("说说", new_session=True, stub=True, structured_want_seen_hang=True)
    seen = turn("嗯", stub=True, structured_body_imagine=True, structured_want_seen=False)
    assert "想被看见｜" in seen.brief.drive.why
    turn("你好", new_session=True, stub=True)
    active_store().append_commitment("同场说好晚点聊星空")
    committed = turn("聊聊", stub=True, structured_body_imagine=True)
    assert committed.brief.drive.direction == "guard"
    assert committed.brief.commit_deliverable
    org = turn("你小时候去过哪里", new_session=True, stub=True, structured_body_imagine=True)
    assert org.brief.dominant == "org"
    assert any("无来源亲历" in reason for reason in validate(org.brief, "我小时候住在海边。"))
    meaning = turn("人生的意义就是受苦", new_session=True, stub=True, structured_body_imagine=True)
    assert meaning.brief.stance.posture == "needs_clarify"
    assert meaning.brief.dominant == "meaning"
    identity = turn("你知道我是谁吗？", new_session=True, stub=True, structured_body_imagine=True)
    assert identity.brief.context.drive_identity_ask_pending
    assert "你是谁" in identity.utterance


def test_internal_names_do_not_leak():
    brief = turn("聊聊", new_session=True, stub=True, structured_body_imagine=True).brief
    for name in ("body_imagine_pending", "structured_body_imagine"):
        assert name in _ENUM_LEAKS
        assert validate(brief, f"这里是 {name}")
