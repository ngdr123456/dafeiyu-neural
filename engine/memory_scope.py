"""Positive evidence of recorded utterances, separate from a bounded view.

No names/values are recovered for the generator here. This only prevents a
finite retrieval window from being mistaken for a history that never existed.
Relation slots remain fallible readings; external facts are not verified.
"""
import re


def describe(entries, raw, origin, current=None):
    from dialogue_memory import eligible_entries
    from relational_memory import _reading, _query
    from input_provenance import digest
    kind = (origin or {}).get("kind", "unknown")
    rows = [(index, row) for index, row in eligible_entries(entries, origin)
            if (row.get("input_origin") or {}).get("kind", "unknown") == kind]
    claims = []
    for _, row in rows:
        provenance = (row.get("input_origin") or {}).get("input_sha256")
        if provenance and provenance != digest(row["raw_input"]):
            continue
        reading = _reading(row["raw_input"], row.get("proposition_reading"))
        if reading:
            claims.extend(reading["propositions"])
    reading = _reading(raw, current)
    query = _query(raw, reading, {n["subject"] for n in claims})
    known = bool(query.get("subject") and query.get("predicate") and any(
        n["subject"] == query["subject"] and n["predicate"] == query["predicate"] for n in claims))
    return {"schema": 1, "view": "finite_selected_utterances", "complete_history_presented": False,
            "same_domain_utterance_count": len(rows), "matching_relation_utterance_known": known,
            "presence_basis": "validated_literal_relation_reports_semantics_fallible",
            "record_absence_verified": False, "external_fact_verified": False}


def check(frame, text):
    from relational_memory import _outside_quotes
    scope = frame.memory_scope or {}
    if scope.get("matching_relation_utterance_known") is not True:
        return []
    outside = _outside_quotes(text)
    bad = []
    for clause in re.split(r"——|—|[。；;！？!?\n]", outside):
        # Mentioning, questioning, prohibiting or negating a denial is not an
        # assertion of absence. This syntax guard is deliberately conservative.
        if re.search(r"有没有|是否|不确定|不清楚|不知道|不能确定|未必|不一定|可能|"
                     r"不能说|不要说|不能断言|不该断言|不是没|并非没|不等于没", clause):
            continue
        qualified = re.search(r"当前.{0,8}(?:片段|检索|这批|原话)|这批.{0,8}(?:片段|原话)|"
                              r"本次检索|这次检索|已检索到|眼前片段|当前可用|(?:手头|提供给我).{0,6}片段", clause)
        denial = re.search(r"(?:我(?:这边|这里|这儿|这)?|你(?:以前|之前|从来)?|这里|这儿|这边)"
                           r".{0,4}(?:没有|没|从未|从没).{0,8}(?:记录|说过|听过|依据)", clause)
        if denial and not qualified:
            bad.append("已知同来源有相关原话记录，不能把当前有限片段写成全局未记录；请限定当前检索范围")
    return bad
