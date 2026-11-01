# -*- coding: utf-8 -*-
"""eval.jsonl 的标准分析入口（改动 ④，2026-10-28，用户已批）。

★ 为什么需要它：实测过辛普森悖论 —— 把"写死模板行"和"她真生成的行"混在一起算，
  会得出反向结论（「<40 字机械率高」其实是短输入里混了大量模板行）。
  所以**任何按 eval.jsonl 做的统计，都必须先分层**。

★ 三层默认口径：
    A 全部（**只在明确说明时才用**，等于把悖论请回来）
    B 排除模板行（按模板特征词判定）—— **默认**
    C 只要 eval_schema >= 8（最新格式，字段齐全）

用法：
    python -B tools/analyze_eval.py                # 默认 B
    python -B tools/analyze_eval.py --layer all
    python -B tools/analyze_eval.py --layer schema8

★ 判据纪律（写在数字之前）：
    · 每个信号报四列：mechanical 侧比例、none 侧比例、精度、提升
    · 提升 = 精度 / 基准率
    · 阳性样本数 < 30 ⇒ 只写「线索」，不下结论
"""
import argparse
import io
import json
import re
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")

EVAL = "state/train/eval.jsonl"
LABELS = "spec/judge重判_20261028.jsonl"

#: 写死模板的特征词（实测取自 behaviors.json 的 REFLECT/JUXTAPOSE 模板）
TEMPLATE_MARKS = ("你用了这样一句话", "我听到的是", "你刚才说的是", "你说的是",
                  "这两句话放一起", "这一块改不了", "这句话我收下了")

ASK = re.compile(r"你说|你觉得|是不是|能不能|吗|？|\?|帮我|你别|你愿意|你会")
STRUCT = re.compile(r"两件事|三件事|两样|三样|两段|三段时间|前一个|后一个|"
                    r"第一个|第二个|一方面|另一边|一回事|几件|你说的那")


def new_rate(out, user):
    if not out:
        return 0.0
    return sum(1 for ch in out if ch not in user) / len(out)


def copy_rate(out, user):
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


def load():
    rows = [json.loads(l) for l in io.open(EVAL, encoding="utf-8") if l.strip()]
    labels = {}
    try:
        by = {}
        for line in io.open(LABELS, encoding="utf-8"):
            if not line.strip():
                continue
            d = json.loads(line)
            by.setdefault(d["index"], {})[d["pass"]] = d["verdict"]
        for i, d in by.items():
            if len(d) == 3:
                labels[i] = Counter(d.values()).most_common(1)[0][0]
    except FileNotFoundError:
        labels = {}
    return rows, labels


def is_template(r):
    o = r.get("output") or ""
    return any(k in o for k in TEMPLATE_MARKS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--layer", default="no_template",
                    choices=("all", "no_template", "schema8"))
    a = ap.parse_args()

    rows, labels = load()
    if a.layer == "all":
        idx = list(range(len(rows)))
    elif a.layer == "schema8":
        idx = [i for i, r in enumerate(rows) if (r.get("eval_schema") or 0) >= 8]
    else:
        idx = [i for i, r in enumerate(rows) if not is_template(rows[i])]

    idx_l = [i for i in idx if i in labels]
    print("  口径：%s｜行数 %d｜有去噪标签 %d" % (a.layer, len(idx), len(idx_l)))
    if not idx_l:
        print("  ★ 没有去噪标签，无法统计")
        return 2
    mech = [i for i in idx_l if labels[i] == "mechanical"]
    none = [i for i in idx_l if labels[i] == "none"]
    base = len(mech) / len(idx_l)
    print("  mechanical %d｜none %d｜基准率 **%.1f%%**" % (len(mech), len(none), 100 * base))
    print()

    def four(name, fn):
        tm = sum(1 for i in mech if fn(rows[i]))
        tn = sum(1 for i in none if fn(rows[i]))
        if not mech or not none:
            return
        prec = tm / max(1, tm + tn)
        lift = prec / base if base else 0
        pos = tm + tn
        verdict = ("线索(n=%d)" % pos) if pos < 30 else (
            "**可用**" if lift >= 2.0 else ("弱" if lift >= 1.5 else "无区分"))
        print("  %-28s %5.0f%% %5.0f%% %6.0f%% %6.2f× %s"
              % (name, 100.0 * tm / len(mech), 100.0 * tn / len(none),
                 100.0 * prec, lift, verdict))

    print("  %-28s %6s %6s %7s %7s %s" % ("信号", "mech", "none", "精度", "提升", "判定"))
    print("  " + "-" * 74)
    four("新词占比 <= 0.30", lambda r: new_rate(r.get("output") or "",
                                                r.get("input") or "") <= 0.30)
    four("复制率 >= 0.60", lambda r: copy_rate(r.get("output") or "",
                                               r.get("input") or "") >= 0.60)
    four("非问句", lambda r: not re.search(r"[？?]", r.get("output") or ""))
    four("输出 <= 18 字", lambda r: len((r.get("output") or "").strip()) <= 18)
    four("非问句 且 >18 字 且 新词<=0.30",
         lambda r: (not re.search(r"[？?]", r.get("output") or ""))
         and len((r.get("output") or "").strip()) > 18
         and new_rate(r.get("output") or "", r.get("input") or "") <= 0.30)
    four("输入 >= 40 字", lambda r: len((r.get("input") or "").strip()) >= 40)
    four("输入含问句/请求", lambda r: bool(ASK.search(r.get("input") or "")))
    four("结构化词", lambda r: bool(STRUCT.search(r.get("output") or "")))
    print()
    print("  长度档：")
    for lo, hi, nm in ((0, 40, "<40"), (40, 61, "40-60"), (61, 10 ** 6, ">60")):
        sub = [i for i in idx_l if lo <= len((rows[i].get("input") or "").strip()) < hi]
        if not sub:
            continue
        m = sum(1 for i in sub if labels[i] == "mechanical")
        print("     %-8s %2d/%3d = %4.0f%%" % (nm, m, len(sub), 100.0 * m / len(sub)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
