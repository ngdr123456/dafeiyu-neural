# -*- coding: utf-8 -*-
"""C1 离线验收（Gemini 批复的第 1 步）。

★ 判据（先写，照 Gemini 批复的第三节）：
  ① 字面校验通过率：通过 `_literal_claim` 保留的 Claim，`raw[start:end] == text` 必须 **100%**
     并报出模型原始返回被丢弃的比例
  ② 四类 Claim 各自在 215 行里的**覆盖率**与**两遍抽取一致率**
     判据：某一类 <5% 的行 ⇒ schema 设计有问题
  ③ 抽样展示 10–15 条真实原话的 Claim 明细（尤其第 191–214 行家教轮）

★ 成本：215 行 × 2 遍 = 430 次调用（约 30 分钟）
★ 落盘：spec/cognition抽取_20261029.jsonl（断点可读）
"""
import io
import json
import os
import sys
import time

sys.path.insert(0, "engine")
sys.stdout.reconfigure(encoding="utf-8")

from cognition import CLAIM_KINDS, _literal_claim, extract  # noqa: E402
from understand import ApiReader                            # noqa: E402

EVAL = "state/train/eval.jsonl"
OUT = "spec/cognition抽取_20261029.jsonl"
#: 靶向重抽的落盘（只跑触发过的行）
TARGET_OUT = "spec/cognition抽取_靶向_20261029.jsonl"


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    only = sys.argv[2] if len(sys.argv) > 2 else ""
    rows = [json.loads(l) for l in io.open(EVAL, encoding="utf-8") if l.strip()]
    todo = [(i, r) for i, r in enumerate(rows) if (r.get("input") or "").strip()]
    if only:
        # ★ 靶向重抽（Gemini 批复第一节）：只跑指定行号，逗号分隔
        keep = {int(x) for x in only.split(",") if x.strip().isdigit()}
        todo = [(i, r) for i, r in todo if i in keep]
        out_path = TARGET_OUT
    else:
        out_path = OUT
    if limit:
        todo = todo[:limit]
    print("  待抽 %d 行（共 %d）｜每行 2 遍｜落盘 %s" % (len(todo), len(rows), out_path))

    done = set()
    if os.path.exists(out_path):
        for line in io.open(out_path, encoding="utf-8"):
            if line.strip():
                try:
                    done.add(json.loads(line)["index"])
                except Exception:                              # noqa: BLE001
                    pass
    print("  已有结果 %d 行（断点续跑）" % len(done))

    reader = ApiReader()
    if not reader.available:
        print("  ★ API 不可用")
        return 2
    print("  API 就绪｜model=%s" % getattr(reader, "model", "?"))
    print()

    t0 = time.time()
    calls = 0
    with io.open(out_path, "a", encoding="utf-8") as fh:
        for n, (i, r) in enumerate(todo, 1):
            if i in done:
                continue
            raw = (r.get("input") or "").strip()
            t1 = time.time()
            res = extract(reader, raw, passes=2)
            calls += 2
            dt = time.time() - t1
            rec = {"index": i, "input": raw, "seconds": round(dt, 1), "result": res}
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            k = {kk: sum(1 for c in res["claims"] if c["kind"] == kk) for kk in CLAIM_KINDS}
            print("  [%3d/%3d] %4.1fs kept=%-2d %s | %s"
                  % (n, len(todo), dt, len(res["claims"]),
                     " ".join("%s=%d" % (kk[:4], v) for kk, v in k.items()), raw[:24]),
                  flush=True)
            if n % 20 == 0:
                el = time.time() - t0
                print("  ── 进度 %d/%d｜%d 次调用｜%.0fs｜均 %.1fs/行 ──"
                      % (n, len(todo), calls, el, el / n), flush=True)

    el = time.time() - t0
    print()
    print("  完成：%d 行｜%d 次调用｜%.0f 秒｜均 %.1f 秒/行" % (len(todo), calls, el, el / max(1, len(todo))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
