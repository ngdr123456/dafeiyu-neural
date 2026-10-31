# -*- coding: utf-8 -*-
"""E 的 OCR 抽检：随机抽 N 条，看 OCR 噪声对映射判定的干扰程度。

用户裁定的抽检要求（原话，2026-10-02）
────────────────────────────────────────────────────────────
> 「严格落实此前定下的风险防控规矩：**随机抽检 20 条**
>   （附**原文 quote、OCR 标记、判定的新旧状态**），
>   重点评估 **OCR 噪声对映射判定的干扰程度**。」

为什么要专门抽检 E
────────────────────────────────────────────────────────────
《自我的发展》是**扫描件 OCR**，条目碎、噪声多。E 的 1597 条「未实现」里
很可能混着 OCR 乱码条 —— 那些被判"未实现"**不是因为系统缺这个能力，
而是因为那句话本身读不通**。两者在数据上长得一模一样，必须靠抽检分辨。

⚠️ 所以本脚本不只贴 quote，还**自动标出 OCR 噪声的形态**，让人一眼看出
   "这条判得对不对"和"这条到底读不读得通"是两件事。

用法
    EGO_ROOT=<副本> python tools/E_OCR抽检.py [--n 20] [--seed 20261002]
"""
from __future__ import annotations

import argparse
import io
import json
import os
import random
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)
DIR = os.path.join(_ROOT, "spec", "观点总表")

# ── OCR 噪声的形态（按**实际观察到的**写法列，不凭想象）
#    这些模式来自 E 表里真实出现过的乱码，不是我预设的"可能形态"。
_OCR_PATTERNS = [
    (r"\[p\d+\]", "页码标记 [pNNN]（原文自带，不算错）"),
    (r"[\u4e00-\u9fff]-+[\u4e00-\u9fff]", "汉字间夹连字符（应为破折号或误识）"),
    (r"-{2,}", "连续连字符"),
    # ⚠️ 页码是**三到四位数**（如 `363这样做将危及…`）。
    #    第一版写成 `\d{2,}`，把 `1939年`、`14年`、`19世纪` 这些**正常年份**也报了 ——
    #    一跑就 42% 带噪，其中一大半是误报。**判据太宽会把噪声率本身变成噪声。**
    (r"(?<!\d)\d{3,}[\u4e00-\u9fff]", "三位以上数字黏在汉字前（页码串进正文）"),
    (r"[\u4e00-\u9fff]\d{3,}(?!\d)", "汉字后黏三位以上数字（同上）"),
    (r"[\ufffd\u25a1]", "替换字符／方框（识别失败）"),
    (r"[a-zA-Z]{1,3}[\u4e00-\u9fff]", "零散拉丁字母混入"),
    (r"[，。；：]{2,}", "重复标点"),
    (r"（\s*）|\(\s*\)", "空括号"),
]


def ocr_flags(q: str) -> list:
    """标出这条 quote 里出现了哪些 OCR 噪声形态。"""
    out = []
    for pat, desc in _OCR_PATTERNS:
        m = re.search(pat, q)
        if m:
            out.append("%s ← %r" % (desc, m.group(0)))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="E 的 OCR 抽检")
    ap.add_argument("--book", default="E")
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--seed", type=int, default=20261002)
    a = ap.parse_args()

    p = os.path.join(DIR, "%s.jsonl" % a.book)
    rows = [json.loads(l) for l in io.open(p, encoding="utf-8") if l.strip()]
    pool = [r for r in rows if r.get("mapped_at")]
    rnd = random.Random(a.seed)
    pick = rnd.sample(pool, min(a.n, len(pool)))

    print("=" * 86)
    print("E 的 OCR 抽检｜seed=%d（可复现）｜从已判的 %d 条里随机抽 %d 条"
          % (a.seed, len(pool), len(pick)))
    print("=" * 86)

    noisy = 0
    for i, r in enumerate(pick, 1):
        rf = r.get("remap_from") or {}
        q = (r.get("quote") or "").replace("\n", " ")
        flags = ocr_flags(q)
        if flags:
            noisy += 1
        print()
        print("【%d】%s" % (i, r["id"]))
        print("    quote：%s" % q)
        print("    OCR 标记：%s" % ("；".join(flags) if flags else "无 ✓"))
        print("    旧状态：%s%s" % (rf.get("status") or "（未判过）",
                                "｜maps_to=%s" % (rf.get("maps_to") or [])
                                if rf else ""))
        print("    新状态：%s｜maps_to=%s"
              % (r.get("status"), r.get("maps_to") or []))
        print("    raw_status=%s｜downgraded=%r"
              % (r.get("raw_status"), r.get("downgraded") or ""))
        if r.get("why_not"):
            print("    why_not：%s" % r["why_not"])
        if r.get("claim"):
            print("    抽出的主张：%s" % r["claim"])

    print()
    print("=" * 86)
    print("小结")
    print("=" * 86)
    print("  抽检 %d 条｜**带 OCR 噪声的 %d 条（%.0f%%）**"
          % (len(pick), noisy, 100.0 * noisy / max(1, len(pick))))
    print("  ⚠️ 判读要点：带噪声且被判「未实现」的，要分清是")
    print("     · 系统真的缺这个能力（该补）")
    print("     · 还是**这句话本身读不通**（该先修 OCR，不该进补缺清单）")
    print("     两者在数据上长得一样，**只能靠人看原文分辨**。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
