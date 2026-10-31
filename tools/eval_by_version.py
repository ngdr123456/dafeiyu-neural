# -*- coding: utf-8 -*-
"""按**版本**统计训练评价 —— 因为跨版本混算会撒谎，而且已经撒过一次。

为什么必须存在（管理员判定的严重度 3 缺陷）
────────────────────────────────────────────────────────────
    我把「管理员可审计率」算在整份 `eval.jsonl` 上，得到 93.9%，
    然后向管理员报告"修复不完全、还有 6.1% 盲区"。

    **实际上那 9 条不可见记录全部在修复前的旧数据里。**
    修复后那次 120 轮训练：不可见 **0** 条，可审计率 **100%**。
    数据是好的，**是我的统计集合错了**。

    而管理员基于我那个错数字，做了一次"暂不验收"的判断。
    —— 所以这不是"报表不好看"，是**它污染了验收决策本身**。
    它给了严重度 3，是对的。

纪律（写死在这里，免得下次又忘）
────────────────────────────────────────────────────────────
    1. **只统计当前 `EVAL_SCHEMA` 的记录。** 旧版本一律不混入。
    2. **混入了几条要说出来** —— 不许静默丢弃，那会让人以为样本是满的。
    3. 任何"率"都必须报出它的**分母**，光报百分比等于藏起样本量。
"""
from __future__ import annotations

import io
import json
import os
import sys
from collections import Counter

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)   # tools/ 的上一级 = 项目根
for _p in (_ROOT, os.path.join(_ROOT, "engine")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

EVAL = os.path.join(_ROOT, "state", "train", "eval.jsonl")


def load(schema: int | None = None) -> tuple[list[dict], dict]:
    """读评价记录。**只返回当前版本的**，并把被排除的数量如实报出来。"""
    from train import EVAL_SCHEMA
    want = EVAL_SCHEMA if schema is None else schema
    rows = []
    if os.path.exists(EVAL):
        for line in io.open(EVAL, encoding="utf-8"):
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:                  # noqa: BLE001
                    pass
    cur = [r for r in rows if r.get("eval_schema") == want]
    old = [r for r in rows if r.get("eval_schema") != want]
    return cur, {"current": want, "kept": len(cur), "excluded": len(old),
                 "excluded_schemas": dict(Counter(str(r.get("eval_schema"))
                                                  for r in old))}


def report(schema: int | None = None) -> dict:
    rows, meta = load(schema)
    n = len(rows)
    saw = sum(1 for r in rows if (r.get("tutor") or {}).get("saw_internals"))
    meta_rows = [r for r in rows if r.get("behavior") in ("META_REPLY", "SILENCE")]
    m_saw = sum(1 for r in meta_rows if (r.get("tutor") or {}).get("saw_internals"))
    probs = Counter((r.get("tutor") or {}).get("problem") for r in rows)
    return {"meta": meta, "n": n, "auditable": saw,
            "auditable_pct": round(100.0 * saw / n, 1) if n else None,
            "meta_n": len(meta_rows), "meta_auditable": m_saw,
            "meta_pct": round(100.0 * m_saw / len(meta_rows), 1) if meta_rows else None,
            "problems": {k: v for k, v in probs.most_common() if k and k != "none"}}


def main() -> int:
    r = report()
    m = r["meta"]
    print("=" * 74)
    print("训练评价统计（**按版本隔离**）")
    print("=" * 74)
    print("当前评价版本：eval_schema = %s" % m["current"])
    print("本次统计用了 %d 条" % m["kept"])
    if m["excluded"]:
        print("**排除旧版本 %d 条**（版本分布 %s）" % (m["excluded"], m["excluded_schemas"]))
        print("   ↑ 必须说出来。上一版我静默把它们算进去了，")
        print("     于是算出 93.9% 并向管理员报了「没修完全」—— 那次判断是错的。")
    print()
    print("管理员可审计：%d / %d = %s%%" % (r["auditable"], r["n"], r["auditable_pct"]))
    print("其中元提问/沉默轮：%d / %d = %s%%"
          % (r["meta_auditable"], r["meta_n"], r["meta_pct"]))
    print()
    print("管理员挑出的问题：%s" % (r["problems"] or "（无）"))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
