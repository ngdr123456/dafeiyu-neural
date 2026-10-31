# -*- coding: utf-8 -*-
"""Claude 建议的 4 项零 API 离线核查（2026-10-28）。

★ 纪律：**判据先写下来，再看数据**（认输清单规则 2）。判据写在每个核查前面。

结果见 spec/核查_克制与模板_20261028.md
"""
import io
import json
import re
import sys
from collections import Counter
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")

ASK = re.compile(r"你说|你觉得|是不是|能不能|吗|？|\?|帮我|你别|你愿意|你会")
NEG = re.compile(r"^(不是|我是说|算了|没事|你没懂|我不是这个意思|我说的是)")
GAP_SECONDS = 120.0          # 会话边界的近似约定（eval.jsonl 没有会话标识）


def copy_rate(out, user):
    """输出里被"用户当轮原话" ≥3 字片段覆盖的比例（贪心最长匹配）。"""
    if not out:
        return 0.0
    covered = i = 0
    n = len(out)
    while i < n:
        best = 0
        for L in range(min(n - i, 40), 2, -1):
            if out[i:i + L] in user:
                best = L
                break
        if best >= 3:
            covered += best
            i += best
        else:
            i += 1
    return covered / n


def stat(xs):
    xs = sorted(xs)
    if not xs:
        return "—"
    n = len(xs)
    return "n=%d 中位=%.2f 均值=%.2f 最小=%.2f 最大=%.2f" % (
        n, xs[n // 2], sum(xs) / n, xs[0], xs[-1])


def _ts(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def main():
    rows = [json.loads(l) for l in io.open("state/train/eval.jsonl", encoding="utf-8") if l.strip()]
    for r in rows:
        r["_problem"] = (r.get("tutor") or {}).get("problem")
        r["_user"] = r.get("input") or ""
        r["_out"] = r.get("output") or ""
        r["_copy"] = copy_rate(r["_out"], r["_user"])
        r["_asked"] = bool(ASK.search(r["_user"]))
        r["_t"] = _ts(r.get("ts"))
    mech = [r for r in rows if r["_problem"] == "mechanical"]
    none = [r for r in rows if r["_problem"] == "none"]

    print("=" * 82)
    print("  核查 1：复制率")
    print("  判据：若两组分布重叠大 ⇒ 复制率不足以单独区分 ⇒ 记入认输清单")
    print("=" * 82)
    print("  mechanical：%s" % stat([r["_copy"] for r in mech]))
    print("  none      ：%s" % stat([r["_copy"] for r in none]))
    o1 = sum(1 for r in mech if r["_copy"] >= 0.60)
    o2 = sum(1 for r in none if r["_copy"] >= 0.60)
    print("  ≥0.60：mechanical %d/%d = %.0f%%｜none %d/%d = %.0f%%"
          % (o1, len(mech), 100.0 * o1 / max(1, len(mech)),
             o2, len(none), 100.0 * o2 / max(1, len(none))))
    print()

    print("=" * 82)
    print("  核查 2/3：REFLECT 本身是不是问题；mechanical 是否集中在「被问」轮")
    print("  判据：若 none 里也有大量「纯叙述 + REFLECT」判为没问题 ⇒ REFLECT 本身不是问题")
    print("=" * 82)
    ma = sum(1 for r in mech if r["_asked"])
    na = sum(1 for r in none if r["_asked"])
    print("  被问轮：mechanical %d/%d = %.0f%%｜none %d/%d = %.0f%%"
          % (ma, len(mech), 100.0 * ma / max(1, len(mech)),
             na, len(none), 100.0 * na / max(1, len(none))))
    narr = [r for r in none if not r["_asked"]]
    nr = [r for r in narr if (r.get("planned_behavior") or r.get("behavior")) == "REFLECT"]
    print("  none 里纯叙述轮：%d｜其中 REFLECT：%d（%.0f%%）"
          % (len(narr), len(nr), 100.0 * len(nr) / max(1, len(narr))))
    print()

    print("=" * 82)
    print("  核查 4（路 C）：机械轮的下一句有没有负面反应")
    print("  判据：会话边界用 ts 间隔 > %ds 近似（**约定，不是已验证事实**）；" % GAP_SECONDS)
    print("        若 mechanical 命中率 ≤ none ⇒ 分不开 ⇒ 记入认输清单")
    print("=" * 82)
    pairs = [(a, b) for a, b in zip(rows, rows[1:])
             if a["_t"] and b["_t"] and (b["_t"] - a["_t"]).total_seconds() <= GAP_SECONDS]
    n_sess = 1 + sum(1 for a, b in zip(rows, rows[1:])
                     if a["_t"] and b["_t"] and (b["_t"] - a["_t"]).total_seconds() > GAP_SECONDS)
    print("  相邻对：%d｜近似会话数：%d" % (len(pairs), n_sess))

    def ev(a, b):
        e = []
        if copy_rate(b["_user"], a["_user"]) >= 0.60:
            e.append("E1重复")
        t = (b["_user"] or "").strip()
        if NEG.search(t):
            e.append("E2否定开头")
        if len(t) < 0.5 * len(a["_user"]):
            e.append("E3骤短")
        return e

    for tag, want in (("mechanical", "mechanical"), ("none", "none")):
        sub = [(a, b) for a, b in pairs if a["_problem"] == want]
        if not sub:
            print("  %-11s 无相邻对" % tag)
            continue
        hits = [(a, b, ev(a, b)) for a, b in sub]
        anyn = sum(1 for _, _, e in hits if e)
        print("  %-11s 相邻对 %d｜命中任一 **%d（%.0f%%）**｜分布 %s"
              % (tag, len(sub), anyn, 100.0 * anyn / len(sub),
                 dict(Counter(x for _, _, e in hits for x in e))))
    print()


if __name__ == "__main__":
    main()
