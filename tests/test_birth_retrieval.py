import json
import os
from pathlib import Path

import pytest

pytest.importorskip("sqlite_vec")

from birth import retrieval


class FakeEmbedder:
    embedding_size = 3

    def embed(self, texts):
        for text in texts:
            if "周末" in text or "故事" in text:
                yield [1.0, 0.0, 0.0]
            elif "月亮" in text:
                yield [0.0, 1.0, 0.0]
            else:
                yield [0.0, 0.0, 1.0]


@pytest.fixture
def fake_model(monkeypatch):
    monkeypatch.setattr(retrieval, "_load_embedder", lambda *args: FakeEmbedder())


def write_ledger(path, sessions):
    path.write_text(json.dumps({"sessions": sessions}, ensure_ascii=False), encoding="utf-8")


def test_build_search_only_target_ledger_and_preserve_bytes(tmp_path, fake_model):
    ledger = tmp_path / "ledger.json"
    write_ledger(ledger, [{"facts": ["周末讲故事", "周末讲故事", "  "],
                           "commitments_pending": ["看月亮"], "ended_at": "today",
                           "stance_traces": [{"kind": "kept", "point": "守住边界", "why": "尊重"}]}])
    write_ledger(tmp_path / "unrelated.json", [{"facts": ["外部秘密"]}])
    before = ledger.read_bytes()
    built = retrieval.build_index(ledger)
    assert built.rebuilt and built.rows == 4
    assert not retrieval.build_index(ledger).rebuilt
    hits = retrieval.search("周末故事", ledger)
    assert hits[0].text == "周末讲故事"
    assert hits[0].field == "facts" and hits[0].session_index == 0 and hits[0].ended_at == "today"
    assert {hit.field for hit in hits} >= {"stance_traces.point", "stance_traces.why"}
    assert all("外部秘密" not in hit.text for hit in retrieval.search("外部秘密", ledger))
    assert ledger.read_bytes() == before


def test_stale_rebuild_and_no_rebuild(tmp_path, fake_model):
    ledger = tmp_path / "ledger.json"
    write_ledger(ledger, [{"facts": ["看月亮"]}])
    first = retrieval.build_index(ledger)
    write_ledger(ledger, [{"facts": ["看月亮"]}, {"open_questions": ["周末讲故事"]}])
    before = ledger.read_bytes()
    assert retrieval.index_status(ledger).stale
    with pytest.raises(retrieval.IndexStale):
        retrieval.search("周末", ledger, rebuild_if_stale=False)
    hits = retrieval.search("周末", ledger)
    assert hits[0].text == "周末讲故事" and hits[0].session_index == 1
    assert retrieval.index_status(ledger).ledger_sha256 != first.ledger_sha256
    assert ledger.read_bytes() == before


def test_unavailable_leaves_ledger_and_index_untouched(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.json"
    write_ledger(ledger, [{"facts": ["周末"]}])
    before = ledger.read_bytes()
    def unavailable(*args):
        raise retrieval.RetrievalUnavailable("missing model")
    monkeypatch.setattr(retrieval, "_load_embedder", unavailable)
    with pytest.raises(retrieval.RetrievalUnavailable):
        retrieval.build_index(ledger)
    assert ledger.read_bytes() == before
    assert not retrieval.default_index_path(ledger).exists()


@pytest.mark.parametrize("contents", [None, "", '{"sessions": []}'])
def test_empty_or_missing_ledger(tmp_path, monkeypatch, contents):
    ledger = tmp_path / "ledger.json"
    if contents is not None:
        ledger.write_text(contents, encoding="utf-8")
    def unavailable(*args):
        raise AssertionError("empty index should not load a model")
    monkeypatch.setattr(retrieval, "_load_embedder", unavailable)
    assert retrieval.build_index(ledger).rows == 0
    assert retrieval.search("什么", ledger) == []


def test_failed_rebuild_preserves_previous_index(tmp_path, fake_model, monkeypatch):
    ledger = tmp_path / "ledger.json"
    write_ledger(ledger, [{"facts": ["月亮"]}])
    retrieval.build_index(ledger)
    index = retrieval.default_index_path(ledger)
    before = index.read_bytes()
    class Broken(FakeEmbedder):
        def embed(self, texts):
            raise RuntimeError("broken")
    monkeypatch.setattr(retrieval, "_load_embedder", lambda *args: Broken())
    with pytest.raises(retrieval.RetrievalUnavailable):
        retrieval.build_index(ledger, force=True)
    assert index.read_bytes() == before
    assert list(tmp_path.glob("*.tmp")) == []


def test_reject_ledger_as_index(tmp_path):
    ledger = tmp_path / "ledger.json"
    write_ledger(ledger, [])
    before = ledger.read_bytes()
    with pytest.raises(ValueError):
        retrieval.build_index(ledger, ledger)
    assert ledger.read_bytes() == before


@pytest.mark.skipif(os.environ.get("BIRTH_RETRIEVAL_REAL") != "1", reason="real model is opt-in")
def test_real_chinese_model(tmp_path):
    model_dir = Path(os.environ.get("BIRTH_RETRIEVAL_MODEL_DIR", "build/retrieval-model-local"))
    if not model_dir.is_dir():
        pytest.skip("local model directory missing")
    ledger = tmp_path / "ledger.json"
    write_ledger(ledger, [{"facts": ["周末要给你讲一个海边的故事", "昨天吃了番茄炒蛋", "窗外下起了雨"]}])
    retrieval.build_index(ledger, model_dir=model_dir)
    assert "周末" in retrieval.search("周末要讲的故事", ledger, model_dir=model_dir)[0].text
