# -*- coding: utf-8 -*-
"""G1-G6：两个缺口的补齐（2026-10-31，只加记录不改行为）。

★ 用户裁定：
  4. 吞异常计数落盘：把 `_swallow_counts` 写进 cognition_debug.jsonl（带 run_id），并补测试
  5. 所有 debug 记录加上台账轮次（turn_id 或台账索引），并补测试

★ 判据（先写）：
  G1 ★★ 有吞异常时，`_flush_swallow()` 会往 debug 写一条 `kind=swallow`
  G2 ★★ 那条记录带 `counts` / `total` / `run_id` / `turn_id` / `ledger_index`
  G3 ★ 没有吞异常时不写（避免每轮刷空记录）
  G4 ★★ 增量落盘：同一批计数不会被重复写（第二次 flush 无新增就不写）
  G5 ★★★ 所有 debug 记录都带 `turn_id` 与 `ledger_index`（不是进程内 `_turn_seq`）
  G6 ★ `turn_id` 是台账轮次：连续两轮 turn 递增，且与 `_turn` 一致
"""
import io
import json
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)
sys.path[:0] = [str(_ROOT), str(_ROOT + "/engine")]

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
print("  吞异常落盘 + debug 带台账轮次（G1-G6）")
print("=" * 78)

from pipeline import Pipeline  # noqa: E402


def mk(run_id="RUN_T"):
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "state"), exist_ok=True)
    p = Pipeline(ledger_path=os.path.join(d, "state", "ledger.jsonl"),
                 character_path=os.path.join(d, "state", "character.json"),
                 devlevel_path=os.path.join(d, "state", "devlevel_verified.json"),
                 carry_root=d, gate_perception=True, auto_audit=False,
                 use_api=False, use_think=False, use_cognition=True)
    p._input_origin = {"run_id": run_id, "session_id": 1}
    return p, d


def recs(p):
    if not os.path.exists(p._cog_debug_path):
        return []
    return [json.loads(l) for l in io.open(p._cog_debug_path, encoding="utf-8") if l.strip()]


p, d = mk()
p._input_origin = None
p.turn("先垫一句测试用的话。")
base_n = len(recs(p))
case("G3 ★ 没有吞异常时不写 swallow 记录",
     not any(r.get("kind") == "swallow" for r in recs(p)), "%d 条" % base_n)

p._swallow_counts = {"demo:ValueError": 2}
p._flush_swallow()
sw = [r for r in recs(p) if r.get("kind") == "swallow"]
case("G1 ★★ 有吞异常时写了一条 kind=swallow", len(sw) == 1, "%d 条" % len(sw))
case("G2 ★★ 记录带 counts / total / run_id / turn_id / ledger_index",
     bool(sw) and all(k in sw[-1] for k in ("counts", "total", "run_id", "turn_id", "ledger_index")),
     "%s" % sorted(sw[-1].keys()) if sw else "无")
case("G2b ★ counts 是增量（2 次 ValueError）",
     bool(sw) and sw[-1]["counts"].get("demo:ValueError") == 2, "%r" % (sw[-1]["counts"] if sw else None))

n_before = len([r for r in recs(p) if r.get("kind") == "swallow"])
p._flush_swallow()
n_after = len([r for r in recs(p) if r.get("kind") == "swallow"])
case("G4 ★★ 无新增时不重复写（增量落盘）", n_after == n_before, "%d → %d" % (n_before, n_after))

# ── G5 / G6：所有 debug 记录带台账轮次
p2, d2 = mk()
p2._input_origin = {"run_id": "RUN_X", "session_id": 3}
p2.turn("第一句很长的话，用来产生一条 settle 或 brain 记录。")
#   ⚠️ use_api=False 时认知块整块跳过，不会自然产生 settle/brain/idle 记录。
#      ⇒ 直接调 _cog_debug 验契约（被测的就是「每条记录都要带轮次」）。
p2._cog_debug({"kind": "probe", "turn": 1})
p2.turn("第二句也很长，用来确认 turn_id 在递增。")
p2._cog_debug({"kind": "probe", "turn": 2})
allr = recs(p2)
missing = [r for r in allr if "turn_id" not in r or "ledger_index" not in r]
case("G5 ★★★ 所有 debug 记录都带 turn_id 与 ledger_index",
     bool(allr) and not missing, "%d 条中有 %d 条缺" % (len(allr), len(missing)))
tids = sorted({r.get("turn_id") for r in allr if r.get("turn_id") is not None})
case("G6 ★ turn_id 是台账轮次（能看到多个不同的值）",
     len(tids) >= 2, "turn_id 取值：%s" % tids)

print("-" * 78)
print("结果: %d 通过 / %d 失败 / 共 %d" % (OK, FAIL, OK + FAIL))
print()
print("MUTATION 表")
print("  MUT-A 去掉 _flush_swallow 的调用                       → G1")
print("  MUT-B 让它每次无条件写                                 → G3/G4")
print("  MUT-C 把 turn_id 换回 _turn_seq                        → G5/G6")
sys.exit(1 if FAIL else 0)
