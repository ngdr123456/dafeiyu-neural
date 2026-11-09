"""上游结构化信号的契约，不是感知器；本模块不判断原始文本。"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from .types import DriveSignal, ThinContext


@dataclass(frozen=True)
class InputSignal:
    act: Literal["ask", "request", "pause", "stop", "ack", "tell", "unknown"]
    addressee: Literal["other", "self", "unclear"]
    source: str
    provenance: str
    degraded: bool = False
    reason: str = ""
    scope: Literal["conversation", "task", "unclear"] = "unclear"

    topic: str = ""
    target_open_question: str = ""
    target_commitment: str = ""
    confidence: Literal["high", "medium", "low"] = "high"
    quoted_or_negated: bool = False
    recall_self: bool = False
    recall_target: str = ""
    experience_intent: Literal["unknown", "inquiry", "fiction", "impersonation"] = "unknown"
    experience_scope: str = ""
    answer_scope: str = ""
    judgment_holder: Literal["user", "third", "unknown"] = "unknown"
    judgment_subject: str = ""
    judgment_content: str = ""
    judgment_span: str = ""
    judgment_relation: Literal["initial", "correction", "qualification", "unrelated", "consume", "unknown"] = "unknown"
    judgment_previous: str = ""
    action_report_relation: Literal["report", "correction", "supplement", "unknown"] = "unknown"
    action_report_holder: Literal["user", "third", "unknown"] = "unknown"
    action_report_asserted: bool = False
    action_report_action: str = ""
    action_report_order: int = -1
    action_report_span: str = ""
    action_report_scope: str = ""
    action_report_effect: Literal["supports", "obstructs", "unknown"] = "unknown"
    action_report_previous: str = ""

    def __post_init__(self) -> None:
        if (self.action_report_relation not in ("report", "correction", "supplement", "unknown")
                or self.action_report_holder not in ("user", "third", "unknown")
                or self.action_report_effect not in ("supports", "obstructs", "unknown")
                or type(self.action_report_order) is not int or type(self.action_report_asserted) is not bool
                or not all(isinstance(getattr(self, x), str) for x in
                           ("action_report_action", "action_report_span", "action_report_scope", "action_report_previous"))):
            raise ValueError("invalid action report")
        if (self.judgment_holder not in ("user", "third", "unknown")
                or self.judgment_relation not in ("initial", "correction", "qualification", "unrelated", "consume", "unknown")
                or not all(isinstance(getattr(self, name), str) for name in
                           ("judgment_subject", "judgment_content", "judgment_span", "judgment_previous"))):
            raise ValueError("invalid judgment interpretation")
        if self.confidence not in ("high", "medium", "low"):
            raise ValueError("invalid confidence")
        if not isinstance(self.quoted_or_negated, bool):
            raise ValueError("quoted_or_negated must be bool")
        if not isinstance(self.recall_self, bool) or not isinstance(self.recall_target, str):
            raise ValueError("invalid recall fields")
        if (self.experience_intent not in ("unknown", "inquiry", "fiction", "impersonation")
                or not isinstance(self.experience_scope, str)):
            raise ValueError("invalid experience intent fields")
        if not isinstance(self.answer_scope, str):
            raise ValueError("answer_scope must be str")
        for name in ("topic", "target_open_question", "target_commitment"):
            object.__setattr__(self, name, getattr(self, name).strip())
        if self.scope not in ("conversation", "task", "unclear"):
            raise ValueError("invalid scope")
        if self.act not in ("ask", "request", "pause", "stop", "ack", "tell", "unknown"):
            raise ValueError("invalid act")
        if self.addressee not in ("other", "self", "unclear"):
            raise ValueError("invalid addressee")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("source must not be blank")
        if not isinstance(self.provenance, str) or not self.provenance.strip():
            raise ValueError("provenance must not be blank")


def drive_signal_from_input(signal: InputSignal | None) -> DriveSignal | None:
    if signal is None or signal.degraded:
        return None
    # 对象感：只把对我说的话当缺口。
    if signal.addressee != "other":
        return None
    if signal.act == "ask":
        return DriveSignal(direction="pursue", salience="mid",
                           why=f"输入信号｜问句｜{signal.source}｜缺口在外，顺着答")
    if signal.act == "request":
        return DriveSignal(direction="pursue", salience="mid",
                           why=f"输入信号｜请求｜{signal.source}｜缺口在外，顺着接")
    if signal.act in ("pause", "stop") and signal.scope == "task":
        return DriveSignal(direction="pursue", salience="mid",
                           why=f"输入信号｜请求｜{signal.source}｜接住具体任务")
    if signal.act == "pause" and signal.scope == "conversation":
        return DriveSignal(direction="hold", salience="low",
                           why=f"输入信号｜暂停｜{signal.source}｜对方要我暂停")
    if signal.act == "stop" and signal.scope == "conversation":
        return DriveSignal(direction="hold", salience="low",
                           why=f"输入信号｜终止｜{signal.source}｜对方要终止")
    return None


def credible_topic(signal: InputSignal | None) -> str:
    if (signal is not None and not signal.degraded and signal.confidence == "high"
            and not signal.quoted_or_negated):
        return signal.topic
    return ""


def visible_judgments(context: ThinContext):
    """Exactly the bounded candidates supplied to this turn's interpreter."""
    return list(context.session_judgments[-4:])


def visible_actions(context: ThinContext):
    """Unique short questions, feedback-bound actions, and the latest action in the window."""
    from .openq_extract import extract_open_question
    if context.session_actions_overflow:
        return []
    actions = context.session_actions
    result = []
    for order, action in list(enumerate(actions))[-8:]:
        question = extract_open_question(action.text)
        if ((order == len(actions) - 1 or (question and len(action.text) <= 80)
             or effective_action_feedback(context, action.text, order))
                and action.text.strip()
                and sum(item.text == action.text for item in actions) == 1):
            result.append((order, action))
    return result


def action_feedback_by_scope(reports):
    """Group effects by their interpreted scope without merging different scopes."""
    grouped = {}
    for report in reports:
        grouped.setdefault(report.scope, set()).add(report.effect)
    return list(grouped.items())


def effective_action_feedback(context: ThinContext, action: str, order: int):
    active = []
    for item in context.action_feedback:
        if item.action != action or item.action_order != order:
            continue
        if item.relation in ("report", "supplement"):
            active.append(item)
        elif item.relation == "correction":
            for index, previous in enumerate(active):
                if previous.evidence == item.previous and previous.scope == item.scope:
                    active[index] = item
                    break
    return active


def validate_action_report(signal: InputSignal | None, text: str, context: ThinContext):
    if signal is None or signal.action_report_relation == "unknown":
        return signal
    previous = [item for item in context.action_feedback
                if item.evidence == signal.action_report_previous]
    candidates = visible_actions(context)
    valid = (not signal.degraded and signal.confidence == "high"
             and signal.action_report_holder == "user" and signal.action_report_asserted
             and signal.addressee == "other"
             and signal.action_report_effect in ("supports", "obstructs")
             and bool(signal.action_report_scope.strip()) and len(signal.action_report_scope) <= 40
             and bool(signal.action_report_span.strip()) and signal.action_report_span in text.strip()
             and len(text.strip()) <= 600 and len(signal.action_report_span) <= 600
             and all(item.evidence != text.strip() for item in context.action_feedback)
             and any(order == signal.action_report_order and action.text == signal.action_report_action
                     for order, action in candidates))
    if signal.action_report_relation == "correction":
        valid = (valid and len(previous) == 1 and previous[0].action == signal.action_report_action
                 and previous[0].action_order == signal.action_report_order
                 and previous[0].scope == signal.action_report_scope
                 and previous[0] in effective_action_feedback(context, signal.action_report_action,
                                                              signal.action_report_order))
    else:
        valid = valid and not signal.action_report_previous
    return signal if valid else replace(signal, action_report_relation="unknown", action_report_previous="",
                                        reason=signal.reason or ("no_visible_action_candidate" if not candidates
                                                                 else "invalid_action_report"))


def validate_judgment(signal: InputSignal | None, text: str, context: ThinContext):
    if signal is None or signal.judgment_relation == "unknown":
        return signal
    relation = signal.judgment_relation
    candidates = visible_judgments(context)
    previous = next((item for item in candidates if item.evidence == signal.judgment_previous), None)
    span = signal.judgment_span
    valid = (not signal.degraded and signal.confidence == "high" and bool(span.strip())
             and span in text.strip() and len(span) <= 40
             and bool(signal.judgment_subject.strip()) and len(signal.judgment_subject) <= 40
             and len(signal.judgment_content) <= 80
             and signal.judgment_holder in ("user", "third"))
    if relation == "consume":
        valid = valid and previous is not None and previous.holder == "user" and signal.judgment_holder == "user"
    else:
        valid = (valid and bool(signal.judgment_content.strip()) and len(text.strip()) <= 40
                 and "用户说：" + text.strip() not in context.facts_this_session
                 and all(entry.evidence != text.strip() for entry in context.session_judgments))
        if relation in ("correction", "qualification"):
            valid = valid and previous is not None and signal.judgment_holder == "user"
            if valid:
                effective = effective_judgment(context, previous.evidence)
                valid = bool(effective and previous in effective)
        else:
            valid = valid and not signal.judgment_previous
    return signal if valid else replace(signal, judgment_relation="unknown", judgment_previous="")


def effective_judgment(context: ThinContext, reference: str):
    """Follow validated session links; return effective content and its evidence."""
    entries = context.session_judgments
    by_evidence = {item.evidence: item for item in entries}
    if len(by_evidence) != len(entries):
        return None
    item = by_evidence.get(reference)
    if item is None:
        return None
    visited = set()
    while item.previous:
        if item.evidence in visited:
            return None
        visited.add(item.evidence)
        item = by_evidence.get(item.previous)
        if item is None:
            return None
    members = {item.evidence}
    effective = [item]
    for later in entries:
        if later.previous in members:
            members.add(later.evidence)
            if later.relation == "correction":
                effective = [later]
            elif later.relation == "qualification":
                effective.append(later)
    return effective


def credible_open_question_answer(signal: InputSignal | None) -> str:
    # Legacy direct targets are trusted only without a sentence-wide quote flag.
    # With that flag, a separately supplied speaker-answer span is required.
    if (signal is not None and not signal.degraded and signal.confidence == "high"
            and (not signal.quoted_or_negated or bool(signal.answer_scope.strip()))
            and signal.addressee == "other"):
        return signal.target_open_question
    return ""


def credible_commitment_target(signal: InputSignal | None) -> str:
    if (signal is not None and not signal.degraded and signal.confidence == "high"
            and not signal.quoted_or_negated and signal.addressee == "other"):
        return signal.target_commitment
    return ""
