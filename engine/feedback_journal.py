"""External opinions saved separately from autobiographical dialogue memory."""
import hashlib
import json
from pathlib import Path


def append(path, *, raw, origin, turn, attempts, final_accepted):
    reviews = [a for a in attempts if a.get("content_review")]
    if not reviews:
        return None
    record = {"schema": 1, "kind": "content_review_opinion", "turn": turn,
              "input_sha256": hashlib.sha256(raw.encode()).hexdigest(),
              "input_origin": origin, "attempts": reviews, "final_accepted": final_accepted,
              "independent_semantic_review_verified": False, "development_credit": 0}
    record["event_id"] = hashlib.sha256(json.dumps(record, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record["event_id"]
