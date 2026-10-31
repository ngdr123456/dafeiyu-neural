# -*- coding: utf-8 -*-
"""同义替换探针 —— 机械地找出词表缺口（lexicon gap）。

为什么写这个
────────────────────────────────────────────────────────────
「词表缺口」这一类缺陷已经**复发四次**，每一次都是用户在真实对话里撞出来的，
不是我们查出来的：
    ① 用户写「没睡好」  —— 词表里只有「睡不好」
    ② 用户写「特别想」  —— 词表里只有「很想」
    ③ 用户写「在干嘛」  —— 元提问库与闸门词表里只有「干什么」
    ④ 用户写「那你说X」 —— 三层全没接住
每次都靠"补一条词"收场。补词是对的，但**靠用户踩雷来发现该补哪条**是错的：
那是把验证成本转嫁给用户。

这个探针把发现过程机械化：
    从现有词表的每一条短语出发，机械地生成它的**同义变体**，
    再问引擎一遍："这条变体你还认得出吗？"
    认不出 —— 就是候选缺口，列出来给人判。

只做两类变形（因为匹配全部是 `p in text` 子串判定）
────────────────────────────────────────────────────────────
  · **替换**类：换掉短语内部的字（程度副词／否定词／疑问代词）
    —— 子串判定只认原字面，换了字就漏。这正是 ①②③ 的成因。
  · **剥离**类：用户写得比词表短（少主语／少语气词／少体助词／少副词）
    —— 词表条目是子串，用户写短了反而不含它。口语里主语脱落极常见。

不做**追加**类变形（前缀"就/也/还"、后缀"啊/呢"、插入"了"）：
    追加后的文本仍然**含有**原短语，`in` 判定必然命中，
    测不出任何东西 —— 那是假检查，只会刷出一堆"通过"。

本探针**只报告，不修改**任何词表
────────────────────────────────────────────────────────────
纪律：不许为了让探针全绿而去改词表（那是拿语料迁就词表，已经犯过一次）。
探针给出的每一行都是**候选**，自然度未判，须由人逐条判断。

用法：
    python tests\\probe_synonyms.py              # 控制台摘要
    python tests\\probe_synonyms.py --tag 否定互换
    python tests\\probe_synonyms.py --md         # 另写完整 markdown 报告
"""
from __future__ import annotations

import argparse
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_ROOT, os.path.join(_ROOT, "engine")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import markers as M            # noqa: E402
import compose as C            # noqa: E402
import understand as U         # noqa: E402


# ══════════════════════════════════════════════════════════ 变形器

# 程度副词。只在这些副词后面**紧跟情绪/意愿动词**时才替换 ——
# 否则会把「好人」换成「很人」这种垃圾变体，噪声淹没信号。
DEGREE = ["很", "好", "挺", "太", "真", "特别", "非常", "有点", "有点儿", "蛮", "超级"]
DEGREE_FOLLOW = set("想要怕烦累难受担心喜欢讨厌生气难过开心高兴焦虑愧疚后悔委屈孤单孤独绝望无力迷茫")

# 否定词。跟在这些字后面的「不」多半不是否定（不是／不错／不但…），跳过。
NEG_ALT = ["不", "没", "没有", "别"]
NEG_GUARD_AFTER = set("是对错少同断仅过但如光只止良安")

# 疑问代词（③「在干嘛」的成因：干什么 ≠ 干嘛 ≠ 干啥）
WH_ALT = {"什么": ["啥", "嘛"], "怎么": ["咋"], "为什么": ["为啥"]}
WH_MA_ONLY_AFTER = set("干做为")

# 只收**纯语气**词。「吗／吧」不收：剥掉它们会把疑问句变成陈述句、
# 把建议变成断言，**意图都变了** —— 那不是缺口，是另一个句式，
# 拿它当缺口报会刷出一堆假条（实测 19 条里绝大多数是这类）。
TAIL_PARTICLES = ["啊", "呀", "呢", "嘛", "哦", "耶", "唉"]
# 但「干嘛／干啥／做嘛」里的「嘛」是词内的字，不是句尾语气词。
# 实测漏了这道闸就产出「在干嘛→在干」这种把词砍断的变体。
TAIL_KEEP_TAIL = ("干", "做", "啥", "为")

# 可能补语：V不C。C 是**补语**，是一个封闭集，用它当判据。
# 上一版不设这道闸，于是「我是不是→没我是是」「能不能帮→没能能帮」
# 「在不在→没在在」全涌出来 —— 判据一松，报告就废了。
COMPLEMENT_HEADS = set("好了着到成完动住起去来上下出过得见开掉走倒翻透尽够")
POTENTIAL_BAD_IN_A = set("不是在也人有会能要不我你他她它")

# 体助词只剥句尾的「了」。不收「着／过」：实测它们多半是词内的字
# （难过、碰上、睡不着），剥出来是另一个词，不是缺口。
ASPECT_TAIL = "了"

LEAD_ADVERBS = ["就", "也", "还", "都", "一直", "总是", "从来", "根本", "反正"]
# 剥离副词时若会**切开一个双字词**就跳过：
#   也许是→许是 / 就是→是 / 都是→是 / 还是→是 / 还能→能
# 实测这条例外挡住了「也许是我不对→许是我不对」这类垃圾变体。
ADV_SPLIT_GUARD = {"也": set("许"), "就": set("是算要得像"), "都": set("是"),
                   "还": set("是有能好得要"), "总": set("是"), "根": set("本"),
                   "反": set("正"), "一": set("直"), "从": set("来")}
PRONOUNS = ["我们", "他们", "她们", "你们", "咱们", "我", "他", "她", "你", "自己"]

# 否定替换的两个护栏：
#   · 别 —— 只许当**来源**，不许当**目标**。「不知道该说→别知道该说」是垃圾。
#   · 状态动词 —— 「知道／认识／是／喜欢…」加「没」不成话，跳过。
NEG_TARGETS = ["不", "没", "没有"]
NEG_STATIVE = ("知道", "认识", "是", "像", "属于", "需要", "应该", "能", "会",
               "可以", "敢", "肯", "愿意", "值得", "怕", "喜欢", "讨厌", "爱", "恨", "有")


def _v_degree(p: str):
    """程度副词互换。产出四元组，第四项是"词头"，供报告聚合用。"""
    for i, ch in enumerate(p):
        if ch not in DEGREE:
            continue
        if i + 1 >= len(p) or p[i + 1] not in DEGREE_FOLLOW:
            continue
        if i > 0 and p[i - 1] not in PRONOUNS and p[i - 1] not in NEG_ALT:
            continue
        for alt in DEGREE:
            if alt == ch:
                continue
            yield "程度副词互换", p[:i] + alt + p[i + 1:], "%s→%s" % (ch, alt), p[i + 1:]


def _v_negation(p: str):
    """否定互换（同位替换）。别只作来源，不作目标。"""
    for i, ch in enumerate(p):
        if p.startswith("没有", i):
            cur, ln = "没有", 2
        elif ch in ("不", "没", "别"):
            cur, ln = ch, 1
        else:
            continue
        if cur == "不" and i + 1 < len(p) and p[i + 1] in NEG_GUARD_AFTER:
            continue
        if i > 0 and p[i - 1] not in PRONOUNS:
            continue
        tail = p[i + ln:]
        if any(tail.startswith(s) for s in NEG_STATIVE):
            continue
        for alt in NEG_TARGETS:
            if alt == cur:
                continue
            yield "否定互换", p[:i] + alt + tail, "%s→%s" % (cur, alt)


def _v_potential(p: str):
    """可能补语互换：V不C ↔ 没VC。

    加这一条是因为它**正是历史缺口①**的形状：
        用户写「没睡好」，词表里只有「睡不好」。
    上一版的否定替换只处理"否定在词首或代词后"，而「睡不好」的否定在中间，
    根本生成不出来 —— 也就是说那一版**抓不到它本该抓的那个 bug**。
    """
    if p.startswith("没") and 3 <= len(p) <= 4:
        x = p[1:]
        if x[-1] in COMPLEMENT_HEADS and x[0] not in POTENTIAL_BAD_IN_A and x[0] not in "什么怎为多":
            yield "可能补语互换", x[:-1] + "不" + x[-1], "没VC→V不C（历史缺口①方向）"
    m = re.match(r"^(.{1,2})不(.{1})$", p)
    if m:
        a, b = m.group(1), m.group(2)
        if any(ch in POTENTIAL_BAD_IN_A for ch in a):
            return
        if b not in COMPLEMENT_HEADS:
            return                      # 「我是不是」「在不在」在这里被挡住
        if b == "了":
            yield "可能补语互换", "没" + a, "V不了→没V（反向，需人判）"
        else:
            yield "可能补语互换", "没" + a + b, "V不C→没VC（反向，需人判）"


def _v_wh(p: str):
    """疑问代词互换。"""
    for w, alts in WH_ALT.items():
        start = 0
        while True:
            i = p.find(w, start)
            if i < 0:
                break
            start = i + 1
            for alt in alts:
                if alt == "嘛" and (i == 0 or p[i - 1] not in WH_MA_ONLY_AFTER):
                    continue
                yield "疑问代词互换", p[:i] + alt + p[i + len(w):], "%s→%s" % (w, alt)


def _v_tail(p: str):
    """语气词剥离：用户少打一个语气词。"""
    if len(p) > 1 and p[-1] in TAIL_PARTICLES:
        stem = p[:-1]
        if any(stem.endswith(k) for k in TAIL_KEEP_TAIL):
            return                      # 「干嘛」「干啥」：嘛 是词内的字
        yield "语气词剥离", stem, "去掉尾字「%s」" % p[-1]


def _v_aspect(p: str):
    """体助词剥离 —— 只剥句尾那一个「了」，且不剥「V不了」的了。

    上一版允许剥任意位置，于是产出「改变不了别人→改变不别人」
    「你会难过吗→你会难吗」这类切开词的垃圾。
    """
    if len(p) > 1 and p[-1] == ASPECT_TAIL and p[-2] != "不":
        yield "体助词剥离", p[:-1], "去掉句尾「了」"


def _v_subject(p: str):
    """主语剥离：口语里主语脱落极常见。"""
    for pr in PRONOUNS:
        if p.startswith(pr) and len(p) > len(pr) + 1:
            yield "主语剥离", p[len(pr):], "去掉开头「%s」" % pr
            break


def _v_adverb(p: str):
    """副词剥离：去掉开头一个副词（会切开双字词时跳过）。"""
    for adv in LEAD_ADVERBS:
        if not p.startswith(adv) or len(p) <= len(adv) + 1:
            continue
        nxt = p[len(adv)]
        if nxt in ADV_SPLIT_GUARD.get(adv[0], set()):
            continue
        yield "副词剥离", p[len(adv):], "去掉开头「%s」" % adv
        break


TRANSFORMS = [_v_degree, _v_negation, _v_potential, _v_wh, _v_tail,
              _v_aspect, _v_subject, _v_adverb]

# 报告排序：越靠前，越可能是真缺口
TAG_ORDER = ["可能补语互换", "疑问代词互换", "程度副词互换", "否定互换",
             "语气词剥离", "主语剥离", "体助词剥离", "副词剥离"]


def variants(phrase: str) -> list[tuple]:
    out, seen = [], set()
    for fn in TRANSFORMS:
        for item in fn(phrase):
            tag, v, note = item[0], item[1], item[2]
            grp = item[3] if len(item) > 3 else ""
            if not v or v == phrase or v in seen:
                continue
            if len(v) < 2:
                continue
            seen.add(v)
            out.append((tag, v, note, grp))
    return out


# ══════════════════════════════════════════════════════════ 词表来源

_CACHE: dict = {}


def _sources():
    """返回 [(来源名, 归属id, 短语)] 的完整清单。"""
    if _CACHE.get("src"):
        return _CACHE["src"]
    rows = []

    rules = M.load_marker_rules()
    for m in rules["markers"]:
        for p in (m.get("patterns") or []):
            rows.append(("标记层 markers.json", m["id"], p))

    meta = M._load_meta()
    for r in meta.get("questions", []):
        for p in (r.get("rule_patterns") or []):
            rows.append(("元提问 元提问库", r["id"], p))
    for r in meta.get("states", []):
        for p in (r.get("rule_patterns") or []):
            rows.append(("状态陈述 元提问库", r["id"], p))

    for p in U._META_ADDRESS_LEXICON:
        rows.append(("指向系统闸门 understand._META_ADDRESS_LEXICON", "_META_ADDRESS_LEXICON", p))

    atoms, _ = C._load()
    for aid, a in atoms.items():
        lex = a.get("lex") or {}
        for p in (lex.get("triggers") or []):
            rows.append(("原子 triggers atoms.py", aid, p))
        for p in (lex.get("anchors") or []):
            rows.append(("原子 anchors atoms.py", aid, p))

    # 去重：同一条短语同时写在 triggers 与 anchors 里是常见的，
    # 不去重就会把同一件事报两遍，看起来像两个缺口。
    seen, uniq = set(), []
    for r in rows:
        key = (r[0], r[1], r[2])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(r)
    _CACHE["src"] = uniq
    return uniq


# ══════════════════════════════════════════════════════════ 判定或acles

def _fires_marker(text: str) -> set:
    if "marker_engine" not in _CACHE:
        _CACHE["marker_engine"] = M.MarkerEngine()
    try:
        res = _CACHE["marker_engine"].parse(text)
    except Exception:
        return set()
    return {h.id for h in res.hits}


def _fires_meta(text: str) -> set:
    if "meta_engine" not in _CACHE:
        _CACHE["meta_engine"] = M.MarkerEngine()
    try:
        rid, _t = _CACHE["meta_engine"].meta_response(text)
    except Exception:
        return set()
    return {rid} if rid else set()


def _fires_state(text: str) -> set:
    if "meta_engine" not in _CACHE:
        _CACHE["meta_engine"] = M.MarkerEngine()
    try:
        rid, _t = _CACHE["meta_engine"].state_response(text)
    except Exception:
        return set()
    return {rid} if rid else set()


def _fires_atom(text: str) -> set:
    try:
        return set(C.recognize(text))
    except Exception:
        return set()


def _fires_address(text: str) -> set:
    return {"_META_ADDRESS_LEXICON"} if U._addresses_system(text) else set()


ORACLE = {
    "标记层 markers.json": _fires_marker,
    "元提问 元提问库": _fires_meta,
    "状态陈述 元提问库": _fires_state,
    "指向系统闸门 understand._META_ADDRESS_LEXICON": _fires_address,
    "原子 triggers atoms.py": _fires_atom,
    "原子 anchors atoms.py": _fires_atom,
}


# ══════════════════════════════════════════════════════════ 基准不命中的分类

# 一个检查要是把"设计使然 / 被遮蔽 / 真缺陷"混成一锅，它比没有检查更糟：
# 人会去修本来就没坏的东西，同时把真坏的那几条埋在噪声里。
_CONJUNCTIVE = {
    "present_missing": "密度标记：要求同句命中 ≥2 个未来指向词，单条本就不成立",
    "want_like_gap": "联合判定：要求全篇无可体验性描述",
}


def classify_baseline(src: str, owner: str, phrase: str) -> tuple[str, str]:
    if src == "标记层 markers.json":
        rules = M.load_marker_rules()
        rule = next((m for m in rules["markers"] if m["id"] == owner), None)
        if rule:
            if owner in _CONJUNCTIVE:
                return "设计使然", _CONJUNCTIVE[owner]
            sp = rule.get("sub_patterns")
            if sp:
                ops = []
                for k in ("passive", "active"):
                    ops += list(((sp.get(k) or {}).get("examples")) or [])
                if phrase not in ops:
                    return "仅作门控", ("顶层 patterns 只过粗判；证据必须来自 sub_patterns，"
                                        "而它不在其中 → 单独出现时认不出")
    if src.startswith(("元提问", "状态陈述")):
        meta = M._load_meta()
        pool = meta.get("questions") if src.startswith("元提问") else meta.get("states")
        for r in (pool or []):
            if r["id"] == owner:
                continue
            if any(p in phrase for p in (r.get("rule_patterns") or [])):
                return "被遮蔽", "首匹配命中制下，被排在前面的 %s 抢走" % r["id"]
    return "真缺陷", "不在上述任何一类 —— 写了但不生效"


# ══════════════════════════════════════════════════════════ 主流程

def run(tag_filter: str | None = None) -> dict:
    rows = _sources()
    baseline_fail = []
    gaps = []
    checked = 0

    for src, owner, phrase in rows:
        oracle = ORACLE[src]
        base_fires = owner in oracle(phrase)
        if not base_fires:
            kind, why = classify_baseline(src, owner, phrase)
            baseline_fail.append((src, owner, phrase, kind, why))
            continue                      # 基准都不命中：先修基准，谈变体没意义
        for tag, v, note, grp in variants(phrase):
            if tag_filter and tag != tag_filter:
                continue
            checked += 1
            if owner in oracle(v):
                continue
            kind = "筛选器抑制" if phrase in v else "词表缺口"
            gaps.append({"source": src, "owner": owner, "base": phrase,
                         "tag": tag, "variant": v, "note": note,
                         "group": grp, "kind": kind})

    gaps.sort(key=lambda g: (TAG_ORDER.index(g["tag"]) if g["tag"] in TAG_ORDER else 9,
                             g["source"], g["owner"], g["base"]))
    return {"rows": len(rows), "checked": checked, "gaps": gaps,
            "baseline_fail": baseline_fail}


def _degree_groups(gaps: list) -> list:
    """程度副词类按(归属, 词头)聚合。

    不聚合的话这一个类别就刷出 166 行（"好想→超级想""很想→太想"…），
    读不了。而它们的**修法是同一个**：给这个词头补齐副词写法。
    所以聚合成一行才是可执行的形态。

    词头相同但分别写在 triggers 与 anchors 里的，也并成一行 ——
    修的时候本来就是一处补一次。
    """
    box: dict = {}
    for g in gaps:
        if g["tag"] != "程度副词互换":
            continue
        box.setdefault((g["owner"], g["group"]), []).append(g)
    out = []
    for (owner, head), gs in box.items():
        missing, bases, srcs = [], [], []
        for g in gs:
            adv = g["note"].split("→")[-1]          # 取真正的替换副词
            if adv not in missing:
                missing.append(adv)
            if g["base"] not in bases:
                bases.append(g["base"])
            if g["source"] not in srcs:
                srcs.append(g["source"])
        out.append({"sources": srcs, "owner": owner, "head": head,
                    "missing": missing, "bases": bases, "n": len(gs)})
    out.sort(key=lambda d: (-len(d["missing"]), d["owner"]))
    return out


def _report_md(res: dict) -> str:
    L = ["# 同义替换探针报告（候选缺口）", "",
         "本报告由 `tests/probe_synonyms.py` 生成。**只报告，不修改任何词表。**",
         "每一行的自然度**未判**，须逐条人工确认；确认后才改词表。", "",
         "| 项 | 值 |", "|---|---|",
         "| 词表短语总数 | %d |" % res["rows"],
         "| 生成的变体总数 | %d |" % res["checked"],
         "| 候选缺口 | %d |" % len(res["gaps"]),
         "| 基准不命中 | %d |" % len(res["baseline_fail"]), ""]

    if res["baseline_fail"]:
        L += ["## 基准不命中 —— 词表里写着的短语，引擎自己认不出", "",
              "**这里必须分类，不能一锅端。**把一个「设计使然」当成缺陷去修，",
              "会改坏本来正确的东西；把真缺陷埋在噪声里，等于没查。", "",
              "| 来源 | 归属 | 短语 | 性质 | 说明 |", "|---|---|---|---|---|"]
        for s, o, p, k, why in res["baseline_fail"]:
            L.append("| %s | %s | %s | **%s** | %s |" % (s, o, p, k, why))
        L.append("")
        cnt: dict = {}
        for r in res["baseline_fail"]:
            cnt[r[3]] = cnt.get(r[3], 0) + 1
        L += ["分类小计：" + "；".join("%s %d 条" % (k, v) for k, v in cnt.items()), ""]

    by_tag: dict = {}
    for g in res["gaps"]:
        by_tag.setdefault(g["tag"], []).append(g)

    L += ["## 按变形类别统计", "", "| 类别 | 候选数 | 说明 |", "|---|---|---|"]
    _tag_note = {
        "可能补语互换": "**历史缺口①「没睡好」正是这一类**（V不C ↔ 没VC）",
        "疑问代词互换": "历史缺口③「在干嘛」属此类（什么≠啥≠嘛）",
        "程度副词互换": "历史缺口②「特别想」属此类",
        "否定互换": "不／没／没有 同位互换",
        "语气词剥离": "用户少打纯语气词（吗／吧 不计入，剥掉会变意图）",
        "主语剥离": "口语主语脱落（中文极常见）",
        "体助词剥离": "用户少打句尾「了/着/过」",
        "副词剥离": "用户少打开头副词",
    }
    for tag in TAG_ORDER:
        if tag in by_tag:
            L.append("| %s | %d | %s |" % (tag, len(by_tag[tag]), _tag_note.get(tag, "")))
    L.append("")

    # ---- 程度副词类：聚合成可执行形态
    dg = _degree_groups(res["gaps"])
    if dg:
        L += ["## 程度副词互换（聚合，%d 组）" % len(dg), "",
              "这一类的修法是同一个：**给同一个词头补齐副词写法**。",
              "所以按词头聚合成一行，才是可执行的形态；逐条列 166 行读不了。", "",
              "| 来源 | 归属 | 词头 | 词表现有写法 | 缺失写法 | 缺几条 |",
              "|---|---|---|---|---|---|"]
        for d in dg:
            L.append("| %s | %s | %s | %s | %s | %d |" %
                     ("、".join(d["sources"]), d["owner"], d["head"],
                      "／".join(d["bases"]), "／".join(d["missing"]), d["n"]))
        L.append("")

    for tag in TAG_ORDER:
        if tag == "程度副词互换":
            continue
        gs = by_tag.get(tag)
        if not gs:
            continue
        L += ["## %s（%d 条）" % (tag, len(gs)), "",
              "| 来源 | 归属 | 词表原短语 | 变体 | 变形 | 判定 |", "|---|---|---|---|---|---|"]
        for g in gs:
            L.append("| %s | %s | %s | %s | %s | %s |" %
                     (g["source"], g["owner"], g["base"], g["variant"], g["note"], g["kind"]))
        L.append("")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default=None)
    ap.add_argument("--md", action="store_true")
    ap.add_argument("--top", type=int, default=6)
    a = ap.parse_args()

    res = run(a.tag)

    print("=" * 70)
    print("同义替换探针 —— 机械查找词表缺口")
    print("=" * 70)
    print("词表短语总数        : %d" % res["rows"])
    print("生成的变体总数      : %d" % res["checked"])
    print("候选缺口            : %d" % len(res["gaps"]))
    print("基准不命中          : %d" % len(res["baseline_fail"]))

    if res["baseline_fail"]:
        cnt: dict = {}
        for r in res["baseline_fail"]:
            cnt.setdefault(r[3], []).append(r)
        print("\n【基准不命中 · 已分类】")
        for k in ("真缺陷", "被遮蔽", "仅作门控", "设计使然"):
            if k not in cnt:
                continue
            print("  ■ %s（%d 条）" % (k, len(cnt[k])))
            for s, o, p, _k, why in cnt[k]:
                print("      %-18s %-14s %s" % (o, p, why))

    by_tag: dict = {}
    for g in res["gaps"]:
        by_tag.setdefault(g["tag"], []).append(g)
    print("\n【候选缺口 · 按类别】")
    for tag in TAG_ORDER:
        if tag in by_tag:
            extra = "（聚合见 markdown）" if tag == "程度副词互换" else ""
            print("   %-12s %4d 条 %s" % (tag, len(by_tag[tag]), extra))

    print("\n各类别前 %d 条：" % a.top)
    for tag in TAG_ORDER:
        gs = by_tag.get(tag)
        if not gs:
            continue
        print("\n  ── %s ──" % tag)
        if tag == "程度副词互换":
            for d in _degree_groups(gs)[:a.top]:
                print("     [%s] 词头「%s」缺：%s" % (d["owner"], d["head"], "／".join(d["missing"])))
            continue
        for g in gs[:a.top]:
            print("     [%s·%s] %s →「%s」" % (g["owner"], g["source"].split()[0],
                                              g["base"], g["variant"]))
        if len(gs) > a.top:
            print("     …共 %d 条" % len(gs))

    if a.md:
        out = os.path.join(_HERE, "_同义替换_候选缺口.md")
        with open(out, "w", encoding="utf-8") as f:
            f.write(_report_md(res))
        print("\n完整报告已写入：%s" % out)

    print("\n注意：本探针只报告。候选缺口须逐条人工判断自然度后才改词表，")
    print("      不许为了让它全绿而迁就词表。")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
