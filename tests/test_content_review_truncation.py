# -*- coding: utf-8 -*-
"""V1-V10：内容校验被截断（C 类 ValueError）的复现与修复（2026-10-30）。

★ 依据：用户要求「先用轮 2 当时的输入复现并写成测试，再用大白话报告根因，再修根因。
        不要用『捕获 ValueError 当作通过』来修；内容校验自己出错时，
        仍要保守退回兜底，不能放行未校验的输出。」

★ 实测事实（台账铁证）：
  36 轮批次里 `content_review_failed:ValueError` 共 **10** 次，
  **全部**是 `truncated_content_review`（`finish_reason == "length"`）。
  一条真实样本（台账逐字）：
    他：你这话我去年就听过了，前年好像也是这么说的——那“以后”到底是哪一天啊…
    她：发生什么？
    候选：你说「没敢开口」——去年听到这话的时候，你开口要过那个数吗？
    → attempt 1 被 ValueError 打掉，attempt 2 才通过

★ 判据（先写）：
  V1 ★★ 顽固截断（预算再高也截断）⇒ verdict 仍 UNKNOWN（**没有放行**）
  V2 ★★ 顽固截断 ⇒ `validation_error` 是 `truncated_content_review`
  V3 ★★★ 预算可救时：`review()` **自己**把预算提上去，拿到完整 JSON
  V4 ★★★ 提升后的预算 = 16384（与项目其它处一致）
  V5 ★★ 调用前后 `reader.max_tokens` 复原（约定：只增不减、用完还原）
  V6 ★★ 修复**没有**把失败当 PASS（保守性未被削弱）
  V7 ★★ 预算提升发生在 `_post` **之前**（不是事后补救）
  V8 ★ 假 reader 真的随预算改变行为（否则测试是空的）
  V9 ★ 复原在 `finally` 里（抛异常也能复原）
  V10 ★★★ **整体不变式**：`review()` 返回的 verdict **永不**因为"校验自己出错"而变成 PASS
"""
import io
import json
import os
import sys

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
print("  内容校验截断的复现与修复（V1-V10）")
print("=" * 78)

import content_fidelity  # noqa: E402
from think import Frame  # noqa: E402

# 轮 2 当时的真实输入（台账逐字）
RAW = ("你这话我去年就听过了，前年好像也是这么说的——"
       "那“以后”到底是哪一天啊，你哪怕给我个大概的数呢？")
CAND = "你说「没敢开口」——去年听到这话的时候，你开口要过那个数吗？"

GOOD = {
    "verdict": "PASS",
    "reason": ("候选逐字引用了原话里的「没敢开口」，并针对当前问题追问那个数，"
               "没有编造关于他的事实，也没有把旧说法当当前事实。判 PASS。"),
    "evidence": [],
}


class _Reader:
    """假的 reader。

    ★ `stubborn=True`：**无视预算，永远截断** —— 复现"校验自己出错"这一支。
    ★ `stubborn=False`：预算够就完整返回，不够就 `finish_reason=length`（真实行为）。
    """

    model = "fake-reasoner"
    timeout = 5

    def __init__(self, budget_needed=5000, stubborn=False):
        self.max_tokens = 4096
        self.budget_needed = budget_needed
        self.stubborn = stubborn
        self.seen_budgets = []
        self.raise_on_post = False
        self.last_response = {}

    def _post(self, messages, json_mode=True):
        self.seen_budgets.append(self.max_tokens)
        if self.raise_on_post:
            raise RuntimeError("boom")
        full = json.dumps(GOOD, ensure_ascii=False)
        ok = (not self.stubborn) and self.max_tokens >= self.budget_needed
        if ok:
            self.last_response = {"finish_reason": "stop"}
            return {"choices": [{"finish_reason": "stop",
                                 "message": {"content": full}}]}, None
        cut = max(8, len(full) // 3)
        self.last_response = {"finish_reason": "length"}
        return {"choices": [{"finish_reason": "length",
                             "message": {"content": full[:cut]}}]}, None


def mk_frame():
    return Frame(raw=RAW, dialogue_sources=[], self_facts=[], memory_scope={},
                 relational_context={})


# ── V1 / V2：顽固截断 ⇒ 保守退回（**没有放行**）
r = _Reader(stubborn=True)
t = content_fidelity.review(r, mk_frame(), CAND)
case("V1 ★★ 顽固截断 ⇒ verdict 仍 UNKNOWN（没有放行）",
     t.get("verdict") == "UNKNOWN", "%r" % t.get("verdict"))
case("V2 ★★ 顽固截断 ⇒ validation_error = truncated_content_review",
     t.get("validation_error") == "truncated_content_review",
     "%r" % t.get("validation_error"))

# ── V3 / V4 / V7：预算可救 ⇒ review 自己提预算
r2 = _Reader(budget_needed=5000)
before = r2.max_tokens
t2 = content_fidelity.review(r2, mk_frame(), CAND)
case("V3 ★★★ 预算可救时：review() 自己提预算，拿到完整 JSON（PASS）",
     t2.get("verdict") == "PASS", "%r / %r" % (t2.get("verdict"), t2.get("reason")))
case("V4 ★★★ 提升后的预算 = 16384",
     bool(r2.seen_budgets) and max(r2.seen_budgets) == 16384, "%r" % (r2.seen_budgets,))
case("V7 ★★ 提升发生在 _post **之前**（第一次调用就已经是 16384）",
     bool(r2.seen_budgets) and r2.seen_budgets[0] == 16384, "%r" % (r2.seen_budgets,))
case("V5 ★★ 调用前后 max_tokens 复原", r2.max_tokens == before,
     "%d → %d" % (before, r2.max_tokens))

# ── V6：保守性不许被削弱（真实失败仍 UNKNOWN）
r3 = _Reader(budget_needed=10 ** 9)
t3 = content_fidelity.review(r3, mk_frame(), CAND)
case("V6 ★★ 修复**没有**把失败当 PASS", t3.get("verdict") == "UNKNOWN",
     "%r" % t3.get("verdict"))

# ── V9：复原在 finally 里
r4 = _Reader()
before4 = r4.max_tokens
r4.raise_on_post = True
try:
    content_fidelity.review(r4, mk_frame(), CAND)
except Exception:                                            # noqa: BLE001
    pass
case("V9 ★ 复原在 finally 里（_post 抛异常也复原）",
     r4.max_tokens == before4, "%d → %d" % (before4, r4.max_tokens))

# ── V8：假 reader 真的随预算改变行为
r5 = _Reader(budget_needed=5000)
r5.max_tokens = 4096
_lo, _ = r5._post([])
r5.max_tokens = 16384
_hi, _ = r5._post([])
case("V8 ★ 假 reader 随预算改变行为（低=截断 / 高=完整）",
     _lo["choices"][0]["finish_reason"] == "length"
     and _hi["choices"][0]["finish_reason"] == "stop")

# ── V10：整体不变式
rows = []
for stubborn in (False, True):
    for need in (5000, 10 ** 9):
        rr = _Reader(budget_needed=need, stubborn=stubborn)
        tt = content_fidelity.review(rr, mk_frame(), CAND)
        rows.append((stubborn, need, tt.get("verdict")))
_pass_when_failed = [x for x in rows if x[2] == "PASS" and (x[0] or x[1] > 16384)]
case("V10 ★★★ 整体不变式：校验自己出错时 verdict **绝不**是 PASS",
     not _pass_when_failed, "%r" % (rows,))

print("-" * 78)
print("结果: %d 通过 / %d 失败 / 共 %d" % (OK, FAIL, OK + FAIL))
print()
print("MUTATION 表")
print("  MUT-A 去掉 review() 里的预算提升                        → V3/V4/V7")
print("  MUT-B 把 UNKNOWN 改成 PASS（放行未校验输出）             → V6/V10")
print("  MUT-C 把复原挪出 finally                                → V9")
print("  MUT-D 预算只提到 8192                                   → V4")
sys.exit(1 if FAIL else 0)
