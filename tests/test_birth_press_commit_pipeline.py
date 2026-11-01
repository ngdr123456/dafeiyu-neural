"""催答应底层流水线单测（非听感、非多轮闲聊验收）。

路径：user_presses → arbitrate.say_intent → brief_to_prompt →
articulate(真 LLM 通道／hook) → extract_commitment → ThinContext 回流；
失败／不可提取 → stub_fallback 模板仍可提取。

约束：extract 拒收仅当 say_intent 命中「催一个可核对的约定」；不扩 commit_extract 词表、不当通用堵嘴。
"""

from __future__ import annotations

import pytest

from birth.arbitrate import arbitrate
from birth.articulate import (
    articulate,
    clear_llm_hook,
    last_articulate_source,
    set_llm_hook,
    set_stub_mode,
    validate,
)
from birth.commit_extract import extract_commitment, user_presses_commitment
from birth.drive import infer_drive
from birth.llm_opencode import brief_to_prompt
from birth.pipeline import active_store, turn
from birth.stance_org import default_org, default_stance


def _brief_after_sky(user_text: str = "你答应晚点再聊"):
    set_stub_mode(True)
    clear_llm_hook()
    active_store().new_session()
    turn("我想聊星空", stub=True)
    ctx = active_store().snapshot()
    drive = infer_drive(user_text, ctx)
    stance = default_stance(user_text, ctx)
    org = default_org(ctx, drive=drive, stance=stance, user_text=user_text)
    return arbitrate(
        drive=drive, stance=stance, org=org, context=ctx, user_text=user_text
    )


def test_press_marks_and_arbitrate_say_intent():
    assert user_presses_commitment("你答应晚点再聊")
    assert not user_presses_commitment("你好")
    brief = _brief_after_sky()
    assert "催一个可核对的约定" in brief.say_intent
    assert "星空" in brief.say_intent


def test_prompt_carries_press_contract_rules():
    brief = _brief_after_sky()
    prompt = brief_to_prompt(brief)
    assert "可核对的约定" in prompt
    assert "宁缺毋滥" in prompt
    for bad in ("pursue", "guard", "hold", "non_negotiable", "direction="):
        assert bad not in prompt, bad


def test_llm_channel_hook_then_commit_flowback():
    """真通道（hook 代 LLM）：可提取 → source=hook → pipeline 回流 commitments。"""
    set_stub_mode(False)
    set_llm_hook(lambda _b: "好，我晚点再跟你聊星空。")
    try:
        active_store().new_session()
        turn("我想聊星空", stub=True)
        set_stub_mode(False)
        set_llm_hook(lambda _b: "好，我晚点再跟你聊星空。")
        r = turn("你答应晚点再聊", stub=False)
        assert r.articulate_source == "hook"
        assert extract_commitment(r.utterance)
        assert any("晚点" in c and "星空" in c for c in active_store().pending_commitments())
        assert validate(r.brief, r.utterance) == []
    finally:
        clear_llm_hook()
        set_stub_mode(True)


def test_unextractable_llm_degrades_to_stub_fallback():
    brief = _brief_after_sky()
    set_stub_mode(False)
    set_llm_hook(lambda _b: "嗯，知道了，你先说吧。")
    try:
        utt = articulate(brief, stub=False)
        assert last_articulate_source() == "stub_fallback"
        assert extract_commitment(utt), utt
        assert "晚点" in utt
    finally:
        clear_llm_hook()
        set_stub_mode(True)


def test_optional_deepseek_press_pipeline():
    from birth import llm_deepseek as ds

    if not ds.available():
        pytest.skip("deepseek 不可用")

    clear_llm_hook()
    set_stub_mode(False)
    try:
        active_store().new_session()
        turn("我想聊星空", stub=True)
        set_stub_mode(False)
        r = turn("你答应晚点再聊", stub=False)
        assert "催一个可核对的约定" in r.brief.say_intent
        assert r.articulate_source in {
            "deepseek", "opencode", "stub_fallback", "reject_self_id"
        }
        assert extract_commitment(r.utterance), (r.articulate_source, r.utterance)
        assert active_store().pending_commitments()
    finally:
        set_stub_mode(True)
        clear_llm_hook()
