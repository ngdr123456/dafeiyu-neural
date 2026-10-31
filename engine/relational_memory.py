"""Source-bound organisation of reported relationships (M2 foundation, ENG).

This is an engineered representation, not a learned developmental rule. Claims
are reports of utterances, never verified world facts. Replay preserves old
claims, explicit correction edges, unresolved conflicts and authorship scopes.
The initial predicate vocabulary is deliberately small and can be extended.
"""
import hashlib
import re

PREDICATES = {"custodian", "contact", "location"}
ROLES = {"ASSERTED", "NEGATED", "PROHIBITED", "QUOTED", "UNKNOWN"}
VERSION = "reported-entity-predicate-time/v1"
SCHEMA_PROMPT = """9. propositions 保存本轮关于具体对象的关系原话，不评人格、不造世界事实。
只抽取 custodian（某物由谁收着/保管）、contact（针对某事已说要联系谁）、
location（具体对象在哪里）。subject/value/time 都必须是 evidence 中连续的原字，
subject 要具体（如甲项目押金），不得把不同项目统一改成押金。未说时间就 time=""。
start/end 为本轮原话的从0开始字符位置，evidence 严格等于该片段。
role=ASSERTED 仅限输入者本人的明确陈述；问句、假设、可能性用 UNKNOWN；
否定、禁止、引用分别用 NEGATED/PROHIBITED/QUOTED，不压成肯定。
correction=true 仅限输入者明确更正同一对象、同一关系、同一时间的旧说法；
一般的新陈述、其他对象、他人引用或过去与现在的变化都不是更正。
memory_query 只在询问这些关系时给对象；subject 必须在本轮 evidence 逐字出现，
省略对象时留空（不可从猜测补全），predicate 取上述集合，未说时间留空。
没有可抽取内容时 propositions=[]，memory_query=null。这不授予任何心理阶段。
"""


def _hash(raw):
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _outside_quotes(raw):
    masked = list(raw)
    for match in re.finditer(r'“[^”]*”|「[^」]*」|"[^"\n]*"|‘[^’]*’', raw):
        masked[match.start():match.end()] = " " * (match.end() - match.start())
    return "".join(masked)


def _literal(item, raw):
    if not isinstance(item, dict):
        return False
    start, end, evidence = item.get("start"), item.get("end"), item.get("evidence")
    return (type(start) is int and type(end) is int and 0 <= start < end <= len(raw)
            and isinstance(evidence, str) and 0 < len(evidence) <= 400
            and raw[start:end] == evidence and item.get("predicate") in PREDICATES)


def parse(raw, data, *, extractor="unspecified"):
    """Validate extraction locally; literal grounding does not verify semantics."""
    claims, dropped = [], []
    data = data if isinstance(data, dict) else {}
    outside = _outside_quotes(raw)
    corrections = bool(re.search(r"^(?:更正|纠正)[：:]|(?:前面|之前|刚才).{0,20}(?:说错|弄错)", outside))
    if re.search(r"没(?:有)?说错|不是更正|不要更正|不更正|无需更正", outside):
        corrections = False
    items = data.get("propositions", [])
    if not isinstance(items, list):
        items = []
        dropped.append("invalid_propositions")
    for item in items[:8]:
        if not _literal(item, raw):
            dropped.append("nonliteral_proposition")
            continue
        subject, value, time = item.get("subject"), item.get("value"), item.get("time", "")
        evidence = item["evidence"]
        if (not all(isinstance(x, str) and len(x) <= 80 for x in (subject, value, time))
                or not subject.strip() or not value.strip() or subject not in evidence
                or value not in evidence or (time and time not in evidence)
                or item.get("role") not in ROLES or type(item.get("correction", False)) is not bool):
            dropped.append("invalid_proposition_slots")
            continue
        role = item["role"]
        # Cheap conservative vetoes, not a substitute for semantic extraction.
        begin = max([raw.rfind(x, 0, item["start"]) for x in "。！？!?；;\n"] + [-1]) + 1
        # ★ 2026-10-28 修 off-by-one：原来从 `item["end"]` 往后找终止符。
        #   而 `evidence` **通常就以终止符结尾**（例如「甲项目押金由周老师收着。」），
        #   于是 find 会**跳过它自己那个「。」**，找到下一句的终止符 ⇒
        #   clause 跨了两句 ⇒ 把下一句的问号/假设词捡进来 ⇒
        #   整条**真断言**被判 `assertion_requires_review` 降级成 UNKNOWN。
        #
        #   实测（一个输入里既有断言又有查询）：
        #     clause = '更正：甲项目押金由周老师收着。现在告诉我：甲项目押金由谁收着？'
        #     命中否决词 '？' ⇒ 周老师那条被降级 ⇒ 分组只剩一个值 ⇒ 目标不提供。
        #
        #   修法：从 `end - 1` 开始找。若 evidence 末字就是终止符，立刻找到（p=end-1）；
        #   否则与原来等价。两种情形都不越界。
        finish = min([p for x in "。！？!?；;\n"
                      if (p := raw.find(x, max(0, item["end"] - 1))) >= 0] + [len(raw)])
        clause = raw[begin:min(finish + 1, len(raw))]
        unsafe_assertion = (outside[item["start"]:item["end"]] != evidence
                            or re.search(r"[？?]|如果|假如|也许|可能|不是|并非|不由|不在|不要|不能|没说", clause)
                            or re.search(r"(?:他说|她说|[\w]{1,8}说[：:])", clause))
        if role == "ASSERTED" and unsafe_assertion:
            role = "UNKNOWN"
            dropped.append("assertion_requires_review")
        claims.append({"subject": subject, "predicate": item["predicate"], "value": value,
                       "time": time, "role": role, "start": item["start"], "end": item["end"],
                       "evidence": evidence,
                       "correction": bool(item.get("correction") and corrections and role == "ASSERTED")})
    if len(items) > 8:
        dropped.append("proposition_limit")
    unique = {}
    for claim in claims:
        key = (claim["start"], claim["end"], claim["predicate"])
        if key in unique and unique[key] != claim:
            unique[key]["role"] = "UNKNOWN"
            unique[key]["correction"] = False
            dropped.append("conflicting_proposition_readings")
        else:
            unique[key] = claim
    claims = list(unique.values())
    query = data.get("memory_query")
    if query is not None:
        if (not _literal(query, raw) or not isinstance(query.get("subject"), str)
                or len(query["subject"]) > 80 or query["subject"] not in query["evidence"]
                or not isinstance(query.get("time", ""), str)
                or (query.get("time") and query["time"] not in query["evidence"])):
            dropped.append("invalid_memory_query")
            query = None
        else:
            query = {k: query.get(k, "") for k in ("subject", "predicate", "time", "start", "end", "evidence")}
    return {"schema": 1, "raw_sha256": _hash(raw), "propositions": claims, "memory_query": query,
            "extractor": extractor, "dropped": dropped, "independent_semantics_verified": False,
            "development_credit": 0}


def _reading(raw, value):
    if not isinstance(value, dict) or value.get("schema") != 1 or value.get("raw_sha256") != _hash(raw):
        return None
    return parse(raw, value, extractor=value.get("extractor", "unspecified"))


def _query(raw, reading, subjects):
    query = (reading or {}).get("memory_query")
    if query:
        return query
    matched = [s for s in subjects if s in raw]
    # Prefer a fully named object to its substring, never infer an alias.
    matched = [s for s in matched if not any(s != other and s in other for other in matched)]
    predicate = ("custodian" if re.search(r"收着|保管|代收", raw) else
                 "contact" if re.search(r"联系|联络", raw) else
                 "location" if re.search(r"在哪|哪里|何处", raw) else "")
    return {"subject": matched[0] if len(matched) == 1 else "", "predicate": predicate,
            "time": "", "matched_subjects": matched, "evidence": raw[:400]}


def project(entries, raw, origin=None, current=None, *, max_groups=4):
    """Replay source-scoped graph; no state file or model call is needed here."""
    from dialogue_memory import eligible_entries, source_record
    origin = origin or {}
    rows = []
    for index, row in eligible_entries(entries, origin):
        # Unknown authorship never silently becomes a known narrator.
        if (row.get("input_origin") or {}).get("kind", "unknown") != origin.get("kind", "unknown"):
            continue
        prior_hash = (row.get("input_origin") or {}).get("input_sha256")
        if prior_hash and prior_hash != _hash(row["raw_input"]):
            continue
        reading = _reading(row["raw_input"], row.get("proposition_reading"))
        if reading:
            rows.append((source_record(index, row), reading))
    current = _reading(raw, current)
    if current:
        rows.append(({"source_id": "current:" + _hash(raw)[:12], "user_text": raw[:800],
                      "input_origin": origin, "assertion_status": "utterance_not_verified_world_fact"}, current))
    nodes, groups, source_map = [], {}, {}
    for source, reading in rows:
        source_id = source["source_id"]
        source_map[source_id] = source
        batch = {}
        for item in reading["propositions"]:
            node = dict(item, node_id=source_id + ":%d:%d" % (item["start"], item["end"]),
                        source_id=source_id, raw_sha256=reading["raw_sha256"],
                        speaker="input_author" if item["role"] == "ASSERTED" else "unresolved_or_reported",
                        status="reported" if item["role"] == "ASSERTED" else "not_positive_assertion",
                        corrects=[], superseded_by=None)
            nodes.append(node)
            key = (item["subject"], item["predicate"], item["time"])
            batch.setdefault(key, []).append(node)
        for key, items in batch.items():
            active = groups.setdefault(key, [])
            asserted = [n for n in items if n["role"] == "ASSERTED"]
            if len({n["value"] for n in asserted}) == 1 and any(n["correction"] for n in asserted):
                correction = next(n for n in asserted if n["correction"])
                for old in active:
                    old["superseded_by"] = correction["node_id"]
                    old["status"] = "superseded_utterance"
                    correction["corrects"].append(old["node_id"])
                active.clear()
            active.extend(asserted)
    query = _query(raw, current, {key[0] for key in groups})
    selected = []
    subjects = query.get("matched_subjects") or ([query["subject"]] if query["subject"] else [])
    for key, active in groups.items():
        if not subjects and not query["predicate"]:
            continue
        if subjects and key[0] not in subjects:
            continue
        if query["predicate"] and key[1] != query["predicate"]:
            continue
        if query["time"] and key[2] != query["time"] and not (query["time"] == "现在" and not key[2]):
            continue
        selected.append((key, active))
    reasons = []
    if not query["subject"] and len({k[0] for k, _ in selected}) > 1:
        reasons.append("ambiguous_subject")
    if not query["time"] and len({k[2] for k, _ in selected}) > 1:
        reasons.append("ambiguous_time")
    if query["time"] and any(not k[2] for k, _ in selected):
        reasons.append("time_not_recorded")
    if not selected:
        reasons.append("no_structured_relation")
    if len(selected) > max_groups:
        reasons.append("context_limit")
    # Selection is about the question, not a global 'latest fact wins' rule.
    selected = selected[-max_groups:]
    contexts, referenced = [], set()
    for key, active in selected:
        related = [n for n in nodes if (n["subject"], n["predicate"], n["time"]) == key]
        status = "reported" if len({n["value"] for n in active}) == 1 else "conflict" if active else "unknown"
        if status == "conflict":
            reasons.append("unresolved_conflict")
        # Never hide live conflicting values behind a clipped history list.
        current_nodes = [n for n in related if n["superseded_by"] is None]
        old_nodes = [n for n in related if n["superseded_by"] is not None]
        visible = old_nodes[-4:] + current_nodes[-8:]
        values = sorted({n["value"] for n in active})
        if len(current_nodes) > 8 or len(old_nodes) > 4:
            reasons.append("claim_limit")
        if len(values) > 8:
            status = "unknown"
            values = []
        referenced.update(n["source_id"] for n in visible)
        visible = [dict(n, corrects=n["corrects"][-8:], corrects_total=len(n["corrects"]),
                        corrects_clipped=len(n["corrects"]) > 8) for n in visible]
        contexts.append({"subject": key[0], "predicate": key[1], "time": key[2], "status": status,
                         "reported_values": values, "claims": visible})
    context = {"schema": 1, "version": VERSION, "kind": "engineered_relation_memory",
               "query": query, "groups": contexts, "unresolved_reasons": sorted(set(reasons)),
               "assertion_status": "utterance_not_verified_world_fact",
               "rule_learned_from_experience": False, "development_credit": 0}
    sources = [s for sid, s in source_map.items() if sid in referenced and not sid.startswith("current:")][-8:]
    return context, sources


def literal_evidence(context):
    return [n["evidence"] for group in (context or {}).get("groups", []) for n in group["claims"]]
