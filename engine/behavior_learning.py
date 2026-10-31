"""Bounded procedural learning from physically realized actions, not tutor scores.

E-158/159: acquire/change relations; DB sensitization: unsuccessful repetition.
ENG: 3 distinct training inputs, then 2 unseen confirmations. These are engineering
criteria for a fallback habit, not criteria for ego development. No text generation.
"""
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path


def _windows_sharing_violation(exc):
    return os.name == "nt" and getattr(exc, "winerror", None) in {5, 32}


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        # On Windows an instantaneous UI read or file scanner can deny rename.
        # Retry the identical, fsynced bytes for <= .21s; permanent denial still
        # fails explicitly. Never truncate the previous committed file.
        for attempt in range(4):
            try:
                os.replace(temporary, path)
                break
            except PermissionError as exc:
                if not _windows_sharing_violation(exc) or attempt == 3:
                    raise
                time.sleep(.03 * (2 ** attempt))
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class BehaviorLearning:
    def __init__(self, path, actions, training=3, validation=2):
        self.path = Path(path)
        self.actions = frozenset(actions)
        self.training, self.validation = training, validation
        self.data = {"schema": 1, "rules": {}, "events": [],
                     "kind": "realization_fallback_habits_not_development"}
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
            if self.data.get("schema") != 1:
                raise ValueError("Unknown behavior learning schema")

    @staticmethod
    def context(markers, offered):
        return {"markers": sorted(set(markers)), "offered": offered,
                "requires_original_realization_failure": True}

    @staticmethod
    def sid(context):
        return hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()[:24]

    def predict(self, context):
        rule = self.data["rules"].get(self.sid(context))
        if rule and rule["status"] == "active" and rule["target"] in self.actions:
            return rule["target"]
        return None

    def observe(self, context, target, raw, turn, *, persist=True):
        if context.get("offered") not in self.actions or target not in self.actions:
            raise ValueError("Learned action must belong to the existing behavior library")
        sid = self.sid(context)
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        rule = self.data["rules"].get(sid)
        kind = None
        # A fresh contradictory observation withdraws the old habit immediately.
        # No voting away contradictory evidence; retain the prior revision in events.
        if rule is not None and target != rule["target"]:
            self.data["events"].append({"kind": "retired", "sid": sid,
                                        "before": dict(rule), "case": digest, "turn": turn})
            revision = rule["revision"] + 1
            rule = None
            kind = "modified"
        else:
            revision = 1
        if rule is None:
            rule = {"context": context, "target": target, "revision": revision,
                    "status": "candidate", "training": [], "validation": []}
            self.data["rules"][sid] = rule
            kind = kind or "formed"
        if digest in rule["training"] or digest in rule["validation"]:
            return None
        if len(rule["training"]) < self.training:
            rule["training"].append(digest)
        else:
            rule["validation"].append(digest)
            if rule["status"] != "active" and len(rule["validation"]) >= self.validation:
                rule["status"] = "active"
                kind = "validated"
        self.data["events"].append({"kind": kind or "observed", "sid": sid,
                                    "revision": rule["revision"], "case": digest,
                                    "turn": turn, "target": target})
        if persist:
            atomic_json(self.path, self.data)
        return {"sid": sid, "kind": kind or "observed", "revision": rule["revision"],
                "status": rule["status"], "target": target}
