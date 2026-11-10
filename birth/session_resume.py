"""Open-session snapshot: pause and resume the same session.

Thin memory (birth_memory.json) still only records an ended session as a prior
trace. This module writes a sibling file, birth_session_open.json, with the
full same-session store so a process exit or window close can continue later.
It is not long-term personality, and it is not mixed into the thin ledger.
"""

from __future__ import annotations

import json
import os
import secrets
from dataclasses import asdict, fields, is_dataclass
from pathlib import Path
from typing import Any

from .memory import active_memory
from .types import (
    ActionFeedback,
    CommitmentCandidate,
    HerUtterance,
    PriorSessionTrace,
    SessionAction,
    SessionJudgment,
    StanceTrace,
    ThinContext,
)

OPEN_SESSION_NAME = "birth_session_open.json"
OPEN_SESSION_VERSION = 1


def open_session_path() -> Path | None:
    mem = active_memory()
    if mem is None:
        return None
    return Path(mem.path).with_name(OPEN_SESSION_NAME)


def _build(cls, data: Any):
    if data is None:
        return None
    if not isinstance(data, dict):
        raise ValueError(f"expected object for {cls.__name__}")
    allowed = {f.name for f in fields(cls)}
    return cls(**{key: data[key] for key in allowed if key in data})


def _list_of(cls, items) -> list:
    return [_build(cls, item) for item in (items or [])]


def _encode_metadata(meta: dict) -> dict:
    encoded = {}
    for name, entries in (meta or {}).items():
        rows = []
        for key, value in dict(entries or {}).items():
            if isinstance(key, tuple):
                rows.append({"key": list(key), "tuple": True, "value": value})
            else:
                rows.append({"key": key, "tuple": False, "value": value})
        encoded[name] = rows
    return encoded


def _decode_metadata(meta: dict) -> dict:
    decoded = {}
    for name, rows in (meta or {}).items():
        entries = {}
        if isinstance(rows, dict):
            # tolerate already-native maps
            decoded[name] = dict(rows)
            continue
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            key = row.get("key")
            if row.get("tuple") and isinstance(key, list):
                key = tuple(key)
            entries[key] = row.get("value")
        decoded[name] = entries
    return decoded


def _context_from_dict(data: dict) -> ThinContext:
    raw = dict(data)
    raw["commitment_candidates"] = _list_of(CommitmentCandidate, raw.get("commitment_candidates"))
    raw["session_judgments"] = _list_of(SessionJudgment, raw.get("session_judgments"))
    raw["session_actions"] = _list_of(SessionAction, raw.get("session_actions"))
    raw["action_feedback"] = _list_of(ActionFeedback, raw.get("action_feedback"))
    raw["stance_traces"] = _list_of(StanceTrace, raw.get("stance_traces"))
    prior = raw.get("prior_session")
    if prior is not None:
        prior = dict(prior)
        prior["stance_traces"] = _list_of(StanceTrace, prior.get("stance_traces"))
        prior["commitment_candidates"] = _list_of(CommitmentCandidate, prior.get("commitment_candidates"))
        raw["prior_session"] = _build(PriorSessionTrace, prior)
    return _build(ThinContext, raw)


def serialize_open_state(state: dict) -> dict:
    context = state["context"]
    return {
        "context": asdict(context) if is_dataclass(context) else context,
        "resolved_commitments": list(state.get("resolved_commitments") or []),
        "her_utterances": [
            asdict(item) if is_dataclass(item) else dict(item)
            for item in (state.get("her_utterances") or [])
        ],
        "prior_her_question_text": state.get("prior_her_question_text") or "",
        "record_metadata": _encode_metadata(state.get("record_metadata") or {}),
        "session_turns": list(state.get("session_turns") or []),
    }


def deserialize_open_state(payload: dict) -> dict:
    return {
        "context": _context_from_dict(payload.get("context") or {}),
        "resolved_commitments": list(payload.get("resolved_commitments") or []),
        "her_utterances": _list_of(HerUtterance, payload.get("her_utterances")),
        "prior_her_question_text": payload.get("prior_her_question_text") or "",
        "record_metadata": _decode_metadata(payload.get("record_metadata") or {}),
        "session_turns": list(payload.get("session_turns") or []),
    }


def save_open_session(store) -> bool:
    path = open_session_path()
    if path is None:
        return False
    payload = {
        "version": OPEN_SESSION_VERSION,
        **serialize_open_state(store.export_open_state()),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.{secrets.token_hex(8)}.tmp"
    try:
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise
    return True


def load_open_session(store) -> bool:
    path = open_session_path()
    if path is None or not path.is_file():
        return False
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(raw, dict) or raw.get("version") != OPEN_SESSION_VERSION:
        return False
    if "context" not in raw:
        return False
    try:
        store.import_open_state(deserialize_open_state(raw))
    except (TypeError, ValueError, KeyError):
        return False
    return True


def clear_open_session() -> None:
    path = open_session_path()
    if path is not None and path.is_file():
        path.unlink()
