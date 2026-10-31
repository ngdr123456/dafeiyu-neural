# -*- coding: utf-8 -*-
"""管理员：审核「系统 × 训练师」的交流与评价，产出待审改动。

判据分两层，**权重完全不同**（这是本模块最要紧的一条纪律）
────────────────────────────────────────────────────────────
    事实层 = 可观察的东西。**只有它能作为改动依据。**
             静默轮／闸门拒绝及原因／无标记命中／手写语料的期望 vs 实际／
             反复同动作／死规则／极性漂移
    意见层 = 训练师 AI 的评价。**只作线索**，用来指出"该去看哪里"。

    为什么不许拿意见当依据：训练师也是模型。拿模型的意见去改系统，
    就是**模型自己给自己判卷**。走这条路，系统最后会变成"讨模型喜欢"
    而不是"对人有用" —— 而"讨好评判者"正是这个项目从一开始就要挡的东西
    （Baldwin 警告：只靠趋避的系统一定会学成迎合）。

三本书不能变成装饰（用户原话：「三本书籍可不能少」）
    做法不是喊口号，是可执行的规则：
    **每一条改动提案，必须能追溯到书里的哪句话（带页码）。
      追溯不到的，必须标 ENG（我拍脑袋），而 ENG 的一律不许自动应用。**
    项目里已有 `tests/verify_traceability.py` 在查这件事，所以这条会被机器拦下。

只报告 + 提案，不偷偷改
    管理员的输出是一个诊断与改进建议队列。D-028已移除桌面批量批准入口；
    历史决定只记录授权，程序修改仍须实施、验证，不能声称下一轮自动生效。
    实际实施程序改动后需回归验证；本观察模块不执行修改或自动回滚。
"""
from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict

# 稳定主键 / 数据指纹 / 结案记录（用户裁定 2026-10-02）
import proposal_log as PL          # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))
# 打包成 exe 后 `__file__` 指向解包出的临时目录 —— 于是 rules/corpus 找不到，
# 而且**台账会写进临时目录、退出就丢**。所以允许用 EGO_ROOT 指定项目根，
# 由启动器（exe）在导入任何引擎模块之前设置。
# 不设 EGO_ROOT 时行为与从前完全一致（源码运行时就是这个分支）。
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)
for _p in (_ROOT, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

TRAIN_DIR = os.path.join(_ROOT, "state", "train")
QUEUE = os.path.join(TRAIN_DIR, "review_queue.json")
DECISIONS = os.path.join(TRAIN_DIR, "decisions.jsonl")
CHANGE_LOG = os.path.join(_ROOT, "spec", "管理员改动记录.md")

SILENCE_LINE = "（本轮不作回应，仅记录。）"

# 样本量的用法：**标注，不压掉**。
#
# ⚠️ 这里改过一次，用户的批评是对的：
#   第一版我拿它**压掉**了发现（"样本不足 → 不报"）。那违反了本项目
#   一整轮在守的规矩（台账作废是标注不是删、反例是标注不是改）——
#   而且压掉比删掉更坏：**用户根本看不到它存在过。**
#   更根本的是：**样本就是 AI 和系统聊出来的**，训练本来就会让它积累。
#   用"样本不足"把发现堵回去，等于把训练的意义否掉了。
#
# 还有一处更细的错：**单轮观察根本不需要样本量**。
#   "这一句回得机械"是对**一轮**的判断 —— 一轮就是一轮。
#   只有**频率类结论**（"30% 的轮次没抓到标记"）才需要标注样本量。
#   第一版把这两类混成一类，是设计错误。
#
# 现在：频率类结论照报，后面附一句样本量；单轮观察一律照报。
MIN_TURNS = 36          # 只用于"这个频率结论可不可靠"的标注，不用于决定报不报


# ------------------------------------------------------------------ 读取

def _read_jsonl(p: str) -> list[dict]:
    out = []
    if not os.path.exists(p):
        return out
    for line in io.open(p, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:                          # noqa: BLE001
            continue
    return out


def load_train(ledger: str | None = None, evals: str | None = None) -> tuple[list, list]:
    lp = ledger or os.path.join(TRAIN_DIR, "ledger.jsonl")
    ep = evals or os.path.join(TRAIN_DIR, "eval.jsonl")
    rows = [r for r in _read_jsonl(lp) if not r.get("__ERA_BOUNDARY__") and not r.get("void")]
    return rows, _read_jsonl(ep)


# ------------------------------------------------------------------ 事实层检查

def _finding(layer: str, kind: str, sev: int, title: str, detail: str,
             evidence: list, proposal: dict | None = None) -> dict:
    return {"id": "%s-%s-%d" % (layer, kind, abs(hash(title)) % 100000),
            "layer": layer, "kind": kind, "severity": sev,
            "title": title, "detail": detail,
            "evidence": evidence[:8],
            "proposal": proposal}


def check_silence(rows: list) -> list[dict]:
    """静默轮 —— 它没接住。这是事实，不是意见。"""
    sil = [r for r in rows if (r.get("output") or "").strip() == SILENCE_LINE]
    if not sil:
        return []
    kinds = Counter("有标记但沉默" if r.get("markers_fired") else "无标记可抓"
                    for r in sil)
    return [_finding("fact", "静默", 2,
                     "有 %d 轮沉默（%.0f%%）" % (len(sil), 100.0 * len(sil) / max(1, len(rows))),
                     "分布：%s。沉默是允许的答案，但**成规模**就说明抓不到用户的话。"
                     % dict(kinds),
                     [{"turn": r.get("turn_id"), "input": r.get("raw_input", "")[:40]}
                      for r in sil])]


def check_gate(rows: list) -> list[dict]:
    """闸门拒绝簇 —— 按原因归类。拒绝率高说明"大脑/渲染基本没生效"。"""
    rej = []
    for r in rows:
        for n in (r.get("notes") or []):
            if "退回" in n or "未过" in n or "被闸门" in n:
                m = re.search(r"（(.{2,60}?)(｜|）)", n)
                rej.append({"turn": r.get("turn_id"),
                            "reason": (m.group(1) if m else n[:50]),
                            "note": n[:110]})
    if not rej:
        return []
    c = Counter(x["reason"] for x in rej)
    top, cnt = c.most_common(1)[0]
    return [_finding("fact", "闸门拒绝", 2,
                     "%d 处退回｜主因：%s（%d 次）" % (len(rej), top, cnt),
                     "退回率 %d/%d。退回越多，模型越白接；输出越像模板。"
                     % (len(rej), len(rows)),
                     rej)]


def check_no_marker(rows: list) -> list[dict]:
    """无标记命中 —— 它在这句话里什么都没听出来。**照报，只附样本量。**"""
    nm = [r for r in rows if not r.get("markers_fired") and r.get("intent") == "ANSWER"]
    if not nm:
        return []
    small = "（样本 %d 轮，低于 %d —— 频率结论先当线索看，但**这不构成不报的理由**）" \
            % (len(rows), MIN_TURNS) if len(rows) < MIN_TURNS else ""
    return [_finding("fact", "无标记", 1,
                     "%d 轮没抓到任何标记（%.0f%%）%s"
                     % (len(nm), 100.0 * len(nm) / max(1, len(rows)), small),
                     "这些轮次系统只能靠机制状态兜底或沉默。若某些说法反复出现却始终抓不到，"
                     "那就是**词表缺口**（本项目已复发多次的那一类）。",
                     [{"turn": r.get("turn_id"), "input": r.get("raw_input", "")[:40]}
                      for r in nm])]


def check_corpus_truth(rows: list, evals: list) -> list[dict]:
    """手写语料的期望 vs 实际 —— **人写的真值**，这是最硬的事实层。

    为什么它最硬：期望是人定的（来自三本书的判据），不是模型说的。
    它是整个循环里唯一不依赖模型意见的锚。
    """
    import train as T
    exp = {c["text"]: set(c["expect"]) for c in T.load_corpus() if c["expect"]}
    if not exp:
        return []
    miss, wrong = [], []
    for r in rows:
        raw = (r.get("raw_input") or "").strip()
        if raw not in exp:
            continue
        got = set(r.get("markers_fired") or [])
        want = exp[raw]
        if want - got:
            miss.append({"turn": r.get("turn_id"), "input": raw[:40],
                         "want": sorted(want), "got": sorted(got)})
        elif got - want:
            wrong.append({"turn": r.get("turn_id"), "input": raw[:40],
                          "want": sorted(want), "got": sorted(got)})
    out = []
    if miss:
        out.append(_finding("fact", "语料漏判", 3,
                            "手写语料里有 %d 处漏判" % len(miss),
                            "期望来自三本书的判据（人写的）。漏判 = 规则层没覆盖到。",
                            miss))
    if wrong:
        out.append(_finding("fact", "语料误判", 3,
                            "手写语料里有 %d 处误判" % len(wrong),
                            "多出来的标记不是期望的 —— 词表太宽或反例没生效。",
                            wrong))
    return out


def check_dead_rule(rows: list) -> list[dict]:
    """死规则 —— 写了但永远不会生效。本项目已发现四例。

    ⚠️ 照报，只附样本量。第一版拿样本量把它**压掉**了 —— 那是错的（见文件头）。
       样本会随训练积累，而"不报"等于让这个问题永远不被看见。
    """
    import mechanism as M
    try:
        allc = [c.id for c in M.conditions(M.MechanismConfig())]
    except Exception:                              # noqa: BLE001
        return []
    seen = Counter((r.get("mech") or {}).get("phase") for r in rows if r.get("mech"))
    never = [c for c in allc if c not in seen]
    if not never:
        return []
    small = "（样本 %d 轮，低于 %d —— 轮次少时「从未触发」较常见，但**照报**，由人判断）" \
            % (len(rows), MIN_TURNS) if len(rows) < MIN_TURNS else ""
    return [_finding("fact", "死规则", 2,
                     "机制条件表里有 %d 条从未触发：%s %s"
                     % (len(never), "、".join(never), small),
                     "先到先得的条件表里，排在后面的条件可能永远轮不到 —— "
                     "`NOTHING_MORE` 就是这样一条（实测 68 轮里一次没轮到）。"
                     "**这是要补的清单，不是「数据不够所以别管」。**",
                     [{"condition": c} for c in never])]


def check_repeat(rows: list, n: int = 4) -> list[dict]:
    """同一个动作连着做 —— [D] 敏化：反复做同一件事，效果递减。"""
    runs, cur = [], []
    for r in rows:
        b = r.get("behavior")
        if cur and cur[-1] == b:
            cur.append(b)
        else:
            if len(cur) >= n:
                runs.append(cur[0])
            cur = [b]
    if len(cur) >= n:
        runs.append(cur[0])
    if not runs:
        return []
    return [_finding("fact", "反复同动作", 1,
                     "有 %d 段连续同动作（≥%d 次）：%s" % (len(runs), n, "、".join(set(runs))),
                     "同一个动作连着做，越做越没用（[D] 敏化）。"
                     "性格层的 R1 规则本该在这里介入 —— 若没介入，说明阈值够不到。",
                     [{"behavior": b} for b in runs])]


def check_polarity(evals: list) -> list[dict]:
    """训练师/管理员的评价聚合。

    ★ 用户已定：**AI 的评价参与决策。**（原话：「内置一个管理员来审核 ai 和系统的
      交流情况，还有 ai 对系统的评价，并以此来更新系统。」）
      我原先写"只作线索，不作依据"，那是**拿我自己的判断盖过用户的指示**，已改。

      现在唯一的约束是**可回溯**：每条意见必须写明它指向哪个可观察对象
      （哪一轮、哪一句话）。理由不是限制它的权力，而是——将来发现系统长歪了，
      要能查出是哪条意见导致的。**没有指向的意见无法回溯，所以无法负责。**
    """
    bad = [e for e in evals if (e.get("tutor") or {}).get("problem", "none") != "none"]
    if not bad:
        return []
    c = Counter((e["tutor"] or {}).get("problem") for e in bad)
    ev = [{"input": e.get("input", "")[:34],
           "output": (e.get("output") or "").replace("\n", " ")[:44],
           "behavior": e.get("behavior"),
           "problem": (e["tutor"] or {}).get("problem"),
           "why": (e["tutor"] or {}).get("why", "")[:60]}
          for e in bad]
    return [_finding("opinion", "训练师评价", 2,
                     "训练师指出 %d 处问题：%s"
                     % (len(bad), "、".join("%s×%d" % (k, v) for k, v in c.most_common())),
                     "**参与决策**（用户指定）。每条意见都指向了具体轮次与具体那句话，"
                     "所以可回溯 —— 将来长歪了，能查出是哪条意见导致的。"
                     "单轮观察不需要样本量：一轮就是一轮。",
                     ev)]


FACT_CHECKS = [check_silence, check_gate, check_no_marker,
               check_corpus_truth, check_dead_rule, check_repeat]
OPINION_CHECKS = [check_polarity]


# ------------------------------------------------------------------ 提案

def propose(findings: list[dict]) -> list[dict]:
    """从**事实层**的发现生成提案。意见层**不生成提案** —— 这是刻意的。

    每条提案必须带 `trace`：
      · "原书 [pNN]" —— 能追溯到书里的哪句话（可自动应用）
      · "ENG"        —— 追溯不到，是我拍脑袋（**必须人批，不许自动应用**）
      · "corpus"     —— 来自手写语料的期望（人写的真值，可自动应用）
    """
    out = []
    for f in findings:
        if f["layer"] != "fact":
            continue
        k = f["kind"]
        if k == "语料漏判":
            for e in f["evidence"]:
                out.append({"kind": "lexicon_gap", "trace": "corpus",
                            "_target": e["input"],
                            "summary": "补词表：让「%s」命中 %s"
                                       % (e["input"][:16], "、".join(e["want"])),
                            "detail": "期望来自手写语料（人写，源自三本书的判据）。"
                                      "**补什么词仍要人写** —— 自动生成同义词是自证循环。",
                            "evidence": e})
        elif k == "语料误判":
            for e in f["evidence"]:
                out.append({"kind": "lexicon_too_wide", "trace": "corpus",
                            "_target": e["input"],
                            "summary": "收窄词表：「%s」不该命中 %s"
                                       % (e["input"][:16], "、".join(set(e["got"]) - set(e["want"]))),
                            "detail": "多出来的标记。收窄要给出**为什么这个词不算**的理由，"
                                      "理由不足就标 ENG。",
                            "evidence": e})
        elif k == "闸门拒绝":
            out.append({"kind": "gate_review", "trace": "ENG",
                        "_target": PL.TARGETS["gate_review"],
                        "summary": "复核闸门主因：%s" % f["title"],
                        "detail": "闸门拒绝对不对要逐个看 —— 有些是模型真的越界（该拒），"
                                  "有些是材料喂错了（该修材料）。**不许为了降低拒绝率而放宽闸门。**",
                        "evidence": f["evidence"][:4]})
        elif k == "死规则":
            out.append({"kind": "dead_rule", "trace": "ENG",
                        "_target": PL.TARGETS["dead_rule"],
                        "summary": f["title"],
                        "detail": "两条路：调阈值让它可达（要说明依据），或承认它是死的并标出来。"
                                  "**不许为了让指标好看而调阈值。**",
                        "evidence": f["evidence"]})
        elif k == "静默":
            out.append({"kind": "coverage", "trace": "ENG",
                        "_target": PL.TARGETS["coverage"],
                        "summary": "复核沉默轮：是不是真的没接到",
                        "detail": "沉默是允许的答案。但成规模时，要分辨是"
                                  "「用户确实没说可观察的东西」还是「我抓不到」。",
                        "evidence": f["evidence"][:4]})
    # 去重（同 kind+summary）
    seen, uniq = set(), []
    for p in out:
        kk = (p["kind"], p["summary"])
        if kk in seen:
            continue
        seen.add(kk)
        uniq.append(p)
    for i, p in enumerate(uniq):
        # pid 是**位次号**，只供界面显示 —— **绝不作持久化外键**
        #   （用户裁定；事由：位次一变 pid 就指向另一条提案，**已实际串号过**）
        p["pid"] = "P%03d" % (i + 1)
        p["sid"] = PL.sid_of(p["kind"], p.pop("_target", p["kind"]))
        p["status"] = "pending"
    return uniq


# ══════════════════════════════════════════════════════════════
# 规律性异常扫描（两级人工授权的触发器）
# ══════════════════════════════════════════════════════════════
#
# 用户裁定的核心准则（原话）：
#   「区分『执行层小毛病』与『战略级冲突』：日常小毛病留给训练自己消化：
#     单次抖动、偶发跑题、轻微机械化等常规问题，由系统在常规迭代中自行解决，
#     **严禁上报打扰人工**。」
#   「升级议案的唯一触发门槛：只有当管理员通过复盘发现——当前执行层的结果
#     已经无法换来大纲目标的完成，或者执行层逻辑与大纲顶层目标产生了
#     无法自愈的根本冲突时，才允许发起登记并申请查阅总纲领。」
#
# ⚠️ 所以：**代码里没有任何阈值**。本模块只负责把统计聚合原样摆到管理员面前，
#    由它凭语义理解判断「这是执行层小毛病，还是推进受阻」。
#    代码机械写死阈值 = 把用户的判断权挪到代码里，那是错的。

ANOMALY_SYSTEM = """你是这个项目的**管理员**。下面是这一批训练的**统计台账**。

你的任务只有一件：判断台账里有没有出现**推进受阻 / 目标冲突**级别的异常。

────────────────────────────────────────────────────────
【什么算 —— 这是唯一的门槛】
────────────────────────────────────────────────────────
只有下面两种情形才允许登记：

  ① **推进受阻**：当前执行层的结果，**已经无法换来大纲目标的完成**。
     不是"这一批跑得不好"，而是"照这样跑下去，目标到不了"。

  ② **根本冲突**：执行层的逻辑与大纲顶层目标产生了**无法自愈**的矛盾。
     不是"某条规则调一下就好"，而是"这两件事本身互相顶着，自己解不开"。

判断的依据是**语义**，不是数字。同一个数字放不同上下文里，
可能是噪声，也可能是结构性问题 —— **判断权在你，不在数字**。

────────────────────────────────────────────────────────
【什么不算 —— 一律不要登记，严禁上报打扰人工】
────────────────────────────────────────────────────────
  · 单次抖动、偶发跑题、轻微机械化 —— 这类日常小毛病留给训练自己消化
  · 数量大但形态分散、根因各异
  · 某个分类次数多，但样本读下来指向的根因各不相同
  · 你自己也说不清依据的「感觉不对」
  · **任何"调个阈值 / 补个词表就能好"的问题** —— 那属于常规迭代，不是战略问题

⚠️ 宁可一条都不报，也不要把执行层小毛病报上来。
   单次不可能有一大堆战略级异常 —— 真到了那一步，核心瓶颈也就 1~3 个。

────────────────────────────────────────────────────────
【若要登记：字段必须严格合规，缺一个都会被底层校验拒止】
────────────────────────────────────────────────────────
  pattern   异常的**类别名**。用台账里**已有**的分类
            （mechanical / off_topic / too_little …；闸门类写 gate:<主因>；
             规则类写 rule:<ID>）。**不要自造新词。**
  count     该形态出现的次数。**必须 ≥ 2，且必须取自上面台账的数字** ——
            不许自己估、不许编。
  window    统计跨了多少轮。同样取自台账。
  evidence  客观依据：一句话说清「什么形态、出现几次、集中在哪」。
  why       你为什么判它到了**推进受阻/根本冲突**这一级（不是"次数多"，
            而是"照这样下去目标到不了"或"这两件事互相顶着"）。

【输出】严格的 JSON 数组，不要任何解释文字、不要 markdown 代码块：
[{"pattern":"...","count":7,"window":30,"evidence":"...","why":"..."}]

一条都不值得登记就输出：[]
"""

ANOMALY_MAX = 3
# 一批最多登记几条。
# 用户原话：「既然是触及大纲完成受阻级别的异常，单次不可能有一大堆，
#            只抓最核心的 1~3 个关键瓶颈即可。」
# ⚠️ 这**不是判定阈值** —— 它不参与"算不算异常"的判断，
#    只限制"一次最多登记几条"。超出的部分记入 rejected，不静默丢弃。


def _anomaly_brief(q: dict, rows: list, evals: list) -> tuple:
    """把聚合压成一段**客观台账**。返回 (文本, 有没有材料)。

    ★ 只陈述数字与样本，**不做任何定性** —— 定性是管理员的活。
    """
    L = []
    L.append("【本轮统计台账】共 %d 轮对话｜%d 条管理员评价"
             % (len(rows), len(evals)))
    if (q.get("current_evidence") or {}).get("has_material"):
        L.append("【当前运行与源码验收】这是工程证据；旧版本和脚本材料不能冒充当前真人经历。")
        L.append(json.dumps(q["current_evidence"], ensure_ascii=False))

    # ── 问题分类计数 + 样本
    bad = [e for e in evals
           if (e.get("tutor") or {}).get("problem", "none") != "none"]
    if bad:
        c = Counter((e["tutor"] or {}).get("problem") for e in bad)
        L.append("问题分类计数：" + "、".join("%s×%d" % (k, v)
                                              for k, v in c.most_common()))
        L.append("  样本（每类取 2 条）：")
        shown: Counter = Counter()
        for e in bad:
            p = (e["tutor"] or {}).get("problem")
            if shown[p] >= 2:
                continue
            shown[p] += 1
            L.append("    %s｜输入「%s」→ 回应「%s」｜管理员说：%s"
                     % (p, (e.get("input") or "")[:30],
                        (e.get("output") or "").replace("\n", " ")[:38],
                        ((e["tutor"] or {}).get("why") or "")[:64]))

    # ── 闸门拒绝（按原因）
    rej = []
    for r in rows:
        for n in (r.get("notes") or []):
            if "退回" in n or "未过" in n or "被闸门" in n:
                m = re.search(r"（(.{2,60}?)(｜|）)", n)
                rej.append(m.group(1) if m else n[:50])
    if rej:
        c = Counter(rej)
        L.append("闸门拒绝 %d 处｜主因：%s"
                 % (len(rej), "、".join("%s×%d" % (k, v)
                                        for k, v in c.most_common(3))))

    # ── 静默
    sil = [r for r in rows if (r.get("output") or "").strip() == SILENCE_LINE]
    if sil:
        kinds = Counter("有标记但沉默" if r.get("markers_fired") else "无标记可抓"
                        for r in sil)
        L.append("沉默 %d 轮（%.0f%%）｜分布：%s"
                 % (len(sil), 100.0 * len(sil) / max(1, len(rows)), dict(kinds)))

    # ── 现成的检查结论（它们已经带了计数）
    fs = (q.get("facts") or []) + (q.get("opinions") or [])
    if fs:
        L.append("已跑出的检查结论：")
        for f in fs:
            L.append("    [%s] %s ｜ %s"
                     % (f.get("layer"), (f.get("title") or "")[:70],
                        (f.get("detail") or "").replace("\n", " ")[:70]))

    has = bool(bad or rej or sil or fs or (q.get("current_evidence") or {}).get("has_material"))
    return "\n".join(L), has


def _existing_aid_for(pattern: str) -> str | None:
    """按 **pattern** 找一条**尚未结案**的异常，用于证据累加。

    ★ 用户裁定：「pattern 到 aid 映射由代码接管，按同类合并累加证据，
      管理员不碰 aid。」

    只走公开接口：`charter.audit()` 拿事件，`charter.state_of()` 折叠状态。
    已提交报告（submitted）的不再合并 —— 那个案子已经结了。
    """
    import charter as C
    last: dict = {}
    for e in C.audit(limit=100000):
        if e.get("ev") == "anomaly":
            last[e.get("aid")] = e.get("pattern")
    for aid, pat in last.items():
        if pat != pattern:
            continue
        try:
            if C.state_of(aid)["report"]["status"] != "submitted":
                return aid
        except Exception:                          # noqa: BLE001
            continue
    return None


def _anomaly_scan(q: dict, rows: list, evals: list) -> dict:
    """把台账交给管理员判断 → 收结构化异常 → 逐条转交登记。

    ★ 用户裁定（甲案）：判断必须由**管理员**做，
      「严禁代码机械写死阈值」。所以本函数只做三件事：
        ① 搬数据（`_anomaly_brief`）
        ② 收结论（一次专门的 API 调用）
        ③ 转交登记（`Admin.note_anomaly`，底层结构化校验照旧生效）

    返回 {"ok", "asked", "filed": [...], "rejected": [...], "skipped": ...}

    ⚠️ 本函数**绝不把异常抛给 review()** —— 审核不该因为这一步挂掉。
    """
    brief, has = _anomaly_brief(q, rows, evals)
    if not has:
        # 用户裁定：空台账直接跳过，不做无谓推断
        return {"ok": True, "asked": False, "skipped": "无任何异常样本",
                "filed": [], "rejected": []}

    try:
        import charter as C
        from admin_agent import Admin                 # 延迟导入，避免循环依赖
        ad = Admin()
        if not ad.available:
            return {"ok": False, "asked": False, "skipped": "管理员 API 不可用",
                    "filed": [], "rejected": []}
        d, _ = ad.reader._post(
            [{"role": "system", "content": ANOMALY_SYSTEM},
             {"role": "user", "content": brief}], json_mode=False)
        txt = (((d.get("choices") or [{}])[0].get("message", {}) or {})
               .get("content") or "").strip()
        txt = re.sub(r"^```(?:json)?\s*|\s*```$", "", txt.strip())   # 容忍代码块
        items = json.loads(txt) if txt else []
        if not isinstance(items, list):
            items = []
    except Exception as e:                             # noqa: BLE001
        return {"ok": False, "asked": True, "error": repr(e)[:160],
                "filed": [], "rejected": []}

    filed, rejected = [], []
    for i, it in enumerate(items):
        if i >= ANOMALY_MAX:
            rejected.append({"_why": "超出单批上限 %d" % ANOMALY_MAX, "item": it})
            continue
        if not isinstance(it, dict):
            rejected.append({"_why": "不是对象", "item": it})
            continue
        pat = str(it.get("pattern") or "").strip()
        merged = _existing_aid_for(pat)
        try:
            aid = merged or C.new_aid()
            # ★ 底层结构化校验在这里生效：缺 count/window/evidence 或 count<2
            #   会抛 ValueError —— 我们**不吞成 pass**，而是如实记进 rejected
            ad.note_anomaly(aid, pat, it.get("count"), it.get("window"),
                            it.get("evidence"), it.get("why", ""))
            filed.append({"aid": aid, "pattern": pat,
                          "count": it.get("count"), "window": it.get("window"),
                          "merged": bool(merged)})
        except Exception as e:                         # noqa: BLE001
            rejected.append({"_why": str(e)[:120], "item": it})

    return {"ok": True, "asked": True, "brief_chars": len(brief),
            "filed": filed, "rejected": rejected}


# ------------------------------------------------------------------ 主入口

def review(ledger: str | None = None, evals: str | None = None) -> dict:
    rows, ev = load_train(ledger, evals)
    findings: list[dict] = []
    for fn in FACT_CHECKS:
        try:
            findings += fn(rows, ev) if fn is check_corpus_truth else fn(rows)
        except TypeError:
            findings += fn(rows)
        except Exception as e:                     # noqa: BLE001
            findings.append(_finding("fact", "检查异常", 1, "%s 崩了" % fn.__name__,
                                     repr(e)[:120], []))
    for fn in OPINION_CHECKS:
        try:
            findings += fn(ev)
        except Exception as e:                     # noqa: BLE001
            findings.append(_finding("opinion", "检查异常", 1, "%s 崩了" % fn.__name__,
                                     repr(e)[:120], []))
    props = propose(findings)
    # 数据指纹 + 结案标注（用户裁定 2026-10-02）
    #   指纹 = 这条提案**依据的是哪一批数据**
    #   （P003 的教训：拿 T33 之前的旧台账下结论，没有指纹就看不出来）
    _fp = PL.fingerprint(len(rows), len(ev), rows)
    for _p in props:
        PL.annotate(_p, _fp)
    q = {"generated": time.strftime("%Y-%m-%d %H:%M:%S"),
         "fingerprint": _fp,
         "turns": len(rows), "evals": len(ev),
         "facts": [f for f in findings if f["layer"] == "fact"],
         "opinions": [f for f in findings if f["layer"] == "opinion"],
         "proposals": props}
    from admin_evidence import snapshot as evidence_snapshot
    q["current_evidence"] = evidence_snapshot(_ROOT)
    os.makedirs(TRAIN_DIR, exist_ok=True)
    # ★ 规律性异常扫描（用户批准的甲案）：把聚合交给管理员**判断**，
    #   由它决定是否 note_anomaly 登记。**这里没有任何阈值。**
    try:
        q["anomaly_scan"] = _anomaly_scan(q, rows, ev)
    except Exception as e:                     # noqa: BLE001
        # 这一步失败不许拖垮审核 —— 但也如实记下来，不静默
        q["anomaly_scan"] = {"ok": False, "error": repr(e)[:160],
                             "filed": [], "rejected": []}
    from behavior_learning import atomic_json
    atomic_json(QUEUE, q)
    return q


def log_decision(pid: str, approve: bool, title: str, note: str = "",
                 sid: str = "", kind: str = "", fp: dict | None = None,
                 root: str | None = None) -> None:
    """记一笔决定。

    `sid` 是**稳定主键**（用户裁定 2026-10-02）。`pid` 只是界面序号，
    留着是为了旧记录可读 —— **但一切对外键都用 sid**。
    """
    rec = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "pid": pid, "sid": sid,
           "decision": "approve" if approve else "reject", "title": title, "note": note}
    # ⚠️ `root` 是**测试隔离入口**（同 carry/crashguard 的 set_dir）：
    #   不给就写真实路径（生产行为不变），给了就整条链都落沙箱。
    _dec = (os.path.join(root, "state", "train", "decisions.jsonl")
            if root else DECISIONS)
    os.makedirs(os.path.dirname(_dec), exist_ok=True)
    with io.open(_dec, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    if approve and not root:
        _log_change(rec)
    # 同步写**结案记录**（proposal_outcomes.jsonl）——
    #   这才是"批准之后有机制后果"的落点：管理员下次生成提案前会读它。
    if sid:
        PL.record(sid, kind or pid, "approved" if approve else "rejected",
                  title, fp=fp, note=note, root=root)
        # ★ 批准 → **进任务清单**（用户裁定：批准必须有机制后果）
        #   驳回**不进**（驳回 = 不改，但按裁定**可以再提**）
        if approve:
            PL.enqueue_task(sid, kind or pid, title, note, root=root)


def _log_change(rec: dict) -> None:
    """批准的改动必须留痕：项目的规矩是**只加分界，不删历史**。"""
    new = not os.path.exists(CHANGE_LOG)
    with io.open(CHANGE_LOG, "a", encoding="utf-8") as f:
        if new:
            f.write("# 管理员改动记录\n\n"
                    "> 训练循环里**经人批准**的改动。只追加，不删。\n"
                    "> 依据分两层：**事实层**（可观察，能作为依据）／"
                    "**意见层**（训练师评价，只作线索）。\n\n"
                    "| 时间 | 提案 | 内容 | 依据 |\n|---|---|---|---|\n")
        f.write("| %s | %s | %s | 人批准 |\n" % (rec["ts"], rec["pid"], rec["title"]))


def regression() -> dict:
    """跑核心回归。应用改动后必须跑，失败就回滚。"""
    res = {}
    for name in ("test_markers.py", "test_pipeline.py", "test_mechanism.py"):
        p = os.path.join(_ROOT, "tests", name)
        try:
            r = subprocess.run([sys.executable, p], capture_output=True, timeout=600,
                               cwd=_ROOT)
            res[name] = {"code": r.returncode, "ok": r.returncode == 0}
        except Exception as e:                     # noqa: BLE001
            res[name] = {"code": -1, "ok": False, "err": repr(e)[:80]}
    res["_all_ok"] = all(v.get("ok") for k, v in res.items() if not k.startswith("_"))
    return res


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="管理员：审核训练过程，产出待审队列")
    ap.add_argument("--regression", action="store_true", help="顺带跑一次回归")
    a = ap.parse_args()
    q = review()
    print("=" * 74)
    print("管理员审核｜交流 %d 轮｜训练师评价 %d 条" % (q["turns"], q["evals"]))
    print("=" * 74)
    print("\n【事实层】可观察，**能作为改动依据**")
    for f in q["facts"]:
        print("  · [%d] %s" % (f["severity"], f["title"]))
        print("      %s" % f["detail"][:96])
    print("\n【意见层】训练师/管理员的评价 —— **参与决策**（用户指定），须可回溯")
    for f in q["opinions"]:
        print("  · [%d] %s" % (f["severity"], f["title"]))
        print("      %s" % f["detail"][:96])
    print("\n【提案】%d 条（只有事实层能生成提案）" % len(q["proposals"]))
    for p in q["proposals"]:
        print("  · %s [%s] %s" % (p["pid"], p["trace"], p["summary"][:60]))
    print("\n队列已写入 %s" % QUEUE)
    if a.regression:
        r = regression()
        print("\n回归：%s" % ("全绿" if r["_all_ok"] else "**有失败**"))
        for k, v in r.items():
            if not k.startswith("_"):
                print("  %-20s %s" % (k, "OK" if v.get("ok") else "FAIL"))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
