"""Bounded literal dialogue retrieval, not inferred facts or personality credit.

ENG: recent 6 + at most 4 lexical matches. Authorship domains are kept apart;
training personas are scoped to a run and session, never memories of a human.
"""
import hashlib
import json
import re


def _tokens(text):
    chars = re.sub(r"[^\w]", "", text)
    return {chars[i:i + 2] for i in range(len(chars) - 1)}


def eligible_entries(entries, origin=None):
    origin = origin or {}
    kind = origin.get("kind", "unknown")
    eligible = []
    for index, entry in enumerate(entries):
        row = entry.to_dict() if hasattr(entry, "to_dict") else entry
        if row.get("void") or not row.get("raw_input", "").strip():
            continue
        prior = row.get("input_origin") or {}
        if origin.get("run_id"):
            if (prior.get("run_id") != origin["run_id"] or
                    prior.get("session_id") != origin.get("session_id")):
                continue
        elif prior.get("run_id") or prior.get("kind") in {
                "tutor_generated", "model_generated", "project_corpus", "project_topic"}:
            continue
        elif kind == "interactive_input" and prior.get("kind") != "interactive_input":
            continue
        eligible.append((index, row))
    return eligible


def _retrieval_brief(scope):
    """把当轮的 memory_scope 压成三个字段，供大脑判断"那次是不是没看全"。

    旧行没有 memory_scope（405 行里 0 条）⇒ 返回 None，
    **不伪造成"看全了"，也不伪造成"没看全"**。
    """
    if not isinstance(scope, dict) or not scope:
        return None
    return {"same_domain_utterance_count": scope.get("same_domain_utterance_count"),
            "matching_relation_utterance_known": scope.get("matching_relation_utterance_known"),
            "complete_history_presented": scope.get("complete_history_presented")}


def source_record(index, row):
    original = row["raw_input"]
    return {"source_id": "dialogue:%d:%s" %
            (index + 1, hashlib.sha256(original.encode()).hexdigest()[:12]),
            "ledger_index": index + 1, "ts": row.get("ts"),
            "input_origin": row.get("input_origin"),
            "user_text": original[:800], "user_text_clipped": len(original) > 800,
            "system_output": (row.get("output") or "")[:400],
            # ★ 当时这一轮的检索范围（2026-10-28）。
            #   有了它，大脑看到自己以前说过什么时，**同时知道那次看得到多少**
            #   —— 这是"同一件事两次不同答案，而她自己知道"的唯一实现方式。
            #   只给三个字段，不含姓名或答案，不构成对世界的断言。
            "retrieval_then": _retrieval_brief(row.get("memory_scope")),
            "assertion_status": "utterance_not_verified_world_fact"}


def retrieve(entries, raw, origin=None, recent=6, related=4):
    eligible = eligible_entries(entries, origin)
    recent_rows = eligible[-recent:] if recent else []
    selected = {index for index, _ in recent_rows}
    tokens = _tokens(raw)
    matches = sorted(((len(tokens & _tokens(row["raw_input"])), index)
                      for index, row in eligible if index not in selected), reverse=True)
    selected.update(index for score, index in matches[:related] if score)
    result = []
    for index, row in eligible:
        if index not in selected:
            continue
        result.append(source_record(index, row))
    return result


def format_history(sources):
    if not sources:
        return "（没有可用的同一来源对话）"
    return json.dumps(sources, ensure_ascii=False, indent=2)
