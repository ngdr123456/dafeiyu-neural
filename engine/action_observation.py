"""Distinguish planned action from observable final speech. No label guessing.

★ 2026-10-28（改动 ③，用户已批）：三个动作原来被误判成 `UNCLASSIFIED`，
  于是训练里 83% 的轮次"说不清做了什么"、经验层学不到东西。
  实测（Gemini 第三封发现 1，我逐条核对过）：

    · `QUESTION` 原判据要求"全文不许有句号"，
      于是「我没说听天由命。你眼下那堆烂摊子，是什么？」这种**先接半句再发问**
      的真追问被踢进 `UNCLASSIFIED` —— 那 13 条误命中里 5 条是这类。
    · `REPORT_OWN_STATE`（「我不知道那半个钟头你在等什么」「我这边没有能翻出来的东西」）
      是弗兰克尔式"我自成一派"的典范，但没有分支 ⇒ 全落 `UNCLASSIFIED`（6 条）。
    · `ACKNOWLEDGE`（≤20 字、引号外没有抄他的实词）也没有分支（2 条并置仍归 UNCLASSIFIED）。

  ⇒ 这三条都是**纯字面/结构**可判的，判了不会变成"猜语义"。
"""
import re

#: 沉默的唯一字面记号（与 behaviors.json 的 SILENCE 模板一致）
SILENCE_TOKEN = "（本轮不作回应，仅记录。）"

#: 自身状态词（第一人称 + 边界声明）。取自实测里那 6 条真·REPORT_OWN_STATE 的原话。
_OWN_STATE = ("我这边", "我这里", "我这儿", "我没有", "我只能", "我刚想说",
              "我不知道", "我答不了", "我不替你", "我分不了", "我给不了",
              "我看不到", "我读不到", "我说不准", "我不动", "我这边没有")

#: 问句放宽后的长度上限：两句式追问实测最长 45 字左右，留余量到 60。
_Q_MAX = 60

_QUOTE_RE = re.compile(r"[「『\"“][^」』\"”]*[」』\"”]")

#: 引文命中时可以剥掉的句首字（第一/第二人称代词 + 连接虚词）
_LEAD_STRIP = re.compile(r"^[我你他她它也又还就都只那这]+")


def quote_hit(q: str, out: str) -> bool:
    """单段引文是否命中。**纯字面剥壳，零语义猜测。**

    ★ 2026-10-29（C5，Gemini 批复第一节；我实测验证）：
      原版只做 `q in out`，于是这几条被误算成"只命中一段"：

        行 124  quotes 有「**我**腿都软了」，她输出的是「**你**腿都软了」
                —— 对用户说话时人称自然转换，只剥掉句首那个"我"
        行  43  quotes 有「他已经走了，**再也回不来了**」
                —— 她引的是后半句
        行 135  quotes 有「我**又**怕他知道」，她引的是「怕他知道」

      ⇒ 两条剥壳规则：
        ① 剥句首人称代词/虚词后 ≥3 字命中即算
        ② 原引文含逗号分句时，任一 ≥4 字分句（同样剥壳后）命中即算

      **实测：STRONG 从 5/16 升到 8/16**（升的是行 43、124、135）。
      ⚠️ Gemini 估的是 9/16，多估了行 88 —— 实测行 88 仍是 1/2：
         它的 quotes 是 ['你别真不盯啊', '不知道拿它怎么办了']，
         而她的输出只用了前一段（后一段没引）。**如实报，不凑数。**

      ⚠️⚠️ **Gemini 的规则 ①（剥句首后 ≥3 字）我删掉了**（2026-10-29 实测：
         16 条真实输出上，"有 ①"与"没有 ①"的 STRONG 都是 **8/16** ⇒ 零贡献。
         原因：凡 ① 能命中的，② 的分句规则也命中 ——
         无标点的引文会被 ② 当成整段分句处理。
         留着它既是死代码，也让变异测试抓不到东西（实测：删掉 ① 无用例失败）。
         ⇒ 只保留 ②。**少一条规则，少一处能被误读成"守卫"的死代码。**
    """
    if not q or not out:
        return False
    if q in out:
        return True
    for sub in re.split(r"[，。；、]", q):
        sc = _LEAD_STRIP.sub("", sub).strip()
        if len(sc) >= 4 and sc in out:
            return True
    return False


def thought_level(out: str, quotes) -> tuple[str, list[str]]:
    """核对"她有没有执行这条思考"。返回 (级别, 命中的引文)。

    三级（用户与 Gemini 已批）：
      · `STRONG` —— 两段引文都命中 ⇒ 她真的把那两处拉扯都摆出来了
      · `WEAK`   —— 只命中一段   ⇒ 用了碎片，没做并置（**不 confirmed**）
      · `""`     —— 一段都没中   ⇒ 未执行

    ⚠️ `WEAK` **不 confirmed**：实测行 2 只问了「随便」、漏了「把最该说的话咽下去」，
       那和行 102 那种两段并置**不该同等对待** —— 否则经验层会把"只抓了碎片"
       也记成一次成功的思考。
    """
    qs = [q for q in (quotes or ()) if q]
    if not qs or not out:
        return "", []
    hits = [q for q in qs if quote_hit(q, out)]
    if len(hits) >= 2:
        return "STRONG", hits
    if hits:
        return "WEAK", hits
    return "", []


def _outside_quotes(text: str) -> str:
    return _QUOTE_RE.sub("", text or "")


def _lcs(a: str, b: str) -> int:
    """最长公共子串长度（a、b 都很短，朴素 DP 足够）。"""
    if not a or not b:
        return 0
    best = 0
    prev = [0] * (len(b) + 1)
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        for j in range(1, len(b) + 1):
            if a[i - 1] == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
        prev = cur
    return best


def _is_question(text: str) -> bool:
    """★ 放宽后的问句判据（改动 ③）。

    旧：`endswith(("？","?"))` 且**全文**不含 `。！!？?`（除了结尾那个）
        ⇒ 两句式追问被误杀。
    新：以问号结尾，且总长 ≤ 60 字。
        ⇒ 「我没说听天由命。你眼下那堆烂摊子，是什么？」现在算 QUESTION。
    ⚠️ 仍然只认"以问号结尾"——不靠任何疑问词表，所以不会把陈述句误判成问句。
    """
    if not text.endswith(("？", "?")):
        return False
    return len(text) <= _Q_MAX


def _is_own_state(text: str) -> bool:
    """★ `REPORT_OWN_STATE`：明确在说**我自己**的边界/状态。

    判据：含自身状态词，且**不是**在问句里（问句已在上一个分支拦掉）。
    """
    return any(w in text for w in _OWN_STATE)


def _is_acknowledge(text: str, raw: str) -> bool:
    """★ `ACKNOWLEDGE`：极短的一句话承认，**而且引号里得是他真说过的字**。

    判据：
      ① 总长 ≤ 20 字，且**引号外** ≤ 15 字
      ② 不是问句
      ③ **必须带一处引号，且引号内的字逐字出现在用户原话里**
      ④ 剥掉引号后，与用户原话的最长公共子串 **< 4 字**

    ⚠️ ③ 是我在实测之后**收紧**的，依据如下：
       原本（Gemini 建议）允许"无引号 + 4-gram 重合 = 0"。
       但实测发现那条判据**方向是反的**：

           「你爸一定又骂你了，你从小就怕他。」（纯编造，16 字）
             raw = 「我爸昨天来了。」
             · 长度 ≤20 ✓  · 无问号 ✓  · 最长公共子串 = 1 字 < 4 ✓
           ⇒ **编造恰好满足"重合低"**，被误判成"承认"。

       根本原因：「干净承认」和「纯编造」在"与原话重合多少"这个维度上**同向**，
       都是"低"。所以重合度**不能**用来区分它们。

       而 ③ 是**可本地核对的**：引号里那几个字必须真的在用户原话里
       （与 `self_goal.literal_check` 同一套办法）。
       ⇒ 代价是覆盖率变低（无引号的短承认不算确认），
         但这项目里"不许编"优先于覆盖率。

    ⚠️ 为什么不许"无引号的承认"：短句也可能整句是编的（上面那个例子就是），
       而在看不到语义的条件下，我没有任何本地依据区分它和真承认。
       ⇒ 宁可记 UNCLASSIFIED（诚实），也不记一个可能是假的"确认"。
    """
    if not raw:
        return False
    inner = _outside_quotes(text)
    if "？" in text or "?" in text:
        return False
    if len(text) > 20 or len(inner) > 15:
        return False
    # ③ 引号内的字必须逐字出现在用户原话里。
    #    ⚠️ 这一步**同时**承担了"必须带引号"的职责：没有引号 ⇒ segs 为空 ⇒ 判否。
    #       （原来另写了一条 `if "「" not in text` 的硬要求，变异测试证明删掉它
    #         不会有任何用例失败 —— 那是死代码，已删，免得留下一个假的守卫。）
    quoted = _QUOTE_RE.findall(text) or re.findall(r"「([^」]*)」", text)
    segs = [re.sub(r"[「」『』\"“”]", "", q) for q in quoted]
    segs = [s for s in segs if s]
    if not segs:
        return False
    if not any(s in raw for s in segs):
        return False
    # ④ 引号外不许抄他的实词（≥4 字连续重合）
    return _lcs(inner, raw) < 4


def observe(text, planned, mode, goal_result=None, raw="", thought_quotes=(),
            focus_quotes=(), focus_origin=""):
    """`goal_result` 是本轮"有界目标"的核对结果（可选）。
    `raw` 是用户原话（可选）—— 只有 `ACKNOWLEDGE` 的重合检查需要它。
    `thought_quotes` 是跨轮思考算子层引用的两段逐字原话（可选）—— 供 C5 核对。

    ★ 2026-10-30（Gemini 拍板的**零混淆扩展**）：
      `focus_quotes` / `focus_origin` 是**本轮唯一胜出的那个焦点**的引文与来源
      （`"input" | "unfinished" | "idle" | ""`，见 `Pipeline._arbitrate_focus`）。

      ⚠️ **为什么不复用 `thought_quotes`**：
         那会把"她引了空档回想的话"混同于"她执行了当轮算子 Thought" ——
         `thought_level` 的语义是"**当轮算子**那两段有没有被说出口"，不能污染。
      ⇒ 所以**正交新增两个字段**，`thought_level` 一字不改。

    ★ 2026-10-28：大脑路径原来除纯问句外全 UNCLASSIFIED，于是
      `pipeline.py` 把 behavior 写成 UNCLASSIFIED，经验层一条事件都产生不了。
      但"逐字引用了指定来源"这件事**是本地核对过的**（self_goal.py 在比对
      evidence 是否逐字出现在输出里）—— 那不是猜语义，是核对字面。
      ⇒ 它应当被当成一个**已确认的动作**，而不是 UNCLASSIFIED。

    ★ 2026-10-28（改动 ③）：再加三条纯字面的分支（QUESTION 放宽 /
      REPORT_OWN_STATE / ACKNOWLEDGE）。它们全部只依赖输出文本、
      输出与用户原话的字面重合 —— **没有一条需要判断"她说了什么意思"**。
    """
    text = (text or "").strip()
    if mode == "template":
        actual, basis, confirmed = planned, "existing_template_realized", True
    elif text == SILENCE_TOKEN:
        actual, basis, confirmed = "SILENCE", "literal_silence_token", True
    elif thought_quotes and thought_level(text, thought_quotes)[0] == "STRONG":
        # ★ C5：她真的把那两处拉扯都摆出来了
        actual = "THOUGHT_EXECUTED_STRONG"
        basis = "both_thought_quotes_literal_present"
        confirmed = True
    elif _is_question(text):
        actual, basis, confirmed = "QUESTION", "one_literal_question_not_detail_classification", True
    elif isinstance(goal_result, dict) and goal_result.get("state") == "FULFILLED_LITERAL":
        # 逐字操作已核对：这是可本地验证的事实，不是语义猜测。
        actual = "QUOTE_SOURCE_SET_CONFIRMED"
        basis = "literal_goal_predicate_matched"
        confirmed = True
    elif _is_own_state(text):
        actual, basis, confirmed = "REPORT_OWN_STATE", "literal_own_state_word", True
    elif _is_acknowledge(text, raw):
        actual, basis, confirmed = "ACKNOWLEDGE", "short_no_unquoted_overlap_ge4", True
    else:
        actual, basis, confirmed = "UNCLASSIFIED", "generated_semantics_not_confirmed", False
    # ★ 2026-10-29（C5）：`thought_level` 记成**独立字段**，而不是 `actual` 的一个值。
    #
    #   为什么改：用户与 Gemini 原定是 `THOUGHT_EXECUTED_WEAK` 作为一个 `actual`
    #   （confirmed=False）。但实测 16 条真实输出：
    #     STRONG 8｜QUESTION 5｜REPORT_OWN_STATE 1｜UNCLASSIFIED 2
    #   ⇒ **WEAK 一次都没落** —— 因为"只用了碎片"的三种情况
    #     全都以问号结尾（行 27/54/187）或含"我答不了"（行 88），
    #     被 `QUESTION` / `REPORT_OWN_STATE` 先抓走了。
    #   ⇒ 它是个**死分支**。
    #
    #   ⇒ 但那个诊断信息有用（"她只用了碎片、没做并置"），
    #     所以改成**独立字段**：`actual` 仍是 QUESTION/REPORT_OWN_STATE（confirmed 照旧），
    #     而 `thought_level` 如实记下 STRONG / WEAK / ""。
    #   ⇒ 这样两边都不丢：动作分类不错，诊断信息也在。
    _lvl, _hits = thought_level(text, thought_quotes) if thought_quotes else ("", [])
    # ★ 2026-10-30：唯一焦点的落地率（与 `thought_level` **正交**）
    _fl, _fh = thought_level(text, focus_quotes) if focus_quotes else ("", [])
    return {"schema": 1, "planned": planned, "actual": actual,
            "mode": mode, "basis": basis, "confirmed": confirmed,
            "thought_level": _lvl, "thought_quote_hits": _hits,
            "focus_origin": focus_origin or "",
            "focus_level": _fl, "focus_quote_hits": _fh}


def learning_action(row):
    observation = row.get("action_observation")
    if observation is None:
        return row.get("behavior", "")  # historical, uncertified labels kept for compatibility
    return observation["actual"] if observation.get("confirmed") else None
