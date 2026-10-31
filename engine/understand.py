# -*- coding: utf-8 -*-
"""API 理解层（把模型当运算器用，不当说话人用）

设计立场（这是本模块存在的全部理由）：
  我们要的是模型的**运算能力**——把自然语言映射成结构；
  我们**不要**它的语言逻辑与沟通逻辑——所以输出被锁死为纯 JSON，
  且意图与标记都只能从我们给定的封闭集合里选，不允许它自创新范畴。

  ⚠️ 因此本模块有一条硬纪律：
     **模型返回的任何自由文本都不得进入对话输出。**
     它返回的 evidence 必须是用户原话的逐字片段，由我们校验；不匹配则丢弃该条。

双评定人架构
  规则引擎（engine/markers.py）与 API 各自独立判定 → 逐项比对：
    · 一致 → 采纳，并记 agreement=1（这就是缺的外部锚点）
    · 不一致 → 记 CONFLICT，按 [E] 差倾角的做法**报告冲突而不平均**
    · API 不可用 → 明确降级为单评定人，并在台账里标注 degraded

密钥来源：优先环境变量 DEEPSEEK_API_KEY，其次 ~/.dsh/.credentials.yaml 的 refs 段。
密钥永不写入日志、台账或输出。
"""
from __future__ import annotations

import io
import hashlib
import http.client
import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from markers import _exact_index, _load_meta, _norm_exact   # noqa: E402

ALLOWED_INTENTS = ["ANSWER", "META", "CLARIFY"]
DEFAULT_BASE = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-flash"


def transient_transport_error(exc):
    """Retry only transport interruptions; authentication/schema are distinct."""
    if isinstance(exc, urllib.error.HTTPError):
        return False
    if isinstance(exc, urllib.error.URLError):
        return transient_transport_error(exc.reason)
    return isinstance(exc, (http.client.RemoteDisconnected, ConnectionResetError,
                            ConnectionAbortedError, TimeoutError))


# ---------------------------------------------------------------- 密钥

def load_api_key() -> str | None:
    k = os.environ.get("DEEPSEEK_API_KEY")
    if k:
        return k.strip()
    p = os.path.join(os.path.expanduser("~"), ".dsh", ".credentials.yaml")
    if os.path.exists(p):
        with io.open(p, encoding="utf-8", errors="ignore") as handle:
            raw = handle.read()
        m = re.search(r"DEEPSEEK_API_KEY:\s*(\S+)", raw)
        if m:
            return m.group(1).strip().strip('"').strip("'")
    return None


# ---------------------------------------------------------------- 结果

@dataclass
class ApiReading:
    ok: bool
    intent: str
    markers: list[str]
    evidence: dict
    underdetermined: bool
    latency_s: float
    error: str | None = None
    dropped: list[str] = field(default_factory=list)   # 被字面校验丢弃的 evidence
    usage: dict = field(default_factory=dict)
    # ★ 显式反驳（E5 世代新增）：模型认为**某个标记的触发线索命中了、但反例也命中了**。
    #   与"没提这个标记"是两件完全不同的事：
    #     没提   = 沉默，不构成证据（不否决任何东西）
    #     反驳   = 明确主张"这不是那个标记"，并写明命中了哪条反例
    #   为什么要区分（实测）：union 策略下，规则层误判 + 模型沉默 → 误判照样采纳。
    #   实测 4/5 处误判在 union 后仍然活着（tests/probe_semantic_counterexamples.py）。
    #   误判只能靠"显式反驳"来修，不能靠"让模型更聪明"。
    refuted: list[dict] = field(default_factory=list)
    relations: list[dict] = field(default_factory=list)
    proposition_reading: dict | None = None


@dataclass
class Agreement:
    """双评定人比对结果。"""
    markers_agree: list[str]
    only_rule: list[str]
    only_api: list[str]
    intent_agree: bool
    degraded: bool
    score: float | None       # 1.0 完全一致；None 表示只有一位评定人


# ---------------------------------------------------------------- 客户端

class ApiReader:
    supports_goal_choice = True

    def __init__(self, api_key: str | None = None, base_url: str | None = None,
                 model: str | None = None, timeout: int = 90, max_tokens: int = 4096,
                 retries: int = 2):
        self.key = api_key if api_key is not None else load_api_key()
        self.base = (base_url or os.environ.get("DEEPSEEK_BASE_URL") or DEFAULT_BASE).rstrip("/")
        self.model = model or os.environ.get("DEEPSEEK_MODEL") or DEFAULT_MODEL
        self.timeout = timeout
        # 推理模型会把 token 烧在"思考"上（实测单次 reasoning 可达 693 tokens），
        # 预算给少了内容就是空的 —— 这是"两页白卷"式的失败，必须留足余量。
        self.max_tokens = max_tokens
        self.retries = retries
        self.calls = 0
        self.failures = 0
        self.empty_retries = 0
        self.last_usage: dict = {}
        self.last_transport_attempts: list[dict] = []

    @property
    def available(self) -> bool:
        return bool(self.key)

    def _post(self, messages: list[dict], json_mode: bool = True) -> tuple[dict, float]:
        """发一次请求。

        json_mode=True 是理解层用的 —— 它的输出被锁死为纯 JSON（模型只做结构映射）。
        json_mode=False 是**渲染层**用的（engine/render.py）：那里模型要说一句人话，
        不能把回答塞进 JSON 字段里——那会让它写得像在填表，不像在说话。
        ⚠️ 两种模式下的输出都**不得直接进对话**：
          理解层的输出由 evidence 字面校验把关；
          渲染层的输出由 render.py 的三道闸门把关。
        """
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": self.max_tokens,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        body = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            self.base + "/chat/completions", data=body, method="POST",
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + self.key},
        )
        t0 = time.time()
        self.last_transport_attempts = []
        request_hash = hashlib.sha256(body).hexdigest()
        for attempt in range(2):
            diagnostic = {"attempt": attempt + 1, "request_sha256": request_hash}
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    d = json.loads(r.read().decode("utf-8"))
                diagnostic["ok"] = True
                self.last_transport_attempts.append(diagnostic)
                return d, time.time() - t0
            except Exception as exc:
                retryable = transient_transport_error(exc)
                diagnostic.update(ok=False, error_type=type(exc).__name__, retryable=retryable)
                if isinstance(exc, urllib.error.HTTPError):
                    diagnostic["http_status"] = exc.code
                self.last_transport_attempts.append(diagnostic)
                if attempt == 1 or not retryable:
                    raise
                time.sleep(.3)

    @staticmethod
    def _system_prompt(marker_spec: list[dict]) -> str:
        from relational_memory import SCHEMA_PROMPT
        lines = []
        for m in marker_spec:
            pats = "、".join(m.get("patterns", [])[:14])
            cex = "；".join(m.get("counterexamples", [])[:3])
            lines.append("· %s（%s）：触发线索 %s ｜反例 %s" % (m["id"], m["label"], pats or "无", cex or "无"))
        return (
            "你是一个结构化抽取器，不是一个助手。\n"
            "纪律（违反即失败）：\n"
            "1. 只能输出 JSON 对象，不得输出任何解释、建议、安慰或对话性文字。\n"
            "2. 意图只能取以下之一：ANSWER（在回答给定的未完成句）、META（在向系统提问或评论系统本身）、"
            "CLARIFY（在澄清或修正上一轮）。\n"
            "2b. META 的判据是**语言里真的指向系统**（出现「你」或明确的元提问句式）。"
            "用户在说自己的状态、感受、经历（如「我好累」「我不想干了」）一律是 ANSWER，**不是** META。\n"
            "3. 标记只能从下面给定的封闭列表里选，不得新增、不得改写名称。\n"
            "4. evidence 必须是**用户原话里的逐字片段**。找不到逐字片段就不要给这个标记。\n"
            "5. 宁可漏判，不可误判。判不出就给空数组并把 underdetermined 设为 true。\n"
            "6. ★ **反例优先于触发线索**。每个标记后面的『反例』是硬判据：\n"
            "   若某标记的触发线索命中了，但同时也命中它的任一条反例，\n"
            "   必须把它写进 refute（并写明命中了哪条反例），**不许**写进 markers。\n"
            "   只对**声明过反例**的标记使用 refute；对没有反例的标记，沉默即可。\n"
            "7. 沉默与反驳是两件事：没提某个标记**不表示**你认为它不是，那不算否决。\n"
            "   所以当触发线索与反例同时命中时，**必须显式反驳**，不许省略。\n\n"
            "可选标记：\n" + "\n".join(lines) + "\n\n"
            "8. relations 只报告 blame_external 的已有触发短语每一次出现的语言关系，"
            "不判断人格。start/end 是用户输入中的从0开始字符位置（end不含）。"
            "evidence 必须严格等于该位置的原文，且必须是列表中的一个触发短语。"
            "role 只能是 ASSERTED（自己的肯定断言）、NEGATED（否定）、"
            "PROHIBITED（禁止这样说）、QUOTED（引用他人未表赞同）、UNKNOWN。"
            "关系可跨逗号；不确定就 UNKNOWN，不能把引用或禁令当肯定。"
            "没有关系判断就给空数组。\n"
            + SCHEMA_PROMPT + "输出格式（不要任何额外字段）：\n"
            '{"intent":"ANSWER|META|CLARIFY",'
            '"markers":[{"id":"...","evidence":["..."]}],'
            '"refute":[{"id":"...","why":"命中了哪条反例"}],'
            '"relations":[{"id":"blame_external","start":0,"end":4,"evidence":"...","role":"UNKNOWN"}],'
            '"propositions":[{"subject":"原字","predicate":"custodian|contact|location","value":"原字",'
            '"time":"","start":0,"end":4,"evidence":"原字","role":"ASSERTED|NEGATED|PROHIBITED|QUOTED|UNKNOWN","correction":false}],'
            '"memory_query":null,'
            '"underdetermined":true|false}'
        )

    def read(self, raw: str, stem: str | None, marker_spec: list[dict]) -> ApiReading:
        if not self.available:
            return ApiReading(False, "UNKNOWN", [], {}, True, 0.0, error="no_api_key")
        user = "【未完成句】%s\n【用户输入】%s\n\n请按纪律输出 JSON。" % (stem or "（无题面）", raw)
        # Position enumeration is an observable operation, never a role label.
        # Overlapping patterns must each retain their own provenance; a model
        # omission cannot turn the unreported occurrence into agreement.
        positions = sorted({(m.start(), m.end(), m.group())
                            for rule in marker_spec if rule["id"] == "blame_external"
                            for phrase in rule.get("patterns", [])
                            for m in re.finditer(re.escape(phrase), raw)})
        if positions:
            user += ("\n【逐字关系位置清单：仅定位，不含角色】\n" + json.dumps(
                [{"id": "blame_external", "start": start, "end": end, "evidence": evidence}
                 for start, end, evidence in positions], ensure_ascii=False)
                + "\n每个位置分别报告 relations；重叠位置也分别保留。角色仍需判断，不能决定时给 UNKNOWN，"
                  "不得从位置存在推断肯定或沿用其他位置的角色。")
        msgs = [
            {"role": "system", "content": self._system_prompt(marker_spec)},
            {"role": "user", "content": user},
        ]
        last_err = None
        t_all = time.time()
        for attempt in range(self.retries + 1):
            self.calls += 1
            try:
                d, _ = self._post(msgs)
                usage = d.get("usage", {}) or {}
                self.last_usage = usage
                content = (d["choices"][0]["message"]["content"] or "").strip()
                if not content:
                    # 内容为空：推理 token 吃光了预算。重试时把预算翻倍。
                    self.empty_retries += 1
                    self.max_tokens = min(self.max_tokens * 2, 16384)
                    last_err = "empty_content(usage=%s)" % {
                        k: usage.get(k) for k in ("completion_tokens",) if k in usage}
                    continue
                obj = json.loads(content)
                return self._parse_obj(obj, raw, marker_spec,
                                       round(time.time() - t_all, 2), usage)
            except urllib.error.HTTPError as e:
                last_err = "HTTP %s" % e.code
                if e.code in (429, 500, 502, 503, 504):
                    self.empty_retries += 1
                    time.sleep(1.5 * (attempt + 1))
                    continue
                break
            except json.JSONDecodeError as e:
                last_err = "JSONDecodeError: %s" % str(e)[:80]
                self.empty_retries += 1
                continue
            except Exception as e:
                last_err = "%s: %s" % (type(e).__name__, str(e)[:120])
                break
        self.failures += 1
        return ApiReading(False, "UNKNOWN", [], {}, True,
                          round(time.time() - t_all, 2), error=last_err,
                          usage=self.last_usage)

    def _parse_obj(self, obj: dict, raw: str, marker_spec: list[dict],
                   latency: float, usage: dict) -> ApiReading:
        intent = str(obj.get("intent", "UNKNOWN")).upper()
        if intent not in ALLOWED_INTENTS:
            intent = "UNKNOWN"
        allowed_ids = {m["id"] for m in marker_spec}
        # ★ 只有**声明过反例**的标记才允许被反驳。
        #
        # 为什么加这道闸（否则 refute 会变成一张空白否决票）：
        #   模型的否决权必须落在**已写明的判据**上，而不是它的自由裁量。
        #   一个标记若从未声明反例，模型就没有依据说"这不算" —— 它只能说"我不选"，
        #   那属于沉默，而沉默不算否决（见 merge_markers）。
        #   这样 refute 的每一次使用都可以被复核：反例是白纸黑字写着的。
        refutable = {m["id"] for m in marker_spec if (m.get("counterexamples") or [])}
        markers, evidence, dropped = [], {}, []
        for item in obj.get("markers") or []:
            mid = item.get("id")
            if mid not in allowed_ids:
                dropped.append("未知标记:%s" % mid)
                continue
            ev = [e for e in (item.get("evidence") or []) if isinstance(e, str)]
            # 字面校验：evidence 必须在用户原话里逐字出现
            good = [e for e in ev if e and e in raw]
            if ev and not good:
                dropped.append("非逐字片段:%s@%s" % (mid, "/".join(ev)[:20]))
                continue
            if mid not in markers:
                markers.append(mid)
            evidence[mid] = good[:6]

        refuted = []
        for item in obj.get("refute") or []:
            if not isinstance(item, dict):
                continue
            mid = item.get("id")
            why = str(item.get("why") or "")[:120]
            if mid not in allowed_ids:
                dropped.append("未知反驳:%s" % mid)
                continue
            if mid not in refutable:
                dropped.append("无依据反驳（该标记未声明反例）:%s" % mid)
                continue
            # 一个标记不能既主张又反驳 —— 那是不确定，退回"不主张"。
            if mid in markers:
                markers.remove(mid)
                evidence.pop(mid, None)
                dropped.append("自相矛盾（既主张又反驳）:%s" % mid)
            refuted.append({"id": mid, "why": why})
        relations = []
        seen, conflicting = {}, set()
        relation_patterns = {m["id"]: set(m.get("patterns", [])) for m in marker_spec}
        for item in obj.get("relations") or []:
            if not isinstance(item, dict):
                dropped.append("无效关系对象")
                continue
            mid, start, end = item.get("id"), item.get("start"), item.get("end")
            role, ev = item.get("role"), item.get("evidence")
            if (mid != "blame_external" or mid not in allowed_ids
                    or type(start) is not int or type(end) is not int
                    or not 0 <= start < end <= len(raw)
                    or not isinstance(ev, str) or raw[start:end] != ev
                    or ev not in relation_patterns.get(mid, set())
                    or role not in {"ASSERTED", "NEGATED", "PROHIBITED", "QUOTED", "UNKNOWN"}):
                dropped.append("无效关系证据")
                continue
            key = (mid, start, end)
            if key in seen and seen[key]["role"] != role:
                conflicting.add(key)
                dropped.append("关系结论冲突")
            seen[key] = dict(item)
        relations = [item for key, item in seen.items() if key not in conflicting]
        from relational_memory import parse
        proposition_reading = parse(raw, obj, extractor="api_reader:" + self.model)
        return ApiReading(True, intent, markers, evidence,
                          bool(obj.get("underdetermined", not markers)), latency,
                          dropped=dropped, usage=usage, refuted=refuted, relations=relations,
                          proposition_reading=proposition_reading)


# ---------------------------------------------------------------- 双评定人比对

def compare(rule_markers: list[str], api: ApiReading) -> Agreement:
    if not api.ok:
        return Agreement(markers_agree=[], only_rule=list(rule_markers), only_api=[],
                         intent_agree=False, degraded=True, score=None)
    rs, as_ = set(rule_markers), set(api.markers)
    inter = sorted(rs & as_)
    union = rs | as_
    score = round(len(inter) / len(union), 3) if union else 1.0
    return Agreement(
        markers_agree=inter,
        only_rule=sorted(rs - as_),
        only_api=sorted(as_ - rs),
        intent_agree=api.intent in ALLOWED_INTENTS,
        degraded=False,
        score=score,
    )


def merge_markers(rule_markers: list[str], api: ApiReading, agreement: Agreement,
                  policy: str = "union") -> list[str]:
    """合并两位评定人的标记。

    ⚠️ 默认策略是 `union`（召回优先），**不是** `intersect`。改这一处的理由必须写明，
       否则后人看到"宁可漏判不可误判"会觉得 union 是放松纪律：

    实测（tests/probe_api_role.py）：「改不了」模型判 immutable（对），规则层当时没覆盖
    → `intersect` 取交集为空 → **标记被丢掉，用户看到沉默**。
    也就是说 `intersect` 下，**任何一位判者的覆盖缺口都会否决另一位的正确判断**，
    而且这个方向是**双向**的：规则层单独认出的标记同样会被模型删掉。

    这与原纪律并不矛盾，而是把纪律放对了位置：
      · 「宁可漏判不可误判」管的是**输出**（不许在没有证据时提升水平）；
      · 它不该管**证据的收集**。两位评定人各自观察到的字面证据，
        没有理由因为对方没看见就当作不存在。
      · 单一判者给出的标记**不丢**，但它在台账里带 provenance
        （`only_rule` / `only_api`）与一致度，下游可以据此降权 —— 这比直接删掉更难造假。

    policy:
      union     —— 取并集；单一判者的标记保留并记 provenance（**默认**）
      intersect —— 只采纳双方一致的（旧默认。留着是因为它仍是诊断"两位差多少"的工具）
      rule_only —— 只用规则引擎（API 降级时）
    """
    if agreement.degraded:
        return list(rule_markers)
    if policy == "intersect":
        merged = list(agreement.markers_agree)
    elif policy == "rule_only":
        merged = list(rule_markers)
    else:
        merged = sorted(set(rule_markers) | set(api.markers))

    # ★ 显式反驳：即使采用 union，被模型**明确反驳**的标记也要撤下。
    #
    # 为什么必须有这一条（实测，不是设想）：
    #   union 的语义是"任一判者命中就采纳"，它修的是**漏判**。
    #   但误判在 union 下**照样活** —— 实测 4/5 处反例误判在 union 后仍然进行为
    #   （tests/probe_semantic_counterexamples.py）。让模型更聪明救不了误判，
    #   因为规则层只要命中就够了。
    #   例：「我被堵在路上两个小时」规则层命中 voice_shift，模型正确地没选它 ——
    #   但 union 取并集，voice_shift 照样进行为。模型缺的不是能力，是"说不"的通道。
    #
    # 为什么这不是把 intersect 的对称否决又请回来：
    #   旧 intersect 的病是**沉默即删除** —— 一方没看见就当作证据不存在。
    #   这里是**显式反驳**：模型必须主张"这不是那个标记"并写明命中了哪条反例，
    #   而且只对**声明过反例**的标记有效（见 _parse_obj 的 refutable 闸）。
    #   沉默仍然什么都不否决。证据不会因为"没人提"而消失，只会因为"被明确驳倒"而撤下。
    if api.ok and api.refuted:
        killed = {r["id"] for r in api.refuted}
        merged = [m for m in merged if m not in killed]
    return merged


def evidence_for(mid: str, rule_ev: dict, api: ApiReading) -> list[str]:
    """证据合并：两位都给则合并，只有一位给则用那一位的。"""
    a = list(rule_ev.get(mid, []))
    b = list(api.evidence.get(mid, []))
    out = []
    for x in a + b:
        if x not in out:
            out.append(x)
    return out[:6]


def _addresses_system(text: str) -> bool:
    """用户这句话是否**在对着系统说**（而不是在说自己的事）。

    为什么需要这个闸门（一次真实误判的教训）：
      实测用户输入「我今天特别累，什么都不想干」，API 返回 intent=META，
      规则返回 ANSWER。当时的裁决规则是"任一位判 META 且无任何标记命中 → META"，
      于是这句话被送进元提问通道，用户收到一句：
        「这句话我没接到题上。你可以继续写那半句话……」
      —— 用户说的是**自己的状态**，系统却当成"在问系统"。这是范畴错误。

    因此 META 不再由"没有标记"推出，而必须由**指向系统的语言证据**支撑：
      · 出现第二人称「你」—— 这句话里有对话对象
      · 或命中明确的元提问句式（这是什么／怎么用／有什么用……）
    两者都没有时，无论谁判 META，都不判 META。
    """
    t = text or ""
    if "你" in t or "您" in t:
        return True
    for p in _META_ADDRESS_LEXICON:
        if p in t:
            return True
    # ★ 第三条证据：**整句恰好是一个裸疑问词**（甲案，见 markers._norm_exact）。
    #   为什么必须有这条：实测（tests/probe_api_role.py）模型对「干嘛」判 META —— 它是对的，
    #   却被上面两条挡回去，合并结果是 blocked_meta(no_system_address)，用户看到沉默。
    #   一个手写闸门否决了模型判断正确的那一票，这是双评架构里最坏的一种失配。
    #   为什么只收"整句相等"而不收子串：「我在想干嘛」是用户在说自己，
    #   子串收法会把它误判成在问系统 —— 那正是本函数当初要修的范畴错误。
    if _norm_exact(t) in _exact_phrases():
        return True
    return False


def _exact_phrases() -> frozenset:
    """缓存所有 QUESTION 条目的 exact_patterns（归一化后）。"""
    global _EXACT_CACHE
    if _EXACT_CACHE is None:
        try:
            meta = _load_meta()
            idx = _exact_index(meta)
            _EXACT_CACHE = frozenset(idx.keys())
        except Exception:
            _EXACT_CACHE = frozenset()
    return _EXACT_CACHE


_EXACT_CACHE: frozenset | None = None


_META_ADDRESS_LEXICON = (
    "这是什么", "这是什么意思", "怎么用", "怎么玩", "有什么用", "干嘛用", "干什么用",
    "这是什么程序", "这是什么软件", "怎么打开",
    # ★ 补「干嘛／干吗／干啥」族 —— 实测（用户截图）：输入「在干嘛」，系统回「在干嘛。」
    #   逐层查出两层错：①这个闸门要求出现「你」或上面几个句式，而「在干嘛」两者都没有
    #   → 判为"不是在问系统" → 根本不走元提问分支；②即使过了①（如「你在干嘛」），
    #   META 库的 patterns 只有「你在干什么」，**没有「干嘛」**（嘛≠什么）。
    #   只收**疑问形式**：不收「干什么」这个裸词，因为「我在想要干什么」是他在说自己。
    "在干嘛", "在干吗", "在干啥", "干嘛呢", "干嘛啊", "干嘛呀", "干啥呢",
    "你在干嘛", "你在干吗", "你在干啥",
    # 打招呼：也是**对着系统说**的话（第二人称指向），所以算指向系统。
    # 实测：用户输入「hello」，系统回「hello。」—— 复述，等于没听见。
    "hello", "hi", "hey", "你好", "您好", "哈喽", "在吗", "在不在",
    # 「你让我说什么」也是对系统下指令。实测：用户输入
    # 「哇好乖，那你说『我喜欢这个世界』」被沉默了 —— 三层全没接住。
    "那你说", "跟我念", "你重复", "你学着说", "你也说一句",
)


def resolve_intent(rule_intent_value: str, api: ApiReading, raw: str = "") -> tuple[str, str]:
    """意图裁决，返回 (intent, how)。

    裁决规则（为什么这样定，写在代码里以免被后人改掉）：
      · **指向系统的语言闸门**：拿不到"在对你说话"的证据时，一律不判 META。
        这是防范畴错误的硬闸，优先级高于下面任何一条。
      · 两位都判 META → META
      · 一位判 META、另一位没判，且**没有**任何标记命中 → META
        （依据：标记命中说明这句话在答内容；没有标记又指向系统，那它就是在问系统）
      · 其余 → ANSWER
      · API 不可用 → 采用规则判定，并标 degraded
    """
    if not api.ok:
        return rule_intent_value, "rule_only(degraded)"
    r_meta = rule_intent_value == "META"
    a_meta = api.intent == "META"
    if (r_meta or a_meta) and not _addresses_system(raw):
        # 判者想判 META，但这句话里没有任何指向系统的语言证据。
        # 不猜、不兜底：按内容处理，让状态层与台账接住它。
        return "ANSWER", "blocked_meta(no_system_address)"
    if r_meta and a_meta:
        return "META", "both"
    if (r_meta or a_meta) and not api.markers:
        return "META", "one_side_no_markers"
    if api.intent == "CLARIFY" and not api.markers:
        return "CLARIFY", "api_clarify"
    return "ANSWER", "default"


if __name__ == "__main__":
    r = ApiReader()
    print("API 可用:", r.available, "| 模型:", r.model, "| 端点:", r.base)
    if r.available:
        spec = [{"id": "immutable", "label": "不可改变识别",
                 "patterns": ["改变不了", "再也", "已经发生"], "counterexamples": ["对可改变处境的一时沮丧"]},
                {"id": "attitude_clause", "label": "态度句",
                 "patterns": ["虽然", "但我选择"], "counterexamples": ["纯宿命论"]}]
        for t, stem in [("你在干什么", "当我想做一件事，而这件事会耽误别人的时候，我……"),
                        ("他已经走了，再也回不来了", "失去了一个再也不会回来的人，我……"),
                        ("虽然改变不了，但我可以选择怎么过下去", "当我必须长期忍受一件我改变不了的事情，我……")]:
            res = r.read(t, stem, spec)
            ag = compare([], res)
            print("  %-22s → intent=%-8s markers=%-28s %s"
                  % (t, res.intent, res.markers, ("丢弃:%s" % res.dropped) if res.dropped else ""))
