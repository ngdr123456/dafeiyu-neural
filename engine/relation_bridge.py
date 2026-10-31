"""Occurrence feedback and conservative use of consolidated relation memory."""
import re


class RelationBridge:
    def __init__(self, learner):
        self.learner = learner

    def apply(self, raw, parsed, api, *, visible, observer, turn, topic_id=None, input_origin=None):
        marker = "blame_external"
        if marker not in visible:
            return None
        spans = sorted({(m.start(), m.end())
                        for p in self.learner.rules[marker]["patterns"]
                        for m in re.finditer(re.escape(p), raw)})
        if not spans:
            return None
        before = {span: self.learner.predict(raw, *span, marker, visible) for span in spans}
        feedback = []
        if api and api.ok:
            for item in getattr(api, "relations", []):
                span = (item["start"], item["end"])
                if item["id"] != marker or span not in before:
                    continue
                feedback.append(self.learner.observe(
                    raw, *span, marker, visible, item["role"],
                    source="external_reviewer", observer=observer, turn=turn, topic_id=topic_id, input_origin=input_origin))
        # Re-read after feedback: a current contradiction must withdraw an old
        # rule before it can affect this very turn, not just the next one.
        after = {span: self.learner.predict(raw, *span, marker, visible) for span in spans}
        suppress = (marker in parsed.markers
                    and all(p["role"] in {"NEGATED", "PROHIBITED", "QUOTED"} for p in after.values())
                    and not (api and api.ok and marker in api.markers))
        if suppress:
            parsed.markers = [m for m in parsed.markers if m != marker]
            parsed.hits = [h for h in parsed.hits if h.id != marker]
            parsed.underdetermined = not parsed.markers
        return {"schema": 1, "marker": marker, "suppressed": suppress,
                "occurrences": [{"span": list(span), "evidence": raw[slice(*span)],
                                 "before": before[span]["role"], "after": after[span]["role"],
                                 "before_execution": before[span].get("execution"),
                                 "after_execution": after[span].get("execution")}
                                for span in spans],
                "feedback": feedback, "development_credit": 0}
