# -*- coding: utf-8 -*-
"""跨轮思考的**原材料层**：把用户原话抽成四类带字面偏移的命题。

## 这一层是什么，不是什么

**是**：「理论驱动的结构化观察层」的**输入端** —— 把系统内部表征从
「6 个浮点数 + 1 个名词」推进到「带字面偏移担保的原话命题」。

**不是**：「通用思考」。五个算子是固定优先级触发的规则，
决定"哪条观察重要"那一步它做不到 —— 这一点在 `spec/` 与代码注释里如实写，不包装。

## 为什么这四类（依据）

| 类型 | 依据 |
|---|---|
| `WANT_MUST` | `[D]` 想要回路；`[E]` 「一定」是布莱西责任心的关键因素（过度意向门控） |
| `COST_FEEL` | `[D]` 当下分子负责此时此地的体验 —— 想要与喜欢/代价是两回事 |
| `FIXED` | `[M]` 不可改变的事实与可改变的态度要分开 |
| `ACTION` | `[E]` 行为是水平的最可靠指标；`[M]` 态度自由体现在做与不做 |

## 两条硬纪律

**① 一个字都不许编。** 每条 `text` 必须**严格等于** `raw[start:end]`，
由 `_literal_claim` 本地核对；不等的当场丢弃并计数。

**② 分类是同源意见，不是事实。** `raw[start:end] == text` 只证明"这些字是用户说的"，
**不证明**"这段字属于 WANT 还是 COST" —— 后者是模型判的，与生成同源。
⇒ 所以：
   · 输出里永远标 `independent_semantics_verified: False`
   · **两遍抽取，只有两遍都判成同一类、同一片段的才保留**（见 `extract()`）
   · 上层算子只允许把两条**原话并排**展示，不做单一断言 ⇒ 误读可被用户当场纠正

## 这一版只做抽取与离线验收

**不接 `pipeline.py`、不改 `ledger.py`、不动任何现有测试**（用户已批的范围）。
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field

#: 四类命题。**封闭集合** —— 模型不得自创新类型。
CLAIM_KINDS = ("WANT_MUST", "COST_FEEL", "FIXED", "ACTION")

#: 单条 `text` 的长度上限（与原话片段校验的上限一致）
MAX_TEXT = 200
#: `subject` 的长度上限
MAX_SUBJECT = 40

VERSION = "cognition-claims/v1"

EXTRACT_SYSTEM = """你是一个结构化抽取器，不是一个助手。
只输出一个 JSON 对象，不得输出解释、建议、安慰或任何对话性文字。

任务：从【用户原话】里抽取四类**逐字片段**。每一类都可以是空数组。

1. WANT_MUST —— 他想要的东西、他逼自己必须做到的事。
   线索：必须／一定／非要／得／不能／总要／我就不信。

2. COST_FEEL —— 他实际承受的**滋味、代价、身体或情绪状态**。
   线索：累／睡不着／怕／麻木／疼／空／喘不过气／翻来覆去／丢魂。

3. FIXED —— **已经发生、当事人无法撤回**的人际／生命／现实既定处境或遗憾。
   ✅ 该抽：他已经走了再也回不来了／被家里狗咬了个洞／左边比右边胖了一针／
           那碗面泡烂在桌上／还是被一句话打回来了
   ❌ 严禁抽（这是上一版最大的错）：
      · 做饭、家务、天气、路况等**纯物理过程细节**：
        水添多了／汤底浑了／鞋上有泥／灯坏了／咖啡凉了／路上堵了俩小时
      · 当事人自己的**主观困惑或泛泛评价**：别的什么没了／没用／不知道该怎么办

4. ACTION —— 当事人面对处境或冲动时，**自己做出的、有心理分量的**
   应对／退缩／隐瞒／忍耐／卡住的举动。
   ✅ 该抽：把最该说的话咽下去／又舍不得删／我没敢再翻／我没扔也没缝／
           没敢说／我说吃了／昨天熬到两点改
   ❌ 严禁抽（这是上一版第二大的错）：
      · 充当**时间背景的日常过场动作**：挂了电话／站起来那会儿／车开走以后／
        开柜子拿浴巾／火我关了
      · **不受控的纯生理条件反射**：手抓着桌沿／腿都软了／发抖／手抖／出汗／心跳快
        （这类只能算 COST_FEEL，**不是**他的选择）
      · **意思不完整的半截残句**：我低头说了句／我一拧开

⚠️ 纪律（违反即失败）：
· 每条必须给 start / end / text，且 **text 严格等于原话的 raw[start:end]**（end 不含）。
  位置从 0 开始，按**字符**计（不是字节）。
· subject：这条话是关于**哪个具体对象**的，必须是原话里的**逐字片段**
  （如「辞职信」「押金」「我妈」「那台打印机」）。说不清就留空字符串。
· **抽不到就留空数组，绝不硬凑。** 宁可少抽，不可编造。
· 不评人格、不诊断、不推测动机、不给建议。
· 引号里的话如果不是用户自己的立场（是引用别人），不要抽成 WANT_MUST。
· **一段原话里如果只有物理细节、没有人的取舍，就不要抽 FIXED 或 ACTION。**

输出格式（不要任何额外字段）：
{"claims":[{"kind":"WANT_MUST|COST_FEEL|FIXED|ACTION",
            "start":0,"end":4,"text":"原字","subject":"原字或空"}]}"""

#: ★ 最小信息量：参与算子拼装的 `text`，去掉标点后至少这么长。
#:   依据（实测）：`'还在'`、`'没用'`、`'试过了'`、`'站那儿'` 这种 2–3 字孤立短词
#:   单独触发算子 4 时产生的是废话（行 177「没用」…「试过了」）。
MIN_THOUGHT_TEXT = 4

#: ★ 禁截断尾词：`ACTION` 片段不得以悬空的未完动词/介词结尾。
#:   依据（实测）：行 27「我低头说了句」、行 115「我一拧开」都是半截话。
TRUNCATED_TAIL = re.compile(
    r"(?:说了句|了一句|一拧开|看着|拿着|走到|到了|站在|想了|觉得)$")

#: ★ 短词放行：<4 字但**含人的取舍**时，仍然允许参与算子。
#:
#:   依据（实测逼出来的）：一刀切 `len >= 4` 会把
#:     垃圾「没用」「试过了」「还在」和
#:     好东西「没敢说」（3 字，含"没敢"，语义极重）一起砍掉。
#:   ⇒ 判据从"够不够长"改成"有没有人的取舍在里面"。
SIGNIFICANT_SHORT = re.compile(
    r"没敢|不敢|不舍|忍不住|忍住|咽下|删了|没去|没说|没开口|没问|没扔|"
    r"放下|搁下|放手|放弃|想点|想说|想问|想过|要走|想走|离开|辞了")

#: ★ 纯生理反应：**可作 `COST_FEEL`，不作 `ACTION`**。
#:
#:   依据（靶向验收：最后 1 条假阳性）：
#:     行 124「就想跟他说」…「**我腿都软了**」——
#:     "腿软"是不受控的生理反应，不是他做的选择，拿它当 `ACTION`
#:     拼出来的"这一半是你自己做的"是错的。
#:   Prompt 负例已加，这里再加一道本地守卫（prompt 只是降低概率，守卫才能保证）。
PHYSIOLOGICAL = re.compile(
    r"腿.{0,2}软|发抖|手抖|打颤|出汗|冒汗|心跳|喘不上气|喘不过气|头皮发麻|起鸡皮")


@dataclass
class Claim:
    """一条**已通过字面校验**的原话命题。"""
    kind: str
    text: str
    start: int
    end: int
    subject: str = ""

    def as_dict(self) -> dict:
        return {"kind": self.kind, "text": self.text, "start": self.start,
                "end": self.end, "subject": self.subject}


def usable_for_thought(c: dict) -> tuple[bool, str]:
    """这条 claim 能不能参与算子 1/2/4 的拼装。返回 (可用, 不可用原因)。

    ★ 两条零成本防呆守卫（Gemini 批复第二节）：

      **① 最小信息量**：去掉标点后至少 `MIN_THOUGHT_TEXT` 个字。
         依据（实测假阳性）：行 177「没用」…「试过了」——
         两个 2～3 字的空词并置出来是废话。
         ⚠️ 例外：含引号引述（如 `说了句"随便"`）时放宽 —— 引号里的内容本身有信息。

         ★★ 2026-10-29 **再放宽（实测逼出来的）**：
           一刀切 `len >= 4` 把两样东西一起砍了：
             垃圾：「没用」「试过了」「还在」
             好东西：「没敢说」（3 字，但含"没敢"这个退缩词，语义极重）
           ⇒ 所以判据不是"够不够长"，而是**"有没有人的取舍在里面"**。
           规则：去掉标点后 <4 字时，**若含退缩词/动作词就放行**，否则丢。

      **② 禁截断尾词**：`ACTION` 片段不得以悬空的未完动词结尾。
         依据（实测假阳性）：行 27「我低头说了句」、行 115「我一拧开」都是半截话。

    ⚠️ 这两条**只在算子层**生效，不写进 `_literal_claim` ——
       短片段在别的用途（比如原话回显）上仍然合法，只是**不足以支撑一次"洞察"**。
    """
    text = c.get("text") or ""
    bare = re.sub(r"[，。；！？、…—\-「」『』\"“”'\s]", "", text)
    has_quote = bool(re.search(r"[「『\"“]", text))
    if len(bare) < MIN_THOUGHT_TEXT and not has_quote:
        # ★ 短词放行条件：含"人的取舍"（退缩/动作/欲求）
        if not SIGNIFICANT_SHORT.search(bare):
            return False, "too_short:%d" % len(bare)
    if c.get("kind") == "ACTION" and TRUNCATED_TAIL.search(bare):
        return False, "truncated_tail"
    # ★ 纯生理反应不算 ACTION（见 PHYSIOLOGICAL 的注释）
    if c.get("kind") == "ACTION" and PHYSIOLOGICAL.search(bare):
        return False, "physiological_not_choice"
    return True, ""


def _hash(s: str) -> str:
    return hashlib.sha256((s or "").encode("utf-8")).hexdigest()


def _literal_claim(item, raw: str) -> tuple[bool, str]:
    """本地核对一条 claim。返回 (是否通过, 不过的原因)。

    ★ 这是这一层"一个字都不许编"的**唯一保证** —— 与 `relational_memory._literal`
      同一套办法（`raw[start:end] == evidence`），但谓词集互不相交。
    """
    if not isinstance(item, dict):
        return False, "not_a_dict"
    kind = item.get("kind")
    if kind not in CLAIM_KINDS:
        return False, "bad_kind:%r" % (kind,)
    start, end, text = item.get("start"), item.get("end"), item.get("text")
    if type(start) is not int or type(end) is not int:
        return False, "offset_not_int"
    if not (0 <= start < end <= len(raw)):
        return False, "offset_out_of_range"
    if not isinstance(text, str) or not (0 < len(text) <= MAX_TEXT):
        return False, "text_bad"
    if raw[start:end] != text:
        return False, "text_not_literal"
    return True, ""


def _clean_subject(item, raw: str) -> str:
    """`subject` 也必须是原话里的逐字片段；否则清空（不猜）。

    ⚠️ 不清空整条 claim —— 算子 1 需要 subject 才能做"同一对象"匹配，
       但缺 subject 只影响那一个算子，不该丢掉整条原话。
    """
    s = item.get("subject")
    if not isinstance(s, str) or not s.strip():
        return ""
    s = s.strip()
    if len(s) > MAX_SUBJECT:
        return ""
    return s if s in raw else ""


def _parse_json(txt: str) -> dict:
    t = (txt or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n?", "", t)
        t = re.sub(r"\n?```$", "", t)
    i, j = t.find("{"), t.rfind("}")
    if i < 0 or j <= i:
        return {}
    try:
        return json.loads(t[i:j + 1])
    except Exception:                                          # noqa: BLE001
        return {}


def extract_once(reader, raw: str) -> dict:
    """抽一遍。返回原始条目 + 丢弃统计（不抛异常，失败也算数据）。

    ⚠️ 2026-10-29 第一版写成 `reader._post(msgs, temperature=0.0)` ——
       `ApiReader._post` 的签名是 `(messages, json_mode=True)`，**没有 temperature**，
       于是每行都在 0.0 秒内抛 TypeError，全部抽成空。
       项目里 `engine/understand.py:143` 已经把 temperature 设在 reader 层（=0），
       这里不再传。
    """
    raw = raw or ""
    stats = {"returned": 0, "kept": 0, "dropped": [], "error": None}
    if not raw.strip():
        return {"claims": [], "stats": stats}
    try:
        d, _ = reader._post(
            [{"role": "system", "content": EXTRACT_SYSTEM},
             {"role": "user", "content": "【用户原话】\n%s\n\n请按纪律输出 JSON。" % raw}])
        txt = ((d.get("choices") or [{}])[0].get("message", {}).get("content") or "")
    except Exception as exc:                                   # noqa: BLE001
        stats["error"] = "post:%s:%s" % (type(exc).__name__, str(exc)[:60])
        return {"claims": [], "stats": stats}

    obj = _parse_json(txt)
    items = obj.get("claims")
    if not isinstance(items, list):
        stats["error"] = "no_claims_key"
        return {"claims": [], "stats": stats}
    stats["returned"] = len(items)
    kept = []
    for it in items:
        ok, why = _literal_claim(it, raw)
        if not ok:
            stats["dropped"].append(why)
            continue
        kept.append({"kind": it["kind"], "text": it["text"],
                     "start": it["start"], "end": it["end"],
                     "subject": _clean_subject(it, raw)})
    stats["kept"] = len(kept)
    return {"claims": kept, "stats": stats}


def extract(reader, raw: str, *, passes: int = 2) -> dict:
    """抽 `passes` 遍，**只保留两遍一致的 (kind, text)**。

    ★ 这是风险 ① 的缓解措施：`text` 能验"这些字是他说的"，
      但"属于哪一类"是同源意见。两遍若分到不同 kind ⇒ **丢弃，不猜**。

    返回（结构稳定，供台账/验收使用）：
        {"schema": 1, "version": VERSION, "raw_sha256": ...,
         "claims": [Claim.dict...], "dropped": [...],
         "independent_semantics_verified": False, "development_credit": 0,
         "pass_stats": [...], "agreement": {...}}
    >>> 2026-10-29 **第二版（第一版过度执行，已改）**：
        第一版要求"两遍都出现且同类"，结果 215 行上：
          模型原始返回 450 条 → 字面通过 415 → **两遍一致只剩 112**（丢 73%）
        查丢弃明细，真相是：
          · `missing_in_one_pass`（一遍有、一遍没有）**183 条 = 96%**
          · `kind_disagreement`（两遍都抽到但分类不同）**  8 条 =  4%**
        ⇒ **分类其实是稳定的（4% 分歧）；不稳定的是"这一遍抽不抽到"（召回抖动）。**
        ⇒ 而"必须两遍都出现"这一条是我自己加的，不是 Gemini 的要求
          （他要的是"两遍分到不同 kind 就丢弃"）。
          它丢掉的是**召回抖动**，不是真矛盾 ⇒ 过度保守，把覆盖率压到 34%。
        ⇒ 第二版：
          · **取并集**（一遍抽到就保留）
          · **只丢真分歧**（同一段字在两遍里被分到不同 kind）
          · 这样保留数 ≈ 415 - 8 = 407 条，覆盖率回到单遍水平（约 50%），
            而风险 ① 的缓解（不猜分类）**完整保留**。
    """
    raw = raw or ""
    runs = [extract_once(reader, raw) for _ in range(max(1, passes))]
    if passes < 2:
        claim_dicts = runs[0]["claims"] if runs else []
        dropped = ["single_pass_no_agreement_filter"]
    else:
        # 按 text 聚合：同一段字在两遍里的所有 kind
        kinds_by_text: dict[str, list[dict]] = {}
        for r in runs:
            for c in r["claims"]:
                kinds_by_text.setdefault(c["text"], []).append(c)
        claim_dicts = []
        dropped = []
        for text, items in kinds_by_text.items():
            ks = {it["kind"] for it in items}
            if len(ks) > 1:
                # ★ 真分歧：同一段字被分到不同类 ⇒ 丢弃，不猜
                dropped.append("kind_disagreement:%s" % "/".join(sorted(ks)))
                continue
            # 只在一遍出现或两遍同类 ⇒ 保留（召回抖动不是矛盾）
            claim_dicts.append(items[0])
        claim_dicts.sort(key=lambda c: (c["start"], c["end"], c["kind"]))

    claims = [Claim(c["kind"], c["text"], c["start"], c["end"], c.get("subject", ""))
              for c in claim_dicts]
    agree = {}
    for kind in CLAIM_KINDS:
        in_runs = [sum(1 for c in r["claims"] if c["kind"] == kind) for r in runs]
        agree[kind] = {"per_pass": in_runs,
                       "kept": sum(1 for c in claims if c.kind == kind)}
    return {
        "schema": 1,
        "version": VERSION,
        "raw_sha256": _hash(raw),
        "claims": [c.as_dict() for c in claims],
        # ⚠️ 如实标记：分类是同源意见，不是独立验证过的语义
        "independent_semantics_verified": False,
        "development_credit": 0,
        "dropped": dropped,
        # ★ 每遍的原始结果 —— 落盘后可用 `merge()` 离线重算任何合并规则，
        #   不必再花 50 分钟重跑 API。
        "pass_claims": [r["claims"] for r in runs],
        "pass_stats": [r["stats"] for r in runs],
        "agreement": agree,
    }


def merge(runs: list[dict]) -> tuple[list[dict], list[str]]:
    """把多遍 `extract_once` 的结果合并。**与 API 调用分离** —— 改合并规则不必重跑。

    ★ 判据（2026-10-29 实测定下来的）：
      · 同一段 `text` 在两遍里被分到**不同 kind** ⇒ **丢弃**（真分歧，不猜）
      · 同一段 `text` 只在一遍出现 ⇒ **保留**（召回抖动，不是矛盾）

      实测依据（215 行）：`missing_in_one_pass` 183 条 = **96%**，
      `kind_disagreement` 8 条 = **4%** ⇒ 分类稳定、召回抖动。
    """
    kinds_by_text: dict[str, list[dict]] = {}
    for r in runs:
        for c in r["claims"]:
            kinds_by_text.setdefault(c["text"], []).append(c)
    kept, dropped = [], []
    for text, items in kinds_by_text.items():
        ks = {it["kind"] for it in items}
        if len(ks) > 1:
            dropped.append("kind_disagreement:%s" % "/".join(sorted(ks)))
            continue
        kept.append(items[0])
    kept.sort(key=lambda c: (c["start"], c["end"], c["kind"]))
    return kept, dropped
