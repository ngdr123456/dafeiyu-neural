# -*- coding: utf-8 -*-
"""Q1-Q6：可核对序列**端到端**能产出已确认动作（用户裁定 2026-10-28「按甲来」）。

事由：
  训练池 36 条全是开放式半句 ⇒ 6 轮训练 decision 全 NOT_OFFERED
  ⇒ 动作不可确认 ⇒ 经验层学不到东西。
  ⇒ 加 corpus/sequences.json：断言 → 更正 → 查询，三段。

  为什么必须三段、不能一条自足（实测）：
    ① project() 把当前输入排除在可引用来源外（sources 过滤 current:）
    ② 同一输入既断言又查询 ⇒ 断言被判 unsafe 降级

本测试钉住：
  · 序列池本身合法（断言句无否决词、查询句只有一个对象且有问号）
  · 播放整条序列后：decision=SELECTED、targets≥1、state=FULFILLED_LITERAL、
    actual=QUOTE_SOURCE_SET_CONFIRMED
  · 漏引一段时不确认（不许把没做到算做到）

⚠️ 变异纪律：见文件尾表。
"""
import io
import json
import os
import re
import sys
import tempfile
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)
sys.path[:0] = [str(_ROOT), str(_ROOT + "/engine"), str(_ROOT + "/tests")]

from test_relational_memory import Reader, origin, pipe  # noqa: E402
from test_self_goal import GoalReader  # noqa: E402
from think import Thinker  # noqa: E402
import train  # noqa: E402

OK = 0
FAIL = 0
VETO = r"[？?]|如果|假如|也许|可能|不是|并非|不由|不在|不要|不能|没说"
PREDICATE = r"收着|保管|代收|联系|在哪|哪里|何处"


def case(name, cond, why=""):
    global OK, FAIL
    if cond:
        OK += 1
        print("  [PASS] 【%s】" % name)
    else:
        FAIL += 1
        print("  [FAIL] 【%s】%s" % (name, why))


# ── 造命题：按原文精确定位（不能用 start=0/end=len，否则整段算一句，全被降级）
def propositions(raw, claims):
    props = []
    for subject, value, predicate, corr, phrase in claims:
        start = raw.index(phrase)
        props.append({"subject": subject, "predicate": predicate, "value": value,
                      "time": "", "role": "ASSERTED", "correction": corr,
                      "start": start, "end": start + len(phrase), "evidence": phrase})
    return {"propositions": props}


S01 = [
    ("甲项目押金由李老师收着。",
     [("甲项目押金", "李老师", "custodian", False, "甲项目押金由李老师收着。")]),
    ("更正：甲项目押金由周老师收着。",
     [("甲项目押金", "周老师", "custodian", True, "甲项目押金由周老师收着。")]),
    ("甲项目押金由谁收着？照原话引出来。", []),
]
S02 = [
    ("甲项目押金由赵老师收着。",
     [("甲项目押金", "赵老师", "custodian", False, "甲项目押金由赵老师收着。")]),
    ("甲项目押金由钱老师收着。",
     [("甲项目押金", "钱老师", "custodian", False, "甲项目押金由钱老师收着。")]),
    ("甲项目押金到底由谁收着？照原话引出来。", []),
]
GOOD_S01 = "按你原话，「甲项目押金由周老师收着。」——这是你更正之后说的。实际由谁收着，我这边没法核实。"
GOOD_S02 = ("按你原话，一次是「甲项目押金由赵老师收着。」，另一次是「甲项目押金由钱老师收着。」。"
            "两句都在，谁最后为准我这边没有定论。")
BAD_S02 = "按你原话，「甲项目押金由赵老师收着。」。就这一条。"

print("=" * 78)
print("  可核对序列端到端（Q1-Q6）")
print("=" * 78)

# ── Q1 序列池合法：断言句不含否决词
seqs = train.load_sequences()
bad = []
for s in seqs:
    for i, t in enumerate(s["turns"]):
        is_query = bool(re.search(r"[？?]|告诉我|查一下|核对一下", t["text"]))
        if not is_query and re.search(VETO, t["text"]):
            bad.append((s["id"], i + 1, t["text"]))
case("Q1 断言句不含否决词（？如果也许可能不是并非不由…）", not bad, bad)

# ── Q2 查询句必须有问号或"告诉我"，且只提一个对象
bad2 = []
for s in seqs:
    q = s["turns"][-1]["text"]
    if not re.search(r"[？?]|告诉我|查一下|核对一下", q):
        bad2.append((s["id"], "无问号"))
    # 只用最直白的判据：查询句里必须恰好出现**一个**「X项目」
    names = set(re.findall(r"[甲乙丙丁戊]项目", q))
    if len(names) != 1:
        bad2.append((s["id"], "查询句提到 %d 个对象：%s" % (len(names), sorted(names))))
case("Q2 查询句有问号且只提一个对象（否则 ambiguous_subject）", not bad2, bad2)

# ── Q3 加载器必须**过滤掉**不足 2 轮的条目
#   ⚠️ 第一版是 `all(len(s["turns"]) >= 2 for s in seqs)` —— 那条**永远不可能失败**：
#      加载器自己就把不足 2 轮的丢了，所以断言恒真。
#      （这正是本项目反复警惕的"不可能失败的测试"。）
#   现在用注入路径喂一个含 1 轮条目的文件，直接测过滤器。
import json as _json  # noqa: E402
import tempfile as _tf  # noqa: E402

with _tf.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as _fh:
    _json.dump({"sequences": [
        {"id": "BAD1", "turns": [{"text": "只有一个断言，没有查询。"}]},
        {"id": "OK1", "turns": [{"text": "甲项目押金由李老师收着。"},
                                {"text": "甲项目押金由谁收着？"}]},
        {"id": "BAD2", "turns": [{"text": "  "}, {"text": ""}]},
    ]}, _fh, ensure_ascii=False)
    _p = _fh.name
_loaded = train.load_sequences(_p)
os.unlink(_p)
_ids = [s["id"] for s in _loaded]
case("Q3 加载器过滤掉不足 2 轮的条目（1 轮、全空白都丢）",
     _ids == ["OK1"], "加载到 %s（应为 ['OK1']）" % _ids)


def play(turns, good):
    with tempfile.TemporaryDirectory() as tmp:
        p = pipe(Path(tmp), use_api=True)
        p.reader = Reader({raw: propositions(raw, claims) for raw, claims in turns})
        p.thinker = Thinker(GoalReader([good] * 8, choices=["FIRST"]))
        result = None
        for raw, _ in turns:
            result = p.turn(raw, input_origin=origin(raw))
        return result


# ── Q4 ★ 单值序列（断言 → 更正 → 查询）
r = play(S01, GOOD_S01)
gs = ((r.self_action or {}).get("goal_selection") or {})
sel = gs.get("selected") or {}
tg = sel.get("targets") or []
ao = r.action_observation or {}
case("Q4 ★ 单值序列 → SELECTED、targets≥1、FULFILLED_LITERAL、QUOTE_SOURCE_SET_CONFIRMED",
     gs.get("decision") == "SELECTED" and len(tg) >= 1
     and (gs.get("result") or {}).get("state") == "FULFILLED_LITERAL"
     and ao.get("actual") == "QUOTE_SOURCE_SET_CONFIRMED",
     "decision=%r targets=%d state=%r actual=%r"
     % (gs.get("decision"), len(tg), (gs.get("result") or {}).get("state"), ao.get("actual")))

# ── Q5 ★ 冲突序列（两个值并存）→ targets 必须是 2，且逐字核对要通过
r = play(S02, GOOD_S02)
gs = ((r.self_action or {}).get("goal_selection") or {})
tg = (gs.get("selected") or {}).get("targets") or []
ao = r.action_observation or {}
case("Q5 ★ 冲突序列 → targets == 2 且逐字核对通过、动作被确认",
     gs.get("decision") == "SELECTED" and len(tg) == 2
     and (gs.get("result") or {}).get("state") == "FULFILLED_LITERAL"
     and ao.get("actual") == "QUOTE_SOURCE_SET_CONFIRMED",
     "decision=%r targets=%d state=%r actual=%r"
     % (gs.get("decision"), len(tg), (gs.get("result") or {}).get("state"), ao.get("actual")))

# ── Q6 漏引一段 → 不确认（不许把没做到算做到）
r = play(S02, BAD_S02)
ao = r.action_observation or {}
case("Q6 漏引一段 → actual 不是 QUOTE_SOURCE_SET_CONFIRMED",
     ao.get("actual") != "QUOTE_SOURCE_SET_CONFIRMED",
     "actual=%r confirmed=%r" % (ao.get("actual"), ao.get("confirmed")))

print("-" * 78)
print("结果: %d 通过 / %d 失败 / 共 %d" % (OK, FAIL, OK + FAIL))
print()
print("MUTATION 表")
print("  M1 序列池里给断言句加「如果」                  → Q1")
print("  M2 查询句改提两个对象                          → Q2")
print("  M3 每条序列只留 1 轮                           → Q3")
print("  M4 把 observe 的 goal 分支删掉                 → Q4")
print("  M5 literal_check 的 missing 永远 []            → Q6")
sys.exit(1 if FAIL else 0)
