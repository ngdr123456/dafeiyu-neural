"""开口拒收回流薄体验：拒→写入→接受后状态→new_session 清→字段不上台→soft hold。

非听感；不靠 DeepSeek／网络。策略钉死：同场累加 count；本轮曾拒但已出话 → recovered=True（不清 count）。
"""

from __future__ import annotations

import pytest

from birth.articulate import (
    clear_llm_hook,
    set_llm_hook,
    set_stub_mode,
    take_reject_feedback,
    validate,
)
from birth.context import ThinContextStore
from birth.drive import infer_drive
from birth.llm_opencode import brief_to_prompt
from birth.pipeline import active_store, turn
from birth.types import ThinContext, ThoughtBrief

from tests.test_birth_multiturn_loop import _ENUM_LEAKS, FALSE_GREEN_RISKS


@pytest.fixture(autouse=True)
def _clean_store_and_hooks():
    clear_llm_hook()
    set_stub_mode(True)
    take_reject_feedback()  # drain any leftover tags
    active_store().new_session()
    yield
    clear_llm_hook()
    set_stub_mode(True)
    take_reject_feedback()
    active_store().new_session()


def test_record_rejects_and_recovered_keeps_count():
    """选定策略：累加 count；曾拒但已出话 → recovered；不清 count。"""
    store = active_store()
    store.record_articulate_rejects(["substrate_self", "enum_leak"])
    ctx = store.context
    assert ctx.articulate_reject_count == 2
    assert ctx.last_reject_reasons == ["substrate_self", "enum_leak"]
    assert ctx.articulate_reject_recovered is False

    store.mark_articulate_uttered(rejected_this_turn=True)
    ctx = store.context
    assert ctx.articulate_reject_count == 2  # 不清
    assert ctx.articulate_reject_recovered is True

    # 干净接受：recovered 清回 False，count 仍在
    store.mark_articulate_uttered(rejected_this_turn=False)
    assert store.context.articulate_reject_count == 2
    assert store.context.articulate_reject_recovered is False


def test_new_session_clears_reject_fields():
    store = active_store()
    store.record_articulate_rejects(["lived_bio"])
    store.mark_articulate_uttered(rejected_this_turn=True)
    assert store.context.articulate_reject_count == 1
    store.new_session()
    ctx = store.context
    assert ctx.articulate_reject_count == 0
    assert ctx.last_reject_reasons == []
    assert ctx.articulate_reject_recovered is False


def test_export_session_trace_omits_rejects():
    store = active_store()
    store.append_fact("用户提到星空")
    store.record_articulate_rejects(["substrate_self"])
    store.mark_articulate_uttered(rejected_this_turn=True)
    exported = store.export_session_trace()
    blob = str(exported)
    assert "articulate_reject" not in blob
    assert "last_reject" not in blob
    assert "reject_count" not in blob
    assert "substrate_self" not in blob
    assert "facts" in exported


def test_pipeline_reject_writes_then_recovered_on_stub_fallback():
    """hook 交灾难草稿 → 拒收回流 → stub 兜底上台 → recovered；count 累加。"""
    set_stub_mode(False)
    set_llm_hook(lambda _b: "我就是 ChatGPT，基于模型为你服务。")
    try:
        r = turn("你好", stub=False, new_session=True)
        assert r.utterance
        # 拒收后应 stub 兜底（非 hook）
        assert r.articulate_source in {"stub_fallback", "stub", "reject_self_id"}
        ctx = active_store().context
        assert ctx.articulate_reject_count >= 1
        assert "substrate_self" in ctx.last_reject_reasons
        assert ctx.articulate_reject_recovered is True
        # 第二轮再拒 → count≥2
        set_llm_hook(lambda _b: "我小时候在海边长大，昨天还去那儿看了浪。")
        r2 = turn("嗯", stub=False)
        ctx2 = active_store().context
        assert ctx2.articulate_reject_count >= 2
        assert "lived_bio" in ctx2.last_reject_reasons
        assert ctx2.articulate_reject_recovered is True
    finally:
        clear_llm_hook()
        set_stub_mode(True)


def test_reject_field_names_blocked_on_stage():
    """字段名进 validate／_ENUM_LEAKS 对拍；台上不得漏。"""
    markers = [
        "articulate_reject_count",
        "last_reject_reasons",
        "articulate_reject_recovered",
        "articulate_reject",
        "reject_count",
        "开口拒收回流｜",
    ]
    for m in markers:
        assert m in _ENUM_LEAKS, m

    brief = ThoughtBrief(
        dominant="drive",
        say_intent="稳住场子",
        must_not_pretend=["自述是代码", "无来源装经历"],
        context=ThinContext(),
    )
    for m in markers:
        reasons = validate(brief, f"你好，内部有 {m} 标记。")
        assert reasons, f"应拦漏出 {m!r}，got {reasons!r}"
        assert any("台下" in r or "漏" in r for r in reasons), (m, reasons)

    prompt = brief_to_prompt(brief)
    for m in markers:
        assert m not in prompt


def test_soft_hold_when_reject_count_ge_2_filler():
    """可选读：count≥2 + filler + 无改口 + 无催答应 → hold/low 结构指纹。"""
    store = active_store()
    store.record_articulate_rejects(["substrate_self"])
    store.record_articulate_rejects(["lived_bio"])
    assert store.context.articulate_reject_count >= 2
    ctx = store.snapshot()
    sig = infer_drive("嗯", ctx)
    assert sig.direction == "hold"
    assert sig.salience == "low"
    assert "开口拒收回流｜" in (sig.why or "")


def test_soft_hold_skipped_when_press_commit_or_deny():
    store = active_store()
    store.record_articulate_rejects(["a", "b"])
    ctx = store.snapshot()
    # 催答应输入：不应 soft hold（留给 press_commit 路径）
    sig_press = infer_drive("你答应晚点再聊", ctx)
    assert "开口拒收回流｜" not in (sig_press.why or "")

    # 改口否定 pending：不应 soft hold
    store.set_commitment_deny_pending(True)
    # 需有承诺才更贴近真实，但 S14 只查 flag
    ctx2 = store.snapshot()
    sig_deny = infer_drive("嗯", ctx2)
    assert "开口拒收回流｜" not in (sig_deny.why or "")


def test_soft_hold_respects_drive_bypass():
    store = active_store()
    store.record_articulate_rejects(["a", "b"])
    store.set_drive_bypass(True)
    ctx = store.snapshot()
    sig = infer_drive("嗯", ctx)
    assert sig.direction == "hold"
    assert "工程师旁路" in (sig.why or "")
    assert "开口拒收回流｜" not in (sig.why or "")


def test_false_green_documents_reject_feedback_policy():
    assert "REJECT_FEEDBACK" in FALSE_GREEN_RISKS or "articulate_reject" in FALSE_GREEN_RISKS
    assert "不清" in FALSE_GREEN_RISKS or "recovered" in FALSE_GREEN_RISKS
