# -*- coding: utf-8 -*-
"""judge 重判一致性：215 行 × 2 遍，text-only，测标签噪声。

★ 判据（先写，来自 Claude）：
    同输入重判不一致 **≥25%** ⇒ 标签噪声太大，任何文本近似物能解释的上限都受限

⚠️ 为什么只跑 text-only、不跑「去掉读数 vs 带读数」的对照：
    215 行里只有 **24 行存了 mech**，其中 mechanical 只有 **3 条**。
    「去读数后 mechanical 翻成 none 的比例 ≥50%」在 3 条上**结构上不可判**。
    ⇒ 那一半标「未知」，等新数据（存了 mech 的轮次攒够）再做。

★ 可断点续跑：结果逐条追加到 spec/judge重判_20261028.jsonl，
    重跑时跳过已有 (index, pass) 对。

用法：
    python -B tools/重判一致性.py --limit 10     # 试点，测延迟
    python -B tools/重判一致性.py                # 全量
"""
import argparse
import io
import json
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "engine")

OUT = os.path.join("spec", "judge重判_20261028.jsonl")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 行（试点）")
    ap.add_argument("--passes", type=int, default=2, help="跑几遍（默认 2；3 = 补第三遍做多数投票）")
    args = ap.parse_args()

    rows = [json.loads(l) for l in io.open("state/train/eval.jsonl", encoding="utf-8") if l.strip()]
    print("  台账 %d 行" % len(rows))

    done = set()
    if os.path.exists(OUT):
        for line in io.open(OUT, encoding="utf-8"):
            if not line.strip():
                continue
            try:
                d = json.loads(line)
                done.add((d["index"], d["pass"]))
            except Exception:
                continue
    print("  已有结果 %d 条（断点续跑）" % len(done))

    from admin_agent import Admin
    ad = Admin()
    if not ad.available:
        print("  ★ API 不可用，退出")
        return 2
    print("  API 就绪｜model=%s" % getattr(ad.reader, "model", "?"))
    print()

    idxs = list(range(len(rows)))
    if args.limit:
        idxs = idxs[:args.limit]

    t0 = time.time()
    calls = 0
    with io.open(OUT, "a", encoding="utf-8") as fh:
        for i in idxs:
            r = rows[i]
            user = r.get("input") or ""
            out = r.get("output") or ""
            original = (r.get("tutor") or {}).get("problem")
            for p in range(1, args.passes + 1):
                if (i, p) in done:
                    continue
                t1 = time.time()
                res = ad.judge(user, out, None)          # ★ text-only
                dt = time.time() - t1
                calls += 1
                rec = {"index": i, "pass": p, "original": original,
                       "verdict": res.get("problem"), "ok": res.get("ok"),
                       "why": (res.get("why") or "")[:80], "seconds": round(dt, 1)}
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fh.flush()
                print("  [%3d/%3d] pass%d %-12s ← 原 %-12s %.1fs"
                      % (i + 1, len(idxs), p, res.get("problem"), original, dt), flush=True)
            if i % 20 == 19:
                el = time.time() - t0
                print("  ── 进度 %d/%d｜%d 次调用｜已用 %.0fs｜均 %.1fs/次 ──"
                      % (i + 1, len(idxs), calls, el, el / max(1, calls)), flush=True)

    el = time.time() - t0
    print()
    print("  完成：%d 次调用｜%.0f 秒｜均 %.1f 秒/次" % (calls, el, el / max(1, calls)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
