"""Conservative, bounded lookup of delivered utterances; never changes the ledger."""
from .types import RecallEvidence

MAX_LEDGER_BYTES = 2_000_000
MAX_RECORDS = 1200
MAX_SCAN_CHARS = 200_000
MAX_EVIDENCE_CHARS = 600


def recall_request(signal, user_text):
    if signal is None or not isinstance(user_text, str) or len(user_text) > 2000:
        return False
    return bool(not signal.degraded and signal.confidence == "high"
                and not signal.quoted_or_negated and signal.act in ("ask", "request")
                and signal.addressee == "other" and signal.recall_self)


def recall(signal, user_text, store, memory):
    if not recall_request(signal, user_text):
        return None
    target = signal.recall_target
    if not isinstance(target, str) or not 4 <= len(target) <= 80 or target not in user_text:
        return None
    try:
        records = []
        if memory is not None:
            try:
                size = memory.path.stat().st_size
            except FileNotFoundError:
                size = 0
            if size > MAX_LEDGER_BYTES:
                return None
            raw_sessions = memory._read_raw()
            for raw in raw_sessions:
                items = raw.get("her_utterances", [])
                fields = ("text", "drive_direction", "stance_posture", "org_grain", "source")
                if not isinstance(items, list) or any(
                    not isinstance(item, dict)
                    or any(not isinstance(item.get(field), str) for field in fields)
                    or ("complete" in item and not isinstance(item["complete"], bool))
                    for item in items
                ):
                    return None
            for index, session in enumerate(memory.list_sessions(), 1):
                records.extend((entry, f"已结束场次 #{index}", session.ended_at) for entry in session.her_utterances)
        records.extend((entry, "同场", "") for entry in store._her_utterances)
        if len(records) > MAX_RECORDS or sum(len(e.text) for e, _, _ in records) > MAX_SCAN_CHARS:
            return None
        hits = [(e, scope, ended) for e, scope, ended in records if signal.recall_target in e.text]
        if len(hits) != 1:
            return None
        entry, scope, ended = hits[0]
        if len(entry.text) > MAX_EVIDENCE_CHARS:
            return None
        return RecallEvidence(entry.text, scope, ended, entry.complete is True)
    except (OSError, ValueError, TypeError, RuntimeError, AttributeError):
        return None
