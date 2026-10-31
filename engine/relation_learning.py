"""Learn literal proposition-role relations; no stage credit or self-scoring.

E-159: relations may be acquired/changed. DB-507/553: reinforcement and
prediction error are engineering analogues, not neuronal measurements.
All labels describe linguistic roles, not the user's values or ego stage.
The module exposes an offline/intake API; it does not override MarkerEngine.
"""
import hashlib
import copy
import re
from pathlib import Path

try:
    from .behavior_learning import BehaviorLearning, atomic_json
    from .markers import load_marker_rules
except ImportError:
    from behavior_learning import BehaviorLearning, atomic_json
    from markers import load_marker_rules

ROLES = frozenset(("ASSERTED", "NEGATED", "PROHIBITED", "QUOTED", "UNKNOWN"))


class RelationLearning:
    def __init__(self, path, *, offline=False, training=3, validation=2, use_organisation=True):
        self.offline = offline
        self.use_organisation = bool(use_organisation)
        existing = Path(path).exists()
        self.learner = BehaviorLearning(path, ROLES, training, validation)
        kind = "proposition_relation_habits_not_stage_development"
        if existing and self.learner.data["kind"] != kind:
            raise ValueError("Incompatible relation memory")
        self.learner.data["kind"] = kind
        self.rules = {r["id"]: r for r in load_marker_rules()["markers"]}

    def context(self, raw, start, end, marker, visible):
        # Visibility is supplied by the existing development gate, never learned.
        if marker not in self.rules or marker not in visible:
            return None
        if not (0 <= start < end <= len(raw)):
            raise ValueError("Invalid evidence span")
        if raw[start:end] not in self.rules[marker].get("patterns", []):
            raise ValueError("Evidence must be an existing literal marker pattern")
        prefix = raw[:start]
        # Fixed observations, not fixed role conclusions: feedback teaches how
        # these observations are related. Clause punctuation is a feature only.
        cues = re.findall(r"不能说|不要说|没有说|没说|不是|并非|不|没|别", prefix)
        last = list(re.finditer(r"不能说|不要说|没有说|没说|不是|并非|不|没|别", prefix))
        suffix = prefix[last[-1].end():] if last else ""
        quote_open = prefix.count("“") > prefix.count("”") or prefix.count('"') % 2 == 1
        features = ["quoted=" + str(quote_open),
                    "cue=" + (cues[-1] if cues else "none"),
                    "punctuation_after_cue=" + str(bool(re.search(r"[，,。；;]", suffix))),
                    "turn_after_cue=" + str(any(w in suffix for w in ("但是", "但", "然而", "不过"))),
                    "sentence_end_after_cue=" + str(bool(re.search(r"[。！？!?;；\n]", suffix))),
                    "cue_distance=" + ("none" if not last else
                                        "near" if len(suffix) <= 6 else
                                        "middle" if len(suffix) <= 20 else "far")]
        return {"marker": marker, "markers": sorted(features), "offered": "UNKNOWN",
                "representation": "literal_scope_relations_v2", "offline": self.offline}

    def predict(self, raw, start, end, marker, visible):
        context = self.context(raw, start, end, marker, visible)
        if context is None:
            return {"role": "UNKNOWN", "reason": "marker_not_visible", "evidence": None}
        if self.use_organisation:
            try:
                from .organisation_runtime import select
            except ImportError:
                from organisation_runtime import select
            refined = select(self.learner.data, context, raw, start, end)
            if refined is not None:
                return dict(refined, evidence={"start": start, "end": end, "text": raw[start:end]}, context=context)
        role = self.learner.predict(context)
        return {"role": role or "UNKNOWN", "reason": "consolidated" if role else "not_validated",
                "evidence": {"start": start, "end": end, "text": raw[start:end]},
                "context": context}

    def observe(self, raw, start, end, marker, visible, role, *, source, observer, turn, topic_id=None, input_origin=None):
        if role not in ROLES:
            raise ValueError("Unknown proposition role")
        allowed = {"offline_fixture"} if self.offline else {"user_correction", "external_reviewer"}
        if source not in allowed or not observer or observer in {"self", "candidate"}:
            raise ValueError("Requires explicit external feedback; prediction is not feedback")
        context = self.context(raw, start, end, marker, visible)
        if context is None:
            return {"kind": "blocked", "reason": "marker_not_visible"}
        if role == "UNKNOWN":
            return {"kind": "undetermined", "reason": "uncertainty_is_not_confirmation_or_refutation"}
        sid = self.learner.sid(context)
        previous = self.learner.data["rules"].get(sid)
        previous_target = previous["target"] if previous else None
        successes = previous.get("confirmed", 0) if previous else 0
        failures = previous.get("contradicted", 0) if previous else 0
        expectation = (successes + 1) / (successes + failures + 2) if previous else None
        outcome = float(previous_target == role) if previous_target else None
        old_length = len(self.learner.data["events"])
        original_data = copy.deepcopy(self.learner.data)
        operational_prediction = self.predict(raw, start, end, marker, visible)
        # One atomic snapshot must contain both the changed rule and its feedback.
        # Never persist an enabled rule first and append its cause in a second write.
        result = self.learner.observe(context, role, raw, turn, persist=False)
        if result is None:
            return {"kind": "duplicate", "sid": sid}
        rule = self.learner.data["rules"][sid]
        # Contradictory feedback already retires the prior revision immediately.
        rule["confirmed"] = (successes + int(outcome == 1)) if previous_target == role else 0
        rule["contradicted"] = failures if previous_target == role else 0
        feedback = {"input_origin": copy.deepcopy(input_origin), "source": source, "observer": observer,
                    "raw_text": raw,
                    "raw_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                    "span": [start, end], "evidence": raw[start:end], "role": role,
                    "predicted_role": previous_target, "expected_correctness": expectation,
                    "observed_correctness": outcome,
                    "prediction_error": outcome - expectation if outcome is not None else None,
                    "strengthened": outcome == 1, "weakened": outcome == 0,
                    "development_credit": 0}
        if operational_prediction.get("execution"):
            feedback["organisation_operation"] = copy.deepcopy(operational_prediction["execution"])
            feedback["observed_role_agreement"] = (
                operational_prediction["role"] == role if operational_prediction["role"] != "UNKNOWN" else None)
            feedback["agreement_scope"] = "declared_reviewer_role_not_world_truth_or_subjective_reward"
        try:
            from .structure_conflict import diagnose
            from .organisation_refinement import observe_ownership
        except ImportError:
            from structure_conflict import diagnose
            from organisation_refinement import observe_ownership
        try:
            from .structure_evidence import record
        except ImportError:
            from structure_evidence import record
        try:
            feedback["organisation_observation"] = observe_ownership(raw, start)
            conflict = diagnose(original_data, sid=sid, incoming=dict(
                feedback, literal_evidence=feedback["evidence"], topic_id=topic_id))
            if conflict:
                feedback["structural_conflict"] = conflict
            for event in self.learner.data["events"][old_length:]:
                event["feedback"] = feedback
            record(self.learner.data, original_data, sid=sid, feedback=feedback,
                   topic_id=topic_id, turn=turn)
            try:
                from .organisation_runtime import synchronise
            except ImportError:
                from organisation_runtime import synchronise
            changes = synchronise(self.learner.data)
            atomic_json(self.learner.path, self.learner.data)
        except Exception:
            self.learner.data = original_data
            raise
        return dict(result, feedback=feedback, organisation_changes=changes)
