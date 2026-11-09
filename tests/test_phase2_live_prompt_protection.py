"""Offline guards for exact question citation and equal action confidence gates."""
import json
import pytest
from birth import input_sense, llm_deepseek, pipeline
from birth.articulate import set_llm_hook, set_stub_mode, clear_llm_hook
from birth.context import ThinContextStore
from birth.memory import configure_memory
from birth.types import ThinContext, SessionAction

QUESTION='你觉得雨天适合散步吗？'
REPLY='我觉得雨天适合散步。'
ACTION='你想怎样安排周末？'
REPORT='你的问题让我更难安排周末。'

def parse(monkeypatch, text, context, value):
    payload={'choices':[{'message':{'content':json.dumps(value,ensure_ascii=False)}}]}
    monkeypatch.setattr(llm_deepseek,'load_api_key',lambda:'synthetic')
    monkeypatch.setattr(input_sense,'_post_json',lambda *a,**k:payload)
    return input_sense.sense_input(text,context=context)

def test_reply_is_not_question_citation_or_settlement(monkeypatch):
    configure_memory(enabled=False)
    store=ThinContextStore(); monkeypatch.setattr(pipeline,'_STORE',store)
    set_stub_mode(False); set_llm_hook(lambda brief:QUESTION)
    try:
        pipeline.turn('聊聊',stub=False,sense=False)
        assert QUESTION in store.pending_questions()
        value={'act':'tell','addressee':'other','confidence':'high','answers_open_question':REPLY,'answer_scope':REPLY}
        signal=parse(monkeypatch,REPLY,store.context,value)
        assert signal.target_open_question==''
        set_llm_hook(lambda brief:'好，我听到了。')
        result=pipeline.turn(REPLY,stub=False,sense=False,input_signal=signal)
        assert result.brief.openq_resolve_target==''
        assert QUESTION in store.pending_questions()
    finally:
        clear_llm_hook(); set_stub_mode(False); configure_memory(enabled=False)

def test_visible_question_exactly_cited_is_kept(monkeypatch):
    value={'act':'tell','addressee':'other','confidence':'high','answers_open_question':QUESTION,'answer_scope':REPLY}
    signal=parse(monkeypatch,REPLY,ThinContext(open_questions=[QUESTION]),value)
    assert signal.target_open_question==QUESTION
    assert signal.answer_scope==REPLY

@pytest.mark.parametrize('confidence,effect,expected',[
    ('medium','obstructs','unknown'),('high','obstructs','report'),
    ('medium','supports','unknown'),('high','supports','report')])
def test_action_effects_share_confidence_gate(monkeypatch,confidence,effect,expected):
    value={'act':'tell','addressee':'other','confidence':confidence,
           'action_report_relation':'report','action_report_holder':'user','action_report_asserted':True,
           'action_report_action':ACTION,'action_report_order':0,'action_report_span':REPORT,
           'action_report_scope':'安排周末','action_report_effect':effect,'action_report_previous':''}
    signal=parse(monkeypatch,REPORT,ThinContext(session_actions=[SessionAction(ACTION,'周末')]),value)
    assert signal.action_report_relation==expected
