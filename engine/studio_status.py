"""Read-only UI adapter: generic rule memories, no Pipeline construction."""
import json
from pathlib import Path


def development_path(root):
    state = Path(root) / "state"
    canonical = state / "devlevel_verified.json"
    legacy = state / "devlevel.json"
    # A display projection must never silently replace a missing canonical.
    if canonical.exists():
        return canonical
    if legacy.exists():
        try:
            data = json.loads(legacy.read_text(encoding="utf-8"))
            if data.get("display_projection"):
                return canonical
        except (ValueError, OSError):
            pass
    return legacy


def learning_line(root):
    labels = {"realization_fallback_habits_not_development": "动作回退",
              "proposition_relation_habits_not_stage_development": "语言关系"}
    groups, errors = [], []
    for directory in (Path(root) / "state", Path(root) / "state/train"):
        for path in sorted(directory.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                if path.name.endswith("_rules.json"):
                    errors.append(path.name + "读取失败")
                continue
            if not isinstance(data, dict) or not isinstance(data.get("rules"), dict) or not isinstance(data.get("events"), list):
                continue
            rules = list(data["rules"].values())
            if any(not isinstance(r, dict) for r in rules + data["events"]):
                errors.append(path.name + "格式错误")
                continue
            active = sum(r.get("status") == "active" for r in rules)
            candidate = sum(r.get("status") == "candidate" for r in rules)
            retired = sum(e.get("kind") == "retired" for e in data["events"])
            groups.append("%s：固化%d/候选%d/退出%d" %
                          (labels.get(data.get("kind"), path.stem), active, candidate, retired))
            runtime = data.get("organisation_runtime")
            if runtime:
                versions = runtime.get("versions", [])
                if runtime.get("schema") != 1 or any(not isinstance(v, dict) for v in versions):
                    errors.append(path.name + "组织执行记录格式错误")
                else:
                    groups.append("组织执行版本（保存状态）：启用%d/候选%d/撤回%d" %
                                  tuple(sum(v.get("status") == status for v in versions)
                                        for status in ("active", "candidate", "withdrawn")))
    own = []
    for directory in (Path(root) / "state", Path(root) / "state/train"):
        path = directory / "ledger.jsonl"
        if not path.exists():
            continue
        latest = None
        latest_goal = None
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                if not row.get("void") and row.get("self_action"):
                    latest = row["self_action"]
                    goal = latest.get("goal_selection") or {}
                    if isinstance(goal, dict) and (goal.get("selected") or goal.get("retired_ids")):
                        latest_goal = goal
            if latest:
                status = {"PERMITTED": "闸门放行", "WITHHELD": "候选未放行",
                          "TEMPLATE_ONLY": "模板操作"}.get(latest.get("procedure_status"), "操作待核对")
                own.append("自身作答（保存状态）：%s／语义结果待核验" % status)
            if latest_goal:
                phase = (latest_goal.get("result") or {}).get("state")
                label = {"FULFILLED_LITERAL": "逐字操作已核对", "PENDING": "承诺待兑现",
                         "NOT_SELECTED": "已退出相关未决目标"}.get(phase, "操作待核对")
                own.append("最近有界目标（保存状态）：%s／语义结果待核验" % label)
        except (OSError, ValueError, AttributeError):
            errors.append("自身作答记录读取失败")
    return "\n学习规则（不计作阶段升级）\n" + ("\n".join(groups + own + errors) or "尚无经历规则")
