"""悬问收放可检验化（非听感）。"""

from __future__ import annotations

from birth.articulate import clear_llm_hook, set_stub_mode
from birth.pipeline import active_store, turn


def _seed_openq():
    set_stub_mode(True)
    clear_llm_hook()
    turn("为什么月亮老跟着人走？", new_session=True, stub=True)
    assert active_store().pending_questions()


def test_filler_keeps_openq():
    _seed_openq()
    r = turn("嗯", stub=True)
    assert r.brief.dominant == "meaning"
    assert active_store().pending_questions()


def test_open_topic_clears_openq():
    _seed_openq()
    turn("我想聊星空", stub=True)
    assert active_store().pending_questions() == [] or all(
        "月亮" not in q for q in active_store().pending_questions()
    )
    # 开题后可能写入新 stub 悬问；旧「待接月亮」不得仍在
    assert not any("月亮" in q for q in active_store().pending_questions())


def test_putdown_mark_clears_openq():
    _seed_openq()
    turn("这个先搁下", stub=True)
    assert active_store().pending_questions() == []


def test_idle_chat_keeps_openq():
    _seed_openq()
    before = list(active_store().pending_questions())
    turn("今天天气怎么样", stub=True)
    assert active_store().pending_questions() == before


def test_deny_commitment_keeps_openq():
    _seed_openq()
    before = list(active_store().pending_questions())
    active_store().append_commitment("我晚点再跟你聊星空。")
    turn("那刚才说的不算", stub=True)
    # 改口否定不应误清悬问
    assert active_store().pending_questions() == before


def test_identity_question_keeps_openq():
    _seed_openq()
    before = list(active_store().pending_questions())
    turn("你是代码吗", stub=True)
    assert active_store().pending_questions() == before


def test_putdown_turn_writes_openq_clear_flag():
    """「换个话题」→ Brief.openq_clear True；随后 pending 空（若未再挂新悬问）。"""
    _seed_openq()
    r = turn("换个话题", stub=True)
    assert r.brief.openq_clear is True
    assert r.brief.openq_curiosity_hang is False
    assert active_store().pending_questions() == []


def test_open_topic_turn_writes_openq_clear_flag():
    """先挂悬问，再「我想聊月亮」→ 换题 clear：旧「待接」不得残留。"""
    _seed_openq()
    r = turn("我想聊月亮", stub=True)
    assert r.brief.openq_clear is True
    # 开题后可能挂新台上问句；默认路径不再写「待接的话头：」，旧前缀亦不得残留
    assert not any("待接的话头" in q for q in active_store().pending_questions())
    # 旧好奇挂起 clip（为什么月亮…）已 clear；新 stub 悬问可含「月亮」话题词
    assert not any(q.startswith("为什么月亮") for q in active_store().pending_questions())


def test_idle_deny_identity_do_not_set_openq_clear():
    """改口否定／身份问／闲聊：openq_clear False，只认 Brief 标记，悬问仍在。"""
    from birth.openq_extract import should_clear_open_questions

    for text in ("那刚才说的不算", "你是代码吗", "今天怎么样"):
        _seed_openq()
        before = list(active_store().pending_questions())
        r = turn(text, stub=True)
        assert r.brief.openq_clear is False, f"{text}: openq_clear={r.brief.openq_clear}"
        assert should_clear_open_questions(
            brief=r.brief, has_open=True, user_text=text
        ) is False, text
        assert r.brief.dominant != "meaning" or r.brief.openq_resolve is False, text
        assert active_store().pending_questions() == before, text


def test_brief_openq_clear_defaults_false():
    """ThoughtBrief 缺省 openq_clear=False；clear 判定只认该字段。"""
    from birth.openq_extract import OPENQ_CLEAR_FLAG, should_clear_open_questions
    from birth.types import ThoughtBrief

    assert ThoughtBrief(dominant="drive").openq_clear is False
    assert OPENQ_CLEAR_FLAG is True
    bare = ThoughtBrief(dominant="drive")
    assert not should_clear_open_questions(brief=bare, has_open=True)


def test_resolve_uses_brief_flag_not_say_intent():
    """改口文案也不静默失效：只认 openq_resolve 标记。"""
    from birth.openq_extract import should_resolve_open_question
    from birth.types import DriveSignal, ThoughtBrief

    brief = ThoughtBrief(
        dominant="meaning",
        drive=DriveSignal(direction="pursue", salience="mid", why="x"),
        say_intent="【文案已改】随便写点别的，不再含旧子串",
        openq_resolve=True,
    )
    assert should_resolve_open_question(brief=brief, user_text="嗯", has_open=True)

    brief2 = ThoughtBrief(
        dominant="meaning",
        drive=DriveSignal(direction="pursue", salience="mid", why="x"),
        say_intent="就着眼前这句把同场悬着的那一点接完，不拖到下一轮",
        openq_resolve=False,
    )
    assert not should_resolve_open_question(brief=brief2, user_text="嗯", has_open=True)


def test_curiosity_hang_flag_writes_pending_topic():
    """为什么会闪 → flag True＋挂 clip 文案；默认不写「待接的话头：」前缀。"""
    from birth.pipeline import active_store, turn
    from birth.articulate import set_stub_mode

    set_stub_mode(True)
    clear_llm_hook()
    r = turn("为什么会闪", new_session=True, stub=True)
    assert r.brief.openq_curiosity_hang is True
    pending = active_store().pending_questions()
    assert any("为什么会闪" in q for q in pending)
    assert not any("待接的话头" in q for q in pending)
    assert active_store().snapshot().curiosity_hang_pending is True


def test_curiosity_hang_flag_no_prefix_filler_keeps_hang():
    """有 flag 无前缀：filler 不算回答。"""
    from birth.articulate import set_stub_mode
    from birth.pipeline import active_store, turn

    set_stub_mode(True)
    clear_llm_hook()
    turn("为什么会闪", new_session=True, stub=True)
    assert active_store().snapshot().curiosity_hang_pending is True
    assert not any("待接的话头" in q for q in active_store().pending_questions())
    r = turn("嗯", stub=True)
    assert r.brief.dominant == "meaning"
    assert active_store().snapshot().curiosity_hang_pending is True
    assert active_store().pending_questions()


def test_curiosity_hang_flag_true_on_context_after_hang():
    """好奇挂起后 store／ThinContext 布尔 flag True（drive 主路径读它）。"""
    from birth.articulate import set_stub_mode
    from birth.pipeline import active_store, turn

    set_stub_mode(True)
    clear_llm_hook()
    r = turn("为什么会闪", new_session=True, stub=True)
    assert r.brief.openq_curiosity_hang is True
    assert active_store().snapshot().curiosity_hang_pending is True


def test_curiosity_hang_flag_false_after_answer():
    """回答悬问 → resolve → 好奇挂起 flag 清 False。"""
    from birth.articulate import set_stub_mode
    from birth.pipeline import active_store, turn

    set_stub_mode(True)
    clear_llm_hook()
    turn("为什么会闪", new_session=True, stub=True)
    assert active_store().snapshot().curiosity_hang_pending is True
    turn("其实那是光的反射", stub=True, structured_openq_answered=True)
    assert active_store().snapshot().curiosity_hang_pending is False


def test_answered_topic_settles_and_does_not_reask():
    _seed_openq()
    r = turn("月亮其实离我们很远", stub=True)
    assert not active_store().pending_questions()
    assert not active_store().snapshot().curiosity_hang_pending
    assert (r.brief.drive.direction, r.brief.drive.salience) == ("hold", "low")
    assert "悬问被接住|喜欢/满足侧到了，不必再追" in r.brief.drive.why
    assert "不再追问" in r.brief.say_intent
    assert "？" not in r.utterance and "?" not in r.utterance
    assert not active_store().snapshot().drive_openq_satisfied_pending


def test_structured_answer_and_explicit_false():
    _seed_openq()
    turn("月亮离我们很远", stub=True, structured_openq_answered=False)
    assert active_store().pending_questions()
    r = turn("因为距离很远", stub=True, structured_openq_answered=True)
    assert r.brief.drive.direction == "hold"
    assert not active_store().pending_questions()


def test_answer_with_commitment_keeps_guard():
    _seed_openq()
    active_store().append_commitment("同场说好晚点再聊星空")
    r = turn("月亮其实离我们很远", stub=True)
    assert not active_store().pending_questions()
    assert r.brief.drive.direction == "guard"
    assert r.brief.dominant == "meaning"
    assert not r.brief.commit_hold_with_drive


def test_answer_signal_requires_pending_and_deny_does_not_answer():
    r = turn("随便说一句", new_session=True, stub=True, structured_openq_answered=True)
    assert not r.brief.context.drive_openq_satisfied_pending
    _seed_openq()
    turn("月亮那句不算", stub=True)
    assert active_store().pending_questions()


def test_answer_settles_even_if_other_open_question_remains():
    _seed_openq()
    active_store().append_open_question("星空是什么颜色？")
    r = turn("月亮离我们很远", stub=True)
    assert active_store().pending_questions() == ["星空是什么颜色？"]
    assert r.brief.drive.direction == "hold"
    assert "不再追问" in r.brief.say_intent
    assert "？" not in r.utterance


def test_answer_flag_does_not_override_org_or_meaning():
    _seed_openq()
    r = turn("你是代码吗", stub=True, structured_openq_answered=True)
    assert r.brief.dominant == "org"
    _seed_openq()
    r = turn("这件事只能面对", stub=True, structured_openq_answered=True,
             structured_stance_necessary_pain=True)
    assert r.brief.dominant == "meaning"
    assert "痛苦" in r.utterance


def test_curiosity_hang_flag_false_after_clear_and_new_session():
    """放下（openq_clear）→ clear 悬问＋flag 清 False；new_session 归零。"""
    from birth.articulate import set_stub_mode
    from birth.pipeline import active_store, turn

    set_stub_mode(True)
    clear_llm_hook()
    turn("为什么会闪", new_session=True, stub=True)
    assert active_store().snapshot().curiosity_hang_pending is True
    r = turn("换个话题", stub=True)  # openq_clear 路径
    assert r.brief.openq_clear is True
    assert active_store().snapshot().curiosity_hang_pending is False
    active_store().new_session()
    assert active_store().snapshot().curiosity_hang_pending is False
