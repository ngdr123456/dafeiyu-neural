"""Input authorship declarations, distinct from semantic feedback authorship."""
import copy
import hashlib


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def training_origin(item, text, *, generated=False, model=None, fallback=False):
    source = item.get("source", "unknown")
    kind = ("tutor_generated" if generated else
            {"hand_corpus": "project_corpus", "topic_stem": "project_topic",
             "synth": "model_generated"}.get(source, "unknown"))
    return {"schema": 1, "kind": kind, "seed_source": source,
            "seed_sha256": digest(item["text"]), "input_sha256": digest(text),
            "topic_id": item.get("topic_id"),
            "topic_basis": "seed_library_id" if item.get("topic_id") else "unknown",
            "seed_authorship": "not_independently_verified",
            "generator": model if kind in {"tutor_generated", "model_generated"} else None,
            "tutor_fallback": fallback, "independent_human_input_verified": False}


def normalize(origin, raw, topic_id):
    if origin is None:
        return {"schema": 1, "kind": "unknown", "input_sha256": digest(raw),
                "topic_id": topic_id, "independent_human_input_verified": False}
    result = copy.deepcopy(origin)
    if result.get("schema") != 1 or result.get("input_sha256") != digest(raw):
        raise ValueError("Input provenance schema/hash mismatch")
    if result.get("topic_id") != topic_id:
        raise ValueError("Input provenance topic mismatch")
    return result
