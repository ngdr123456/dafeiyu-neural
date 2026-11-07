import json
from dataclasses import asdict

import pytest

from birth import pipeline
from birth.commit_extract import extract_commitment
from birth.context import ThinContextStore
from birth.input_contract import InputSignal
from birth.memory import BirthMemoryStore, SessionTraceRecord, configure_memory
from birth.types import CommitmentCandidate, PriorSessionTrace


def meta(subject="星空", truncated=False):
    return {"origin": "her_utterance", "subject": subject, "truncated": truncated}


@pytest.fixture(autouse=True)
def reset_pipeline():
    configure_memory(enabled=False)
    pipeline.active_store().new_session()
    yield
    configure_memory(enabled=False)
    pipeline.active_store().new_session()


@pytest.mark.parametrize("utterance, expected_commitment, expected_truncated", [
    # 整句原样
    ("我答应你明天聊星空。", "我答应你明天聊星空。", False),
    # 从整句里摘出的一段
    ("好的，我答应你明天聊星空。", "我答应你明天聊星空。", True),
    # 超过 40 字被截断
    ("我答应你" + "明天聊星空" * 10,
     "我答应你明天聊星空明天聊星空明天聊星空明天聊星空明天聊星空明天聊星空明天聊星空明…", True),
])
def test_pipeline_commitment_persisted(tmp_path, monkeypatch, utterance, expected_commitment, expected_truncated):
    path = tmp_path / "ledger.json"
    configure_memory(enabled=True, path=path)
    monkeypatch.setattr(pipeline, "articulate", lambda *args, **kwargs: utterance)
    pipeline.turn("聊聊星空", input_signal=InputSignal("tell", "other", "test", "test", topic="星空"), stub=True)
    assert extract_commitment(utterance) == expected_commitment
    pipeline.end_session()
    record = json.loads(path.read_text(encoding="utf-8"))["sessions"][0]
    assert record["commitments_pending"] == [expected_commitment]
    assert record["record_metadata"]["commitments_pending"] == [{**meta(truncated=expected_truncated), "subject_credible": True}]


def test_resolve_and_clear_candidate_metadata():
    store = ThinContextStore()
    store.append_commitment("承诺", metadata=meta())
    candidate = CommitmentCandidate("回头聊", "承诺", "same_session_press")
    store.append_commitment_candidate(candidate, metadata=meta(truncated=True))
    assert store.resolve_commitment() == "承诺"
    trace = store.export_session_trace()
    assert trace["commitments_resolved"] == ["承诺"]
    assert trace["record_metadata"]["commitments_resolved"] == [meta()]
    assert not trace["record_metadata"]["commitment_candidates"]
    assert not store._record_metadata["commitment_candidates"]
    store.append_commitment("另一个", metadata=meta())
    store.append_commitment_candidate(CommitmentCandidate("再聊", "另一个", "same_session_press"), metadata=meta())
    store.clear_commitments()
    assert not store._record_metadata["last_commitments"]
    assert not store._record_metadata["commitment_candidates"]
    assert store.export_session_trace()["record_metadata"]["commitments_resolved"] == [meta()]


def test_clear_commitments_keeps_surviving_candidate_metadata():
    """整场放下只删有对应承诺的候选；指向上场未兑现承诺的候选仍在，来源不许抹成未知。"""
    store = ThinContextStore()
    store.set_prior_session(PriorSessionTrace(
        commitments_pending=["上场的债"],
        record_metadata={"commitments_pending": {"上场的债": meta("旧")}},
    ))
    store.append_commitment_candidate(CommitmentCandidate("回头聊", "上场的债", "prior_press"), metadata=meta("旧"))
    store.append_commitment("本场的债", metadata=meta("今"))
    store.append_commitment_candidate(CommitmentCandidate("再聊", "本场的债", "same_session_press"), metadata=meta("今"))
    store.clear_commitments()
    assert [c.text for c in store._context.commitment_candidates] == ["回头聊"]
    trace = store.export_session_trace()
    assert [c.text for c in trace["commitment_candidates"]] == ["回头聊"]
    assert trace["record_metadata"]["commitment_candidates"] == [meta("旧")]


def test_cross_session_resolution_and_copies(tmp_path):
    memory = BirthMemoryStore(tmp_path / "ledger.json")
    first = ThinContextStore()
    first.append_commitment("承诺", metadata=meta())
    first.append_commitment_candidate(CommitmentCandidate("回头聊", "承诺", "same_session_press"), metadata=meta(truncated=True))
    memory.append_session(**first.export_session_trace())
    prior = memory.latest_prior()
    store = ThinContextStore()
    store.set_prior_session(prior)
    assert store.resolve_prior_commitment("承诺") == "承诺"
    live = store.snapshot().prior_session
    assert live.record_metadata["commitments_pending"] == {}
    assert live.record_metadata["commitments_resolved"] == {"承诺": meta()}
    assert live.record_metadata["commitment_candidates"] == {}
    assert prior.record_metadata["commitments_pending"] == {"承诺": meta()}
    assert store.export_session_trace()["record_metadata"]["commitments_resolved"] == [meta()]
    memory.append_session(**store.export_session_trace())
    assert memory.latest().record_metadata["commitments_resolved"] == [meta()]


def test_legacy_and_misaligned_metadata_are_unknown(tmp_path):
    path = tmp_path / "ledger.json"
    old = {"commitments_pending": ["旧承诺"], "commitments_resolved": ["旧兑现"]}
    path.write_text(json.dumps({"sessions": [old]}, ensure_ascii=False), encoding="utf-8")
    memory = BirthMemoryStore(path)
    store = ThinContextStore()
    store.set_prior_session(memory.latest_prior())
    trace = store.export_session_trace()
    assert trace["record_metadata"]["commitments_pending"] == [None]
    assert trace["record_metadata"]["commitments_resolved"] == [None]
    memory.append_session(**trace)
    assert json.loads(path.read_text(encoding="utf-8"))["sessions"][0] == old
    malformed = SessionTraceRecord(commitments_pending=["a", "b"], record_metadata={"commitments_pending": [meta()]})
    assert malformed.to_prior().record_metadata["commitments_pending"] == {}


def test_filtered_raw_candidates_cannot_shift_metadata(tmp_path):
    path = tmp_path / "ledger.json"
    raw = {"sessions": [{"commitments_pending": ["承诺"], "commitment_candidates": [
        {"text": "无效", "target": "承诺", "frame": "bad"},
        {"text": "有效", "target": "承诺", "frame": "prior_press"},
    ], "record_metadata": {"commitment_candidates": [meta()]}}]}
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    prior = BirthMemoryStore(path).latest_prior()
    assert [c.text for c in prior.commitment_candidates] == ["有效"]
    assert prior.record_metadata["commitment_candidates"] == {}


def test_duplicates_and_prior_conflict_are_unknown():
    store = ThinContextStore()
    store.append_commitment("承诺", metadata=meta())
    store.append_commitment("承诺", metadata=meta("月亮"))
    assert store.export_session_trace()["record_metadata"]["commitments_pending"] == [None]
    store.append_commitment("摘录", metadata=meta(truncated=True))
    store.append_commitment("摘录", metadata=meta(truncated=True))
    assert store.export_session_trace()["record_metadata"]["commitments_pending"][-1] == meta(truncated=True)
    store.set_prior_session(PriorSessionTrace(commitments_pending=["摘录"], record_metadata={"commitments_pending": {"摘录": meta("月亮")}}))
    assert store.export_session_trace()["record_metadata"]["commitments_pending"][0] is None


def test_prior_candidate_metadata_agrees_or_goes_unknown():
    """上场与本场同一条候选：来源一致才用，不一致就是未知。"""
    def build(local_subject):
        store = ThinContextStore()
        store.set_prior_session(PriorSessionTrace(
            commitments_pending=["承诺"],
            commitment_candidates=[CommitmentCandidate("回头聊", "承诺", "prior_press")],
            record_metadata={"commitment_candidates": {"承诺": {"回头聊": meta("月亮")}}},
        ))
        store.append_commitment_candidate(
            CommitmentCandidate("回头聊", "承诺", "prior_press"), metadata=meta(local_subject)
        )
        trace = store.export_session_trace()
        assert [c.text for c in trace["commitment_candidates"]] == ["回头聊"]
        return trace["record_metadata"]["commitment_candidates"]

    assert build("月亮") == [meta("月亮")]
    assert build("星空") == [None]


def test_candidate_capacity_and_disk_alignment(tmp_path):
    store = ThinContextStore()
    store.append_commitment("承诺", metadata=meta())
    for i in range(23):
        store.append_commitment_candidate(CommitmentCandidate(str(i), "承诺", "same_session_press"), metadata=meta(str(i)))
    assert set(store._record_metadata["commitment_candidates"]) == {("承诺", str(i)) for i in range(3, 23)}
    trace = store.export_session_trace()
    assert trace["record_metadata"]["commitment_candidates"] == [meta(str(i)) for i in range(3, 23)]
    memory = BirthMemoryStore(tmp_path / "ledger.json", max_commits=3)
    record = memory.append_session(**trace)
    assert [c.text for c in record.commitment_candidates] == ["20", "21", "22"]
    assert record.record_metadata["commitment_candidates"] == [meta(str(i)) for i in range(20, 23)]


def test_degraded_signal_and_pressed_candidate(tmp_path, monkeypatch):
    path = tmp_path / "ledger.json"
    configure_memory(enabled=True, path=path)
    store = pipeline.active_store()
    store.append_commitment("同场说好晚点聊月亮", metadata=meta("月亮"))
    utterance = "好，我晚点再跟你聊月亮。"
    monkeypatch.setattr(pipeline, "articulate", lambda *args, **kwargs: utterance)
    signal = InputSignal("tell", "other", "test", "test", degraded=True, topic="猜测的月亮")
    pipeline.turn("月亮的事呢", input_signal=signal, stub=True)
    pipeline.end_session()
    record = json.loads(path.read_text(encoding="utf-8"))["sessions"][0]
    assert record["commitment_candidates"]
    expected = meta("猜测的月亮", extract_commitment(utterance) != utterance.strip())
    expected["subject_degraded"] = True
    assert record["record_metadata"]["commitment_candidates"] == [expected]


def test_debug_brief_serializes_prior_candidate_metadata(tmp_path, monkeypatch):
    """--debug 工程师通道直接 json.dumps(asdict(brief))：元数据键必须 JSON 安全。"""
    path = tmp_path / "ledger.json"
    configure_memory(enabled=True, path=path)
    pipeline.active_store().append_commitment("同场说好晚点聊月亮", metadata=meta("月亮"))
    monkeypatch.setattr(pipeline, "articulate", lambda *args, **kwargs: "好，我晚点再跟你聊月亮。")
    pipeline.turn("月亮的事呢", input_signal=InputSignal("tell", "other", "test", "test", topic="月亮"), stub=True)
    pipeline.end_session()
    saved = json.loads(path.read_text(encoding="utf-8"))["sessions"][0]
    assert saved["record_metadata"]["commitment_candidates"]

    configure_memory(enabled=True, path=path)
    monkeypatch.setattr(pipeline, "articulate", lambda *args, **kwargs: "嗯，我在。")
    result = pipeline.turn("在吗", input_signal=InputSignal("tell", "other", "test", "test", topic="在吗"), stub=True, new_session=True)
    prior = result.brief.context.prior_session
    assert prior is not None and prior.record_metadata["commitment_candidates"]
    json.dumps(asdict(result.brief), ensure_ascii=False)


def test_degraded_signal_on_pending(tmp_path, monkeypatch):
    path = tmp_path / "ledger.json"
    configure_memory(enabled=True, path=path)
    utterance = "我答应你明天聊星空。"
    monkeypatch.setattr(pipeline, "articulate", lambda *args, **kwargs: utterance)
    signal = InputSignal("tell", "other", "test", "test", degraded=True, topic="猜测的星空")
    pipeline.turn("聊聊星空", input_signal=signal, stub=True)
    pipeline.end_session()
    record = json.loads(path.read_text(encoding="utf-8"))["sessions"][0]
    expected = meta("猜测的星空", extract_commitment(utterance) != utterance.strip())
    expected["subject_degraded"] = True
    assert record["record_metadata"]["commitments_pending"] == [expected]
