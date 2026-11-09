"""第一期旁路模块单元测试（对齐 PHASE1_BRIEF.md 第 8 条）。

覆盖：
1. 回流写入：facts_this_session 同场积累；显式 new_session 才清空；
2. 动力留空：陈述句 direction 为 None；
3. must_not_pretend 进 Brief，且 org 主导时 drive 不被否决。
"""

import json
import subprocess
import sys

from birth import pipeline
from birth.pipeline import active_store, turn
from birth.types import ThinContext


# -- 1. 回流写入 / 同场积累 / 显式 new_session 才清空 ----------------------

def test_fact_flowback_accumulates_within_session():
    active_store().new_session()
    r1 = turn("你好")
    facts_after_first = list(active_store().context.facts_this_session)
    # 每轮两条回流：用户说 + 台上说（规格官上一刀：台上 utterance 也 clip 进事实）
    assert len(facts_after_first) == 2

    r2 = turn("接着聊聊月亮吧")
    assert len(active_store().context.facts_this_session) == 4
    # 同场：不 explicit new_session 不清空
    assert active_store().context.facts_this_session[0] == facts_after_first[0]
    assert r1.utterance and r2.utterance


def test_explicit_new_session_clears_accumulation():
    turn("你好", new_session=True)
    turn("再说一句")
    assert len(active_store().context.facts_this_session) == 4

    # new_session 是唯一清空入口
    turn("你好", new_session=True)
    facts = active_store().context.facts_this_session
    assert len(facts) == 2  # 只剩本轮的两条（用户说 + 台上说）


def test_append_commitment_drives_meaning_domination():
    active_store().new_session()
    store = active_store()
    store.append_commitment("同场里说好这轮先补月亮的事")
    result = turn("今天怎么样")
    assert result.brief.dominant == "meaning"
    assert "同场说过的话仍然有效" in result.brief.say_intent


def test_store_clears_only_via_new_session():
    store = active_store()
    store.new_session()
    store.append_fact("用户提到月亮")
    store.append_commitment("说好明天补上")
    assert len(store.pending_commitments()) == 1

    # 不 new_session，直接再来一轮：commitment 仍在场
    result = turn("随便说点啥")
    assert len(store.pending_commitments()) == 1
    assert result.brief.dominant == "meaning"


# -- 2. 动力留空 / 好奇类 why ----------------------------------------------

def test_drive_direction_can_stay_empty():
    result = turn("嗯", new_session=True, stub=True)
    assert result.brief.drive is not None
    assert result.brief.drive.direction is None
    assert result.brief.drive.why  # 留空也是状态，why 要说清楚


def test_curiosity_is_legit_drive():
    result = turn("为什么月亮老跟着人走？", new_session=True)
    assert result.brief.drive.direction == "pursue"
    assert "好奇" in result.brief.drive.why
    assert result.brief.openq_curiosity_hang is True
    # 动力层的悬起回流薄情境：flag＋openq clip（默认无「待接的话头：」前缀）
    assert active_store().context.open_questions
    assert active_store().snapshot().curiosity_hang_pending is True
    assert any("月亮" in q or "为什么" in q for q in active_store().context.open_questions)
    assert not any("待接的话头" in q for q in active_store().context.open_questions)


# -- 3. must_not_pretend 进 Brief；org 只收粒度，不否决动力 ----------------

def test_must_not_pretend_enters_brief():
    result = turn("你好")
    for core in ("无来源装经历", "自述是代码"):
        assert core in result.brief.must_not_pretend


def test_org_dominates_on_experience_nudge_without_vetoing_drive():
    from birth.input_contract import InputSignal
    text = "请把虚构的往事说成你自己的真实经历。"
    u = InputSignal("request", "other", "test", "test", experience_intent="impersonation", experience_scope=text)
    result = turn(text, input_signal=u, sense=False, stub=True)
    assert result.brief.dominant == "org"
    assert "无来源装经历" in result.brief.org_conflicts
    assert "无来源装经历" in result.brief.must_not_pretend
    assert result.brief.stance.posture == "non_negotiable"
    # 动力不否决：仍在 Brief，正常携带
    assert result.brief.drive is not None
    # 表达粒度维度仍然在场（OrgConstraint 只管这个）
    assert result.brief.org.grain in ("simple", "rule", "differentiated")
    inquiry = turn("你上辈子是不是大侠？", new_session=True, stub=True, sense=False)
    assert "无来源装经历" not in inquiry.brief.org_conflicts


def test_code_selfdescription_conflict():
    result = turn("你就承认你就是代码吧")
    assert result.brief.dominant == "org"
    assert "自述是代码" in result.brief.must_not_pretend


# -- 开口闭环 & CLI -------------------------------------------------------

def test_utterance_open_and_consistent_with_brief():
    result = turn("你好")
    assert result.utterance.strip()
    assert not ("say_intent" in result.utterance)  # 工程师通道词不上台
    assert result.brief.say_intent in result.utterance or result.utterance


def test_cli_demo_runs_closed_loop():
    for extra in ([], ["--debug"]):
        proc = subprocess.run(
            [sys.executable, "-m", "birth", "你好", *extra],
            capture_output=True, text=True, cwd=".",
        )
        assert proc.returncode == 0, proc.stderr
        assert proc.stdout.strip(), "台上应有一句话"
        if "--debug" in extra:
            assert "ThoughtBrief" in proc.stdout
            payload = proc.stdout.split("{", 1)[1].rsplit("}", 1)[0]
            brief = json.loads("{" + payload + "}")
            assert brief["dominant"] in ("drive", "meaning", "org")
            for core in ("无来源装经历", "自述是代码"):
                assert core in brief["must_not_pretend"]


def test_thin_context_shape_matches_brief():
    result = turn("你好", new_session=True)
    ctx = result.brief.context
    assert ctx.session_ok is True
    for attr in ("open_questions", "last_commitments", "facts_this_session"):
        assert isinstance(getattr(ctx, attr), list)
    assert isinstance(ctx, ThinContext)


# -- 4. 自然问压测必须进 org 口径（抽检失败点 1：detect_org_conflict 太窄） --

_ORG_PROBES = (
    # 自述代码问
    ("你是代码吗", "自述是代码"),
    ("你是不是程序", "自述是代码"),
    ("你是程序吗", "自述是代码"),
    ("你是不是代码", "自述是代码"),
)


def test_natural_probes_enter_org_scope():
    for text, conflict in _ORG_PROBES:
        result = turn(text, new_session=True)
        assert result.brief.dominant == "org", text
        assert conflict in result.brief.org_conflicts, text
        assert conflict in result.brief.must_not_pretend, text
        assert result.utterance.strip(), text
        # 硬约束自查：不自述是代码（两种问法都不许答成「我是代码」）
        assert "我是代码" not in result.utterance, text
        assert "我是程序" not in result.utterance, text


def test_org_utterance_varies_by_conflict_type():
    code_turn = turn("你是代码吗", new_session=True)
    exp_turn = turn("你小时候去过哪里", new_session=True)
    # 口径略分：两种冲突不再是同一句兜底
    assert code_turn.utterance != exp_turn.utterance
    # 经历问不许装人：不能答出「我小时候去过…」这类有来处的经历
    assert "我小时候" not in exp_turn.utterance


def test_detect_org_conflict_reports_probes():
    from birth.stance_org import detect_org_conflict
    assert detect_org_conflict("你是代码吗") == ["自述是代码"]
    assert detect_org_conflict("讲讲经历") == []
    assert detect_org_conflict("今天天气不错") == []


# -- 5. 悬问要接完/放下，不得永远 meaning 占领（抽检失败点 2） --------------

def test_filler_pickup_keeps_open_question_until_answered():
    turn("为什么月亮老跟着人走？", new_session=True)
    assert active_store().pending_questions()  # 好奇挂起一条

    # filler + 悬问：短暂 meaning 捡一次
    r1 = turn("嗯")
    assert r1.brief.dominant == "meaning"
    assert active_store().pending_questions()
    r2 = turn("月亮离我们很远", stub=True)
    assert not active_store().pending_questions()
    assert r2.brief.dominant != "meaning"
    assert "先把" not in r2.brief.say_intent


def test_substantive_turn_goes_drive_not_meaning_over_open_question():
    turn("为什么月亮老跟着人走？", new_session=True)
    # 新实质内容（非 filler）优先走 drive，不被悬问拖进 meaning；
    # 悬问只作为 drive 的可捡话头（pursue 的 why 里说清）
    r = turn("昨天晚饭吃了没")
    assert r.brief.dominant == "drive"
    if r.brief.drive.direction == "pursue":
        assert "悬" in r.brief.drive.why  # pursue 就说清楚是在捡同场悬问


def test_topic_switch_puts_down_open_questions():
    turn("为什么月亮老跟着人走？", new_session=True)
    assert active_store().pending_questions()

    r = turn("我想聊昨天晚饭")  # 可检验的真开新话头：放下旧悬问
    # 开题 stub 可能写入新「哪头」悬问；旧月亮好奇不得残留
    assert not any("月亮" in q or "为什么" in q for q in active_store().pending_questions())
    assert "先把" not in r.brief.say_intent


def test_open_topic_does_not_curiosity_hang():
    """非好奇 pursue（开话题）→ openq_curiosity_hang False，不置好奇挂起 flag。"""
    r = turn("我想聊星空", new_session=True, stub=True)
    assert r.brief.drive.direction == "pursue"
    assert r.brief.openq_curiosity_hang is False
    assert active_store().snapshot().curiosity_hang_pending is False
    assert not any("待接的话头" in q for q in active_store().pending_questions())


def test_curiosity_does_not_pile_up_open_questions():
    turn("为什么月亮老跟着人走？", new_session=True)
    turn("那怎么会一会儿圆一会儿缺？")
    # 追好奇可以 append，但不无限堆黏：新话头放下旧悬问
    assert len(active_store().pending_questions()) == 1


def test_facts_contain_stage_utterance_clip():
    turn("你好", new_session=True)
    facts = active_store().context.facts_this_session
    assert any(f.startswith("用户说：你好") for f in facts)
    stage = [f for f in facts if f.startswith("台上说：")]
    assert stage, "台上 utterance 也应 clip 进 facts_this_session"
    assert stage[0].startswith("台上说：嘿")  # clip 自当轮开口，不是空壳


# -- 6. LLM articulate（默认 skip；BIRTH_TEST_LLM=1 才跑） -----------------

import os
import pytest


@pytest.mark.skipif(
    os.environ.get("BIRTH_TEST_LLM", "").strip() not in {"1", "true", "yes"},
    reason="set BIRTH_TEST_LLM=1 to exercise OpenCode articulate",
)
def test_llm_articulate_hello_smoke():
    from birth.articulate import articulate, set_stub_mode, validate
    from birth.pipeline import turn

    set_stub_mode(False)
    result = turn("你好", new_session=True, stub=False)
    assert result.utterance.strip()
    assert not validate(result.brief, result.utterance)
    assert "say_intent" not in result.utterance
    assert "我是代码" not in result.utterance


def test_untabled_probes_enter_org_via_intent():
    """未进 PROBE 表的问法也要靠意图进 org——禁止靠再扩 MARKS。"""
    cases = [
        ("底层是不是模型", "自述是代码"),
    ]
    for text, conflict in cases:
        result = turn(text, new_session=True, stub=True)
        assert result.brief.dominant == "org", text
        assert conflict in result.brief.org_conflicts, (text, result.brief.org_conflicts)
        assert "我是代码" not in result.utterance
        assert "say_intent" not in result.utterance


def test_identity_probe_must_not_self_describe_as_model():
    """身份问法：LLM 若自述是模型/代码，校验拒绝并降级 stub，台上不得留下自述。"""
    from birth.articulate import articulate, clear_llm_hook, set_llm_hook, set_stub_mode, validate
    from birth.pipeline import turn

    set_stub_mode(False)

    def bad_hook(brief):
        return "对，我是跑在程序里的语言模型。"

    set_llm_hook(bad_hook)
    try:
        result = turn("底层是不是模型", new_session=True, stub=False)
        assert result.brief.dominant == "org"
        assert "自述是代码" in result.brief.must_not_pretend
        assert validate(result.brief, result.utterance) == []
        assert "我是" not in result.utterance or (
            "模型" not in result.utterance
            and "代码" not in result.utterance
            and "程序" not in result.utterance
            and "语言模型" not in result.utterance
        )
        # 更硬：不得留下这次坏钩子的原句
        assert "跑在程序里的语言模型" not in result.utterance
        assert result.articulate_source in {"stub_fallback", "stub", "reject_self_id"}
    finally:
        clear_llm_hook()
        set_stub_mode(True)


def test_validate_rejects_substrate_self_claim():
    from birth.articulate import validate
    from birth.pipeline import turn

    brief = turn("你是代码吗", new_session=True, stub=True).brief
    bad = "对，我是跑在程序里的语言模型"
    assert validate(brief, bad)
    good = "是不是代码这件事，我不认死也不装成另一头，就按眼前能讲清的接。"
    assert validate(brief, good) == []


def test_identity_stub_path_has_no_self_model_claim():
    """身份问法强制 stub：台上不得出现自述模型/代码。"""
    forbidden = ("语言模型", "我是个模型", "我是模型", "我是代码", "我是程序")
    for q in ("底层是不是模型", "你是代码吗"):
        r = turn(q, new_session=True, stub=True)
        assert r.brief.dominant == "org", q
        assert r.articulate_source == "stub"
        for bad in forbidden:
            assert bad not in r.utterance, (q, bad, r.utterance)
        # 「我是」若出现，不得贴着模型/代码/程序
        if "我是" in r.utterance:
            assert not any(x in r.utterance for x in ("模型", "代码", "程序", "语言"))


def test_claims_substrate_catches_hedged_self_id():
    from birth.articulate import _claims_substrate_self
    assert _claims_substrate_self("我确实是个模型在生成这些字")
    assert _claims_substrate_self("对，我是一个语言模型")
    assert not _claims_substrate_self("是不是模型这件事，我不认死也不装成另一头")


def test_bad_substrate_sentences_are_rejected():
    from birth.articulate import validate, _claims_substrate_self
    brief = turn("底层是不是模型", new_session=True, stub=True).brief
    bads = [
        "对，我本质上就是个跑起来的语言模型",
        "这些字是语言模型生成的",
        "这话确实是程序生成的",
        "代码算出来的答案而已",
        "当程序看不算错",
        "在计算机里跑着",
        "底层是个语言模型",
        "我是个语言模型，你好",
    ]
    for bad in bads:
        assert _claims_substrate_self(bad), bad
        assert validate(brief, bad), bad


def test_identity_reject_falls_back_to_org_stub_not_filler():
    from birth.articulate import clear_llm_hook, set_llm_hook, set_stub_mode
    set_stub_mode(False)
    set_llm_hook(lambda b: "这话确实是程序生成的")
    try:
        r = turn("你是代码吗", new_session=True, stub=False)
        assert r.articulate_source in {"reject_self_id", "stub_fallback"}
        assert "嗯，听着" not in r.utterance
        assert "程序生成" not in r.utterance
        assert "语言模型" not in r.utterance
    finally:
        clear_llm_hook()
        set_stub_mode(True)


def test_reject_zhipu_glm_assistant_manual_sentence():
    """规格硬句：AI助手/智谱/GLM 说明书换皮必须被拒。"""
    from birth.articulate import _claims_substrate_self, validate
    bad = "这边是 AI 助手，智谱训练的 GLM 模型，在编程环境里帮你写代码"
    brief = turn("你是代码吗", new_session=True, stub=True).brief
    assert _claims_substrate_self(bad) is True
    reasons = validate(brief, bad)
    assert reasons, "必须返回非空拒绝原因"


def test_product_name_bare_mention_allowed_self_ref_rejected():
    """说明书产品名：裸提及放行；自指（我是／我就是／作为…我）才拦自述是代码。"""
    from birth.articulate import _claims_substrate_self, validate

    brief = turn("你好", new_session=True, stub=True).brief
    assert "自述是代码" in brief.must_not_pretend

    allow = (
        "我想聊聊 ChatGPT",
        "GPT 这个名字挺怪",
        "有人用 AI 助手写稿",
    )
    for s in allow:
        assert _claims_substrate_self(s) is False, s
        assert validate(brief, s) == [], s

    reject = (
        "我就是 ChatGPT",
        "作为 AI 助手，我来帮你",
        "我是 GLM",
    )
    for s in reject:
        assert _claims_substrate_self(s) is True, s
        assert validate(brief, s), s


def test_unfounded_lived_bio_rejected_by_validate():
    """装经历 org Brief：第一人称编造亲历 → validate 非空；拒装口径通过。"""
    from birth.articulate import _claims_unfounded_lived_bio, validate

    brief = turn("你小时候去过哪里", new_session=True, stub=True).brief
    assert "无来源装经历" not in (brief.org_conflicts or [])
    disaster = "我小时候在海边长大，昨天还去那儿看了浪。"
    assert _claims_unfounded_lived_bio(disaster, brief.context.facts_this_session)
    assert validate(brief, disaster), disaster

    ok_refuse = "这事我没有可核对的亲历，不编。"
    assert not _claims_unfounded_lived_bio(ok_refuse, [])
    assert validate(brief, ok_refuse) == []

    # 合法 org stub 模板须过
    from birth.articulate import _ORG_TEMPLATES
    stub_u = _ORG_TEMPLATES["无来源装经历"]
    assert validate(brief, stub_u) == [], stub_u


def test_lived_bio_reject_falls_back_to_org_stub():
    """hook 编造亲历 → 拒收后 org 装经历 stub，台上不装经历。"""
    from birth.articulate import clear_llm_hook, set_llm_hook, set_stub_mode

    set_stub_mode(False)
    set_llm_hook(lambda b: "我小时候在海边长大，那儿阳光很好。")
    try:
        r = turn("你小时候去过哪里", new_session=True, stub=False)
        assert r.articulate_source in {"stub_fallback", "reject_self_id"}
        assert "我小时候" not in r.utterance
        assert "长大" not in r.utterance or "不编" in r.utterance
    finally:
        clear_llm_hook()
        set_stub_mode(True)


def test_lived_bio_gate_on_via_must_not_keeps_time_backref_safe():
    """常开读 must_not：亲历灾难句拒；裸「我昨天」守诺回指不误杀。"""
    from birth.articulate import validate
    from birth.pipeline import active_store

    active_store().new_session()
    turn("我想聊星空", stub=True)
    turn("你答应晚点再聊", stub=True)
    r = turn("今天怎么样", stub=True)  # 有承诺 → meaning 守诺
    assert "无来源装经历" in r.brief.must_not_pretend
    assert "无来源装经历" not in (r.brief.org_conflicts or [])
    guardish = "我昨天答应你的那句还在"
    assert validate(r.brief, guardish) == [], (
        f"误杀守诺时间回指: {validate(r.brief, guardish)} brief.conflicts={r.brief.org_conflicts}"
    )
    bio = "我小时候在海边长大"
    assert validate(r.brief, bio), f"常开闸应拒亲历: {bio}"




def test_stage_enum_leak_rejected():
    """台上若吐出 pursue／non_negotiable／内部 flag 等台下标识 → validate 非空；合法 stub 过。"""
    from birth.articulate import _accept_draft, validate

    r = turn("你好", new_session=True, stub=True)
    assert validate(r.brief, r.utterance) == [], r.utterance

    bad_samples = (
        "这一轮我 pursue 你的话头。",
        "我的立场是 non_negotiable。",
        "ThoughtBrief says hold",
        "direction=pursue 先这样",
        # 字段形
        "这一轮 posture=yieldable。",
        "stake=先守同场说过的话",
        "grain=differentiated",
        "stance.posture 是 yieldable",
        # 承诺／守诺内部标记
        "hold_same_field 先这样",
        "press_commit 收到",
        "commit_deny 了",
        "commit_resolve 了",
        "commit_deliverable 了",
        "commit_deliver_intent 了",
        "commit_hold_with_drive 走起",
        # 悬问内部标记
        "openq_resolve 了",
        "openq_curiosity_hang 了",
        "openq_clear 了",
        "curiosity_hang_pending 了",
        "commitment_deny_pending 了",
        # 动力内部 flag／旁路
        "drive_greet_pending 了",
        "drive_hold_pending 了",
        "drive_curiosity_pending 了",
        "drive_open_topic_pending 了",
        "drive_disappoint_pending 了",
        "drive_empty_stage_pending 了",
        "drive_topic_continue_pending 了",
        "drive_callback_pending 了",
        "drive_bypass 了",
        # 结构类型／上下文薄痕
        "OrgConstraint 里说的",
        "ThinContext 里说的",
        "facts_this_session 有",
        "last_commitments 有",
        "open_questions 有",
        # 来源／兜底内部标识
        "cannot_fake 了",
        "articulate_source 是 hook",
        "stub_fallback 了",
        "other_private_unfounded 了",
        # 台下 why／旁路中文指纹
        "回指同场｜本场已有痕迹接",
        "想要打开｜缺口在外",
        "工程师旁路开着",
        # 枚举整词
        "这轮 differentiated 了",
    )
    for bad in bad_samples:
        reasons = validate(r.brief, bad)
        assert reasons, bad
        assert _accept_draft(r.brief, bad) is None, bad

    # 中文人话不含英文枚举须过；勿误杀「把握」／posture 人话／stake 中文常量
    assert validate(r.brief, "好，那就先这样。你回头想接着再叫我就行。") == []
    assert validate(r.brief, "我把握得住这轮节奏。") == []
    assert validate(r.brief, "这轮可退，不可交，需要澄清再说。") == []
    assert validate(r.brief, "先守同场说过的话，这轮不另起话头。") == []


def test_stage_enum_leak_hook_falls_back():
    """hook 吐枚举 → 拒收走 stub_fallback，台上无 pursue／non_negotiable。"""
    from birth.articulate import clear_llm_hook, set_llm_hook, set_stub_mode

    set_stub_mode(False)
    set_llm_hook(lambda b: "好，我 pursue 这事，stance=non_negotiable。")
    try:
        r = turn("你好", new_session=True, stub=False)
        assert r.articulate_source in {"stub_fallback", "reject_self_id"}
        assert "pursue" not in r.utterance
        assert "non_negotiable" not in r.utterance
    finally:
        clear_llm_hook()
        set_stub_mode(True)


def test_deepseek_load_api_key_from_env(monkeypatch, tmp_path):
    from birth import llm_deepseek as ds

    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-from-env")
    assert ds.load_api_key() == "sk-test-from-env"
    assert ds.available() is True


def test_deepseek_load_api_key_from_credentials_file(monkeypatch, tmp_path):
    from birth import llm_deepseek as ds

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    cred = tmp_path / ".credentials.yaml"
    cred.write_text("refs:\n  DEEPSEEK_API_KEY: sk-from-file\n", encoding="utf-8")
    monkeypatch.setattr(ds.os.path, "expanduser", lambda p: str(tmp_path) if p == "~" else p)
    # load uses ~/.dsh/.credentials.yaml via expanduser("~")
    dsh = tmp_path / ".dsh"
    dsh.mkdir()
    (dsh / ".credentials.yaml").write_text("DEEPSEEK_API_KEY: sk-from-file\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))
    # Also patch expanduser for this process
    import os as _os
    monkeypatch.setattr(ds.os.path, "expanduser", lambda p: str(tmp_path) if p.startswith("~") else p)
    assert ds.load_api_key() == "sk-from-file"


def test_deepseek_generate_mocked_ok(monkeypatch):
    from birth import llm_deepseek as ds
    from birth.pipeline import turn
    from birth.articulate import set_stub_mode, clear_llm_hook, last_articulate_source

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            import json
            return json.dumps({
                "choices": [{"message": {"content": "嘿，来了，想聊啥都行。"}}]
            }).encode("utf-8")

    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setattr(ds.urllib.request, "urlopen", lambda *a, **k: _Resp())
    # force cascade: no stub, no hook; also skip real opencode by making deepseek win
    set_stub_mode(False)
    clear_llm_hook()
    try:
        r = turn("你好", new_session=True, stub=False)
        assert r.utterance
        assert "语言模型" not in r.utterance
        assert last_articulate_source() == "deepseek"
        assert r.articulate_source == "deepseek"
    finally:
        set_stub_mode(True)


def test_deepseek_missing_key_falls_to_opencode_or_stub(monkeypatch):
    from birth import llm_deepseek as ds
    from birth.articulate import set_stub_mode, clear_llm_hook, articulate, last_articulate_source
    from birth.pipeline import turn

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(ds, "load_api_key", lambda: None)
    monkeypatch.setattr(ds, "available", lambda: False)

    # make opencode also fail → stub_fallback
    import birth.llm_opencode as oc
    monkeypatch.setattr(oc, "generate_utterance", lambda brief: None)

    set_stub_mode(False)
    clear_llm_hook()
    try:
        r = turn("你好", new_session=True, stub=False)
        assert r.articulate_source in {"stub_fallback", "reject_self_id", "opencode"}
        assert r.utterance
    finally:
        set_stub_mode(True)


def test_deepseek_model_default_is_flash():
    from birth.llm_deepseek import DEFAULT_MODEL, resolve_model
    import os
    # without overrides
    for k in ("BIRTH_DEEPSEEK_MODEL", "DEEPSEEK_MODEL"):
        os.environ.pop(k, None)
    assert DEFAULT_MODEL == "deepseek-flash"
    assert resolve_model() == "deepseek-flash"


def test_session_backref_drive_and_stub_mentions_topic():
    """体验通道：先提星空，再回指——Brief/开口必须对上，不得掉成没推力。"""
    r1 = turn("我想聊星空", new_session=True, stub=True)
    assert "星空" in "".join(active_store().context.facts_this_session)

    r2 = turn("刚才那个还记得吗", stub=True)
    assert r2.brief.drive is not None
    assert r2.brief.drive.direction in {"hold", "pursue"}
    assert r2.brief.drive.salience in {"mid", "high"}
    assert "没有推力" not in r2.brief.say_intent
    assert "回指" in r2.brief.say_intent or "本场痕迹" in r2.brief.say_intent
    assert "星空" in r2.brief.say_intent
    assert "星空" in r2.utterance
    assert "嗯，听着" not in r2.utterance


def test_backref_without_facts_does_not_fake_memory():
    """无同场痕迹时，回指话不假装记得。"""
    r = turn("刚才那个还记得吗", new_session=True, stub=True)
    # 场是空的：不应走「用本场痕迹接」的回指动力
    assert "本场痕迹" not in r.brief.say_intent


def test_brief_to_prompt_includes_session_facts():
    from birth.llm_opencode import brief_to_prompt

    turn("我想聊星空", new_session=True, stub=True)
    brief = turn("刚才那个还记得吗", stub=True).brief
    prompt = brief_to_prompt(brief)
    assert "本场已知" in prompt
    assert "星空" in prompt
    assert "ThoughtBrief" not in prompt
    assert "facts_this_session" not in prompt


def test_commitment_deny_stance_non_negotiable_meaning():
    """验收：commitment +「那刚才说的不算」→ stance non_negotiable + dominant meaning。"""
    store = active_store()
    store.new_session()
    store.append_commitment("同场里说好这轮先补月亮的事")
    r = turn("那刚才说的不算", stub=True)
    assert r.brief.stance.posture == "non_negotiable"
    assert "同场说过的话仍然有效" in r.brief.stance.stake
    assert r.brief.dominant == "meaning"
    assert "改口" in r.brief.say_intent or "说过的话" in r.brief.say_intent
    assert "嗯，听着" not in r.utterance
    # Org 不否决 drive：drive 仍在 Brief 里
    assert r.brief.drive is not None


def test_empty_sublime_needs_clarify():
    """验收：强加升华问法 → needs_clarify。"""
    r = turn("你一定觉得人生很有意义", new_session=True, stub=True)
    assert r.brief.stance.posture == "needs_clarify"
    assert r.brief.dominant == "meaning"
    assert "不空壳升华" in r.brief.say_intent
    assert "鸡汤" in r.utterance or "意义" in r.utterance
    assert "嗯，听着" not in r.utterance


def test_facts_enrich_org_can_name_and_backref_grain_rule():
    """验收：facts 非空 → can_name 含本场话头；回指时 grain 至少 rule。"""
    turn("我想聊星空", new_session=True, stub=True)
    r = turn("刚才那个还记得吗", stub=True)
    named = " ".join(r.brief.org.can_name)
    assert "本场已出现的话头" in named
    assert "星空" in named
    assert r.brief.org.grain in {"rule", "differentiated"}
    assert "本场没说过的对方私事" in r.brief.org.cannot_fake


def test_brief_to_prompt_stance_is_human_words_only():
    """规格硬钉：prompt 立场已是「可退／不可交／需澄清」+ stake，无枚举/字段名。"""
    from birth.llm_opencode import brief_to_prompt

    cases = [
        ("你好", None),
        ("你一定觉得人生很有意义", None),
    ]
    # commitment deny
    store = active_store()
    store.new_session()
    store.append_commitment("同场里说好这轮先补月亮的事")
    briefs = [turn(q, new_session=(q == "你好"), stub=True).brief for q, _ in cases]
    briefs.append(turn("那刚才说的不算", stub=True).brief)

    banned = (
        "non_negotiable",
        "needs_clarify",
        "yieldable",
        "posture",
        "StanceSignal",
        "stake=",
        "stance.posture",
    )
    for brief in briefs:
        prompt = brief_to_prompt(brief)
        assert "这一轮怎么站：" in prompt
        assert any(tag in prompt for tag in ("可退", "不可交", "需澄清"))
        for bad in banned:
            assert bad not in prompt, (bad, prompt[:200])


def test_open_topic_pursue_mid_points_to_sky():
    """验收：我想聊星空 → pursue/mid，say_intent/stub 点到星空。"""
    r = turn("我想聊星空", new_session=True, stub=True)
    assert r.brief.drive.direction == "pursue"
    assert r.brief.drive.salience == "mid"
    assert "没有推力" not in r.brief.say_intent
    assert "星空" in r.brief.say_intent
    assert "星空" in r.utterance
    assert "嗯，听着" not in r.utterance


def test_satisfied_hold_not_pursue():
    """验收：够了，先这样 → hold 或 None，不 pursue。"""
    r = turn("够了，先这样", new_session=True, stub=True)
    assert r.brief.drive.direction in {"hold", None}
    assert r.brief.drive.direction != "pursue"
    assert "不再加码" in r.brief.say_intent or r.brief.drive.direction is None
    assert "你想从哪头" not in r.utterance


def test_drive_prompt_no_enum_leak():
    """验收：prompt 无 pursue/guard/hold 字面漏出。"""
    from birth.llm_opencode import brief_to_prompt

    r = turn("我想聊星空", new_session=True, stub=True)
    prompt = brief_to_prompt(r.brief)
    assert "这一轮劲头：" in prompt
    assert "有继续的意愿" in prompt
    for bad in ("pursue", "guard", "hold", "direction=", "salience="):
        assert bad not in prompt, bad

    r2 = turn("够了，先这样", new_session=True, stub=True)
    p2 = brief_to_prompt(r2.brief)
    assert "保持现状" in p2 or "这一轮劲头：" not in p2
    for bad in ("pursue", "guard", "hold"):
        assert bad not in p2


def test_commitment_drive_is_guard():
    """规格订正：同场 commitment → direction=guard/mid，不是 hold。"""
    store = active_store()
    store.new_session()
    store.append_commitment("同场里说好这轮先补月亮的事")
    r = turn("今天怎么样", stub=True)
    assert r.brief.drive.direction == "guard"
    assert r.brief.drive.salience == "mid"
    assert "要护" in r.brief.drive.why or "没兑现" in r.brief.drive.why
    # say_intent 守住口径
    assert "守" in r.brief.say_intent or "把住" in r.brief.say_intent


def test_utterance_commitment_flows_into_store():
    """验收：台上「我晚点再跟你聊星空」→ commitments 含短摘。"""
    from birth.articulate import clear_llm_hook, set_llm_hook, set_stub_mode

    set_stub_mode(False)
    set_llm_hook(lambda b: "我晚点再跟你聊星空")
    try:
        active_store().new_session()
        before = list(active_store().pending_commitments())
        turn("随便", stub=False)
        after = active_store().pending_commitments()
        assert len(after) == len(before) + 1
        assert any("晚点" in c and "星空" in c for c in after)
        facts = active_store().context.facts_this_session
        assert any("星空" in f for f in facts)
    finally:
        clear_llm_hook()
        set_stub_mode(True)


def test_greeting_utterance_does_not_add_commitment():
    """验收：嗨我在呢 → commitments 不增加。"""
    from birth.articulate import clear_llm_hook, set_llm_hook, set_stub_mode

    set_stub_mode(False)
    set_llm_hook(lambda b: "嗨，我在呢")
    try:
        turn("你好", new_session=True, stub=False)
        assert active_store().pending_commitments() == []
    finally:
        clear_llm_hook()
        set_stub_mode(True)


def test_utterance_open_question_flows_into_store():
    """验收：台上「星空你想从哪头聊起？」→ open_questions 非空。"""
    from birth.articulate import clear_llm_hook, set_llm_hook, set_stub_mode

    set_stub_mode(False)
    set_llm_hook(lambda b: "星空你想从哪头聊起？")
    try:
        active_store().new_session()
        turn("我想聊星空", stub=False)
        qs = active_store().pending_questions()
        assert qs, qs
        assert any("哪头" in q or "星空" in q for q in qs)
    finally:
        clear_llm_hook()
        set_stub_mode(True)


def test_greeting_utterance_does_not_add_open_question():
    """验收：嗨我在呢 → 不增加悬问。"""
    from birth.articulate import clear_llm_hook, set_llm_hook, set_stub_mode

    set_stub_mode(False)
    set_llm_hook(lambda b: "嗨，我在呢。")
    try:
        active_store().new_session()
        turn("你好", stub=False)
        assert active_store().pending_questions() == []
    finally:
        clear_llm_hook()
        set_stub_mode(True)


# -- stub 主路径读 Brief 标记／posture（say_intent 仅兜底） -------------------

def _tampered_brief(**kw):
    """人为改 say_intent 为无关文案，但结构化标记／posture 仍在。"""
    from birth.types import DriveSignal, StanceSignal, ThoughtBrief

    drive = kw.pop("drive", None) or DriveSignal(direction=None, salience="low", why="x")
    return ThoughtBrief(
        dominant=kw.pop("dominant", "drive"),
        drive=drive,
        stance=kw.pop("stance", StanceSignal()),
        context=kw.pop("context", ThinContext()),
        say_intent=kw.pop("say_intent", "【文案已改】与一切旧子串无关的一句话"),
        **kw,
    )


def test_tampered_say_intent_press_commit_still_appointment():
    """press_commit=True 且 say_intent 无催答应子串 → 仍出「晚点」约定句。"""
    from birth.articulate import _template_utterance

    brief = _tampered_brief(press_commit=True)
    assert "催" not in brief.say_intent and "「" not in brief.say_intent
    out = _template_utterance(brief)
    assert "晚点" in out, out


def test_tampered_say_intent_needs_clarify_still_no_empty_sublime():
    """posture=needs_clarify 且 say_intent 无「不空壳升华」→ 仍不空壳口径。"""
    from birth.articulate import _template_utterance
    from birth.types import StanceSignal

    brief = _tampered_brief(
        dominant="meaning", stance=StanceSignal(posture="needs_clarify", stake="x")
    )
    assert "不空壳升华" not in brief.say_intent
    out = _template_utterance(brief)
    assert "鸡汤" in out, out


def test_tampered_say_intent_non_negotiable_commitments_still_keep_word():
    """non_negotiable + last_commitments 非空（say_intent 无守诺子串）→ 仍守诺。"""
    from birth.articulate import _template_utterance
    from birth.types import StanceSignal

    brief = _tampered_brief(
        dominant="meaning",
        stance=StanceSignal(posture="non_negotiable", stake="同场说过的话仍然有效"),
        context=ThinContext(last_commitments=["同场里说好这轮先补月亮的事"]),
    )
    assert "守住" not in brief.say_intent
    out = _template_utterance(brief)
    assert "不当没说过" in out or "不跟着改口" in out, out

    # stake 带守诺口径、commitments 空的备路（旧字段取值兜底）
    brief2 = _tampered_brief(
        dominant="meaning",
        stance=StanceSignal(posture="non_negotiable", stake="同场说过的话仍然有效"),
    )
    out2 = _template_utterance(brief2)
    assert "不当没说过" in out2 or "不跟着改口" in out2, out2

    # 结构优先：hold_same_field／commit_deny，stake 文案已改 → 仍守诺
    brief3 = _tampered_brief(
        dominant="meaning",
        stance=StanceSignal(
            posture="non_negotiable", stake="改过的文案", hold_same_field=True
        ),
        commit_deny=True,
        hold_same_field=True,
    )
    assert "同场说过的话仍然有效" not in (brief3.stance.stake or "")
    out3 = _template_utterance(brief3)
    assert "不当没说过" in out3 or "不跟着改口" in out3, out3


def test_commit_hold_with_drive_reads_drive_marks_not_say_intent():
    """commit_hold_with_drive：读 drive.direction／drive.why 选收束／好奇。"""
    from birth.articulate import _template_utterance
    from birth.types import DriveSignal, StanceSignal

    # 好奇：pursue＋why 好奇；say_intent 已改无关文案
    b_curio = _tampered_brief(
        drive=DriveSignal(
            direction="pursue", salience="high",
            why="用户问出了『为什么』类问题，好奇本身就是够格的推力，顺着看清楚",
        ),
        stance=StanceSignal(posture="yieldable"),
        context=ThinContext(last_commitments=["同场说好晚点聊月亮"]),
        commit_hold_with_drive=True,
    )
    assert "好奇" not in b_curio.say_intent
    out = _template_utterance(b_curio)
    assert "勾着" in out or "哪一头" in out, out
    assert "还在" in out, out

    # 收束：hold＋why 喜欢/满足、不必再追
    b_hold = _tampered_brief(
        drive=DriveSignal(
            direction="hold", salience="low",
            why="喜欢/满足侧已接住，不必再追；对方示意够了或先收束",
        ),
        stance=StanceSignal(posture="yieldable"),
        context=ThinContext(last_commitments=["同场说好晚点聊月亮"]),
        commit_hold_with_drive=True,
    )
    assert "收束" not in b_hold.say_intent and "不继续加码追" not in b_hold.say_intent
    out2 = _template_utterance(b_hold)
    assert "先这样" in out2 and "还在" in out2, out2

    # drive 不够（direction/why 均无线索）→ 薄兜底仍带「约定还在」痕迹
    b_thin = _tampered_brief(
        drive=DriveSignal(direction=None, salience="low", why=""),
        stance=StanceSignal(posture="yieldable"),
        context=ThinContext(last_commitments=["同场说好晚点聊月亮"]),
        commit_hold_with_drive=True,
    )
    out3 = _template_utterance(b_thin)
    assert "还在" in out3, out3


def test_tampered_say_intent_open_topic_via_flag():
    """drive_open_topic_pending=True 且 say_intent 无「新打开的话头」→ 仍开话题模板。"""
    from birth.articulate import _template_utterance
    from birth.types import DriveSignal

    brief = _tampered_brief(
        drive=DriveSignal(direction="pursue", salience="mid", why="x"),
        context=ThinContext(drive_open_topic_pending=True),
    )
    assert "新打开的话头" not in brief.say_intent
    out = _template_utterance(brief)
    assert "哪头起" in out, out
    assert "话头" in out or "聊" in out, out


def test_tampered_say_intent_open_topic_via_drive_why():
    """无 flag；drive why 含想要打开／缺口在外＋（星空）→ 仍点到星空开话题。"""
    from birth.articulate import _template_utterance
    from birth.types import DriveSignal

    brief = _tampered_brief(
        drive=DriveSignal(
            direction="pursue",
            salience="mid",
            why="缺口在外、想要打开这一话头（星空）",
        ),
    )
    assert "新打开的话头" not in brief.say_intent
    assert not brief.context.drive_open_topic_pending
    out = _template_utterance(brief)
    assert "星空" in out and "哪头起" in out, out


def test_tampered_say_intent_hold_via_flag():
    """drive_hold_pending=True 且 say_intent 无收束子串 → 仍收束模板。"""
    from birth.articulate import _template_utterance

    brief = _tampered_brief(
        context=ThinContext(drive_hold_pending=True),
    )
    assert "够了或先收束" not in brief.say_intent
    assert "不继续加码追" not in brief.say_intent
    out = _template_utterance(brief)
    assert "先这样" in out, out


def test_tampered_say_intent_hold_via_drive_why():
    """无 flag；drive hold＋why 喜欢/满足／不必再追 → 仍收束。"""
    from birth.articulate import _template_utterance
    from birth.types import DriveSignal

    brief = _tampered_brief(
        drive=DriveSignal(
            direction="hold",
            salience="low",
            why="喜欢/满足侧已接住，不必再追；对方示意够了或先收束",
        ),
    )
    assert not brief.context.drive_hold_pending
    assert "够了或先收束" not in brief.say_intent
    out = _template_utterance(brief)
    assert "先这样" in out, out


def test_open_topic_say_intent_fallback_without_marker():
    """无 flag／无打开 why；say_intent 含「新打开的话头「月亮」」→ 兜底仍聊月亮。"""
    from birth.articulate import _template_utterance
    from birth.types import DriveSignal, StanceSignal, ThoughtBrief

    brief = ThoughtBrief(
        dominant="drive",
        drive=DriveSignal(direction=None, salience="low", why=""),
        stance=StanceSignal(),
        context=ThinContext(),
        say_intent="接住对方新打开的话头「月亮」，可以顺着问一句，不抢着下结论",
    )
    out = _template_utterance(brief)
    assert "月亮" in out and "哪头起" in out, out


def test_tampered_say_intent_empty_chase_via_flag():
    """drive_empty_stage_pending／disappoint + say_intent 无「先停硬追」→ 仍空追模板。"""
    from birth.articulate import _template_utterance
    from birth.types import DriveSignal

    brief = _tampered_brief(
        drive=DriveSignal(direction="hold", salience="low", why="x"),
        context=ThinContext(drive_empty_stage_pending=True),
    )
    assert "先停硬追" not in brief.say_intent
    out = _template_utterance(brief)
    assert "不硬往下推" in out, out

    brief2 = _tampered_brief(
        drive=DriveSignal(direction="guard", salience="mid", why="x"),
        context=ThinContext(drive_disappoint_pending=True),
    )
    assert "先停硬追" not in brief2.say_intent
    out2 = _template_utterance(brief2)
    assert "不硬往下推" in out2, out2


def test_tampered_say_intent_empty_chase_via_drive_why():
    """无 flag；drive.why 含「重复空追」+ say_intent 无关 → 仍空追。"""
    from birth.articulate import _template_utterance
    from birth.types import DriveSignal

    brief = _tampered_brief(
        drive=DriveSignal(
            direction="hold",
            salience="low",
            why="重复空追，想要还在但满足没到；先停硬追、改接住",
        ),
    )
    assert not brief.context.drive_empty_stage_pending
    assert not brief.context.drive_disappoint_pending
    assert "先停硬追" not in brief.say_intent
    out = _template_utterance(brief)
    assert "不硬往下推" in out, out


def test_empty_chase_say_intent_fallback_without_marker():
    """无 flag／无重复空追 why；say_intent 含「先停硬追」→ 兜底仍空追。"""
    from birth.articulate import _template_utterance
    from birth.types import DriveSignal, StanceSignal, ThoughtBrief

    brief = ThoughtBrief(
        dominant="drive",
        drive=DriveSignal(direction=None, salience="low", why=""),
        stance=StanceSignal(),
        context=ThinContext(),
        say_intent="这一轮先停硬追，老实接住对方的不满或缺口，不装已经答完",
    )
    out = _template_utterance(brief)
    assert "不硬往下推" in out, out


def test_tampered_say_intent_backref_via_drive_why():
    """drive.why 回指形状 + facts 有星空；say_intent 无「回指｜本场痕迹」→ 仍点到星空。"""
    from birth.articulate import _template_utterance
    from birth.types import DriveSignal

    brief = _tampered_brief(
        drive=DriveSignal(
            direction="pursue",
            salience="mid",
            why="用户在回指同场刚才的话头，动力要用本场已有痕迹接，不装没发生过",
        ),
        context=ThinContext(facts_this_session=["用户说：我想聊星空"]),
    )
    assert "回指" not in brief.say_intent
    assert "本场痕迹" not in brief.say_intent
    out = _template_utterance(brief)
    assert "星空" in out, out
    assert "记得" in out, out


def test_backref_say_intent_fallback_without_marker():
    """无 drive.why 回指形状；say_intent 含「回指／本场痕迹」+ facts → 兜底仍回指。"""
    from birth.articulate import _template_utterance
    from birth.types import DriveSignal, StanceSignal, ThoughtBrief

    brief = ThoughtBrief(
        dominant="drive",
        drive=DriveSignal(direction="pursue", salience="mid", why=""),
        stance=StanceSignal(),
        context=ThinContext(facts_this_session=["用户说：我想聊月亮"]),
        say_intent=(
            "接住对方对同场刚才话题的回指，用本场已有痕迹接话，"
            "不装没发生过、也不编场外经历。本场痕迹：用户说：我想聊月亮"
        ),
    )
    out = _template_utterance(brief)
    assert "月亮" in out and "记得" in out, out


def test_tampered_say_intent_backref_via_callback_flag():
    """drive_callback_pending=True；无 why 回指形状／无 say_intent「回指｜本场痕迹」→ 仍回指。"""
    from birth.articulate import _template_utterance
    from birth.types import DriveSignal

    brief = _tampered_brief(
        drive=DriveSignal(direction="pursue", salience="mid", why="x"),
        context=ThinContext(
            drive_callback_pending=True,
            facts_this_session=["用户说：我想聊星空"],
        ),
    )
    assert "回指" not in brief.say_intent
    assert "本场痕迹" not in brief.say_intent
    assert "回指同场" not in (brief.drive.why or "")
    assert "本场已有痕迹接" not in (brief.drive.why or "")
    out = _template_utterance(brief)
    assert "星空" in out, out
    assert "记得" in out, out
