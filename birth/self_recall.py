"""Conservative, bounded lookup of delivered utterances; never changes the ledger."""
import re

from .types import HerUtterance, RecallEvidence, RecallResult

MAX_LEDGER_BYTES = 2_000_000
MAX_RECORDS = 1200
MAX_SCAN_CHARS = 200_000
MAX_EVIDENCE_CHARS = 600


def _credible_request(signal):
    return bool(signal is not None and not signal.degraded and signal.confidence == "high"
                and not signal.quoted_or_negated and signal.act in ("ask", "request")
                and signal.addressee == "other" and signal.recall_self)


def recall_request(signal, user_text):
    return bool(isinstance(user_text, str) and len(user_text) <= 2000
                and _credible_request(signal))


def _asking_clause(target, user_text):
    """Recognize only a content-free, final ask-back clause from this question."""
    question = user_text.strip()
    clause = target.strip().rstrip("?？ ")
    if not clause or not question.endswith(("?", "？")):
        return False
    body = question.rstrip("?？ ")
    if not body.endswith(clause):
        return False
    return bool(re.fullmatch(
        r"你(?:之前|刚才|先前|以前)?问(?:过)?我(?:什么|哪(?:个|些)问题)"
        r"|what did you ask me", clause, re.IGNORECASE))


def recall_result(signal, user_text, store, memory):
    if not _credible_request(signal):
        return RecallResult("not_requested")
    if not recall_request(signal, user_text):
        return RecallResult("unavailable")
    target = signal.recall_target
    # Missing fragments or the complete current question refer to hanging questions.
    frame = isinstance(target, str) and (not target.strip() or (
        target.strip().rstrip("?？ ") == user_text.strip().rstrip("?？ ")
        and user_text.strip().endswith(("?", "？"))) or _asking_clause(target, user_text))
    if frame:
        try:
            ctx = store.snapshot()
            questions = [(q, "同场") for q in ctx.her_questions if q in ctx.open_questions]
            if ctx.prior_session:
                questions += [(q, "上场") for q in ctx.prior_session.her_questions]
            if any(not isinstance(q, str) or not q or len(q) > MAX_EVIDENCE_CHARS for q, _ in questions):
                return RecallResult("unavailable")
            if not questions:
                return RecallResult("no_match")
            if len(questions) > 1:
                texts = tuple(q for q, _ in questions)
                return RecallResult(
                    "multiple",
                    RecallEvidence("\n".join(texts), "同场", "", True, texts),
                )
            q, scope = questions[0]
            return RecallResult("unique", RecallEvidence(q, scope, "", not q.startswith("…")))
        except (ValueError, TypeError, AttributeError):
            return RecallResult("unavailable")
    if not isinstance(target, str) or not 4 <= len(target) <= 80 or target not in user_text:
        return RecallResult("unavailable")
    try:
        records = []
        incomplete = False
        fields = ("text", "drive_direction", "stance_posture", "org_grain", "source")
        if memory is not None:
            # Validate and consume the same bounded snapshot; do not read the ledger twice.
            for index, raw in enumerate(memory._read_raw(max_bytes=MAX_LEDGER_BYTES), 1):
                if "her_utterances" not in raw:
                    incomplete = True
                items = raw.get("her_utterances", [])
                if not isinstance(items, list) or any(
                    not isinstance(item, dict)
                    or any(not isinstance(item.get(field), str) for field in fields)
                    or ("complete" in item and not isinstance(item["complete"], bool))
                    for item in items
                ):
                    return RecallResult("unavailable")
                ended = str(raw.get("ended_at") or "")
                for item in items:
                    entry = HerUtterance(**{field: item[field] for field in fields},
                                         complete=item.get("complete") is True)
                    records.append((entry, f"已结束场次 #{index}", ended))
        records.extend((entry, "同场", "") for entry in store._her_utterances)
        if len(records) > MAX_RECORDS or sum(len(e.text) for e, _, _ in records) > MAX_SCAN_CHARS:
            return RecallResult("unavailable")
        incomplete |= any(e.complete is not True for e, _, _ in records)
        hits = [(e, scope, ended) for e, scope, ended in records if target in e.text]
        evidence = None
        if len(hits) == 1:
            entry, scope, ended = hits[0]
            if len(entry.text) > MAX_EVIDENCE_CHARS:
                return RecallResult("unavailable")
            evidence = RecallEvidence(entry.text, scope, ended, entry.complete is True)
        if incomplete:
            # Preserve the legacy evidence API while acknowledging missing text or history.
            return RecallResult("unavailable", evidence)
        if not hits:
            return RecallResult("no_match")
        if len(hits) > 1:
            return RecallResult("multiple")
        return RecallResult("unique", evidence)
    except (OSError, ValueError, TypeError, RuntimeError, AttributeError):
        return RecallResult("unavailable")


def recall(signal, user_text, store, memory):
    """Compatibility API: only the single retained piece of evidence, or None."""
    return recall_result(signal, user_text, store, memory).evidence


def apply_recall_to_brief(brief, recalled) -> None:
    """把回忆结果压进意图/焦点，供仲裁后开口消费；压过守诺焦点。"""
    if not getattr(brief, "recall_requested", False):
        return
    brief.focus_source = "self_recall"
    status = recalled.status
    evidence = recalled.evidence
    if status == "unique" and evidence is not None:
        brief.focus = evidence.text
        brief.say_intent = (
            f"只依据检索到的系统侧提问作答，如实复述：「{evidence.text}」；"
            "绝不要把用户说过的话当成我问过的。"
        )
        return
    if status == "multiple" and evidence is not None:
        qs = list(evidence.questions) if evidence.questions else [
            line for line in evidence.text.splitlines() if line
        ]
        brief.focus = "\n".join(qs) if qs else evidence.text
        listed = "；".join(qs) if qs else evidence.text
        brief.say_intent = (
            f"检索到多条系统侧提问，不确定对方指哪一条，如实列出：{listed}；"
            "绝不要把用户说过的话当成我问过的。"
        )
        return
    if status == "no_match":
        brief.focus = "没有可检索的提问"
        brief.say_intent = (
            "诚实说明：可检索范围内我没有问过可核对的提问；"
            "绝不要把用户说过的话当成我问过的。"
        )
        return
    brief.focus = "回忆不可用"
    brief.say_intent = (
        "说明本次回忆无法可靠完成，不要编造我问过的内容，"
        "也不要把用户说过的话当成我问过的。"
    )

