# -*- coding: utf-8 -*-
"""M1-M6：H6(b) **根源记忆 + 语义判别**（2026-11-01）。

★ 用户裁定的架构准则：
  「严禁靠堆砌按字匹配的关键词黑名单和反拦截正则补丁去堵她的嘴」
  ⇒ 本测试**不测任何字面禁词**，只测两个根源：
    ① 本场记忆保底（她看得见自己前几句）
    ② 首轮明确化（"这是本场第 1 轮"）
    ③ content_fidelity 里有语义判别条款

★ 判据（先写）：
  M1 ★★★ 首轮 `format_history([])` 明确输出「本场对话的第 1 轮」
  M2 ★★★ 同场前序轮次**即使无关键词重合**也保底进 `dialogue_sources`
  M3 ★★  保底最多 5 条
  M4 ★★  content_fidelity.SYSTEM 含防奉承顺认的语义条款
  M5 ★★★ `think.py` 里**没有**新增字面禁词（防「这点我认」那类被误杀）
  M6 ★   `association.py` 里**没有** `past_attribution`/`comply_violations`（已回退）
"""
import io
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)
sys.path[:0] = [str(_ROOT), str(_ROOT + "/engine"), str(_ROOT + "/state")]

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


print("=" * 78)
print("  H6(b) 根源记忆 + 语义判别（M1-M6）")
print("=" * 78)

# ── M1：首轮明确化
from dialogue_memory import format_history  # noqa: E402

out = format_history([])
case("M1 ★★★ 首轮明确输出「本场对话的第 1 轮」",
     "第 1 轮" in out and "没有说过任何话" in out, "%r" % out[:50])

# ── M2 / M3：同场保底
from pipeline import Pipeline  # noqa: E402
import tempfile  # noqa: E402


def mk():
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "state"), exist_ok=True)
    return Pipeline(ledger_path=os.path.join(d, "state", "ledger.jsonl"),
                    character_path=os.path.join(d, "state", "character.json"),
                    devlevel_path=os.path.join(d, "state", "devlevel_verified.json"),
                    carry_root=d, gate_perception=True, auto_audit=False,
                    use_api=False, use_think=False, use_cognition=True)


p = mk()
# 造 7 轮同场历史（内容互不相关 —— 关键词检索捞不到）
TOPICS = [
    "我妈住院那回我在走廊站了一夜。",
    "出院那天东西收拾了一大包。",
    "医院那地方我一向不喜欢。",
    "现在想想那阵子也就是那么熬过来的。",
    "昨天买菜为了两块钱磨了半天。",
    "楼上装修吵得我睡不着。",
    "手机屏幕摔裂了一道。",
]
#   ⚠️ `p._input_origin = {...}` 无效 —— `turn()` 会用
#      `normalize(input_origin=None, ...)` 把它覆盖掉。
#      必须**作为参数传进去**。
#   ★ `normalize()` 要求 origin 里带 schema/input_sha256/topic_id 且必须与 raw 对得上，
#     所以用 `origin()` 助手构造（它在 test_relational_memory 里已有同名实现）。
from input_provenance import digest as _digest

def _orig(raw, rid="SEED", sid=1):
    return {"schema": 1, "kind": "engineered_scripted", "input_sha256": _digest(raw),
            "topic_id": None, "independent_human_input_verified": False,
            "run_id": rid, "session_id": sid}

for k, raw in enumerate(TOPICS):
    p.turn(raw, input_origin=_orig(raw))

# 最后问一个跟前面全无关键词重合的话
Q = "你说这事还有别的说法吗？"
p._input_origin = {"run_id": "SEED", "session_id": 1}
pr = p.markers.parse(Q, None)
fr = p._build_frame(Q, pr)
srcs = fr.dialogue_sources or []
same_sess = [s for s in srcs if (s.get("origin") or "") == "同场保底"]
case("M2 ★★★ 同场前序轮次即使无关键词重合也保底进 sources",
     len(srcs) > 0, "sources=%d 条（其中同场保底 %d 条）" % (len(srcs), len(same_sess)))
case("M3 ★★ 保底最多 5 条", len(same_sess) <= 5,
     "同场保底 %d 条" % len(same_sess))

# ── M4：语义条款
t = io.open(os.path.join(_ROOT, "engine", "content_fidelity.py"), encoding="utf-8").read()
case("M4 ★★ content_fidelity.SYSTEM 含防奉承顺认语义条款",
     "奉承式承认" in t and "unsupported_fact" in t)

# ── M5：think.py 里没有新增字面禁词
think_src = io.open(os.path.join(_ROOT, "engine", "think.py"), encoding="utf-8").read()
case("M5 ★★★ think.py 里没有新增字面禁词（「这点我认」等）",
     "这点我认" not in think_src and "comply_violations" not in think_src)

# ── M6：association.py 已回退
assoc_src = io.open(os.path.join(_ROOT, "engine", "association.py"), encoding="utf-8").read()
case("M6 ★ association.py 里没有 past_attribution / comply_violations（已回退）",
     "def past_attribution" not in assoc_src
     and "def comply_violations" not in assoc_src)

print("-" * 78)
print("结果: %d 通过 / %d 失败 / 共 %d" % (OK, FAIL, OK + FAIL))
print()
print("MUTATION 表")
print("  MUT-A 删掉同场保底                                   → M2")
print("  MUT-B format_history 改回「（没有可用的同一来源对话）」 → M1")
print("  MUT-C 把「这点我认」塞进 think.py 当禁词              → M5")
sys.exit(1 if FAIL else 0)
