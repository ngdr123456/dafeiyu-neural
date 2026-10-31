# -*- coding: utf-8 -*-
"""F1-F8：失败分类（A/B/C）与落盘（2026-10-30）。

★ 依据：甲方决定 ——
  · C 类（自身代码异常）**必须 0 次才算通过**；同一批出现 2 次以上，实测自动中止并报警
  · A 类重试后仍失败的轮，列出次数和原因，不设硬指标
  · B 类按原因列出，不设上限

★ 判据（先写）：
  F1 ★ A 类：网络/超时错误归 A
  F2 ★★ C 类：自身代码异常归 C（**含 ValueError**）
  F3 ★ B 类：有 violations / reason 的归 B
  F4 ★ 没失败 ⇒ 空串
  F5 ★★ **优先级：C 先于 A**（`ValueError` 不得被当成网络错误）
  F6 ★ 未知异常保守归 C（不归 A —— 不可归因的异常不该当网络抖动）
  F7 ★ brain 记录会落盘（成功与失败都落）
  F8 ★ 失败记录的 retry_log 字段存在（下一批要往里写重试记录）
"""
import io
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
print("  失败分类（F1-F8）")
print("=" * 78)

from association import classify_failure, failure_detail  # noqa: E402

case("F1 ★ A 类：HTTPError / TimeoutError / ConnectionError 都归 A",
     all(classify_failure(x) == "A"
         for x in ("HTTPError", "TimeoutError", "ConnectionError", "URLError")),
     str([(x, classify_failure(x)) for x in ("HTTPError", "TimeoutError",
                                              "ConnectionError", "URLError")]))
case("F2 ★★ C 类：ValueError / KeyError / TypeError 都归 C",
     all(classify_failure(x) == "C" for x in ("ValueError", "KeyError", "TypeError")),
     str([(x, classify_failure(x)) for x in ("ValueError", "KeyError", "TypeError")]))
case("F3 ★ B 类：有 violations 或无 error_type 但有 reason 的归 B",
     classify_failure("", ["REJECT"]) == "B" and classify_failure("", [], "rejected") == "B")
case("F4 ★ 没失败 ⇒ 空串", classify_failure("", [], "") == "")
case("F5 ★★ 优先级：C 先于 A（`ValueError` 不得被当网络错误）",
     classify_failure("ValueError") == "C" and classify_failure("HTTPError") == "A")
case("F6 ★ 未知异常保守归 C（不归 A）",
     classify_failure("WeirdUnknownError") == "C",
     classify_failure("WeirdUnknownError"))
#   ⚠️ 2026-10-30 更正我自己一处混淆：
#      `failure_detail` 是**给日志的**，内部词在里面是对的（查问题时正要看它）。
#      要清洗的是**给她看的那一份** —— 那是 `plain_violation_text`。
from association import plain_violation_text  # noqa: E402

_V = ["候选断言不存在「上次失败」，但 memory_scope 表明仅有有限片段、"
      "record_absence_verified=false，不能据此作全局否定。"]
_P = plain_violation_text("", _V)
case("F6b ★★ **给她的**那份不含内部词（memory_scope / record_absence_verified）",
     "memory_scope" not in _P and "record_absence_verified" not in _P,
     "%r" % _P[:60])
case("F6c ★ 改写后仍读得懂（不是被抹成空串）",
     len(_P) > 8 and ("记录" in _P or "确认" in _P), "len=%d" % len(_P))

# ── F7：brain 记录落盘（直接调 _cog_debug 验契约）
from pipeline import Pipeline  # noqa: E402

d = tempfile.mkdtemp()
os.makedirs(os.path.join(d, "state"), exist_ok=True)
p = Pipeline(ledger_path=os.path.join(d, "state", "ledger.jsonl"),
             character_path=os.path.join(d, "state", "character.json"),
             devlevel_path=os.path.join(d, "state", "devlevel_verified.json"),
             carry_root=d, gate_perception=True, auto_audit=False,
             use_api=False, use_think=False, use_cognition=True)
p._cog_debug({"kind": "brain", "turn": 1, "mode": "template", "fail_class": "C",
              "fail_detail": "系统异常：ValueError", "error_types": ["ValueError"],
              "violations": [], "attempts": 1, "retry_log": []})
p._cog_debug({"kind": "brain", "turn": 2, "mode": "brain", "fail_class": "",
              "fail_detail": "", "attempts": 1})
import json  # noqa: E402

recs = [json.loads(l) for l in io.open(p._cog_debug_path, encoding="utf-8") if l.strip()]
br = [r for r in recs if r.get("kind") == "brain"]
case("F7 ★ brain 记录落盘（成功与失败都落）",
     len(br) == 2 and br[0].get("fail_class") == "C" and br[1].get("fail_class") == "",
     "%d 条" % len(br))
case("F8 ★ 失败记录含 retry_log 字段（下一批往里写重试记录）",
     "retry_log" in br[0] and br[0]["retry_log"] == [])

# ── 附加：验收口径的可执行化（C 类必须 0 次）
from collections import Counter  # noqa: E402

_c = Counter(r.get("fail_class") for r in br if r.get("mode") == "template")
case("F9 ★ 验收口径可算：C 类次数 = %d（必须 0 才算通过）" % _c.get("C", 0),
     "C" in _c, "本测试自己造了一条 C，所以这里是 1 —— 真实批测里应为 0")

print("-" * 78)
print("结果: %d 通过 / %d 失败 / 共 %d" % (OK, FAIL, OK + FAIL))
print()
print("MUTATION 表")
print("  MUT-A 把 ValueError 挪进 A 类                              → F2/F5")
print("  MUT-B 去掉「未知异常归 C」的兜底                            → F6")
print("  MUT-C 失败分支不写 brain 记录                              → F7")
sys.exit(1 if FAIL else 0)
