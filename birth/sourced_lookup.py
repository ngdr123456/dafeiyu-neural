"""按可信结构主题精确读取带来源的记录。"""

from __future__ import annotations


def for_topic(items, metadata, *, topic, origins=None, require_complete=True):
    """返回主题完全相同、来源可用的记录及其元数据。"""
    try:
        if not isinstance(topic, str) or not topic:
            return []
        if not isinstance(metadata, list) or len(metadata) != len(items):
            return []
        result = []
        for item, meta in zip(items, metadata):
            if not isinstance(meta, dict):
                continue
            origin = meta.get("origin")
            if not isinstance(origin, str) or not origin.strip():
                continue
            if origins is not None and origin not in origins:
                continue
            if (meta.get("subject_credible") is not True
                    or meta.get("subject") != topic or "subject_degraded" in meta
                    or "subject_truncated" in meta):
                continue
            if require_complete and meta.get("truncated"):
                continue
            result.append((item, meta))
        return result
    except Exception:
        return []


def single_for_topic(items, metadata, *, topic, origins=None, require_complete=True):
    matches = for_topic(items, metadata, topic=topic, origins=origins,
                        require_complete=require_complete)
    return matches[0] if len(matches) == 1 else None
