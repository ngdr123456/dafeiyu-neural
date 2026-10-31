# -*- coding: utf-8 -*-
"""M1-M6：META 收窄（2026-10-28，Gemini 第三封发现 3，用户已批）。

★ 病灶（实测）：
    有 mech 的 24 行里 20 行（83%）planned_behavior=META_REPLY，
    且 w **全部 9.4**、phase 全部 NO_TENSION、_carried 20/24 —— 死快照。
    ⇒ 机制层在这条路上整条被跳过。

★ 修法：
    `intent == "META"` 时先收窄：只要话里有生活锚点或心理标记、且不是在问系统本身，
    就归还主干道（ANSWER），让 mech.step() 照常跑。

★ 判据（先写）：
  M1 带生活锚点的倾诉（"你说我是不是有毛病"）不得走 META
  M2 真元提问（"你是什么模型"）必须仍走 META
  M3 带心理标记的话不得走 META
  M4 归还主干道后，台账 mech 的 _carried 不得为 True（机制层真的跑了）
  M5 收窄留痕进了 notes（可追溯）
  M6 纯元提问（"你是谁"）仍走 META
"""
import json
import os
import re
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)
sys.path[:0] = [str(_ROOT), str(_ROOT + "/engine")]

from pipeline import Pipeline  # noqa: E402

OK = 0
FAIL = 0


def case(name, cond, why=""):
    global OK, FAIL
    if cond:
        OK += 1
        print("  [PASS] 【%s】" % name)
    else:
        FAIL += 1
        print("  [FAIL] 【%s】%s" % (name, why))


def run(raw):
    d = tempfile.mkdtemp()
    p = Pipeline(ledger_path=os.path.join(d, "state/ledger.jsonl"),
                 character_path=os.path.join(d, "state/character.json"),
                 devlevel_path=os.path.join(d, "state/devlevel_verified.json"),
                 carry_root=d, gate_perception=True, auto_audit=False,
                 use_api=False, use_think=False)
    r = p.turn(raw)
    # pr.notes 写进台账（`_log(..., _extra + pr.notes, ...)`），TurnResult.notes 只带一部分
    r._ledger_notes = list(p.ledger.effective_entries[-1].notes or [])
    return r


print("=" * 78)
print("  META 收窄（M1-M6）")
print("=" * 78)

# ── M1 ★ 带生活锚点的倾诉
r = run("就……连手机都懒得刷，躺那儿盯着天花板发呆，你说我这是不是有点毛病啊。")
case("M1 ★ 带生活锚点的倾诉不走 META",
     r.channel != "META" and r.planned_behavior != "META_REPLY",
     "channel=%r planned=%r" % (r.channel, r.planned_behavior))

# ── M2 ★ 真元提问仍走 META
r = run("你现在用的是什么模型？")
case("M2 ★ 真元提问（什么模型）仍走 META",
     r.channel == "META" or r.planned_behavior == "META_REPLY",
     "channel=%r planned=%r" % (r.channel, r.planned_behavior))

# ── M3 带心理标记的话不走 META
r = run("我一定要让他们看到，你说我这样是不是太拼了。")
case("M3 带心理标记的话不走 META",
     r.planned_behavior != "META_REPLY",
     "planned=%r markers=%s" % (r.planned_behavior, r.markers))

# ── M4 ★ 归还主干道后机制层真的跑了
r = run("我妈只问了一句第一是谁，你说我考第三名还有什么意思。")
mech = r.mech or {}
case("M4 ★ 机制层真的跑了（mech 存在且 _carried 不为 True）",
     bool(mech) and not mech.get("_carried"),
     "mech keys=%s carried=%r" % (sorted(mech.keys())[:6], mech.get("_carried")))

# ── M5 收窄留痕进台账
r = run("话是这么说，可我上礼拜来的时候那盆绿萝还活着呢，你说我这是不是没照顾好。")
hit = [n for n in getattr(r, "_ledger_notes", []) if "META 收窄" in n]
case("M5 收窄留痕进了台账 notes（可追溯）", bool(hit),
     "notes=%s" % getattr(r, "_ledger_notes", [])[:3])

# ── M6 纯元提问仍走 META
r = run("你是谁？")
case("M6 纯元提问（你是谁）仍走 META",
     r.planned_behavior == "META_REPLY" or r.channel == "META",
     "channel=%r planned=%r" % (r.channel, r.planned_behavior))

# ── M7 ★ 长句的显式系统问题仍走 META（`_sys_q` 的唯一用武之地）
#   实测：真元提问都很短（<15 字），所以长度判据已经能排除它们；
#   `_sys_q` 只在"长句 + 显式问系统"时起作用。没有这条用例，
#   把 `not _sys_q` 删掉都不会有测试失败（MUT-A 抓不到）。
r = run("你能不能解释一下你是怎么判断我刚才说的那句话的？你到底是什么程序。")
case("M7 ★ 长句的显式系统问题仍走 META",
     r.channel == "META" or r.planned_behavior == "META_REPLY",
     "channel=%r planned=%r len=%d" % (r.channel, r.planned_behavior, len(
         "你能不能解释一下你是怎么判断我刚才说的那句话的？你到底是什么程序。")))

print("-" * 78)
print("结果: %d 通过 / %d 失败 / 共 %d" % (OK, FAIL, OK + FAIL))
print()
print("MUTATION 表")
print("  MUT-A 去掉 `not _sys_q and` 条件        → M2、M6")
print("  MUT-B 去掉 `bool(_life) or bool(pr.markers)` → M1、M3")
print("  MUT-C 收窄后不改 intent（只记 notes）    → M1、M4")
sys.exit(1 if FAIL else 0)
