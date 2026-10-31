# -*- coding: utf-8 -*-
"""交集：观点之间的矛盾，以及**逻辑闭环**的总检查。

用户要求（本模块存在的理由）
────────────────────────────────────────────────────────────
> 「至于怎么验证书籍的每个观点，这需要你自己整理并**做并集交集整理，
>   形成逻辑闭环**。最后再喂回系统里。」

并集 = 每条观点都有归宿（`map_claims.py` 在做）
交集 = 观点之间不互相矛盾，矛盾必须有裁决（本模块）

**逻辑闭环的判据**（四条同时成立才算闭环）
    ① 每条观点都落进一个状态：已实现／未实现／明确不实现／冲突待裁
       —— **不许有"没提到"**
    ② 已实现 → 必须指出对应哪个单元（指不出就是没实现）
    ③ 明确不实现 → 必须写明用途（写不出就退回"未实现"）
    ④ 冲突待裁 → 必须在冲突裁决表里有对应行，且该行有上位依据
    四条缺任何一条，"闭环"就是自封的。

裁决依据的位阶（写在规格 §1，这里引用，不另立）
    伦理约束 → 事实描述 → 机制解释 → 测量与工程
    真冲突按这个位阶判；假冲突则说明"它们其实不是同一个量/同一层"。

⚠️ 本模块**只检查，不裁决**。新发现的矛盾进「待裁」队列，由人或管理员裁，
   并写回裁决表。理由：裁决是价值判断，不许由一个检查脚本自动做。
"""
from __future__ import annotations

import io
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
# 打包成 exe 后 `__file__` 指向解包出的临时目录 —— 于是 rules/corpus 找不到，
# 而且**台账会写进临时目录、退出就丢**。所以允许用 EGO_ROOT 指定项目根，
# 由启动器（exe）在导入任何引擎模块之前设置。
# 不设 EGO_ROOT 时行为与从前完全一致（源码运行时就是这个分支）。
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)
for _p in (_ROOT, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

TABLE = os.path.join(_ROOT, "spec", "冲突裁决表.jsonl")
RANK = ["伦理约束", "事实描述", "机制解释", "测量与工程"]     # 位阶，低位服从高位
OK_STATUS = ("已实现", "未实现", "明确不实现", "冲突待裁")


def load() -> list[dict]:
    out = []
    if not os.path.exists(TABLE):
        return out
    for line in io.open(TABLE, encoding="utf-8"):
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except Exception:                      # noqa: BLE001
                pass
    return out


def save(rows: list[dict]) -> None:
    with io.open(TABLE, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def add(topic: str, kind: str, why: str, ruling: str, upper: str,
        spec_ref: str = "", spans: list[str] | None = None) -> dict:
    rows = load()
    cid = "C%d" % (len(rows) + 1)
    rec = {"id": cid, "topic": topic, "type": kind, "why": why, "ruling": ruling,
           "upper_basis": upper, "spec_ref": spec_ref, "spans": spans or [],
           "status": "已裁决" if ruling else "待裁", "logical_form": ""}
    rows.append(rec)
    save(rows)
    return rec


# ------------------------------------------------------------------ 闭环检查

def closure(book: str | None = None) -> dict:
    """四条闭环判据，逐条查。返回每条的问题清单。"""
    import claims as C
    cs = C.load(book) if book else C.load()
    table = {c["id"]: c for c in load()}
    bad_status, no_maps, no_why, no_ruling = [], [], [], []
    for c in cs:
        st = c.get("status")
        if st not in OK_STATUS:
            bad_status.append({"id": c["id"], "status": st})
            continue
        if st == "已实现" and not (c.get("maps_to") or []):
            no_maps.append({"id": c["id"], "claim": (c.get("claim") or "")[:40]})
        if st == "明确不实现" and not (c.get("why_not") or "").strip():
            no_why.append({"id": c["id"], "claim": (c.get("claim") or "")[:40]})
        if st == "冲突待裁":
            cid = c.get("conflict_id")
            row = table.get(cid) if cid else None
            if not row or not (row.get("upper_basis") or "").strip():
                no_ruling.append({"id": c["id"], "claim": (c.get("claim") or "")[:40],
                                  "conflict_id": cid})
    return {"total": len(cs),
            "①状态非法": bad_status,
            "②已实现但指不出单元": no_maps,
            "③明确不实现但没写用途": no_why,
            "④冲突待裁但裁决表里没有依据": no_ruling,
            "裁决表条数": len(table)}


def check_table() -> dict:
    """裁决表自身的体检：真冲突必须有上位依据；假冲突必须说明为什么不是同一个量。"""
    prob = []
    for r in load():
        t = r.get("type")
        if t == "真冲突" and not (r.get("upper_basis") or "").strip():
            prob.append({"id": r["id"], "why": "真冲突却没有上位依据"})
        if t == "假冲突" and not (r.get("why") or "").strip():
            prob.append({"id": r["id"], "why": "假冲突却没说明为什么不是同一个量"})
        if r.get("status") == "已裁决" and not (r.get("ruling") or "").strip():
            prob.append({"id": r["id"], "why": "标了已裁决却没有裁决内容"})
    return {"total": len(load()), "problems": prob}


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="交集与逻辑闭环检查")
    ap.add_argument("--book", default=None)
    a = ap.parse_args()
    t = check_table()
    print("=" * 74)
    print("冲突裁决表：%d 条｜问题 %d 处" % (t["total"], len(t["problems"])))
    for p in t["problems"]:
        print("   ✗ %s：%s" % (p["id"], p["why"]))
    for r in load():
        print("   %s [%s] %s → %s" % (r["id"], r["type"], r["topic"],
                                     (r["ruling"] or "")[:54]))
    cl = closure(a.book)
    print()
    print("=" * 74)
    print("逻辑闭环检查（观点 %d 条）" % cl["total"])
    print("=" * 74)
    for k in ("①状态非法", "②已实现但指不出单元",
              "③明确不实现但没写用途", "④冲突待裁但裁决表里没有依据"):
        v = cl[k]
        print("  %s %s：%d 条" % ("✓" if not v else "✗", k, len(v)))
        for x in v[:5]:
            print("       · %s" % x)
    ok = all(not cl[k] for k in cl if k.startswith(tuple("①②③④")))
    # ★ 空转的通过必须自己说出来。
    #   第一次跑时 376 条全在「未实现」，四条检查一条都碰不到东西，
    #   于是打印「闭环：成立」—— 那句话是**假的安慰**：
    #   它看起来像验证过了，其实什么也没验。
    #   判据：映射做完了吗？没做完，闭环检查就还没有效力。
    import claims as C
    cs = C.load(a.book) if a.book else C.load()
    unmapped = sum(1 for c in cs
                   if c.get("status") == "未实现" and not c.get("mapped_at"))
    ratio = unmapped / max(1, len(cs))
    print()
    print("映射进度：%d/%d 条还没判过（%.0f%%）" % (unmapped, len(cs), 100 * ratio))
    if ratio > 0.5:
        print("⚠️ **本次闭环检查是空转的** —— 绝大多数观点还停在「未实现」，")
        print("   四条判据碰不到东西，所以上面的「成立」不构成任何证据。")
        print("   等并集映射做完（python engine/map_claims.py）再看这个结论。")
        return 0
    print("闭环：%s" % ("成立" if ok else "**不成立 —— 上面带 ✗ 的就是缺口**"))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
