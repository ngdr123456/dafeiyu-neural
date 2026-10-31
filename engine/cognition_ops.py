# -*- coding: utf-8 -*-
"""跨轮思考算子层（C3）—— 在**已校验的原话命题**上做确定性推演。

## 这一层是什么

**「理论驱动的结构化观察层」。** 把系统内部表征从「6 个浮点数 + 1 个名词」
推进到「带字面偏移担保的双引文张力命题」。

**它不是「通用思考」** —— 五个算子按固定优先级触发，
"决定哪条观察重要"那一步它做不到。这一点在 `spec/` 与注释里如实写，不包装。

## 五个算子

| 算子 | 触发 | 依据 |
|---|---|---|
| `HABITUATION_LOOP_BREAK` | 同一 `signature_key` 连续 ≥3 次 | `[D]` 耐受（同一刺激反复，反应衰减） |
| `IMMUTABLE_VS_ACTION_SPLIT` | 有 `FIXED` 且有 `ACTION` | `[M]` 不可改变的事实与可改变的态度分开 |
| `CROSS_TURN_CONTRADICTION` | 本轮 `ACTION`/`COST_FEEL` + 历史 `WANT_MUST` + **同一 subject** | `[E]` 两个相反观念并存 ⇒ 平衡化压力 |
| `WANT_VS_COST_GAP` | 机制 `WANT_NO_LIKE` + 同轮有 `WANT_MUST` 与 `COST_FEEL` | `[D]` 想要回路与喜欢回路是两回事 |
| `CONCRETE_CURIOSITY` | 前四个都不满足 | 兜底：退回单点追问 |

## 三条硬纪律

**① 一个字都不编。** `Thought.quotes` 里每一条都必须是**已通过 `_literal_claim` 的
`Claim.text`**；本模块**不生成任何原话**，只挑与拼。

**② 不诊断、不评价。** `hint` 是固定连接语（模板），主语永远不是「他怎么样」。
算子 3 特意不用「你在兜圈子」这种话，改成纯事实计数。

**③ 一次只让一个 Thought 胜出**，按"越具体、越可核对越优先"排序；
被让位的算子 ID 记在 `yielded` 里（便于事后查假阳性）。

## 会话边界

跨轮匹配**必须**在同一会话内，否则「第 11 行」和「第 104 行」会被硬凑。
`session_of()` 三级取：
  ① `input_origin.session_id`（实测 12/215 有值）
  ② `turn_id` 回退（实测 24/215）
  ③ **ts 间隔 > 120 秒视作新会话**（**是约定，不是事实** —— 调用方要如实标注）
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from cognition import usable_for_thought
from datetime import datetime

#: 核心人物词 —— 单字时**保留**（汉语里至亲天然单字）
PERSON_SINGLE = frozenset("他她爸妈哥姐弟妹妻")

#: 显式行动退缩词：`COST_FEEL` 命中这些时，**兼作 ACTION 候选**
#: （依据 Gemini 批复：`ACTION` 的缺失不是 `COST_FEEL`，但也不必为此重跑 API）
RETREAT_WORDS = re.compile(r"没开口|没去|没说|没敢|没提|忍住|删了|不敢说|不知道该干嘛|"
                           r"没做|放弃了|没回|没接|躲开")

#: 会话切分的时间间隔约定（秒）
SESSION_GAP = 120.0

#: 一次最多看多少轮历史
HISTORY_K = 6

OP_ORDER = ("HABITUATION_LOOP_BREAK", "CHAIN_EXTENSION", "DILEMMA",
            "IMMUTABLE_VS_ACTION_SPLIT",
            "CROSS_TURN_CONTRADICTION", "WANT_VS_COST_GAP",
            "IDLE_RECOMBINE", "CONCRETE_CURIOSITY")


@dataclass
class Thought:
    """一条**结构化观察**。`quotes` 全部是已校验的逐字原话。"""
    op: str
    quotes: list[str]
    hint: str
    yielded: list[str] = field(default_factory=list)
    #: 这两段引自哪里 —— `[{"turn", "start", "end", "kind", "subject"}, ...]`
    #
    #  ⚠️ 2026-10-29 实测逼出来的：离线体检时想反查"这两段出自哪轮"，
    #     用 `text` 去搜，结果同一段文本在**不同轮、不同 kind** 都出现过
    #     （`「是我选的」`在轮 72 判 FIXED、轮 152 也可能判别的），
    #     搜出 3 个匹配、`where` 比 `quotes` 长，直接 IndexError。
    #  ⇒ 所以**由产生者自己记录来源**，而不是让调用方事后按字符串反查。
    sources: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"op": self.op, "quotes": list(self.quotes),
                "hint": self.hint, "yielded": list(self.yielded),
                "sources": list(self.sources)}


def normalize_subject(s: str) -> str:
    """`subject` 归一化。

    ⚠️ **不许一刀切清空单字** —— 实测 508 条里 `subject` 单字的：
       `她` 15 次、`他` 9 次 —— 那是汉语里最核心的指向对象，
       一刀切会杀掉 24 次最该匹配的人物锚点（Gemini 的防坑提醒，我采纳）。
    ⇒ 单字若属核心人物词（他她爸妈哥姐弟妹妻）⇒ 保留；
      其余单字死物（饭／水／话／面／灯／腿…）⇒ 清空（太泛，跨轮匹配必假阳性）。
    """
    s = (s or "").strip()
    if not s:
        return ""
    if len(s) == 1:
        return s if s in PERSON_SINGLE else ""
    return s


def subject_declared(c: dict) -> bool:
    """这条 claim 是否**真的声明了一个可用的 subject**。

    ⚠️ 2026-10-29 实测踩的洞：
       `normalize_subject("鞋")` 返回 `""`（单字死物被清空），
       于是 `subject="鞋"` 的 claim 与 `subject=""` 的 claim
       **两边都成了空**，走了"都为空也允许配"那条宽路 ——
       配出「我这鞋上还沾着泥呢」+「先别说了」这种没有张力的对。

    ⇒ 判据必须区分两件事：
       · **原本就是空**（抽取时说不清对象）⇒ 可以走宽路（FIXED+ACTION 那对）
       · **归一化后才空**（原本有，但是单字死物）⇒ 不许走宽路
    """
    raw = (c.get("subject") or "").strip()
    # ★ 只看 raw：**填了**就算声明过。
    #   ⚠️ 第一版写成 `bool(raw) and bool(normalize_subject(raw))`（要求归一化后也非空），
    #      于是 `subject="鞋"`（单字死物，归一化成 ""）被判成"未声明"，
    #      和另一条"未声明"的一起走了宽路 —— 实测放出 4 条假配对
    #      （`('鞋','')`、`('水','')`、`('车','')`、`('你','')`）。
    #   ⇒ 单字死物既然归一化后为空、无法参与 subject 匹配，
    #      就**更不该**获得"都为空可以配"的宽路许可。
    return bool(raw)


def subject_compatible(c1: dict, c2: dict, *, same_session: bool = True,
                       t1: int = 0, t2: int = 0) -> bool:
    """两个 claim 的对象**是否说得通是同一件事**（兼容汉语口语的"零形回指"）。

    ★ 2026-10-29（Gemini 抓的真凶 1，我采纳并用离线数据验证）：

      实测那 12 轮里，`subject` 撞不上的原因是**汉语口语会省略宾语**：
        「到嗓子眼儿又咽回去」   subject=""
        「不敢点开」            subject=""
        「没敢说」              subject=""
        「把最该说的话咽下去」    subject=""
        「饭都不想吃」           subject=""

      而前一句/前一轮他刚说过 `subject="她"` 或 `"方案"`。
      在人脑子里这两句 100% 是同一件事 —— 但我原来要求 `subject` 全等且非空，
      `"她" != ""` ⇒ **90% 真正的同轮/跨轮张力全被字符串不等拦在门外。**

    ## 分层判据（越近越宽，越远越严）
      1. 两边都是**不同的非空实词**（且不互为子串、不是代词）⇒ **不兼容**（绝不乱凑）
      2. **同轮**（dist == 0）⇒ 兼容（同一口气说的两半句）
      3. 同会话 **≤2 轮** ⇒ 兼容（零形回指天然发生在这里）
      4. **≥3 轮**远距离 ⇒ 必须两边都有非空 subject 且匹配（严防翻远年旧账）

    ⚠️ 第 4 条是精度护栏：它保证"放宽的只是近邻"，不是"什么都配"。
    """
    s1 = normalize_subject(c1.get("subject", "") or "")
    s2 = normalize_subject(c2.get("subject", "") or "")
    dist = abs(int(t1) - int(t2))
    pron = {"他", "她", "它", "那", "这", "对方"}
    # 1. 两个不同的非空实词 ⇒ 互斥
    if s1 and s2 and s1 != s2 and not (s1 in s2 or s2 in s1) \
            and not (s1 in pron or s2 in pron):
        return False
    # 2. 同轮 ⇒ 兼容
    if dist == 0:
        return True
    # 3. 同会话 **≤ `IDLE_SPAN` 轮** ⇒ 兼容（零形回指）
    #
    #   ★ 2026-10-29 第二次放开（Gemini 第三节，但**理由和他说的不一样**）：
    #     他猜「死锁」——当轮算子把 dist==1 全吃光了，所以 idle 永远是 0。
    #     **离线重算证明那个假设不成立**：think() 只吃过 4 对（且都是 DILEMMA 的 -1 轮次），
    #     而 `idle_recombine` 在现有规则下就能配出 **15 条**。
    #     ⇒ 「0 次」的真因是我把 `ruminate()` 写错在 `_describe_last()` 里（已修）。
    #
    #   ★ 那还要不要放开？**要。** 离线重算显示放开到 5 轮能多出 **6 条真跨轮**：
    #     轮 11 dist=5「她还劝我别太较真」+「根本不敢看」；
    #     轮 33 dist=3「先把阳台那堆东西清出个退货运单号来」+「就那种完了的感觉」。
    #     `train.py` 的同题长会话修好之后，同 session 内 dist=2..5 **确实在聊同一件事**。
    #   ⚠️ 仍要求**至少一方有 subject**（两边都空 ⇒ 各说各的，不是回指）。
    #
    #   ⚠️⚠️ 2026-10-29 三次收紧的实测记录（**这是本项目"放宽会掉精度"的又一个实例**）：
    #
    #     版本 A：`dist <= 2` 无条件兼容
    #       ⇒ 12 条 → **94 条**，抽 30 条人眼判 **好 15 / 假 15（~50%）**
    #
    #     版本 B：`dist <= 2` 且"至少一方 subject 非空"
    #       ⇒ 94 → **92 条**（只掉 2 条），假的还在
    #         例：第 16 轮「踩了个水坑」(subject="水坑") + 「先别说了」(subject="")
    #         —— 一方非空，但两者毫无关系
    #
    #     版本 C（本版）：**只放宽同轮**（dist == 0）
    #       ⇒ 理由：同轮内的省略是**真正的零形回指**（同一口气说的两半句）；
    #         跨轮的省略更可能是"**换话题了**"（这批家教语料第 3 轮就换题）。
    #
    #   ⇒ 结论：Gemini 对**机制**的判断是对的（零形回指确实把 90% 的张力挡在门外），
    #     但在这个语料上，"跨轮省略"不能当成"同一件事"的证据。
    if same_session and dist <= IDLE_SPAN:
        return bool(s1 or s2)
    # 4. ≥3 轮 ⇒ 必须非空且匹配
    return bool(s1 and s2 and (s1 == s2 or s1 in s2 or s2 in s1))


def subjects_match(a: str, b: str) -> bool:
    """两个 subject 是否指向同一对象。

    规则（全部字面）：
      · 完全相等 ⇒ 是
      · 一个是另一个的子串，且短的那个 ≥2 字 ⇒ 是（「我妈」vs「妈」不成立，因为单字已归一化；
        但「我妈」vs「我妈的电话」成立）
      · 单字人物词 vs 含它的多字（「他」vs「他们」）⇒ **否**（"他们"是群体，不是同一人）
    """
    a, b = normalize_subject(a), normalize_subject(b)
    if not a or not b:
        return False
    if a == b:
        return True
    if len(a) == 1 or len(b) == 1:
        return False
    return a in b or b in a


def session_of(index: int, rows: list[dict]) -> str:
    """三级取会话 ID。返回字符串，同一会话返回同一个值。"""
    r = rows[index] if 0 <= index < len(rows) else {}
    origin = r.get("input_origin") or {}
    sid = origin.get("session_id")
    if sid is not None:
        # 实测 session_id 会重复（0/1/2 各两次）⇒ 与"连续段"一起构成唯一键
        return "sid:%s" % sid
    ts = r.get("ts")
    if not ts:
        return "ts:unknown"
    try:
        t = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
    except Exception:                                          # noqa: BLE001
        return "ts:bad"
    # 用"与上一行间隔"分段：这里只返回粗粒度，真正的分段由 session_spans 做
    return "ts:%s" % t.strftime("%Y-%m-%d %H:%M")


def session_spans(rows: list[dict]) -> list[tuple[int, int]]:
    """把行切成会话区间 [(start, end_exclusive), ...]。

    ★ 优先级：
      ① 有 `input_origin.session_id` 的连续段 ⇒ 一个会话（**真边界**）
      ② 其余：`ts` 间隔 > SESSION_GAP ⇒ 新会话（**约定，不是事实**）
    调用方在用 ② 时必须如实标注。
    """
    spans: list[tuple[int, int]] = []
    i, n = 0, len(rows)
    while i < n:
        o = (rows[i].get("input_origin") or {})
        if o.get("session_id") is not None:
            sid = o["session_id"]
            j = i + 1
            while j < n and (rows[j].get("input_origin") or {}).get("session_id") == sid:
                j += 1
            spans.append((i, j))
            i = j
            continue
        # ts 段
        j = i + 1
        t_prev = _ts(rows[i].get("ts"))
        while j < n:
            if (rows[j].get("input_origin") or {}).get("session_id") is not None:
                break
            t = _ts(rows[j].get("ts"))
            if t_prev and t and (t - t_prev).total_seconds() > SESSION_GAP:
                break
            t_prev = t or t_prev
            j += 1
        spans.append((i, j))
        i = j
    return spans


def _ts(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S") if s else None
    except Exception:                                          # noqa: BLE001
        return None


def _spans_overlap(a: dict, b: dict) -> bool:
    """两条 claim 在原话里的区间是否重叠（同一轮内才有意义）。"""
    return not (a["end"] <= b["start"] or b["end"] <= a["start"])


def _too_similar(a: dict, b: dict, *, same_turn: bool = True) -> bool:
    """两条 claim 的文本是否同源到没有并置价值。

    ⚠️ 实测（第一次离线跑，39 条 `IMMUTABLE_VS_ACTION_SPLIT` 里大量是这种）：
        「我当初怎么就没多问一句呢」 vs 「没多问一句」
      —— 两条是**同一句话的两个重叠片段**，并置出来是废话。
      ⇒ 判据：文本互为子串 ⇒ 没有并置价值。

    ⚠️ 区间重叠**只在同一轮内可比**。
       跨轮的 start/end 各自相对自己那句原话，数字不可比 ——
       第一次改这里时我误把跨轮也做区间检查，`CROSS_TURN_CONTRADICTION` 直接从 2 变成 0。
    """
    ta, tb = a["text"], b["text"]
    if ta == tb or ta in tb or tb in ta:
        return True
    return _spans_overlap(a, b) if same_turn else False


def _acts(claims: list[dict], kind: str) -> list[dict]:
    """取某一类的 claim（已过"最小信息量 + 禁截断"两条守卫）。

    `ACTION` 额外并入"命中退缩词"的 `COST_FEEL`（依据 Gemini 批复：
    `ACTION` 的缺失常被抽成 `COST_FEEL`，但不必为此重跑一次 API）。
    """
    out = [c for c in claims if c["kind"] == kind and usable_for_thought(c)[0]]
    if kind == "ACTION":
        out += [c for c in claims
                if c["kind"] == "COST_FEEL"
                and RETREAT_WORDS.search(c["text"])
                and usable_for_thought(c)[0]]
    return out


def _hint_for(op: str, quotes: list[str], n: int = 0) -> str:
    """给 `Thinker` 的**结构简报**，不是给她照念的台词。

    ★ 2026-10-29 第二版（第一版是固定台词，已改）：

      **这一条是最后一层窗户纸。** 第一版把 `hint` 写成
        「「{a}」这一半已经定了；「{b}」这一半是你自己做的。」
      然后 **38 条里有 36 条用同一句** ⇒ 一眼就看出是模板。
      更糟的是：行 187 的好素材「那碗面泡烂在桌上」+「我说吃了」，
      在这句连接语里被说成"这是你自己做的"—— 但"我说吃了"是**掩饰**，不是"选择"。
      ⇒ **固定连接语会把好素材说歪。**

      ⇒ 第二版：`hint` 只写**给大脑的一句话结构简报**
        （"你注意到两处原话，一边是…一边是…，不要用套话，把这两处并排点出来"），
        具体怎么串交给 `Thinker` 按语境自己造句。

      ★ 而 `C5` 的本地核对**只认 `quotes` 的两段逐字命中**，不核对连接词 ——
        所以"不写死台词"不会削弱可确认性。
    """
    a = quotes[0] if quotes else ""
    b = quotes[1] if len(quotes) > 1 else ""
    if op == "IMMUTABLE_VS_ACTION_SPLIT":
        return ("【你注意到的两处原话】一边是既定处境「%s」，另一边是他当时的应对「%s」。"
                "不要用固定套话，只把这两处原话用引号并排点出来，"
                "或就「%s」轻轻问他一句。" % (a, b, b))
    if op == "WANT_VS_COST_GAP":
        return ("【你注意到的两处原话】一边是他想要的「%s」，另一边是他实际承受的「%s」。"
                "把这两处原话用引号并排摆给他看，不加评判。" % (a, b))
    if op == "CROSS_TURN_CONTRADICTION":
        return ("【你注意到的两处原话】他前面说过「%s」，但实际发生的是「%s」。"
                "把这两句原话用引号并排放在一起。" % (a, b))
    if op == "HABITUATION_LOOP_BREAK":
        return ("【你注意到的重复原话】「%s」这句他已经第 %d 次提到了。"
                "如实点出这是他第 %d 次说到这句，不要评价。" % (a, n, n))
    return "【你注意到的原话】「%s」。" % a


def _first_subject(claims: list[dict]) -> str:
    for c in claims:
        s = normalize_subject(c.get("subject", ""))
        if s:
            return s
    return ""


def think(turn_index: int, claims_by_turn: dict[int, list[dict]],
          rows: list[dict], phase_by_turn: dict[int, str],
          spans: list[tuple[int, int]] | None = None,
          *, k: int = HISTORY_K) -> Thought | None:
    """在一轮上跑五个算子，返回**胜出的那一个**（或 None）。

    ⚠️ 这一层**不做任何原话生成** —— 只从已校验的 claim 里挑与拼。
    """
    cur = claims_by_turn.get(turn_index) or []
    if not cur:
        return None
    spans = spans or session_spans(rows)
    # 找当前轮所在会话
    span = next(((a, b) for a, b in spans if a <= turn_index < b), None)
    if span is None:
        return None
    lo, hi = span
    hist_idx = [i for i in range(max(lo, turn_index - k), turn_index) if i >= lo]

    fired: list[Thought] = []

    # ---- 算子 3：原地兜圈子（同 signature_key 连续 ≥3 次）
    sig = (rows[turn_index].get("_signature_key")
           or (rows[turn_index].get("input_origin") or {}).get("signature_key"))
    if sig:
        run_len = 0
        for i in range(turn_index, lo - 1, -1):
            s_i = (rows[i].get("_signature_key")
                   or (rows[i].get("input_origin") or {}).get("signature_key"))
            if s_i == sig:
                run_len += 1
            else:
                break
        if run_len >= 3:
            rep = cur[0]["text"]
            fired.append(Thought(
                "HABITUATION_LOOP_BREAK", [rep],
                _hint_for("HABITUATION_LOOP_BREAK", [rep], run_len)))

    # ---- 算子 4：死局与活口切分
    #   ★ 必须"两条彼此独立"：同一句话的两个重叠片段并置出来是废话（实测教训）。
    fixed = _acts(cur, "FIXED")
    action = [c for c in _acts(cur, "ACTION") if c["kind"] == "ACTION"]
    for f_c in fixed:
        for a_c in action:
            if _too_similar(f_c, a_c):
                continue
            f, a = f_c["text"], a_c["text"]
            fired.append(Thought(
                "IMMUTABLE_VS_ACTION_SPLIT", [f, a],
                _hint_for("IMMUTABLE_VS_ACTION_SPLIT", [f, a])))
            break
        else:
            continue
        break

    # ---- 算子 1：跨轮言行撞车（本轮 ACTION/COST + 历史 WANT + **同一 subject**）
    now_acts = [c for c in _acts(cur, "ACTION") if c["kind"] == "ACTION"] + _acts(cur, "COST_FEEL")
    for c_now in now_acts:
        subj_now = normalize_subject(c_now.get("subject", ""))
        for hi_ in reversed(hist_idx):
            for c_hist in _acts(claims_by_turn.get(hi_) or [], "WANT_MUST"):
                subj_hist = normalize_subject(c_hist.get("subject", ""))
                same = (subjects_match(subj_now, subj_hist)
                        or subj_now == subj_hist == "" and False)
                if same and c_hist["text"] != c_now["text"] and not _too_similar(c_hist, c_now, same_turn=False):
                    fired.append(Thought(
                        "CROSS_TURN_CONTRADICTION", [c_hist["text"], c_now["text"]],
                        _hint_for("CROSS_TURN_CONTRADICTION",
                                  [c_hist["text"], c_now["text"]])))
                    break
            else:
                continue
            break

    # ---- 算子 2：欲求-代价落差
    #
    #   ★ 在线触发条件：机制层 phase == WANT_NO_LIKE。
    #   ★ **历史数据的放宽**（Gemini 批复第三节，我采纳）：
    #     历史 `eval.jsonl` 前 191 行根本没存 `mech.phase`，后 24 行又因为
    #     META 劫持（已修）被卡死在 `NO_TENSION` ⇒ 按 phase 严格判，
    #     这个算子**结构上永远是 0**；而 508 条 Claim 里 WANT_MUST 有 83 行、
    #     COST_FEEL 有 69 行。
    #     ⇒ 本轮**没有鲜活 mech**（不在 phase_by_turn 里）时，退回
    #       "同轮同时有 WANT_MUST 与 COST_FEEL"这条纯字面条件。
    #     ⚠️ 在线运行时 `phase_by_turn` 有值 ⇒ 走严格路径（仍以 phase 为准）。
    want = _acts(cur, "WANT_MUST")
    cost = _acts(cur, "COST_FEEL")
    has_live_phase = turn_index in phase_by_turn
    phase_ok = phase_by_turn.get(turn_index) == "WANT_NO_LIKE"
    if (phase_ok or not has_live_phase) and want and cost \
            and not _too_similar(want[0], cost[0], same_turn=True):
        fired.append(Thought(
            "WANT_VS_COST_GAP", [want[0]["text"], cost[0]["text"]],
            _hint_for("WANT_VS_COST_GAP", [want[0]["text"], cost[0]["text"]])))

    # ---- 算子 1 的**同轮版**：同一轮里 WANT 与 ACTION/COST 指向同一对象
    #   ★ Gemini 批复第三节：跨轮窗口太小时（实测只有 6 个真会话），
    #     允许同轮前后半句的拉扯也触发。
    for c_w in want:
        sw = normalize_subject(c_w.get("subject", ""))
        for c_a in (action + cost):
            if c_a["kind"] == "WANT_MUST":
                continue
            sa = normalize_subject(c_a.get("subject", ""))
            if (subjects_match(sw, sa) or sw == sa == "") \
                    and not _too_similar(c_w, c_a, same_turn=True):
                fired.append(Thought(
                    "CROSS_TURN_CONTRADICTION",
                    [c_w["text"], c_a["text"]],
                    _hint_for("CROSS_TURN_CONTRADICTION", [c_w["text"], c_a["text"]])))
                break
        else:
            continue
        break

    if not fired:
        return None
    # ---- 优先级：越具体、越可核对越优先
    fired.sort(key=lambda t: OP_ORDER.index(t.op))
    winner = fired[0]
    winner.yielded = [t.op for t in fired[1:]]
    return winner

# ------------------------------------------------------------------ 自发想
#
# ★ 2026-10-29：**现有五个算子都不能在"没有新输入"时触发** ——
#   算子 1/2/4 都要"本轮有 X"，算子 3 要同一轮内的 signature_key 连续重复。
#   所以"她自己想"不能靠"重跑一遍算子"，得有一个**只吃历史**的算子。
#
#   人闲着的时候在干什么？不是重新观察，是**用已经有的材料换一个配对**。
#     「他说的那句『随便』，和她真去做了 —— 这两件我以前放在一起过。
#       可我今天又想到，他是不是早就知道她会去做？」
#
#   ⇒ `idle_recombine`：拿台账里所有已验证的 claim，找一组**从未配过**的
#     （处境 × 应对）或（想要 × 代价），并且两段来自**不同轮**。
#
#   ⚠️ 三条防假阳性：
#     ① 两段必须来自不同轮（同轮的在算子 2/4 里已经配过了）
#     ② subject 必须匹配（或都为空，且 kind 组合是 FIXED+ACTION —— 那对最有辨识度）
#     ③ 这一对**没在任何历史 Thought 的 quotes 里出现过**（配过的不再配）
#
#   ⚠️ 找不到就返回 None —— **不硬凑**。宁可这一晚什么都没想。


#: 自发想允许的配对类型（kind_a, kind_b）—— 必须是**反差极性**组合
IDLE_PAIRS = (("FIXED", "ACTION"), ("WANT_MUST", "COST_FEEL"), ("WANT_MUST", "ACTION"))

#: 自发想的配对窗口（无 session_id 时）
IDLE_WINDOW = 6

#: 零形回指放宽的最大轮次距离（同会话内）
#: ⚠️ 只在 `idle_recombine` 的路径上生效 —— 当轮算子仍用 dist<=1，
#:   因为「他刚说的」和「他前面说的」在注意力上是两件事。
IDLE_SPAN = 5

#: 两段文本的字符重合率上限（超过就当成"同义复述"，不配）
IDLE_MAX_OVERLAP = 0.40


def _lcs_ratio(a: str, b: str) -> float:
    """最长公共子串占**短句**的比例。用来判"这两句是不是在说同一件事"。"""
    if not a or not b:
        return 0.0
    if len(a) > len(b):
        a, b = b, a
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
    return best / float(len(a))


def same_span(c1: dict, c2: dict, turn1: int, turn2: int) -> bool:
    """两条 claim 是不是**原话里同一位置**的片段（只是切法不同）。

    ★ Q5.2（Gemini 拍板）：`seen_pairs` 不能只比字符串全等 ——
      「这件事改不了」(raw[10:16]) 与「改不了」(raw[13:16]) 是**同一处**，
      但它们字符串不同。而每条 claim 都有 `(turn, start, end)` 偏移量：
      **同一轮 且区间重叠 ⇒ 同一个片段**，换十种切法也认得出。

      ⇒ 所以去重键不是 `text`，是 `(turn, start, end)` 的区间语义。
    """
    if turn1 != turn2:
        return False
    try:
        a1, b1 = int(c1["start"]), int(c1["end"])
        a2, b2 = int(c2["start"]), int(c2["end"])
    except (KeyError, TypeError, ValueError):
        return c1.get("text") == c2.get("text")
    return not (b1 <= a2 or b2 <= a1)


def pair_seen(c1: dict, c2: dict, t1: int, t2: int, seen: list) -> bool:
    """这一对是否已经想过了。`seen` 是历史 Thought 的 [(turn, start, end), ...] 展平列表。"""
    # seen 里存的是 (turn, start, end) 三元组；只要任一条与两个待配片段
    # 在同一轮且区间重叠，就算"这对里有一段想过/配过了"。
    for (st, sa, sb) in seen:
        if same_span(c1, {"start": sa, "end": sb}, t1, st):
            return True
    return False


def _pair_key(a: dict, b: dict) -> tuple[str, str]:
    """把两条 claim 归一成一个无序对（按 text 排序），用于去重。"""
    x, y = sorted([a["text"], b["text"]])
    return (x, y)


def idle_recombine(claims_by_turn: dict[int, list[dict]],
                   rows: list[dict],
                   seen: list[tuple[int, int, int]] | None = None,
                   spans: list[tuple[int, int]] | None = None,
                   *, window: int = IDLE_WINDOW) -> Thought | None:
    """**没有新输入时**，用历史 claim 重新配对，产生一条新的观察。

    返回 `Thought`（`op = "IDLE_RECOMBINE"`）或 `None`。

    ⚠️ 这是"她自己想"的唯一入口 —— 它**不读本轮原话**，只读历史。

    ## 三条防假阳性（Q5，Gemini 拍板）

    **① 防隔空乱凑：同会话 + 限窗。**
       只能在同一 `session_id`（无 session_id 时限定在最近 `window` 轮内）配对。
       ⇒ 绝不允许把第 3 轮和第 20 轮硬凑在一起。

    **② 防同义复述自配：字符重合率 < `IDLE_MAX_OVERLAP`。**
       两句都在说"办离婚手续"的顺承句不算反差，直接排除。

    **③ 防"换个切法又当新配对"：用 `(turn, start, end)` 区间重叠去重。**
       ⚠️ 不能只比字符串 —— 「这件事改不了」与「改不了」是**原话里同一处**，
          字符串不同但区间重叠。`same_span()` 认得出。

    ⚠️ 找不到就返回 `None` —— **不硬凑**，宁可这一晚什么都没想。
    """
    seen = list(seen or [])
    spans = spans or session_spans(rows)

    def _span_of(t: int):
        return next((k for k, (x, y) in enumerate(spans) if x <= t < y), None)

    pool = {"FIXED": [], "ACTION": [], "WANT_MUST": [], "COST_FEEL": []}
    for t, cs in claims_by_turn.items():
        if _span_of(t) is None:
            continue
        for kind in pool:
            for c in _acts(cs, kind):
                if usable_for_thought(c)[0]:
                    pool[kind].append((t, c))

    def _recent(pairs):
        return sorted(pairs, key=lambda tc: -tc[0])

    for kind_a, kind_b in IDLE_PAIRS:
        for ta, ca in _recent(pool[kind_a]):
            for tb, cb in _recent(pool[kind_b]):
                if ta == tb:
                    continue                          # 必须跨轮
                # ---- 守卫 ①：同会话 + 限窗
                sa_i, sb_i = _span_of(ta), _span_of(tb)
                if sa_i != sb_i:
                    continue                          # 不同会话 ⇒ 不配
                lo = min(spans[sa_i][0], spans[sa_i][1])
                if abs(ta - tb) > window and lo + window <= min(ta, tb):
                    # 同会话但隔得太远（且不是会话开头那一段）
                    if abs(ta - tb) > window:
                        continue
                # ---- 守卫 ②：同义复述
                if _too_similar(ca, cb, same_turn=False):
                    continue
                if _lcs_ratio(ca["text"], cb["text"]) >= IDLE_MAX_OVERLAP:
                    continue
                # ---- subject 匹配
                # ★ 真凶 1：用 `subject_compatible`（兼容零形回指），不是字符串全等
                same = subject_compatible(ca, cb, same_session=True, t1=ta, t2=tb)
                # ★ 跨轮配对**必须有 subject 证据**（2026-10-29 实测定的）。
                #
                #   曾经有一条宽路："两条都没声明 subject 且是 FIXED+ACTION 就允许配"。
                #   实测 28 → 21 条里，走这条宽路的一共 7 条：**好 3 / 假 4（57%）**。
                #   而砍掉它之后：16 条，好 11 / 假 1（**6%**）—— 只少 3 条好的，少 4 条假的。
                #
                #   ⇒ 原则：跨轮配对如果没有 subject，那两条只是"都在他说的某句话里"，
                #      **不足以说它们是同一件事**。
                #      "死局 vs 活口"在同**一轮**内由算子 4 做，不需要跨轮去凑。
                if not same:
                    continue
                # ---- 守卫 ③：区间重叠去重（不是字符串去重）
                if _seen_either(ca, ta, cb, tb, seen):
                    continue
                quotes = [ca["text"], cb["text"]]
                hint = ("【你没在听他说话时，自己又想到的两处原话】"
                        "第 %d 轮他说过「%s」，第 %d 轮他说过「%s」。"
                        "这两处你之前没放在一起过。不要用套话 —— "
                        "如果它们之间确实有张力，就把这两处并排放在心里。"
                        % (ta + 1, quotes[0], tb + 1, quotes[1]))
                return Thought("IDLE_RECOMBINE", quotes, hint, sources=[
                    {"turn": ta, "start": ca["start"], "end": ca["end"],
                     "kind": ca["kind"], "subject": ca.get("subject", "")},
                    {"turn": tb, "start": cb["start"], "end": cb["end"],
                     "kind": cb["kind"], "subject": cb.get("subject", "")},
                ])
    return None


def _seen_either(ca: dict, ta: int, cb: dict, tb: int,
                 seen: list[tuple[int, int, int]]) -> bool:
    """这一对里**任一段**是否已经出现过（按区间，不按字符串）。"""
    for (st, sa, sb) in seen:
        if same_span(ca, {"start": sa, "end": sb}, ta, st):
            return True
        if same_span(cb, {"start": sa, "end": sb}, tb, st):
            return True
    return False

# ------------------------------------------------------------------ 2 环连锁
#
# ★ 依据（Gemini Q6 + 第 ③ 步施工图）：
#   严格限深 **2 环** —— 第 1 环是**历史已形成的 Thought**，第 2 环是**本轮新 Claim**。
#
#   ⚠️ 为什么这样误差不累积：第 1 环如果已经拿到 `THOUGHT_EXECUTED_STRONG`，
#      它的准确率接近 100%（她已经真的把那两段说出来了）⇒ 没有 0.94² 的滚雪球。
#
#   ⚠️⚠️ **物理锁死深度**：`prev.op != "CHAIN_EXTENSION"` ——
#      连锁算子**绝不再套连锁算子**。这一行判断就把深度锁在 2 环，
#      不靠"我们记得别写太深"。

#: 可以作为"第 1 环"的算子（**不含 CHAIN_EXTENSION** —— 那是深度锁）
CHAIN_BASE_OPS = ("CROSS_TURN_CONTRADICTION", "WANT_VS_COST_GAP",
                  "IMMUTABLE_VS_ACTION_SPLIT", "IDLE_RECOMBINE")

#: 第 1 环最多往前看几轮
CHAIN_LOOKBACK = 3


def chain_extension(turn_index: int,
                    claims_by_turn: dict[int, list[dict]],
                    prev_thoughts: dict[int, dict],
                    executed: dict[int, str] | None = None,
                    *, k: int = CHAIN_LOOKBACK) -> Thought | None:
    """把「前几轮已经形成的那条思考」和「这一轮的新进展」串成一条线。

    返回 `Thought`（`op = "CHAIN_EXTENSION"`）或 `None`。

    ## `prev_thoughts` 的形状
    `{turn: {"op": ..., "quotes": [q1, q2], "sources": [...]}}`
    —— 由调用方从台账的 `cognition` 字段读出来。

    ## 产出
    `quotes = [q2, c_new.text]` —— **只放两段**。
    ⚠️ 为什么不是三段：逼她在 30 字里逐字背三段会极其笨重。
       而 `q2` 本身就是上一轮思考的枢纽，只要她把 `q2` 和新进展串起来，
       三点一线就已经完成，而 `C5` 核对这两段命中即判 STRONG。

    ## 关联性守卫（二选一，Gemini 施工图）
    ① **同对象延续**：`c_new.subject` 非空且与 `prev` 关联的 subject 匹配；
    ② **紧邻轮直接承接**：`prev` 就在 `t-1`，且上一轮她**真的执行了**那条思考
       （`executed[t-1] in ("STRONG", "WEAK")`），且 `c_new` 是 `ACTION` 或 `COST_FEEL`。
    """
    executed = executed or {}
    cur = claims_by_turn.get(turn_index) or []
    if not cur:
        return None

    # ---- 第 1 环：找最近的一条可用历史 Thought（**不可再看 CHAIN_EXTENSION**）
    prev_turn = None
    prev = None
    for t in range(turn_index - 1, max(-1, turn_index - 1 - k), -1):
        cand = prev_thoughts.get(t)
        if not cand:
            continue
        if cand.get("op") not in CHAIN_BASE_OPS:
            continue                      # ★ 深度锁：CHAIN_EXTENSION 不做前件
        qs = [q for q in (cand.get("quotes") or []) if q]
        if len(qs) < 2:
            continue
        prev_turn, prev = t, cand
        break
    if prev is None:
        return None

    q1, q2 = prev["quotes"][0], prev["quotes"][1]
    prev_sources = prev.get("sources") or []
    prev_subject = ""
    for src in prev_sources:
        ss = normalize_subject(src.get("subject", "") or "")
        if ss:
            prev_subject = ss
            break
    prev_level = executed.get(prev_turn, "")

    # ---- 第 2 环：本轮的新进展
    for kind in ("ACTION", "COST_FEEL", "FIXED", "WANT_MUST"):
        for c_new in _acts(cur, kind):
            # 守卫 1：不能是同一处的重复
            if _too_similar({"text": q2, "start": 0, "end": len(q2)}, c_new, same_turn=False):
                continue
            if _lcs_ratio(q2, c_new["text"]) >= IDLE_MAX_OVERLAP:
                continue
            # 守卫 2：关联性（二选一）
            # ★ 真凶 1：同对象延续也用 `subject_compatible`
            _prev_c = {"subject": prev_subject}
            by_subject = subject_compatible(_prev_c, c_new, same_session=True,
                                            t1=prev_turn, t2=turn_index)
            # ⚠️ 但跨轮连锁**不允许**走"两边都空"那条宽路 ——
            #   连"前件说的对象"都不知道，就没资格说"这是同一件事的延续"。
            if not normalize_subject(_prev_c.get("subject", "")) \
                    and not normalize_subject(c_new.get("subject", "")):
                by_subject = False
            by_adjacency = (prev_turn == turn_index - 1
                            and prev_level in ("STRONG", "WEAK")
                            and kind in ("ACTION", "COST_FEEL"))
            if not (by_subject or by_adjacency):
                continue
            hint = ("【你把前后的事串成了一条线】"
                    "前面你刚注意到他从「%s」走到「%s」；这一轮他又接着说「%s」。"
                    "你可以用第一人称把上次的「%s」和这次的「%s」串起来回应他，"
                    "或问他这一步是怎么走过来的。"
                    % (q1, q2, c_new["text"], q2, c_new["text"]))
            return Thought("CHAIN_EXTENSION", [q2, c_new["text"]], hint, sources=[
                {"turn": prev_turn, "start": (prev_sources[1]["start"] if len(prev_sources) > 1 else 0),
                 "end": (prev_sources[1]["end"] if len(prev_sources) > 1 else len(q2)),
                 "kind": (prev_sources[1].get("kind", "") if len(prev_sources) > 1 else ""),
                 "subject": (prev_sources[1].get("subject", "") if len(prev_sources) > 1 else "")},
                {"turn": turn_index, "start": c_new["start"], "end": c_new["end"],
                 "kind": c_new["kind"], "subject": c_new.get("subject", "")},
            ])
    return None

#: ★ 2026-10-29（Gemini 的架构改造 B，我采纳）：
#:
#:   **为什么这一条最关键。**
#:   用户说「接着改还是先睡一觉」时，她回「这两个我替你挑不了」——
#:   因为系统**没把这个句子识别成任何张力**，`Thinker` 直接面对一个裸的选择问句，
#:   触发了预训练里的"助手拒单反射"。
#:
#:   而一个人对朋友叹气说「我是接着改，还是先睡一觉？」时，
#:   表层是选择问句，**认知深层是他自己内心的两个相反冲动同时在拉扯他**。
#:   ⇒ 把它当作 `Thought` 递进去，她就不可能再说出"我替你挑不了"。
# ⚠️ 允许多一个逗号在「还是」前（「我是接着改，还是先睡一觉」这种口语最常见）
DILEMMA_RE = re.compile(r"([^，。；！？\s「」『』]{2,14})[，,、\s]?还是([^，。；！？\s「」『』]{2,14})")

#: 「该不该 / 要不要 / 能不能 + 动作」也是两难（A 与"不 A"）
DILEMMA_WHETHER_RE = re.compile(r"(该不该|要不要|能不能|会不会)([^，。；！？\s「」『』]{2,14})")

#: 出现这些词就不是两难，是元提问/事实追问
DILEMMA_BLOCK = re.compile(r"是什么|为什么|几点|多少|怎么用|哪个模型|你是谁|在哪")


def extract_dilemma(raw: str, claims: list[dict] | None = None) -> Thought | None:
    """把「A 还是 B」抽成一条**句内两难**的观察（`op = "DILEMMA"`）。

    ⚠️ 两道守卫：
      ① 出现 `DILEMMA_BLOCK` 里的词 ⇒ 不是两难（"你是什么模型还是…"那种不算）
      ② A、B 都要 ≥2 字且不同 ⇒ 否则"还是"可能只是连词（"你还是别去了"）

    ★ 产出的两段 quotes 都**逐字来自原话**（用 `raw.find` 定位），
      所以 `C5` 照样只认两段字面命中。
    """
    if not raw:
        return None
    if DILEMMA_BLOCK.search(raw):
        return None
    m = DILEMMA_RE.search(raw)
    if m:
        a, b = m.group(1).strip(), m.group(2).strip()
    else:
        # ★ 「该不该再试一回」= 「再试一回」vs「不再试一回」也是两难
        w = DILEMMA_WHETHER_RE.search(raw)
        if not w:
            return None
        a, b = w.group(1), w.group(2).strip()
        if len(b) < 2:
            return None
    if len(a) < 2 or len(b) < 2 or a == b:
        return None
    # 两侧都要在原话里能定位到（切出来的片段本来就在，这里是保险）
    if a not in raw or b not in raw:
        return None
    hint = ("【你看到的句内两难】他把「%s」和「%s」摆成了二选一 —— "
            "这不是在让你替他挑，是这两头此刻都在拽着他。"
            "不要表态「我替你挑不了」，直接照亮这两头："
            "哪一头让他没法安心选另一头？" % (a, b))
    return Thought("DILEMMA", [a, b], hint, sources=[
        {"turn": -1, "start": raw.find(a), "end": raw.find(a) + len(a), "kind": "", "subject": ""},
        {"turn": -1, "start": raw.find(b), "end": raw.find(b) + len(b), "kind": "", "subject": ""},
    ])
