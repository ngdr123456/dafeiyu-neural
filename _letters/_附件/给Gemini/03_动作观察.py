"""Distinguish planned action from observable final speech. No label guessing."""
import re


def observe(text, planned, mode, goal_result=None):
    """`goal_result` 是本轮"有界目标"的核对结果（可选）。

    ★ 2026-10-28：大脑路径原来除纯问句外全 UNCLASSIFIED，于是
      `pipeline.py` 把 behavior 写成 UNCLASSIFIED，经验层一条事件都产生不了。
      但"逐字引用了指定来源"这件事**是本地核对过的**（self_goal.py 在比对
      evidence 是否逐字出现在输出里）—— 那不是猜语义，是核对字面。
      ⇒ 它应当被当成一个**已确认的动作**，而不是 UNCLASSIFIED。
    """
    text = (text or "").strip()
    if mode == "template":
        actual, basis, confirmed = planned, "existing_template_realized", True
    elif text == "（本轮不作回应，仅记录。）":
        actual, basis, confirmed = "SILENCE", "literal_silence_token", True
    elif text.endswith(("？", "?")) and not re.search(r"[。！!？?]", text[:-1]):
        actual, basis, confirmed = "QUESTION", "one_literal_question_not_detail_classification", True
    elif isinstance(goal_result, dict) and goal_result.get("state") == "FULFILLED_LITERAL":
        # 逐字操作已核对：这是可本地验证的事实，不是语义猜测。
        actual = "QUOTE_SOURCE_SET_CONFIRMED"
        basis = "literal_goal_predicate_matched"
        confirmed = True
    else:
        actual, basis, confirmed = "UNCLASSIFIED", "generated_semantics_not_confirmed", False
    return {"schema": 1, "planned": planned, "actual": actual,
            "mode": mode, "basis": basis, "confirmed": confirmed}


def learning_action(row):
    observation = row.get("action_observation")
    if observation is None:
        return row.get("behavior", "")  # historical, uncertified labels kept for compatibility
    return observation["actual"] if observation.get("confirmed") else None
