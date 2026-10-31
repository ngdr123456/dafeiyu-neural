# -*- coding: utf-8 -*-
"""T21：1882 条候选池的二次筛选 + 系统补缺清单。

为什么候选池不能直接取「未实现」
────────────────────────────────────────────────────────────
用户裁定：
> 「『未实现 ↔ 明确不实现』互翻率：M 28% ｜ DB 15% ｜ E 24%。
>   而这个边界是**同一份材料、同一个模型、两次判断**的结果差异。
>   所以『现在是未实现』既可能是真缺口，也可能只是一次判断的落点。」

候选池（1882）＝ 未实现 1862 ＋ 待核 5 ＋ 不复现 15

四道筛子（**全部本地判定，不花 API**）
────────────────────────────────────────────────────────────
    A 侧日志回查   —— 曾被判已实现又被拒的 = 判断摇摆
    B 稳定性列     —— 两次都判未实现 = 高置信；只判过一次 = 中置信
    C OCR 噪声标记 —— E 的带真噪声条目单列「先修 OCR」
    D 运行状态     —— 映射到未启用单元的 = 接线（**口径 X 窄**：只认 19 条有物理落点的）

四类归属（**互斥，合计 1882**）
────────────────────────────────────────────────────────────
用户修正后的口径（原写法有算术漏洞）：
> 「你在定义『补缺』时写了『高置信 + 无噪声 + 不属接线』，但如果这样定义，
>   首次判定的『中置信』健康条目（1000+ 条）在四类互斥归属里就没有容身之地了，
>   加起来到不了 1882。
>   请修正口径：**补缺 = 所有无噪声、非接线、非待核的候选条目
>   （其内部同时包含高置信、中置信、摇摆）**」

    补缺      所有无噪声、非接线、非待核的候选（内部再分 高／中／摇摆）
    先修 OCR  385 条（带真噪声的 E 条目）
    接线      19 条（口径 X：只认有物理代码落点的）
    待核      20 条（待核 5 ＋ 未复现 15）—— **严格锁死，不得剔除**

两条红线（用户明令）
────────────────────────────────────────────────────────────
 ① 补缺清单中**必须显式保留「创造途径」**，注明被 M-232 遮蔽、人工恢复
 ② 待核 5 条与未复现 15 条**严格锁在「待核」归属中**，不得擅自剔除

不碰：engine/consensus*.py｜spec/观点总表｜spec/共识核*.jsonl｜app 运行时
"""
from __future__ import annotations

import io
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)
for _p in (_ROOT, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

OUT_JSON = os.path.join(_ROOT, "spec", "补缺清单.jsonl")
OUT_MD = os.path.join(_ROOT, "spec", "补缺清单报告.md")
SIDE = os.path.join(_ROOT, "spec", "重判侧日志.jsonl")
CONSENSUS = os.path.join(_ROOT, "spec", "共识核.jsonl")
BOOKS = ("M", "DB", "E")
MAX_QUOTE = 120

# ★ 待核 5 条（用户裁定）
WAIT5 = {
    "E-168": "通用阶段论命题（层次／不可逆），SELF_RULES 是冲动控制规则按水平解锁 —— 宽松命中",
    "E-229": "「不变序列」同样是通用阶段论 —— 宽松命中",
    "E-156": "挂到 const 单元；常量数值书里不会有，claim 不可能「实现」一个数值",
    "E-892": "讲「行为反映不出未达到的水平」是产出侧；PERCEPTION_GATE 是感知侧 —— 近亲不是同一件事",
    "M-232": "同一句里含「创造性的工作」，而创造途径是 T17 **刻意标缺**的；判它已实现会让缺口隐身",
}

# ── OCR 噪声形态（与 tools/E_OCR抽检.py 同一套判据）
_OCR = [
    (r"\[p\d+\]", "页码标记（原文自带，不算错）"),
    (r"[\u4e00-\u9fff]-+[\u4e00-\u9fff]", "汉字间夹连字符"),
    (r"-{2,}", "连续连字符"),
    (r"(?<!\d)\d{3,}[\u4e00-\u9fff]", "三位以上数字黏在汉字前"),
    (r"[\u4e00-\u9fff]\d{3,}(?!\d)", "汉字后黏三位以上数字"),
    (r"[\ufffd\u25a1]", "替换字符／方框"),
    (r"[a-zA-Z]{1,3}[\u4e00-\u9fff]", "零散拉丁字母混入"),
    (r"[，。；：]{2,}", "重复标点"),
    (r"（\s*）|\(\s*\)", "空括号"),
]


def has_real_noise(q: str) -> bool:
    """真噪声 = 除页码标记以外还有别的形态（页码是原文自带的，不算错）。"""
    return any(re.search(p, q) for p, d in _OCR if "页码标记" not in d)


# ── 缺口类型的**规则首判**（零 API）
#
# ⚠️ 这一项是**读原文才能定准**的，本地只能用已有字段做首判。
#    所以每条都带 `缺口类型_判据` 说明它凭什么被这么分，
#    并且留 `未定` 一类 —— **不许为了好看硬塞**。
_KIND_MAP = {
    "机制":   ("缺机制量", "claim 的 kind=机制 —— 多半是应该被算出来的量或条件"),
    "方法":   ("缺流程",   "kind=方法 —— 多半是多轮才成立的做法"),
    "事实":   ("未定",     "kind=事实 —— 可能是真缺识别能力，也可能本就不该实现"),
    "临床":   ("未定",     "kind=临床 —— 临床观察常是规则的来源而非判据，要读原文"),
    "规范":   ("非缺口",   "kind=规范 —— 价值主张，本就不该落成判据"),
    "伦理":   ("非缺口",   "kind=伦理 —— 硬底线范畴，不在补缺范围"),
    "生存策略": ("缺规则", "kind=生存策略 —— 多半是「什么时候做什么」的条件"),
    "精神性": ("非缺口",   "kind=精神性 —— 立场与底色，不落判据"),
}


def _load() -> tuple:
    claims = {}
    for b in BOOKS:
        p = os.path.join(_ROOT, "spec", "观点总表", "%s.jsonl" % b)
        for line in io.open(p, encoding="utf-8"):
            if line.strip():
                c = json.loads(line)
                claims[c["id"]] = (b, c)
    side = {}
    if os.path.exists(SIDE):
        for line in io.open(SIDE, encoding="utf-8"):
            if line.strip():
                x = json.loads(line)
                side[x["id"]] = x
    return claims, side


def _wiring() -> dict:
    """口径 X（窄）：只认共识核里那 19 条有物理代码落点的命中。"""
    out = {}
    if not os.path.exists(CONSENSUS):
        return out
    for line in io.open(CONSENSUS, encoding="utf-8"):
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("运行状态") == "生效中":
            continue
        ids = ([d["id"] for d in r.get("指定依据") or [] if d.get("模型是否确认")]
               + list(r.get("独立命中") or []) + list(r.get("待核") or []))
        for cid in ids:
            out[cid] = r["单元"]
    return out


def main() -> int:
    claims, side = _load()
    wiring = _wiring()

    # ── 候选池：未实现 1862 + 待核 5 + 不复现 15
    pool = {}
    for cid, (b, c) in claims.items():
        if c.get("status") == "未实现":
            pool[cid] = "未实现"
    for cid in WAIT5:
        if cid in claims:
            pool[cid] = "待核"
    # 不复现：原已实现、第二次判的不是已实现（现在表里被还原成已实现）
    for cid, (b, c) in claims.items():
        rf = c.get("remap_from") or {}
        if rf.get("status") == "已实现" and cid in side and side[cid].get("新") != "已实现":
            pool[cid] = "不复现"

    # ── 四道筛子 → 四类归属
    rows = []
    for cid, src in sorted(pool.items()):
        b, c = claims[cid]
        q = (c.get("quote") or "").replace("\n", " ")
        noise = has_real_noise(q)

        if cid in WAIT5:
            bucket, why = "待核", WAIT5[cid]
        elif src == "不复现":
            bucket, why = "待核", "原判已实现、重判未复现，现被还原成已实现 —— 两次判断不一致"
        elif cid in wiring:
            bucket, why = "接线", "映射到未启用单元 %s —— 处置是**接线**（T33），不是重写" % wiring[cid]
        elif noise:
            bucket, why = "先修 OCR", "原文带真 OCR 噪声 —— 可能是「读不通」而非「缺能力」"
        else:
            bucket, why = "补缺", "无噪声、非接线、非待核"

        # 置信（只在「补缺」内部有调度意义）
        rf = c.get("remap_from")
        if cid in side and side[cid].get("新") == "已实现":
            conf, cwhy = "摇摆", "曾被判已实现又被拒 —— 判断摇摆，降优先级"
        elif not rf:
            conf, cwhy = "中", "只判过一次（首次判定），没有第二次对照"
        elif rf.get("status") == "未实现":
            conf, cwhy = "高", "两次都判未实现"
        else:
            conf, cwhy = "摇摆", "原状态 %s、重判未实现 —— 两次不一致" % rf.get("status")

        kt, kw = _KIND_MAP.get(c.get("kind") or "", ("未定", "kind 未知"))
        rows.append({
            "id": cid, "书": b, "kind": c.get("kind") or "",
            "quote": q[:MAX_QUOTE],
            "claim": (c.get("claim") or "")[:MAX_QUOTE],
            "归属": bucket, "归属理由": why,
            "置信": conf, "置信理由": cwhy,
            "缺口类型": kt, "缺口类型_判据": kw,
            "噪声": "有" if noise else "无",
            "来源状态": src,
        })

    # ── ★ 红线①：显式保留「创造途径」
    rows.append({
        "id": "GAP-创造途径", "书": "M", "kind": "—",
        "quote": "（不是一条观点，是 T17 刻意标缺的一条能力）",
        "claim": "意义途径·创造：主体在现实世界里完成具体作为、改变客观境遇",
        "归属": "补缺",
        "归属理由": "★ **人工恢复**：它被 M-232 的「已实现」判定遮蔽过 —— "
                    "M-232 那句里含「创造性的工作」，而创造途径是 T17 刻意标缺的"
                    "（清单每行都是已实现单元，收进去会让缺口被算成已实现）。"
                    "**本条的存在就是为了不让缺口隐身。**",
        "置信": "高", "置信理由": "T17 已裁定它无可观察量，是确定的缺口",
        "缺口类型": "未定", "缺口类型_判据": "要等真正做的时候才定",
        "噪声": "无", "来源状态": "人工恢复",
    })

    io.open(OUT_JSON, "w", encoding="utf-8").write(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))

    # ── 报告
    from collections import Counter
    # ⚠️ **分母只有一个：候选池**（real = rows 去掉人工恢复那一行）。
    #    第一版这里用的是 `rows`（含人工恢复行），而交叉表用的是 `real` ——
    #    两个分母，于是报告里出现 772 vs 771、490 vs 489、353 vs 352 三处对不上。
    #    用户逐格重数抓到了。**一行人工恢复的插入不该改变任何一格统计。**
    _real = [r for r in rows if r["来源状态"] != "人工恢复"]
    _art = [r for r in rows if r["来源状态"] == "人工恢复"]
    bc = Counter(r["归属"] for r in _real)
    conf_all = Counter(r["置信"] for r in _real if r["归属"] == "补缺")
    kt_all = Counter(r["缺口类型"] for r in _real if r["归属"] == "补缺")
    by_book = Counter(r["书"] for r in _real if r["归属"] == "补缺")
    L = ["# 补缺清单报告", "",
         "> 由 `engine/gapfill.py` 生成。候选池 1882 条经四道筛子分成四类归属。", "",
         "## 四类归属（互斥）", "", "| 归属 | 条数 |", "|---|---|"]
    art0 = [r for r in rows if r["来源状态"] == "人工恢复"]
    real0 = [r for r in rows if r["来源状态"] != "人工恢复"]
    br0 = Counter(r["归属"] for r in real0)
    for k in ("补缺", "先修 OCR", "接线", "待核"):
        L.append("| %s | %d |" % (k, br0.get(k, 0)))
    L += ["| **合计** | **%d** |" % len(real0), "",
          "⚠️ **「接线」在池内计 0 条，但原因不是「都不在池里」**（第一版这么写是错的，"          "用户指出：池的定义本来就含待核 5 条，这是**一物两名，不是不在池里**）：", "",
          "19 条命中 = 去重 **16 个观点**，拆成两半：", "",
          "| 部分 | 条数 | 当前状态 | 在池里的身份 |",
          "|---|---|---|---|",
          "| 非待核 | **11** | 已实现 | **不在池里**（已实现不是缺口） |",
          "| 待核 5 条 | **5** | E-892 E-168 E-229 E-156 M-232 | **已由「待核」先认领** |", "",
          "**所以池内「接线」是 0 —— 因为那 5 条被「待核」先记账了，不重复计数。**",
          "四类归属仍然互斥、仍然合计 1882。", "",
          "19 条作为 T33 的工程电闸清单，完整交付在 `spec\\共识核.jsonl` 与",
          "`spec\\共识核报告.md` 的「接线清单」一节。", "",
          "⚠️ **「先修 OCR」池内 %d 条**，而 E 全量带真噪声的是 385 条 ——"
          % br0.get("先修 OCR", 0),
          "差额 %d 条的状态是「明确不实现」或「已实现」，本就不在候选池。"
          % (385 - br0.get("先修 OCR", 0)), "",
          "★ 另有 **%d 行人工恢复**（创造途径），**不属于候选池**，单列在下面。" % len(art0), "",
          "### 补缺（大类）内部的置信分级", "", "| 置信 | 条数 | 含义 |", "|---|---|---|",
          "| 高 | %d | 两次都判未实现 |" % conf_all.get("高", 0),
          "| 中 | %d | 只判过一次（首次判定） |" % conf_all.get("中", 0),
          "| 摇摆 | %d | 两次判断不一致，降优先级 |" % conf_all.get("摇摆", 0),
          "", "### 补缺的缺口类型（规则首判）", "", "| 类型 | 条数 |", "|---|---|"]
    for k, v in kt_all.most_common():
        L.append("| %s | %d |" % (k, v))
    L += ["", "### 补缺的按书分布", "", "| 书 | 条数 |", "|---|---|"]
    for b in BOOKS:
        L.append("| %s | %d |" % (b, by_book.get(b, 0)))
    L += ["", "## ★ 红线：被遮蔽的缺口（人工恢复）", ""]
    for r in rows:
        if r["来源状态"] == "人工恢复":
            L += ["**`%s`**" % r["claim"], "", "> %s" % r["归属理由"], ""]
    L += ["## 待核（严格锁死，不得剔除）", ""]
    for r in rows:
        if r["归属"] == "待核":
            L.append("- `%s`（%s）%s" % (r["id"], r["书"], r["归属理由"]))
    L += ["", "## 接线（口径 X 窄：只认有物理代码落点的 19 条）", ""]
    for r in rows:
        if r["归属"] == "接线":
            L.append("- `%s`（%s）%s" % (r["id"], r["书"], r["归属理由"]))
    # ── ★ 开发队列的白名单纪律（用户裁定，2026-10-02）
    #
    #   用户原话：
    #   > 「白名单纪律（开发队列只认缺口类型 ∈ 五类，未定 489 条读原文前不进队列）
    #   >   和未定 489 的处置路径说明，写进补缺清单报告.md 一节即可。」
    L += ["", "## ★ 开发队列的白名单纪律", "",
          "**开发队列只认这五类 `缺口类型`：**", "",
          "| 进队列 | 含义 | 当前条数 |", "|---|---|---|",
          "| `缺机制量` | 应该被算出来的量，机制层没这个变量 | %d |"
          % kt_all.get("缺机制量", 0),
          "| `缺流程` | 多轮才成立的做法，pipeline 里没有 | %d |"
          % kt_all.get("缺流程", 0),
          "| `缺规则` | 「什么时候做什么」的条件，条件表里没有 | %d |"
          % kt_all.get("缺规则", 0),
          "| `缺标记` | 该现象在标记表里没有对应检测项 | %d |"
          % kt_all.get("缺标记", 0),
          "| `缺原子` | 可组合的判断，原子里没有 | %d |"
          % kt_all.get("缺原子", 0), "",
          "**不进队列的两类：**", "",
          "| 类型 | 条数 | 处置 |", "|---|---|---|",
          "| `未定` | **%d** | **读原文前不进开发队列** —— 见下一节 |"
          % kt_all.get("未定", 0),
          "| `非缺口` | %d | **理念底色归档**：价值宣言与人性论断，"
          "本就不该落成判据 |" % kt_all.get("非缺口", 0), "",
          "⚠️ 白名单是**执行层**的闸门 —— 它在 `归属=补缺` 内部再筛一道，",
          "   不改变四类归属互斥（合计 %d）的骨架。" % len(real0), "",
          "## 未定 %d 条的处置路径" % kt_all.get("未定", 0), "",
          "**为什么不能直接进队列**：这一类的 `kind` 是「事实」或「临床」。",
          "本地零 API 判不出它到底是：", "",
          "```",
          "· 系统真的缺这个识别能力        → 该补",
          "· 这句话本就不该是判据          → 不该补（但本地认不出来）",
          "  —— 尤其 [E] 里有大量「某某认为……」的**转述**，",
          "     以及「这是别人方案的内部结构」的**文献综述**",
          "```",
          "",
          "**处置路径（三步，按顺序）：**", "",
          "```",
          "第 1 步（零 API）  按 OCR 噪声把未定条一分为二",
          "                  · 带真噪声 → 已归「先修 OCR」，先修语料",
          "                  · 无噪声   → 留在未定，等第 2 步",
          "",
          "第 2 步（要人读）  抽样读原文，判「该补 / 不该补」",
          "                  · 抽样比例与成本**先报数字**再跑",
          "                  · 用户已定：这类要花 API 的动作一律先报批",
          "",
          "第 3 步（产出）    该补的 → 补上缺口类型，进开发队列",
          "                  不该补的 → 归「非缺口」，转理念底色",
          "```", "",
          "**⚠️ 在第 2 步做完之前，这 %d 条一条都不许进开发队列。**"
          % kt_all.get("未定", 0), "", "## 先修 OCR", "",
          "带真噪声的条目。**它们不是「系统缺能力」，是「那句话读不通」** —— "
          "应先修语料，不进补缺清单。", "",
          "| 条数 | %d |" % bc.get("先修 OCR", 0), "|---|---|"]
    io.open(OUT_MD, "w", encoding="utf-8").write("\n".join(L) + "\n")

    print("=" * 80)
    print("T21｜候选池二次筛选")
    print("=" * 80)
    print("  候选池：%d 条（未实现 %d ＋ 待核 %d ＋ 不复现 %d）"
          % (len(pool), sum(1 for v in pool.values() if v == "未实现"),
             sum(1 for v in pool.values() if v == "待核"),
             sum(1 for v in pool.values() if v == "不复现")))
    print()
    # ⚠️ 「人工恢复」那一行（创造途径）**不是候选** —— 把它从四类里拆出来，
    #    否则总数会读成 1883、像是算错了。
    art = _art
    real = _real
    br = Counter(r["归属"] for r in real)
    print("  四类归属（互斥，候选池 %d 条）：" % len(real))
    for k in ("补缺", "先修 OCR", "接线", "待核"):
        print("     %-10s %4d" % (k, br.get(k, 0)))
    print("     %-10s %4d %s" % ("合计", len(real),
                                 "✓ = %d" % len(pool) if len(real) == len(pool) else "★"))
    print()
    print("  ★ 另有**人工恢复 %d 行**（不属于候选池）：%s"
          % (len(art), [r["claim"][:20] for r in art]))
    print()
    print("  补缺内部置信：%s" % dict(conf_all))
    print("  补缺缺口类型：%s" % dict(kt_all))
    print("  补缺按书：%s" % dict(by_book))
    print()
    print("已写出：%s" % OUT_JSON)
    print("已写出：%s" % OUT_MD)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
