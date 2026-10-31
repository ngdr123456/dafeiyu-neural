"""Evidence-bound adaptive work order. Replanning never awards development.

The executor still has to implement and verify the selected task. This selects
work; it is not an arbitrary-code executor or a consciousness certificate.
"""
import hashlib
import json
from pathlib import Path

REGISTRY = "spec/最终行动方案_20261007.json"
REGRESSION = "spec/有界目标承诺回归_20261008.json"
LIVE = "spec/有界目标承诺真实诊断_20261008.json"
FOUNDATION = "spec/有界目标承诺关系基础复验_20261008.json"
ORGANISATION = "spec/有界目标承诺组织复验_20261008.json"
SELF_ACTION = "spec/有界目标承诺作答复验_20261008.json"
SELF_GOAL = "spec/有界目标承诺验收_20261008.json"
SELF_GOAL_LIVE = "spec/有界目标承诺模型诊断_20261008.json"


def source_hashes(root):
    root = Path(root)
    files = []
    # ★ 用户裁定 2026-10-28（方案丙）：**不绑 tests/ 与 tools/**
    #   运行时行为只取决于 engine/ 与 rules/、corpus/。
    #   tests/ 与 tools/ 是验证基础设施 —— 把它们绑进来会导致：
    #     ① 为验证写的临时脚本，让它要验证的那次结果作废（当天犯了 3 次）
    #     ② 改一行 tests/ 也要重跑约 25 分钟的 LIVE
    #   ⚠️ 代价：改验证工具不再使证据失效，但可能改变"验证的严格程度"
    #      ⇒ 纪律：**改 tests/ 或 tools/ 时，手动重跑相关证据。**
    for directory in ("engine",):
        files.extend((root / directory).glob("*.py"))
    files.extend((root / "state").glob("*.py"))
    for directory in ("rules", "corpus"):
        files.extend(p for p in (root / directory).rglob("*") if p.is_file())
    if (root / REGISTRY).exists():
        files.append(root / REGISTRY)
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(files)}


def choose(signals):
    """Priority may move backwards on counterevidence, never on desire to pass."""
    if not signals["regression_fresh_pass"]:
        return {"id": "REPAIR_BASELINE", "title": "先修复或重验当前版本的基线",
                "reason": "回归失败、证据缺失或代码已变化；旧通过不能为新版本背书"}
    if signals.get("training_run_failed"):
        return {"id": "REPAIR_TRAINING", "title": "先处理并复验最新正式训练的中断",
                "reason": "最新正式批次失败；隔离案例通过不能覆盖实际训练中断"}
    if signals.get("unresolved_content_failures"):
        return {"id": "REPAIR_CONTENT", "title": "先定位最新事实或话题失败，再恢复小批诊断",
                "reason": "实际反馈仍有未放行轮次，不用扩大训练量掩盖失败"}
    if not signals.get("live_fresh_pass"):
        return {"id": "LIVE_DIAGNOSIS", "title": "进行联系人、更正、重启及反例的小批真实诊断",
                "reason": "隔离测试只证明接线，需要当前版本的实际模型结果"}
    if signals.get("structure_counterevidence"):
        return {"id": "REFUTE_STRUCTURE", "title": "处理组织候选的反例，保留旧能力后重新提出候选",
                "reason": "整份候选出现反证，原候选不能发布；新拟合必须重新冻结和验证"}
    if not signals.get("causal_organisation_verified"):
        if signals.get("relational_foundation_fresh_pass"):
            if signals.get("organisation_rule_execution_fresh_pass"):
                if signals.get("self_action_revision_fresh_pass"):
                    if signals.get("declared_goal_process_fresh_pass"):
                        return {"id": "GOAL_RULE_INTEGRATION", "title": "把目标操作失配接到可验证组织规则及跨维度影响",
                                "reason": "有界目标选择、承诺接续及逐字结果已验收；一般目标生成、语义兑现和共同组织仍缺"}
                    return {"id": "SELF_GOAL_ORGANISATION", "title": "从程序作答任务推进主体目标的选择、承诺与结果验证",
                            "reason": "自己的作答失败已能改变后续尝试；目标仍为工程责任，语义兑现和跨维度组织尚缺证据"}
                return {"id": "SELF_ACTION_OUTCOME", "title": "接齐自身目标、实际动作、期待和结果，再验证组织影响",
                        "reason": "有界语言规则执行已验收；生成语义动作、主体目标及跨维度整合仍缺证据"}
            return {"id": "STRUCTURE_RULE_LEARNING", "title": "把失配接到组织规则的形成、修改、淘汰与后续验证",
                    "reason": "关系记忆的工程作用已验证；仍需系统自己改变支配关系的规则，保留旧能力"}
        return {"id": "STRUCTURE_CAUSAL", "title": "实现并验证经历到可执行组织改变的因果链",
                # ⚠️ 原措辞是「记忆和校验**已接通**」—— 而这一支被选中恰好因为
                #    `relational_foundation_fresh_pass` 为假。自相矛盾。
                #    且该信号为假多数时候是**证据过期**（见 stale_evidence），
                #    不是"没接上"。改成不预判状态的写法。
                "reason": "关系记忆的当前版本尚未重验（或未接通）；"
                          "本步要做的是经历 → 组织改变 → 迁移与旧能力保留的因果链"}
    if not signals.get("joint_development_verified"):
        return {"id": "JOINT_DEVELOPMENT", "title": "验证组织对理解、自我克制、人际连续性和意义取向的共同影响",
                "reason": "单一语言分类或习惯改进不能替代人格整体的发展"}
    return {"id": "LONGITUDINAL_VALIDATION", "title": "扩展长期反例、独立复核及发展测量",
            "reason": "保留共同组织的证据，扩大场景时持续检查失效与旧能力丢失"}


def _read(path, default):
    return json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else default


def snapshot(root):
    root = Path(root)
    registry = _read(root / REGISTRY, {})
    if registry.get("schema") != 1:
        raise ValueError("Missing/unknown action plan registry")
    current = source_hashes(root)
    regression = _read(root / REGRESSION, {})
    live = _read(root / LIVE, {})
    foundation = _read(root / FOUNDATION, {})
    organisation = _read(root / ORGANISATION, {})
    own = _read(root / SELF_ACTION, {})
    goal = _read(root / SELF_GOAL, {})
    goal_live = _read(root / SELF_GOAL_LIVE, {})
    training = _read(root / "state/train/progress.json", {})
    failures, feedback_ids, rejected = [], [], []
    for directory in (root / "state/train", root / "state"):
        journal = directory / "feedback.jsonl"
        if journal.exists():
            latest_outcomes = {}
            for line in journal.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                event = json.loads(line)
                if event.get("schema") != 1 or "final_accepted" not in event:
                    raise ValueError("Invalid feedback journal event")
                feedback_ids.append(event["event_id"])
                origin = event.get("input_origin") or {}
                key = (event["input_sha256"], origin.get("kind"), origin.get("run_id"), origin.get("session_id"))
                latest_outcomes[key] = event
            failures.extend(event["event_id"] for event in latest_outcomes.values()
                            if not event["final_accepted"])
        rules = directory / "relation_rules.json"
        if rules.exists():
            from structure_evidence import report
            for candidate in report(_read(rules, {})).get("organisation_candidates", []):
                if candidate["status"] == "rejected":
                    rejected.append(candidate["fingerprint"])
    # ★ 证据过期清单（用户裁定 2026-10-28「按 (乙)」）
    #   这四个文件 passed=True，但它们的 source_hashes 绑定 170 个源码文件。
    #   代码一改，它们就永远对不上，而**没有生成器** ⇒ 无法续期。
    #   ⇒ 判 False **是对的**（我们确实没有当前代码的证据），
    #      问题不是判据，是**缺续期手段**。
    #   ⇒ 所以单独列出来，**不改优先级顺序**（风险最小）。
    _stale = []
    for _label, _p in (("关系基础", FOUNDATION), ("组织规则执行", ORGANISATION),
                       ("自身动作修订", SELF_ACTION), ("声明目标流程", SELF_GOAL)):
        _d = _read(root / _p, {})
        if _d.get("passed") is True and _d.get("source_hashes") != current:
            _stale.append({"signal": _label, "file": _p,
                           "note": "验过（10-08 代码），但证据绑定 170 个源码文件；"
                                   "代码已改 ⇒ 对当前版本无证据；无生成器 ⇒ 无法续期"})
    signals = {
        "stale_evidence": _stale,
        "regression_fresh_pass": bool(regression.get("all_checks_passed") and
                                      regression.get("source_hashes") == current),
        "live_fresh_pass": bool(live.get("passed") and live.get("source_hashes") == current),
        "training_run_failed": bool(training.get("failure") and training.get("failure") != "user_stopped"),
        "latest_training_run": training.get("run_id"),
        "unresolved_content_failures": sorted(set(failures)),
        "structure_counterevidence": sorted(set(rejected)),
        "relational_foundation_fresh_pass": bool(
            foundation.get("schema") == 1 and foundation.get("passed") is True
            and foundation.get("source_hashes") == current
            and foundation.get("rule_origin") == "engineered"
            and foundation.get("learned_rule_change") is False
            and len(foundation.get("cases", [])) == 3
            and all(case.get("passed") is True and case.get("ablation_loses_selected_relation") is True
                    and case.get("unaffected_object_retained") is True and case.get("restart_equal") is True
                    for case in foundation.get("cases", []))),
        "organisation_rule_execution_fresh_pass": bool(
            organisation.get("schema") == 1 and organisation.get("passed") is True
            and organisation.get("source_hashes") == current
            and organisation.get("scope") == "bounded_linguistic_rule_execution"
            and organisation.get("feedback_origin") == "declared_engineered_fixture"
            and organisation.get("causal_pipeline_contrast") is True
            and organisation.get("restart_equal") is True
            and organisation.get("same_turn_withdrawal") is True
            and organisation.get("old_context_retained") is True
            and organisation.get("formation_validation_disjoint") is True
            and organisation.get("development_credit") == 0),
        "self_action_revision_fresh_pass": bool(
            own.get("schema") == 1 and own.get("passed") is True
            and own.get("source_hashes") == current and own.get("scope") == "bounded_own_response_revision"
            and own.get("goal_origin") == "engineered_dialogue_obligation"
            and own.get("real_API") is False and own.get("development_credit") == 0
            and {case.get("case") for case in own.get("cases", [])} == {
                "identical_history_enable_disable", "restart_resumes_committed_failure",
                "permission_not_semantic_fulfillment", "fresh_second_review_can_reconsider", "changed_evidence_reopens"}
            and all(case.get("passed") is True for case in own.get("cases", []))),
        "declared_goal_process_fresh_pass": bool(
            goal.get("schema") == 1 and goal.get("passed") is True
            and goal.get("source_hashes") == current and goal.get("scope") == "source_bound_declared_goal_commitments"
            and goal.get("goal_origin") == "model_declared_bounded_task"
            and goal.get("selection_origin") == "declared_engineered_selection_and_review"
            and goal.get("real_API") is False and goal.get("development_credit") == 0
            and {c.get("case") for c in goal.get("cases", [])} == {
                "identical_history_goal_ablation", "paraphrase_resume", "source_change_reconsider",
                "conflict_complete_quotes", "decline_retires_pending", "literal_outcome_not_semantic_fit", "other_object_preserved"}
            and all(c.get("passed") is True for c in goal.get("cases", []))
            and goal_live.get("source_hashes") == current and goal_live.get("passed") is True
            and goal_live.get("real_API") is True and goal_live.get("goal_origin") == "model_declared_bounded_task"
            and {c.get("case") for c in goal_live.get("cases", [])} == {
                "actual_relation_seed", "actual_choice_with_injected_candidate_failure", "actual_paraphrase_resume",
                "actual_source_change_reconsider", "actual_conflict_quotes_complete"}
            and all(c.get("passed") is True for c in goal_live.get("cases", []))
            # ★ 没有 unstable 才算通过（两次一致才算数）
            and not (goal_live.get("unstable_cases") or [])),
        # No current mechanism verifies these. Do not infer them from counts,
        # stage names, model ratings, or someone writing 'verified' in a file.
        "causal_organisation_verified": False, "joint_development_verified": False}
    # ★ 用户裁定 2026-10-28：**抽样不稳 ≠ 系统缺陷**
    #   实证：同模型、同 temperature=0、同输入，连跑两遍
    #         第 1 遍 actual_source_change_reconsider 过、第 2 遍不过
    #   ⇒ 单次 live 失败不能证明系统有缺陷
    #   ⇒ unstable 的 case **不进 unresolved_content_failures**，
    #      但**单独可见**（下面的 live_unstable_cases），不静默丢弃
    # unstable 由**聚合层** verify_self_goal_live.py 写入 LIVE
    # （它把整套 4 个部分跑两遍后逐项比对 —— 覆盖全部 part，
    #   而不是只覆盖 trial_self_goal 一个）
    signals["live_unstable_cases"] = list(live.get("unstable_cases") or [])
    if live.get("source_hashes") == current and live.get("passed") is False:
        signals["unresolved_content_failures"].extend(
            "live:" + case["case"] for case in live.get("cases", [])
            if case.get("passed") is False and not case.get("unstable"))
    action = choose(signals)
    issues = []
    for issue in registry["issues"]:
        item = dict(issue)
        item["current_status"] = ("工程回归已验证，剩余问题见验收边界" if
                                  issue.get("engineering_repair") and signals["regression_fresh_pass"]
                                  else "待验证" if issue.get("engineering_repair") else "仍需实现或研究")
        issues.append(item)
    return {"schema": 1, "objective": registry["objective"], "signals": signals,
            "next_action": action, "issues": issues,
            "feedback_event_ids": sorted(set(feedback_ids)),
            "rejected_candidates": sorted(set(rejected)), "source_hashes": current,
            "development_credit": 0, "goal_achieved": False,
            "policy": "counterevidence_can_reopen_work_no_monotonic_success_claim"}


def write_report(root):
    result = snapshot(root)
    from behavior_learning import atomic_json
    atomic_json(Path(root) / "spec/当前行动方案.json", result)
    return result
