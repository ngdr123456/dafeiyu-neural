# -*- coding: utf-8 -*-
"""T20 丙：主张级共识核（提炼 → 交叉 → 双跑鲁棒性）。

与 `consensus.py` 的甲乙部分（单元级证据表）分开：
    甲乙 = 拿现成的 maps_to 归拢，**不花 API**
    丙   = 让模型提炼三本书各自的核心主张，再判哪些是共有的，**花 API**

用户批准的设计（原话，2026-10-02）
────────────────────────────────────────────────────────────
> 「引用校验用程序做，不靠模型：每条共识引用的 id 必须存在、且属于对应那本书，
>   不满足就丢弃并计数。展示给我的原文由程序从观点总表取，不由模型转写。
>  强度只有『同义』『蕴含』进三本层，『相关』单列，不进。
>  第二遍不靠温度（推理模型可能不认），改为**打乱分批顺序（固定种子）**。
>  『两遍一致』用**依据 id 的交集**判断，不用文本相似度，三本各自都有交集才算一致，
>   阈值请提议，写进方案。
>  每条共识加『可落地性』字段……『人需要意义』这种抽象的标『否』。
>  提炼 JSON 沿用已有防护……某批失败只重跑那批；同一批连败两次就停下报告。
>  两遍都跑完再停。」
> 阈值批准：**档 A = 三本各自依据交集 ≥1 且三本交集总数 ≥3**；档 B 单列待裁。
> 「可落地性 = 否 的，**即使达到档 A 也不得并入系统的规则映射**，仅作理念底色归档。」

用法
    python engine/consensus.py --claims            # 跑两遍
    python engine/consensus.py --claims --dry      # 只看分批与提示词，不发 API
"""
from __future__ import annotations

import io
import json
import os
import random
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)
for _p in (_ROOT, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

OUT_CLAIMS = os.path.join(_ROOT, "spec", "共识核_主张级.jsonl")
# ★ 每批提炼结果的缓存（用户规则的落地）
#
#   用户裁定：「某批失败**只重跑那批**；同一批连败两次就停下报告，不要硬撞。」
#   ⚠️ 第一版没有缓存 —— 于是"只重跑那批"**跨进程不成立**：
#      网络在 E 批 4 断掉、脚本按规则停下，重跑却会把前面 9 批**全部重来**。
#      规则写了，机制没跟上。
#   缓存放 state/：`syntax_gate` 只 glob `state/*.py`、部署脚本排除 state/ ——
#   都不扫它。
CACHE = os.path.join(_ROOT, "state", "共识核_提炼缓存.jsonl")
BOOKS = ("M", "DB", "E")
BATCH = 300              # 每批条数（用户批准：M 3 / DB 3 / E 6 = 12 批）

# ★ 输出预算（实测必须抬，否则整条链跑不动）
#
#   第一版用默认 4096，结果第一批就 `finish_reason=length`、**正文 0 字**：
#   `deepseek-flash` 是**推理模型**，300 条输入会让它把 4096 的 completion 预算
#   全花在 reasoning token 上 —— 这与 `map_claims.py` 里记过的坑**是同一个**，
#   我写丙时没把那两道防护搬过来。
#   实测：max_tokens=16384 时，300/150/80 条三种批大小**全部 finish=stop**。
MAX_TOKENS = 16384
SEED = 20261002
ID_RE = re.compile(r"\b(?:M|DB|E)-\d+\b")
MAX_PER_BOOK = 40        # 提炼上限（防止某本吐一大堆把交叉那步撑爆）

EXTRACT_SYSTEM = """你在读一本书的连续片段。下面给你这本书的一批观点（每条有 id 与抽出的主张）。

任务：从这批里提炼**这本书自己**的核心主张。

规则：
  A. 一条主张 = 一个**可判真假**的陈述。不要话题标签
     （「苦难」不是主张；「苦难有意义当且仅当它不可避免」才是）。
  B. 每条主张必须挂**该书里的依据 id**（1~4 条），id 必须来自下面给出的清单。
     不许编造 id，不许引用别的书的 id。
  C. ⚠️ 不要把作者**批评或转述**的观点当成他的主张 ——
     这本书里有大量「某某认为……」的转述。凡是被作者引来反驳的，**不是他的主张**。
  D. 不要把主题不同的东西合并成一条。宁可多列几条。
  E. 最多输出 12 条，选**最核心**的。

⚠️ **JSON 字符串里绝对不要出现 ASCII 双引号（\"）**，要强调就用中文引号「」。

只输出严格的 JSON 数组，不要别的字：
[{"主张":"…","依据":["M-123","M-456"]}]
"""

CROSS_SYSTEM = """下面给你三本书各自提炼出的核心主张（已标好是哪一本、以及依据 id）。

任务：找出**三本书都主张了**的东西。

判据：
  · 「都主张了」= 三条主张说的是**同一件事**，不是话题相近。
  · 三本书主题不同（多巴胺／意义／自我发展），**宁缺毋滥**；找不到就返回空数组。
  · ⚠️ 不许把「三本都提到某个话题」当成共识 —— **提到 ≠ 主张同一件事**。

每条输出四个字段：
  共识   —— 一句话说清那个共同主张
  M / DB / E —— 各自依据的 id 数组（**必须来自上面给出的清单，不许编造**）
  强度   —— 同义 / 蕴含 / 相关
            同义 = 三本说的是同一句话
            蕴含 = 一本的主张能从另一本推出来
            相关 = 只是话题相关
  可落地性 —— {"值":"是|部分|否","落成什么":"…"}
            「是」  = 能落成系统里可检测的标记／可执行的规则／可算的机制量
            「部分」= 能落成规则，但要补条件，或只能覆盖一部分情形
            「否」  = 价值宣言或人性论断，**落不成任何判据**（例：「人需要意义」）

⚠️ **JSON 字符串里绝对不要出现 ASCII 双引号（\"）**，要强调就用中文引号「」。

只输出 JSON 数组，不要别的字。一条都没有就输出 []：
[{"共识":"…","M":["M-1"],"DB":["DB-2"],"E":["E-3"],
  "强度":"同义","可落地性":{"值":"是","落成什么":"…"}}]
"""


def _load() -> dict:
    out = {}
    for b in BOOKS:
        p = os.path.join(_ROOT, "spec", "观点总表", "%s.jsonl" % b)
        for line in io.open(p, encoding="utf-8"):
            if line.strip():
                c = json.loads(line)
                out[c["id"]] = (b, c)
    return out


def _parse(txt: str):
    """容忍 markdown 代码块；失败返回 None（由调用方决定重跑）。"""
    t = (txt or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    i, j = t.find("["), t.rfind("]")
    if i < 0 or j < 0:
        return None
    try:
        return json.loads(t[i:j + 1])
    except Exception:                                  # noqa: BLE001
        return None


def _load_cache() -> dict:
    out = {}
    if os.path.exists(CACHE):
        for line in io.open(CACHE, encoding="utf-8"):
            if line.strip():
                x = json.loads(line)
                out[x["key"]] = x["items"]
    return out


def _put_cache(key: str, items: list) -> None:
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with io.open(CACHE, "a", encoding="utf-8") as f:
        f.write(json.dumps({"key": key, "items": items}, ensure_ascii=False) + "\n")


def extract(reader, book: str, claims: list, order: list, dry: bool, run: int = 1):
    """提炼：把该书的观点按 order 分批，逐批提炼核心主张。"""
    ids = [c["id"] for c in claims]
    batches = [ids[i:i + BATCH] for i in range(0, len(ids), BATCH)]
    if order is not None:                              # 第二遍：打乱分批顺序
        batches = [batches[i] for i in order]
    got, fails = [], 0
    by_id = {c["id"]: c for c in claims}
    cache = {} if dry else _load_cache()
    for k, bat in enumerate(batches, 1):
        key = "run%d|%s|%s|%d" % (run, book, bat[0], len(bat))
        if key in cache:                               # ★ 已提炼过的批直接复用
            got.extend(cache[key])
            print("   %s 批 %d/%d：**缓存命中** %d 条" % (book, k, len(batches),
                                                       len(cache[key])), flush=True)
            continue
        body = "\n".join(
            "%s ｜ %s" % (i, (by_id[i].get("claim") or by_id[i].get("quote") or "")[:60])
            for i in bat)
        if dry:
            print("   [dry] %s 批 %d/%d：%d 条" % (book, k, len(batches), len(bat)))
            continue
        user = "【本书的 id 清单（只能引用这些）】\n%s\n\n【观点】\n%s" % (
            "、".join(bat), body)
        ok = False
        # ⚠️ 用户裁定：「同一批连败两次就停下报告」。所以**两次都试这一批**，
        #    两次都败就立刻停 —— 不是"累计两批失败"。
        #    第一版写成了累计计数，报错信息还说成"连败两次"，是**判据与说法不符**。
        for attempt in (1, 2):
            why = ""
            try:
                d, _ = reader._post([{"role": "system", "content": EXTRACT_SYSTEM},
                                     {"role": "user", "content": user}])
                ch = (d.get("choices") or [{}])[0]
                txt = ((ch.get("message", {}) or {}).get("content") or "").strip()
                if not txt:
                    # ★ 空正文不是异常，是"推理吃光了输出预算" —— 必须单独识别并说出原因
                    why = ("空正文（finish_reason=%s）—— 推理吃光了输出预算"
                           % ch.get("finish_reason"))
                    arr = None
                else:
                    arr = _parse(txt)
                    if arr is None:
                        why = "JSON 解析失败｜尾部=%s" % txt[-70:]
            except Exception as e:                     # noqa: BLE001
                arr, why = None, "%s: %s" % (type(e).__name__, repr(e)[:110])
            if isinstance(arr, list):
                items = [x for x in arr if isinstance(x, dict)]
                got.extend(items)
                _put_cache(key, items)                 # ★ 每批立刻落盘
                print("   %s 批 %d/%d：提炼 %d 条" % (book, k, len(batches), len(items)),
                      flush=True)
                ok = True
                break
            # ★ 把原因**打出来** —— 第一版吞了它，于是"为什么失败"不可知
            print("   %s 批 %d/%d：**失败**（第 %d 次）｜%s"
                  % (book, k, len(batches), attempt, why), flush=True)
        if not ok:
            fails += 1
            raise SystemExit(
                "★ %s 批 %d **连败两次** —— 停下报告，不硬撞。\n"
                "   已提炼 %d 条。原因见上面最后一行。" % (book, k, len(got)))
    return got, fails


def cross(reader, pools: dict, dry: bool):
    """交叉：三份主张池一起判「哪些是三本书共有的」。"""
    if dry:
        print("   [dry] 交叉：%s" % {b: len(v) for b, v in pools.items()})
        return []
    body = []
    for b in BOOKS:
        body.append("【%s 的核心主张】" % b)
        for x in pools[b]:
            body.append("  %s ｜ %s" % (",".join(x.get("依据") or []),
                                        (x.get("主张") or "")[:80]))
    d, _ = reader._post([{"role": "system", "content": CROSS_SYSTEM},
                         {"role": "user", "content": "\n".join(body)}])
    txt = ((d.get("choices") or [{}])[0].get("message", {}) or {}).get("content") or ""
    return _parse(txt) or []


def validate(items: list, claims: dict) -> tuple:
    """★ 程序强校验（用户裁定：不靠模型）。返回 (合格的, 丢弃计数)。"""
    drop = {"id 不存在": 0, "id 不属于该书": 0, "某本依据为空": 0}
    keep = []
    for it in items:
        if not isinstance(it, dict):
            continue
        good, bad = {}, False
        for b in BOOKS:
            ids = [i for i in (it.get(b) or []) if isinstance(i, str)]
            ok = []
            for i in ids:
                if i not in claims:
                    drop["id 不存在"] += 1
                    continue
                if claims[i][0] != b:
                    drop["id 不属于该书"] += 1
                    continue
                ok.append(i)
            if not ok:
                bad = True
            good[b] = sorted(set(ok))
        if bad:
            drop["某本依据为空"] += 1
            continue
        it["_依据"] = good
        it["_原文"] = {b: [{"id": i, "quote": claims[i][1].get("quote") or ""}
                          for i in good[b]] for b in BOOKS}
        keep.append(it)
    return keep, drop


def pair_and_judge(r1: list, r2: list) -> list:
    """★ 两遍一致：按**依据 id 交集**贪心配对（不用文本相似度）。

    档 A（三本共识候选）：三本各自依据交集 ≥1 **且** 三本交集总数 ≥3
    档 B（单列待裁）    ：只满足部分条件
    """
    used = set()
    out = []
    for a in r1:
        best, best_n, best_i = None, 0, None
        for i, b in enumerate(r2):
            if i in used:
                continue
            n = sum(len(set(a["_依据"][x]) & set(b["_依据"][x])) for x in BOOKS)
            if n > best_n:
                best, best_n, best_i = b, n, i
        if best is None or best_n == 0:
            out.append({**a, "档": "B", "各本交集": {b: 0 for b in BOOKS}, "总交集": 0})
            continue
        used.add(best_i)
        inter = {b: len(set(a["_依据"][b]) & set(best["_依据"][b])) for b in BOOKS}
        tot = sum(inter.values())
        jac = {}
        for b in BOOKS:
            u = len(set(a["_依据"][b]) | set(best["_依据"][b]))
            jac[b] = round(inter[b] / u, 2) if u else 0.0
        level = "A" if (all(inter[b] >= 1 for b in BOOKS) and tot >= 3) else "B"
        out.append({**a, "档": level, "各本交集": inter, "总交集": tot, "Jaccard": jac,
                    "第二遍_共识": best.get("共识")})
    for i, b in enumerate(r2):
        if i not in used:
            out.append({**b, "档": "B", "各本交集": {x: 0 for x in BOOKS}, "总交集": 0})
    return out


def main() -> int:
    dry = "--dry" in sys.argv
    if "--claims" not in sys.argv:
        print("用法：python engine/consensus.py --claims [--dry]")
        return 2
    claims = _load()
    if dry:
        reader = None
    else:
        from understand import ApiReader
        reader = ApiReader()
        if not reader.available:
            print("★ API 不可用")
            return 2
        reader.max_tokens = MAX_TOKENS      # ★ 见文件头 MAX_TOKENS 的说明
        print("  输出预算 max_tokens = %d（默认 4096 会被推理吃光）" % MAX_TOKENS)

    rnd = random.Random(SEED)
    print("=" * 80)
    print("T20 丙：主张级共识核%s" % ("（dry-run）" if dry else ""))
    print("=" * 80)
    results = []
    for run in (1, 2):
        print()
        print("── 第 %d 遍%s ──" % (run, "（打乱分批顺序，seed=%d）" % SEED if run == 2 else ""))
        pools = {}
        for b in BOOKS:
            cs = [c for cid, (bb, c) in claims.items() if bb == b]
            cs.sort(key=lambda c: c["id"])
            order = None
            if run == 2:
                n = (len(cs) + BATCH - 1) // BATCH
                order = list(range(n))
                rnd.shuffle(order)
            got, _ = extract(reader, b, cs, order, dry, run=run)
            pools[b] = got[:MAX_PER_BOOK]
            print("   %s 提炼合计 %d 条（截取前 %d）" % (b, len(got), len(pools[b])))
        items = cross(reader, pools, dry)
        keep, drop = validate(items, claims)
        print("   交叉得到 %d 条｜程序校验后 %d 条｜丢弃 %s" % (len(items), len(keep), drop))
        results.append({"pools": pools, "keep": keep, "drop": drop, "raw": len(items)})

    if dry:
        print()
        print("（dry-run 结束，未发任何 API）")
        return 0

    paired = pair_and_judge(results[0]["keep"], results[1]["keep"])
    A = [x for x in paired if x["档"] == "A"]
    B = [x for x in paired if x["档"] == "B"]
    # 强度：「相关」不进三本层（用户裁定）
    A_ok = [x for x in A if (x.get("强度") or "") in ("同义", "蕴含")]
    A_rel = [x for x in A if (x.get("强度") or "") not in ("同义", "蕴含")]

    io.open(OUT_CLAIMS, "w", encoding="utf-8").write(
        "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in paired))

    print()
    print("=" * 80)
    print("统计总览")
    print("=" * 80)
    for i, r in enumerate(results, 1):
        print("  第 %d 遍：提炼 %s｜交叉原始 %d｜校验后 %d｜丢弃 %s"
              % (i, {b: len(r["pools"][b]) for b in BOOKS}, r["raw"],
                 len(r["keep"]), r["drop"]))
    print()
    print("  两遍一致：档 A %d 条｜档 B %d 条" % (len(A), len(B)))
    print("  档 A 里：强度=同义/蕴含 %d 条｜强度=相关（**不进三本层**）%d 条"
          % (len(A_ok), len(A_rel)))
    print()
    print("已写出：%s（%d 条）" % (OUT_CLAIMS, len(paired)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
