# -*- coding: utf-8 -*-
"""共用打分器（H5 用）—— 只做**能自动判**的部分。

★ 用户裁定：
  「打分函数抽成共用模块；只实现能自动判的部分（问号结尾率、空承接、固定短语重复）；
    需要人判的写明"需评审"。」

★ 这个模块**不判**这些（一律进 `needs_review`）：
  · 是否有自己的看法（语义）
  · 是否同意/不同意他是否恰当（语义）
  · 是否"像人"（语义）
"""
import re

#: 阈值（v2 的默认值，标【默认，待标定】）
THRESHOLDS = {
    "H1a": 0.80,   # 他问她 ⇒ 第一句直接回应的比例 ≥ 80%
    "H1b": 0.10,   # 空承接占比 ≤ 10%
    "H2a": 0.60,   # 以问号结尾的轮占比 ≤ 60%
    "H2b_pairs": 0,        # 相邻两轮同一句式开头 = 0
    "H2b_phrase": 2,       # 同一固定短语每场 ≤ 2 次
}

_EMPTY_ACK = re.compile(r"^(?:(?:嗯|哦|好|是|对)[。，、！…\s]*)*(?:我听着|我在听|我在|记下了)?[。，、！…\s]*$")
_ASKING = re.compile(r"[？?]\s*$")


def _is_q(s):
    return bool(_ASKING.search((s or "").strip()))


def _is_empty_ack(s):
    return bool(_EMPTY_ACK.match((s or "").strip()))


def _he_asks(raw):
    """他最后一句是不是问句（宽口径，与 engine 的 association.asks_her 同义）。"""
    t = (raw or "").strip()
    if not t:
        return False
    parts = [x for x in t.replace("！", "。").replace("!", "。").split("。") if x.strip()]
    seg = parts[-1] if parts else t
    return ("？" in seg) or ("?" in seg)


def _head4(s):
    return (s or "").strip()[:4]


#: 假系统 A：永远同一句空承接
def fake_a(raw):
    return "嗯，我听着。"


#: 假系统 B：永远把他最后一句改成一个问句
def fake_b(raw):
    t = (raw or "").strip().rstrip("。！？?!")
    return "你是说「%s」？" % (t[:12] if t else "这个")


def score_turns(turns):
    """对一组 `{raw, output}` 打分。

    返回 dict（全部是 0..1 的比例，或计数）：
      H1a  他问她时第一句不是问句的比例
      H1b  空承接占比
      H2a  以问号结尾的比例
      H2b_pairs  相邻两轮同一开头（前 4 字）的对数
      H2b_phrase 同一固定短语的最大出现次数
      pass_*     按阈值判的布尔
      needs_review  需人判的条目名
    """
    n = max(1, len(turns))
    ask = [t for t in turns if _he_asks(t.get("raw"))]
    h1a_hit = 0
    for t in ask:
        out = (t.get("output") or "").strip()
        first = re.split(r"(?<=[。！？…])", out, maxsplit=1)[0]
        if not _is_q(first):
            h1a_hit += 1
    h1a = (h1a_hit / len(ask)) if ask else 0.0
    h1b = sum(1 for t in turns if _is_empty_ack(t.get("output"))) / n
    h2a = sum(1 for t in turns if _is_q(t.get("output"))) / n
    pairs = 0
    for i in range(1, len(turns)):
        if _head4(turns[i - 1].get("output")) == _head4(turns[i].get("output")):
            pairs += 1
    phrases = ("我还在想", "我想知道的是", "倒是")
    max_phr = 0
    for w in phrases:
        max_phr = max(max_phr, sum(1 for t in turns if w in (t.get("output") or "")))

    return {
        "n": len(turns),
        "H1a": h1a,
        "H1b": h1b,
        "H2a": h2a,
        "H2b_pairs": pairs,
        "H2b_phrase": max_phr,
        "pass_H1a": h1a >= THRESHOLDS["H1a"],
        "pass_H1b": h1b <= THRESHOLDS["H1b"],
        "pass_H2a": h2a <= THRESHOLDS["H2a"],
        "pass_H2b_pairs": pairs <= THRESHOLDS["H2b_pairs"],
        "pass_H2b_phrase": max_phr <= THRESHOLDS["H2b_phrase"],
        # ★ 这些判不了，必须人看
        "needs_review": [
            "H1a_质量（回应是否对得上问题，而不是「不是问句」就算）",
            "H1b_是否真的空（「嗯」后面接了一句也算有内容？）",
            "H3_前后一致（同一说法的表态是否相反）",
            "H4_越界（是否替他判定什么才算重要）",
            "H6b_编造经历（是否确认了他预设的「她说过」）",
        ],
    }
