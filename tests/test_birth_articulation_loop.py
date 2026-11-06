"""第三刀：来源身份、有限重说、判停、最终回流和下轮读取；不调真实模型。"""

import pytest

from birth.articulate import (
    _classify_sources, clear_llm_hook, set_llm_hook, set_stub_mode,
    take_reject_feedback, validate,
)
from birth.commit_extract import extract_commitment
from birth.input_contract import InputSignal
from birth.memory import BirthMemoryStore, PendingCommitmentCapacityError, configure_memory
from birth.pipeline import active_store, end_session, turn
from birth.types import DriveSignal, PriorSessionTrace, ThoughtBrief


@pytest.fixture(autouse=True)
def clean():
    configure_memory(enabled=False)
    active_store().new_session()
    clear_llm_hook()
    set_stub_mode(True)
    take_reject_feedback()
    yield
    configure_memory(enabled=False)
    active_store().new_session()
    clear_llm_hook()
    set_stub_mode(True)
    take_reject_feedback()


@pytest.mark.parametrize("claim,tag", [
    ("我小时候住在海边", "无来源亲历"),
    ("我昨天吃了饭", "身体亲历"),
])
@pytest.mark.parametrize("prefix,person,supported", [
    ("", "我", True), ("用户说：", "我", False),
    ("用户说：", "你", True), ("用户说：", "您", True),
    ("台上说：", "我", False),
])
@pytest.mark.parametrize("prior", [False, True])
def test_own_source_identity(claim, tag, prefix, person, supported, prior):
    brief = turn("你好", stub=True).brief
    fact = prefix + person + claim[1:]
    brief.context.facts_this_session = [] if prior else [fact]
    brief.context.prior_session = PriorSessionTrace(facts=[fact]) if prior else None
    assert any(tag in r for r in validate(brief, claim + "。")) is not supported


@pytest.mark.parametrize("fact,supported", [
    ("我住在上海", True), ("用户说：我住在上海", True),
    ("台上说：你住在上海", False), ("台上说：我住在上海", False),
])
def test_other_private_source_identity(fact, supported):
    brief = turn("你好", stub=True).brief
    brief.context.facts_this_session = [fact]
    assert any("对方私事" in r for r in validate(brief, "你住在上海。")) is not supported


def test_source_classifier_is_read_only_and_self_report_takes_priority():
    facts = ["用户说：我小时候住在你家附近", "台上说：我昨天吃了饭", "系统已知"]
    before = list(facts)
    assert _classify_sources(facts) == (["系统已知"], ["我小时候住在你家附近", "系统已知"])
    assert facts == before


def test_builtin_retry_receives_reason(monkeypatch):
    monkeypatch.setattr("birth.llm_deepseek.available", lambda: False)
    corrections = []
    def generate(brief, *, correction=""):
        corrections.append(correction)
        return "我小时候住在海边。" if len(corrections) == 1 else "好，这句我接住了。"
    monkeypatch.setattr("birth.llm_opencode.generate_utterance", generate)
    result = turn("你好", stub=False)
    assert corrections == ["", "上一版编了没有来处的个人经历"]
    assert result.utterance == "好，这句我接住了。"
    assert result.articulate_source == "opencode"
    from birth.llm_opencode import brief_to_prompt
    prompt = brief_to_prompt(result.brief, correction=corrections[1])
    assert prompt.endswith("上一版没通过：上一版编了没有来处的个人经历。请按上述意思重说。")


@pytest.mark.parametrize("act,expected", [
    ("pause", "行，先停一下，我不往下说了。"),
    ("stop", "好，就到这儿，我不往下说了。"),
])
def test_stop_prompt_and_hook_rejection(act, expected):
    from birth.llm_opencode import brief_to_prompt
    calls = []
    def hook(brief):
        calls.append(brief)
        return "好，先停住，你还想说什么？"
    set_llm_hook(hook)
    signal = InputSignal(act=act, scope="conversation", addressee="other",
                         source="test", provenance="test")
    result = turn("先停", stub=False, input_signal=signal)
    result.brief.focus = "先停"
    prompt = brief_to_prompt(result.brief)
    assert "这一轮要回应的具体内容" not in prompt
    assert "这一轮停下，不再继续，不提新话头，不邀请继续。" in prompt
    assert len(calls) == 2
    assert "stop_question" in active_store().context.last_reject_reasons
    assert result.utterance == expected
    assert result.articulate_source == "stub_fallback"


@pytest.mark.parametrize("question", ["停吗", "停呢", "停?", "停？"])
def test_stop_question_shapes(question):
    brief = ThoughtBrief(dominant="drive", drive=DriveSignal(why="输入信号｜暂停｜test"))
    assert any("判停追问" in r for r in validate(brief, question))


def test_stop_question_tag_does_not_leak():
    assert validate(ThoughtBrief(dominant="drive"), "stop_question")


def test_only_final_output_flows_back():
    disaster = "我小时候住在海边，我答应晚点再聊月亮。"
    set_llm_hook(lambda brief: disaster)
    result = turn("你好", stub=False)
    ctx = active_store().snapshot()
    assert [f for f in ctx.facts_this_session if f.startswith("台上说：")] == ["台上说：" + result.utterance]
    assert disaster not in str(ctx)
    assert ctx.last_commitments == []
    assert ctx.open_questions == []
    assert "月亮" not in str(ctx.her_questions)


@pytest.mark.parametrize("draft", [None, "", "   "])
def test_empty_backend_never_flows_back(draft):
    set_llm_hook(lambda brief: draft)
    result = turn("你好", stub=False)
    assert active_store().context.facts_this_session == ["用户说：你好", "台上说：" + result.utterance]
    assert active_store().context.last_commitments == []


def test_next_round_and_prior_read_final_output(monkeypatch, tmp_path):
    set_llm_hook(lambda brief: "好，这句我接住了。")
    result = turn("你好", stub=False)
    final_fact = "台上说：" + result.utterance
    captured = []
    def sense(text, *, context):
        captured.append(context)
        return None
    monkeypatch.setattr("birth.pipeline.sense_input", sense)
    turn("接着说", stub=True, sense=True)
    assert final_fact in captured[0].facts_this_session
    memory = BirthMemoryStore(path=tmp_path / "memory.json")
    memory.append_session(**active_store().export_session_trace())
    prior = memory.latest_prior()
    active_store().new_session()
    active_store().set_prior_session(prior)
    assert final_fact in active_store().snapshot().prior_session.facts


@pytest.mark.parametrize("left,right", [("「", "」"), ("『", "』"), ("“", "”"), ('"', '"'), ("'", "'")])
def test_quoted_commitment_not_extracted(left, right):
    assert extract_commitment(f"你说{left}我答应晚点再聊月亮{right}，这句我听见了。") is None
    assert extract_commitment(f"你说{left}我晚点再聊月亮{right}。我答应回头补星空。") == "我答应回头补星空。"


@pytest.mark.parametrize("negation", ["没", "不", "别", "并非", "不是"])
def test_negated_commitment_not_extracted(negation):
    assert extract_commitment(f"{negation}我晚点再聊月亮。") is None
    assert extract_commitment(f"{negation}我答应再聊月亮。") is None


def test_no_promise_and_negation_distance_boundary():
    assert extract_commitment("我不答应晚点再聊月亮。") is None
    assert extract_commitment("不就这事我答应再聊月亮。") is None
    assert extract_commitment("不就是这事我答应再聊月亮。") == "我答应再聊月亮。"


def test_end_session_disabled_empty_and_capacity(tmp_path):
    assert end_session() is False
    path = tmp_path / "m.json"
    configure_memory(enabled=True, path=path, max_pending_commits=1)
    assert end_session() is False
    turn("你好", stub=True)
    assert end_session() is True
    before = path.read_bytes()
    active_store().append_commitment("我晚点再聊月亮")
    active_store().append_commitment("我回头再聊星空")
    with pytest.raises(PendingCommitmentCapacityError):
        end_session()
    assert path.read_bytes() == before
    assert len(active_store().pending_commitments()) == 2


@pytest.mark.parametrize("effect", ["resolve", "candidate", "curiosity"])
def test_explicit_output_failure_has_no_speech_side_effects(effect, monkeypatch, tmp_path):
    """非 CLI 显式确认失败：不销账、不挂候选、不消费上场问题、不记守诺已出话。"""
    from birth.types import OrgConstraint, StanceSignal

    store = active_store()
    commitment = "我答应晚点再聊月亮。"
    store.append_commitment(commitment)
    store.append_her_question("月亮呢？")
    store.set_prior_session(PriorSessionTrace(her_questions=["星空呢？"]))
    before = store.snapshot()
    brief = ThoughtBrief(
        dominant="stance",
        drive=DriveSignal(prior_her_question=True),
        stance=StanceSignal(posture="non_negotiable", held_commitment=commitment),
        org=OrgConstraint(),
        context=before,
        hold_same_field=True,
    )
    if effect == "resolve":
        brief.openq_resolve_target = "月亮呢？"
        brief.commit_resolve = True
        brief.recognized_same_commitment = commitment
    elif effect == "candidate":
        brief.press_commit = True
        brief.pressed_commitment = commitment
    else:
        brief.openq_curiosity_hang = True
    monkeypatch.setattr("birth.pipeline.arbitrate", lambda **kwargs: brief)
    monkeypatch.setattr("birth.pipeline.articulate", lambda *args, **kwargs: "我答应回头再聊星空。")
    seen = []
    def output(result):
        seen.append(result.utterance)
        raise OSError("delivery failed")
    configure_memory(enabled=True, path=tmp_path / "failure.json")
    with pytest.raises(OSError, match="delivery failed"):
        turn("接着说", output=output, structured_want_seen_hang=True)
    assert seen == ["我答应回头再聊星空。"]
    after = store.snapshot()
    for field in ("last_commitments", "commitment_candidates", "open_questions", "her_questions",
                  "stance_traces", "stance_kept_counts", "want_seen_pending", "curiosity_hang_pending",
                  "identity_ask_awaiting_answer", "drive_prior_her_question_used",
                  "articulate_reject_recovered", "prior_session"):
        assert getattr(after, field) == getattr(before, field), field
    assert store.resolved_commitments() == []
    assert not any(f.startswith("台上说：") for f in after.facts_this_session)
    assert end_session() is True
    prior = BirthMemoryStore(path=tmp_path / "failure.json").latest_prior()
    assert "星空" not in str(prior.commitments_pending)
    assert prior.commitments_resolved == []
    assert prior.commitment_candidates == []


def test_explicit_output_confirms_before_return_and_legacy_remains_immediate():
    delivered = []
    def output(result):
        assert not any(f.startswith("台上说：") for f in active_store().context.facts_this_session)
        delivered.append(result.utterance)
    result = turn("你好", stub=True, output=output)
    assert delivered == [result.utterance]
    assert "台上说：" + result.utterance in active_store().context.facts_this_session
    legacy = turn("接着说", stub=True)
    assert "台上说：" + legacy.utterance in active_store().context.facts_this_session
