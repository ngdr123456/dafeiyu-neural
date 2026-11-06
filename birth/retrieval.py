from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .memory import BirthMemoryStore

DEFAULT_MODEL = "BAAI/bge-small-zh-v1.5"
_SCHEMA_VERSION = "1"
_FIELDS = ("facts", "commitments_pending", "commitments_resolved", "open_questions", "her_questions")


class RetrievalUnavailable(RuntimeError):
    """The vector extension or embedding model is unavailable."""


class IndexStale(RuntimeError):
    """The index is absent, incompatible, or does not match the ledger."""


class LedgerError(RuntimeError):
    """The ledger cannot be safely read for retrieval."""


class LedgerUnreadable(LedgerError):
    """The ledger cannot be read."""


class LedgerInvalid(LedgerError):
    """The ledger is not a valid supported JSON structure."""


@dataclass(frozen=True)
class RetrievalHit:
    text: str
    field: str
    session_index: int
    ended_at: str
    distance: float


@dataclass(frozen=True)
class IndexStatus:
    index_path: str
    exists: bool
    stale: bool
    schema_version: str | None = None
    model: str | None = None
    dim: int | None = None
    ledger_path: str | None = None
    ledger_sha256: str | None = None
    ledger_size: int | None = None
    built_at: str | None = None
    rows: int = 0
    rebuilt: bool = False


def default_index_path(ledger_path: str | Path) -> Path:
    path = Path(ledger_path).expanduser()
    return path.with_name(path.stem + ".vec.sqlite3")


def _paths(ledger_path, index_path):
    ledger = Path(ledger_path).expanduser().resolve()
    index = Path(index_path).expanduser().resolve() if index_path is not None else default_index_path(ledger)
    if ledger == index or (ledger.exists() and index.exists() and os.path.samefile(ledger, index)):
        raise ValueError("index path must be different from ledger path")
    return ledger, index


def _read_ledger_bytes(path):
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return b""
    except OSError as exc:
        raise LedgerUnreadable(f"Cannot read ledger {path}: {exc}") from exc


def _preflight_ledger(path):
    try:
        path.stat()
    except FileNotFoundError:
        return []
    except OSError as exc:
        raise LedgerUnreadable(f"Cannot read ledger {path}: {exc}") from exc
    try:
        data = _read_ledger_bytes(path)
    except OSError as exc:
        raise LedgerUnreadable(f"Cannot read ledger {path}: {exc}") from exc
    if not data:
        raise LedgerInvalid(f"Invalid ledger {path}: empty file")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LedgerInvalid(f"Invalid ledger {path}: not UTF-8") from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LedgerInvalid(f"Invalid ledger {path}: invalid JSON at line {exc.lineno}, column {exc.colno}") from exc
    if isinstance(payload, dict):
        sessions = payload.get("sessions")
    else:
        sessions = payload
    if not isinstance(sessions, list):
        raise LedgerInvalid(f"Invalid ledger {path}: sessions must be a list")
    for number, session in enumerate(sessions):
        if not isinstance(session, dict):
            raise LedgerInvalid(f"Invalid ledger {path}: session {number} must be an object")
        for field in _FIELDS:
            if field in session and (not isinstance(session[field], list)
                                     or any(not isinstance(value, str) for value in session[field])):
                raise LedgerInvalid(f"Invalid ledger {path}: session {number} {field} must be a list of strings")
        if "stance_traces" in session:
            traces = session["stance_traces"]
            if not isinstance(traces, list) or any(not isinstance(trace, dict) for trace in traces):
                raise LedgerInvalid(f"Invalid ledger {path}: session {number} stance_traces must be a list of objects")
            for trace in traces:
                for field in ("kind", "point", "why"):
                    if field in trace and not isinstance(trace[field], str):
                        raise LedgerInvalid(f"Invalid ledger {path}: session {number} stance_traces.{field} must be a string")

    return sessions


def _fingerprint(path):
    try:
        data = _read_ledger_bytes(path)
    except OSError as exc:
        raise LedgerUnreadable(f"Cannot read ledger {path}: {exc}") from exc
    return hashlib.sha256(data).hexdigest(), len(data)


def _load_vec():
    try:
        import sqlite_vec
        return sqlite_vec
    except (ImportError, OSError) as exc:
        raise RetrievalUnavailable("sqlite-vec unavailable; install sqlite-vec and put it on PYTHONPATH") from exc


def _load_embedder(model, model_dir=None, cache_dir=None):
    try:
        from fastembed import TextEmbedding
        kwargs = {"model_name": model}
        if cache_dir is not None:
            kwargs["cache_dir"] = str(cache_dir)
        if model_dir is not None:
            kwargs["specific_model_path"] = str(model_dir)
        return TextEmbedding(**kwargs)
    except Exception as exc:
        raise RetrievalUnavailable("fastembed or model unavailable; install fastembed and provide a valid --model-dir, or configure cache/network access") from exc


def _connect_vec(path):
    vec = _load_vec()
    conn = sqlite3.connect(str(path))
    try:
        conn.enable_load_extension(True)
        vec.load(conn)
        conn.enable_load_extension(False)
    except Exception as exc:
        conn.close()
        raise RetrievalUnavailable(f"could not load sqlite-vec extension; check sqlite-vec installation: {exc}") from exc
    return conn, vec


def _items(ledger):
    seen = set()
    for number, session in enumerate(BirthMemoryStore(ledger).list_sessions()):
        for field in (*_FIELDS, "stance_traces.point", "stance_traces.why"):
            if field.startswith("stance_traces."):
                attr = field.split(".", 1)[1]
                values = (getattr(trace, attr) for trace in session.stance_traces)
            else:
                values = getattr(session, field)
            for value in values:
                if not isinstance(value, str) or not value.strip():
                    continue
                key = (number, field, value)
                if key not in seen:
                    seen.add(key)
                    yield number, field, value, session.ended_at


def index_status(ledger_path, index_path=None, *, model=DEFAULT_MODEL, dim=None):
    _preflight_ledger(Path(ledger_path).expanduser())
    ledger, index = _paths(ledger_path, index_path)
    digest, size = _fingerprint(ledger)
    if not index.is_file():
        return IndexStatus(str(index), False, True)
    try:
        # URI read-only avoids accidentally creating a database during inspection.
        conn = sqlite3.connect(index.as_uri() + "?mode=ro", uri=True)
        try:
            meta = dict(conn.execute("SELECT key, value FROM meta"))
        finally:
            conn.close()
        stored_dim = int(meta["dim"])
        rows = int(meta["rows"])
        stale = (meta["schema_version"] != _SCHEMA_VERSION or meta["model"] != model
                 or meta["ledger_path"] != str(ledger) or meta["ledger_sha256"] != digest
                 or int(meta["ledger_size"]) != size
                 or (dim is not None and rows > 0 and stored_dim != dim))
        return IndexStatus(str(index), True, stale, meta["schema_version"], meta["model"],
                           stored_dim, meta["ledger_path"], meta["ledger_sha256"],
                           int(meta["ledger_size"]), meta["built_at"], rows)
    except (sqlite3.Error, KeyError, TypeError, ValueError):
        return IndexStatus(str(index), True, True)


def build_index(ledger_path, index_path=None, *, model=DEFAULT_MODEL, model_dir=None, cache_dir=None, force=False):
    _preflight_ledger(Path(ledger_path).expanduser())
    ledger, index = _paths(ledger_path, index_path)
    digest, size = _fingerprint(ledger)
    items = list(_items(ledger))
    if _fingerprint(ledger) != (digest, size):
        raise RuntimeError("ledger changed while reading; retry index build")
    embedder = _load_embedder(model, model_dir, cache_dir) if items else None
    dim = int(embedder.embedding_size) if embedder else 0
    if items and dim < 1:
        raise RetrievalUnavailable("embedding model has invalid embedding_size")
    status = index_status(ledger, index, model=model, dim=dim)
    if not force and not status.stale:
        return status
    index.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=index.name + ".", suffix=".tmp", dir=index.parent)
    os.close(fd)
    try:
        conn, vec = _connect_vec(temporary)
        try:
            conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            conn.execute("CREATE TABLE memory_items (id INTEGER PRIMARY KEY, session_index INTEGER NOT NULL, field TEXT NOT NULL, text TEXT NOT NULL, ended_at TEXT NOT NULL, UNIQUE(session_index, field, text))")
            # Empty indexes need a vec0 table but do not require loading a model.
            conn.execute(f"CREATE VIRTUAL TABLE vec_items USING vec0(embedding float[{dim or 1}])")
            if items:
                try:
                    vectors = iter(embedder.embed([item[2] for item in items]))
                    for rowid, item in enumerate(items, 1):
                        vector = list(next(vectors))
                        if len(vector) != dim:
                            raise ValueError("embedding dimension mismatch")
                        conn.execute("INSERT INTO memory_items VALUES (?, ?, ?, ?, ?)", (rowid, *item))
                        conn.execute("INSERT INTO vec_items(rowid, embedding) VALUES (?, ?)", (rowid, vec.serialize_float32(vector)))
                    if next(vectors, None) is not None:
                        raise ValueError("embedding count mismatch")
                except Exception as exc:
                    raise RetrievalUnavailable("embedding failed; check fastembed and the model files") from exc
            meta = {"schema_version": _SCHEMA_VERSION, "model": model, "dim": dim,
                    "ledger_path": str(ledger), "ledger_sha256": digest, "ledger_size": size,
                    "built_at": datetime.now(timezone.utc).isoformat(), "rows": len(items)}
            conn.executemany("INSERT INTO meta VALUES (?, ?)", [(key, str(value)) for key, value in meta.items()])
            conn.commit()
        finally:
            conn.close()
        if _fingerprint(ledger) != (digest, size):
            raise RuntimeError("ledger changed during index build; retry")
        os.replace(temporary, index)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    from dataclasses import replace
    return replace(index_status(ledger, index, model=model, dim=dim), rebuilt=True)


def search(query, ledger_path, index_path=None, *, k=5, model=DEFAULT_MODEL, model_dir=None, cache_dir=None, rebuild_if_stale=True):
    if not isinstance(k, int) or isinstance(k, bool) or not 1 <= k <= 50:
        raise ValueError("k must be an integer between 1 and 50")
    status = index_status(ledger_path, index_path, model=model)
    ledger, index = _paths(ledger_path, index_path)
    if status.stale:
        if not rebuild_if_stale:
            raise IndexStale("retrieval index is missing or stale")
        status = build_index(ledger, index, model=model, model_dir=model_dir, cache_dir=cache_dir)
    if not status.rows:
        return []
    embedder = _load_embedder(model, model_dir, cache_dir)
    dim = int(embedder.embedding_size)
    if dim != status.dim:
        if not rebuild_if_stale:
            raise IndexStale("embedding dimension differs from index")
        status = build_index(ledger, index, model=model, model_dir=model_dir, cache_dir=cache_dir, force=True)
        if dim != status.dim:
            raise RetrievalUnavailable("embedding dimension changed during rebuild")
    try:
        vector = list(next(iter(embedder.embed([query]))))
        if len(vector) != dim:
            raise ValueError("embedding dimension mismatch")
    except Exception as exc:
        raise RetrievalUnavailable("query embedding failed; check fastembed and the model files") from exc
    conn, vec = _connect_vec(index)
    try:
        rows = conn.execute("SELECT m.text, m.field, m.session_index, m.ended_at, v.distance FROM vec_items v JOIN memory_items m ON m.id = v.rowid WHERE v.embedding MATCH ? AND k = ? ORDER BY v.distance", (vec.serialize_float32(vector), min(k, status.rows))).fetchall()
        return [RetrievalHit(*row) for row in rows]
    finally:
        conn.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Local read-only memory retrieval sidecar")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("build", "search", "status"):
        p = sub.add_parser(command)
        p.add_argument("--ledger", required=True)
        p.add_argument("--index")
        p.add_argument("--model", default=DEFAULT_MODEL)
        p.add_argument("--model-dir")
        p.add_argument("--cache-dir")
        if command == "build":
            p.add_argument("--force", action="store_true")
        if command == "search":
            p.add_argument("query")
            p.add_argument("--k", type=int, default=5)
            p.add_argument("--no-rebuild", action="store_true")
    args = parser.parse_args(argv)
    try:
        common = dict(model=args.model)
        if args.command == "status":
            result = asdict(index_status(args.ledger, args.index, **common))
        elif args.command == "build":
            result = asdict(build_index(args.ledger, args.index, model_dir=args.model_dir, cache_dir=args.cache_dir, force=args.force, **common))
        else:
            result = [asdict(hit) for hit in search(args.query, args.ledger, args.index, k=args.k, model_dir=args.model_dir, cache_dir=args.cache_dir, rebuild_if_stale=not args.no_rebuild, **common)]
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (RetrievalUnavailable, IndexStale, ValueError, OSError, sqlite3.Error, RuntimeError) as exc:
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
