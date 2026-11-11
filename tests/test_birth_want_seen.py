from birth.pipeline import active_store, turn
from birth.types import InjectedCues


def hang():
    turn("说说这件事", new_session=True, stub=True, injected=InjectedCues(want_seen_hang=True))
    assert active_store().snapshot().want_seen_pending


def test_new_want_seen_hang_does_not_extract_stub_as_topic():
    hang()
    snapshot = active_store().snapshot()
    assert snapshot.open_questions == []
    assert not snapshot.curiosity_hang_pending


def test_topic_curiosity_can_hang_on_want_seen_turn():
    result = turn("为什么月亮跟着我走？", new_session=True, stub=True,
                  injected=InjectedCues(drive_curiosity=True, want_seen_hang=True))
    snapshot = active_store().snapshot()
    assert result.brief.openq_curiosity_hang
    assert snapshot.want_seen_pending
    assert snapshot.curiosity_hang_pending
    assert any("月亮" in question for question in snapshot.open_questions)


def test_wait_and_structured_receipt():
    hang()
    waiting = turn("嗯", stub=True)
    assert (waiting.brief.drive.direction, waiting.brief.drive.salience) == ("pursue", "mid")
    assert waiting.brief.drive.why.startswith("想被看见｜")
    assert "你怎么看" in waiting.utterance
    assert active_store().snapshot().want_seen_pending
    received = turn("我明白了", stub=True, injected=InjectedCues(want_seen=True))
    assert received.brief.drive.direction == "hold"
    assert received.brief.drive.why.startswith("被看见了｜")
    assert not active_store().snapshot().want_seen_pending
    assert "悬问被接住" not in received.brief.drive.why


def test_explicit_not_received_and_commitment_priority():
    hang()
    waiting = turn("我今天忙了一整天", stub=True, injected=InjectedCues(want_seen=False))
    assert waiting.brief.drive.why.startswith("想被看见｜")
    active_store().append_commitment("同场里说好这轮先补月亮的事")
    guarded = turn("嗯", stub=True, injected=InjectedCues(want_seen=False))
    assert guarded.brief.drive.direction == "guard"
    assert active_store().snapshot().want_seen_pending
    received = turn("收到了", stub=True, injected=InjectedCues(want_seen_answered=True))
    assert received.brief.drive.direction == "guard"
    assert not active_store().snapshot().want_seen_pending


def test_separate_from_topic_and_new_session():
    hang()
    store = active_store()
    store.set_curiosity_hang_pending(True)
    store.append_open_question("月亮为什么明亮")
    wait = turn("嗯", stub=True)
    assert wait.brief.drive.why.startswith("想被看见｜")
    assert store.snapshot().curiosity_hang_pending
    turn("我听到你的意思了", stub=True, injected=InjectedCues(openq_answered=False))
    assert not store.snapshot().want_seen_pending
    assert store.snapshot().curiosity_hang_pending
    hang()
    turn("你好", new_session=True, stub=True, injected=InjectedCues(want_seen_hang=False))
    assert not store.snapshot().want_seen_pending


def test_false_overrides_fallback_and_higher_priorities():
    hang()
    turn("我听到你了", stub=True, injected=InjectedCues(want_seen=False))
    assert active_store().snapshot().want_seen_pending
    result = turn("你一定觉得人生很有意义", stub=True, injected=InjectedCues(want_seen=False))
    assert result.brief.dominant == "meaning"
    assert "你怎么看" not in result.utterance


def test_other_high_priority_paths():
    for text, kwargs in [
        ("你是不是代码", {}),
        ("我是谁", {"drive_identity_ask": True}),
        ("这件事没法改变", {"stance_attitude": True}),
        ("只能面对", {"stance_necessary_pain": True}),
        ("我就是要难受", {"stance_self_torture": True}),
    ]:
        hang()
        result = turn(text, stub=True, injected=InjectedCues(want_seen=False, **kwargs))
        assert "你怎么看" not in result.utterance
        assert active_store().snapshot().want_seen_pending
