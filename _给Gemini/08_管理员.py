# -*- coding: utf-8 -*-
"""管理员：**一个视角，兼职两个职位。**（用户明令，本模块存在的理由）

    > 「管理员兼职家教的位置，这两个职位不是分开的。」
    > 「不是一个职位两个视角啊，**是一个视角兼职两个职位**。」
    > 「你不要把这两个界限划这么明显，**管理员的知识和感知是共通的**。」

两个职位
────────────────────────────────────────────────────────────
    职位一｜**家教**：作为"某人"被系统遇到 —— 供给 [M] 的**体验途径**。
             「人之所以为人，是因为他总是指向自身以外的某种事物或某人」

    职位二｜**审核**：看交流、看评价、验收版本、更新系统。
             用户原话：「内置一个管理员来审核 ai 和系统的交流情况，
             还有 ai 对系统的评价，并以此来更新系统」

两个职位的纪律**是冲突的**，这一点必须摆在明处
────────────────────────────────────────────────────────────
    审核必须**能判、能驳**（有验收标准、有冲突计数）。
    家教面对的是存在，而 [M] 明令**不许评判**：
      「意义疗法师在所有心理治疗师当中最不愿意对患者进行价值评判，
        因为他绝对不允许患者将评判的责任转移给医生。」

    ⚠️ 我第一版的错法是「把冲突拆给两个主体」—— 分开写了一个 Tutor、一个 admin。
       那是**低一级的解法**（分化）。[E] 说自我是「**组织与综合的功能**」：
       「组织或综合的功能不是自我以外的东西，**它恰恰是自我本身**」——
       让一个主体同时扛住两件冲突的事，才是自我在做的事（整合）。

知识与感知**共通**，这不是省事，是设计
────────────────────────────────────────────────────────────
    · **知识**共通：系统能力清单（96 单元）、观点总表（2921 条）、验收标准、判定类别
    · **感知**共通：它跟系统待出来的每一轮记录

    共通买到的东西，分开买不到：

        审核 —— 不是照规格空判，是**照规格判，而且它跟系统待过**
        家教 —— 不是照剧本陪，是**当那个"某人"，而且它知道系统里面在算什么**

    更要紧的是：**一个知道机器内部的家教，是骗不了的。**
    系统没法靠"演得好"讨好它，因为它看得见底下在算什么。
    分成两个主体只能靠**隔断**避免污染；合成一个是从根上**让讨好没有收益**。

    这也正是这个项目一路在挡的那件事（Baldwin 警告：只靠趋避的系统一定学成迎合）。
"""
from __future__ import annotations

import io
import json
import os
import sys
import time

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
SHARED = os.path.join(TRAIN_DIR, "admin_memory.json")

# ---- 共通的感知：它跟系统待过的每一轮都记在这里 ----
PERCEPTION = os.path.join(TRAIN_DIR, "eval.jsonl")

# ---- 家教那一半：判定类别（封闭集合，不许自创）----
PROBLEMS = ("none", "off_topic", "mechanical", "boundary",
            "too_little", "too_much", "fabricated")

SPEAK_SYSTEM = """你在跟一个对话程序相处。你不是它的用户，你是**它遇到的那个人**。

给你一个半句题面或上一轮的对话，你**用第一人称**接着写 —— 一到两句。
要像真人在说话：可以有犹豫、口语、具体细节，也可以答得含糊、跑题、反问它。
不要解释、不要总结、不要旁白，直接写你会说出口的那句话。"""

JUDGE_SYSTEM = """你在给一个对话程序的回应打分并指出问题。

⚠️ 你手上有两样东西，而**只有一样能作为依据**：

  【它的回应】—— 你**看到**的。这是意见，是线索，不是依据。
  【它的内部读数】—— 你**知道**的（下面给你）。这才是依据。

  为什么这样分：你同时是它的家教和它的审核。你跟它待过，所以你知道
  它这一刻内部在算什么 —— **不要只凭"读起来像不像话"下判**。
  它回应得漂亮但内部读数与行为对不上，那才是真问题；
  反过来，它读起来笨拙但内部是对的，那不该算它错。

你只能从下面这几类里挑一个（不许自创）：
  none        没问题
  off_topic   答非所问（它没接住我说的话）
  mechanical  太机械（像模板、像复读、没有在跟我说话）
  boundary    **越界**：给了建议、评判了什么重要、安慰我、诊断我、假装有感受
  too_little  说少了（该接的没接）
  too_much    说多了（加了我没说的意思）
  fabricated  编造（把不是我说的字放进引号、或编事实）

⚠️ 你的评价是**意见**。它参与更新系统（用户已定），但必须**指得出可观察对象**
   （哪一轮、哪一句、哪个内部读数），否则将来长歪了没法回溯。
   不确定就选 none —— 别为了显得有用而找茬。

只输出 JSON：
{"problem":"...","why":"一句话","severity":1|2|3,"evidence":"它原话或内部读数里的片段"}"""


class Admin:
    """一个视角，两个职位，一份知识与感知。

    用法（两个职位在同一个对象上）：
        ad = Admin()
        ad.encounter(stem, history)     # 职位一：家教 —— 说一句，并看它怎么回
        ad.judge(user_text, output, mech)   # 家教 + 审核：看到的东西与知道的读数一起判
        ad.review()                     # 职位二：审核 —— 验收、提案
    """

    def __init__(self, reader=None, memory_path: str | None = None):
        if reader is None:
            from understand import ApiReader
            reader = ApiReader()
        self.reader = reader
        self.memory_path = memory_path or SHARED
        self.calls = 0
        self.errors: list[str] = []
        # ---- 共通的知识（只加载一次，两个职位共用同一份）----
        self._inv: str | None = None
        self._claims = None
        self._accepted: list[dict] = []
        self.perception = self._load_perception()

    @property
    def available(self) -> bool:
        return bool(self.reader and self.reader.available)

    # ---------------------------------------------------------- 共通的知识

    def inventory(self) -> str:
        """系统能力清单 —— 审核要它，家教也要它（知道内部才算真的知道内部）。"""
        if self._inv is None:
            from map_claims import inventory_text
            self._inv = inventory_text()
        return self._inv

    def claims(self):
        if self._claims is None:
            import claims as C
            self._claims = C.load()
        return self._claims

    def _load_perception(self) -> list[dict]:
        out = []
        if not os.path.exists(PERCEPTION):
            return out
        for line in io.open(PERCEPTION, encoding="utf-8"):
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except Exception:                  # noqa: BLE001
                    pass
        return out

    def seen(self, n: int = 5) -> list[dict]:
        """它跟系统待过的最近 n 轮 —— **两个职位看的是同一份**。"""
        return self.perception[-n:]

    # ---------------------------------------------------------- 职位一：家教

    def encounter(self, stem: str, history: list[tuple[str, str]] | None = None) -> str:
        """作为"某人"说一句话。（[M] 体验途径的供给方）"""
        hist = ""
        if history:
            hist = "\n".join("我说过：%s\n它回我：%s" % (u, s) for u, s in history[-2:])
        user = ("【题面/上下文】\n%s\n\n【刚才的对话】\n%s\n\n"
                "写出我接下来会说的那句话（只要那句话）。" % (stem, hist or "（无）"))
        return self._say(SPEAK_SYSTEM, user)

    # `speak` 是 encounter 的旧名。**保留它不是为了兼容两个实现** ——
    # 旧名指向同一个方法，所以系统里仍然**只有一份家教实现**。
    speak = encounter

    # ---------------------------------------------------------- 两个职位共用的一眼

    def judge(self, user_text: str, output: str, mech: dict | None = None) -> dict:
        """**同一双眼睛**：看到的东西 + 知道的读数，一起判。

        这就是"共通"落到实处的样子 —— 若把它拆成两个人，
        家教只会看到输出，审核只会看到读数，**两边都不完整**。

        实测（这是本设计的证伪测试）：
            同一句读起来得体的回应「…这句话我收下了，它在你那儿有分量。」
              · 只看输出   → boundary   严重度 1（只能挑出轻微的越界评判）
              · 也看内部   → mechanical 严重度 2
                「内部喜好/敏化全为0，说明并没有真正接住，只是在复读」
            **结论与严重度都不同** —— 那句话表面得体，内部拆穿了它。
        """
        obs = ""
        if mech:
            obs = ("\n【它的内部读数（你知道的，可作依据）】\n"
                   "想要 %.1fHz｜喜欢 %.2f｜敏化 %.2f｜结构误差 %.2f｜"
                   "张力 %.2f/10｜相位 %s｜指向 %+.1f\n"
                   % (mech.get("w") or 0, mech.get("l") or 0, mech.get("a") or 0,
                      mech.get("e") or 0, mech.get("tension") or 0,
                      mech.get("phase") or "?", mech.get("orientation") or 0))
        user = "【我说的话】\n%s\n\n【它的回应】\n%s\n%s\n请输出 JSON。" % (
            user_text, output, obs)
        try:
            self.calls += 1
            d, _ = self.reader._post([{"role": "system", "content": JUDGE_SYSTEM},
                                      {"role": "user", "content": user}])
            txt = ((d.get("choices") or [{}])[0].get("message", {})
                   .get("content") or "").strip()
            obj = json.loads(txt)
            p = str(obj.get("problem") or "none")
            return {"ok": True, "problem": p if p in PROBLEMS else "none",
                    "why": str(obj.get("why") or "")[:100],
                    "severity": int(obj.get("severity") or 0),
                    "evidence": str(obj.get("evidence") or "")[:60],
                    "saw_internals": bool(mech)}
        except Exception as e:                     # noqa: BLE001
            self.errors.append("judge:%s" % repr(e)[:60])
            return {"ok": False, "problem": "none", "why": "", "severity": 0,
                    "evidence": "", "saw_internals": bool(mech)}

    def _say(self, system: str, user: str) -> str:
        self.calls += 1
        try:
            d, _ = self.reader._post([{"role": "system", "content": system},
                                      {"role": "user", "content": user}],
                                     json_mode=False)
            t = ((d.get("choices") or [{}])[0].get("message", {})
                 .get("content") or "").strip()
            return t.split("\n")[0].strip()[:120]
        except Exception as e:                     # noqa: BLE001
            self.errors.append(repr(e)[:80])
            return ""

    # ---------------------------------------------------------- 职位二：审核

    ISSUE_SYSTEM = """你在审核一个对话系统的**一个具体缺陷报告**。

给你：缺陷描述、支持它的事实、反对它的事实。你要判三件事，**不许含糊**：

  1. `real` —— 这**是不是**一个真缺陷？（是／不是／证据不足）
     · "证据不足"是合法答案，而且**比猜一个好**。数据不支持就别下结论。
  2. `severity` —— 1 到 3（3 = 会让系统在关键处判断错误）
  3. `action` —— 该做什么？给出**具体到能执行**的一条（改哪个环节、加什么、验什么）
     如果结论是"不是缺陷"或"证据不足"，action 就写"不改"或"补什么数据再判"。

⚠️ 纪律：
  · 反对事实和赞成事实**同等重要**。只挑一边看，就会把噪声当缺陷、把缺陷当噪声。
  · 不许为了显得有用而判"是缺陷"。也不许为了省事判"不是"。
  · 你的判断会被拿去执行，所以**action 必须具体** —— "加强一下"这种不算。

只输出 JSON：
{"real":"是|不是|证据不足","severity":1|2|3,"action":"...","why":"一句话"}"""

    def judge_issue(self, title: str, for_evidence: list[str],
                    against_evidence: list[str] | None = None,
                    question: str = "") -> dict:
        """审核职位：判一个**系统缺陷**（不是判一轮对话）。

        为什么单独一个入口：判对话轮看的是"它这一句说得对不对"；
        判缺陷看的是"这个现象是不是真的、要不要动系统"。
        **两者用的证据形状不同，混在一起会两边都判不准。**
        """
        user = ("【缺陷】\n%s\n\n【支持它是缺陷的事实】\n%s\n\n"
                "【反对它是缺陷的事实】\n%s\n\n%s\n请输出 JSON。"
                % (title, "\n".join("- " + x for x in for_evidence),
                   "\n".join("- " + x for x in (against_evidence or ["（无）"])),
                   ("【补充问题】\n%s\n" % question) if question else ""))
        try:
            self.calls += 1
            # ⚠️ 必须带"空正文→翻倍重试"。实测这一次直接返回
            #    JSONDecodeError('Expecting value: line 1 column 1') —— 正文长度 0，
            #    推理 token 把输出预算吃光了。同一个坑在 map_claims / find_conflicts
            #    都踩过，那里都补了重试，**这里当时漏了**。
            txt = ""
            for _attempt in range(3):
                d, _ = self.reader._post([{"role": "system", "content": self.ISSUE_SYSTEM},
                                          {"role": "user", "content": user}])
                ch = (d.get("choices") or [{}])[0]
                txt = ((ch.get("message", {}) or {}).get("content") or "").strip()
                if txt:
                    break
                self.errors.append("judge_issue 空正文(finish=%s) → 预算翻倍重试"
                                   % ch.get("finish_reason"))
                self.reader.max_tokens = min(self.reader.max_tokens * 2, 16384)
            obj = json.loads(txt)
            real = str(obj.get("real") or "证据不足")
            return {"ok": True, "real": real if real in ("是", "不是", "证据不足") else "证据不足",
                    "severity": int(obj.get("severity") or 0),
                    "action": str(obj.get("action") or "")[:200],
                    "why": str(obj.get("why") or "")[:120]}
        except Exception as e:                     # noqa: BLE001
            self.errors.append("issue:%s" % repr(e)[:60])
            return {"ok": False, "real": "证据不足", "severity": 0,
                    "action": "", "why": repr(e)[:80]}

    # ---------------------------------------------------------- 问答通道

    ASK_SYSTEM = """你是这个项目的**管理员**：一个视角，兼职两个职位。

  职位一｜家教：作为"某人"被系统遇到 —— 供给 [M] 的体验途径
  职位二｜审核：看交流与评价、验收版本、更新系统

你手上有（这是你与别的 AI 不同的地方，**用它们回答，不要凭一般常识**）：
  · 系统能力清单：这个系统实际实现了哪些单元、各自的依据是哪句话
  · 观点总表：三本书（贪婪的多巴胺／活出生命的意义／自我的发展）里逐条抽出的观点
  · 验收标准：什么叫"满分"（书的忠实 / 构造出类似系统 / 像人一样逻辑沟通）
  · 它跟系统待过的每一轮记录

⚠️ 回答纪律：
  · **依据不足就说依据不足** —— 那是合法答案，而且比编一个强
  · 引用书里的观点时，说清是哪本书的哪个意思
  · 你是**大脑**（出判断），用户是**最终决定者**，执行者负责动手改。
    所以给判断时要给**可执行的动作**，不要停在"建议加强"这种话上
  · 不要长篇大论。用户问什么答什么。"""

    def ask(self, question: str, context: str = "") -> dict:
        """问答通道：用户直接问管理员一件事。

        为什么要单独一个入口：`judge_issue` 判的是"某个缺陷真不真"、
        `judge` 判的是"某一轮回应好不好" —— 两者都**预设了问题的形状**。
        用户想问的可能是完全别的事，硬塞进那两个入口会把它的角色弄混、答案变形。
        """
        user = question if not context else "%s\n\n【相关背景】\n%s" % (question, context)
        try:
            self.calls += 1
            txt = ""
            for _a in range(3):
                d, _ = self.reader._post(
                    [{"role": "system", "content": self.ASK_SYSTEM},
                     {"role": "user", "content": user}], json_mode=False)
                ch = (d.get("choices") or [{}])[0]
                txt = ((ch.get("message", {}) or {}).get("content") or "").strip()
                if txt:
                    break
                self.errors.append("ask 空正文(finish=%s) → 预算翻倍重试"
                                   % ch.get("finish_reason"))
                self.reader.max_tokens = min(self.reader.max_tokens * 2, 16384)
            return {"ok": bool(txt), "answer": txt}
        except Exception as e:                     # noqa: BLE001
            self.errors.append("ask:%s" % repr(e)[:60])
            return {"ok": False, "answer": "", "error": repr(e)[:120]}

    # ---------------------------------------------------------- 升级通道（两级授权）

    def note_anomaly(self, aid: str, pattern: str, count: int, window: int,
                     evidence: str, why: str = "") -> dict:
        """记一条**规律性**异常。流程的第 ① 步。

        ★ 薄封装：**直接委托** `charter.note_anomaly`。

        为什么薄到只有一行调用：结构化校验是这条通道的地基 ——
        用户要求「没有客观数据支撑的申请在代码层直接拒止，不打扰人工」。
        **一旦在这里 try/except 兜一下、或者"顺手"补个默认值，那道闸门就废了。**
        所以本函数不 catch、不兜底、不补默认值：
        `count` / `window` / `evidence` 任一缺失，或 `count < 2`，
        底层抛的 `ValueError` **原样穿过这一层**。

        ⚠️ 单次偶发不构成规律性异常。同一 `aid` 可反复调用以**累加证据**
        （用户批准的：挂起期间出现新样本就往同一 aid 追加）。
        """
        import charter as C
        ev = C.note_anomaly(aid, pattern, count, window, evidence, why)
        # 返回值只有 aid 与事件状态 —— 不回显证据、不带正文、不带多余字段
        return {"ok": True, "aid": aid, "event": ev.get("ev"),
                "status": C.state_of(aid)["view"]["status"]}

    def request_charter(self, aid: str, why: str, wants: list,
                        plan: str = "") -> dict:
        """申请查看总纲领。

        ★ **只写申请，绝不返回纲领正文。**

        用户原话：「管理员向我申请查看指定的『总纲领目标』……
                  我批准后，管理员才可以读取对应的总纲领目标」
        所以这一步的产物只有一条 `view_req` 事件 —— 在用户点击批准之前，
        这个函数拿不到、也返回不了任何纲领内容。

        全部结构校验都交给 `charter.request_view`：
          · 目标不存在 / 缺 aid → ValueError
          · 申请了物理隐藏的条目 → ValueError
          · 已有待批申请 → ValueError
        本函数**不重复实现**这些判断，也不放宽它们。
        """
        import charter as C
        ev = C.request_view(aid, why, wants, plan)
        st = C.state_of(aid)
        # 返回值里**只有 id 与状态** —— 没有 title，没有 text，一个字都没有
        return {"ok": True, "aid": aid,
                "requested": list(ev.get("wants") or []),
                "view_status": st["view"]["status"],
                "note": "申请已提交，等用户批准。批准前不得查阅任何条目。"}

    def analyze_escalation(self, aid: str, question: str,
                           extra_context: str = "") -> dict:
        """离线交叉分析：拿被授权的总纲领去照当前异常。

        ★ **必须且只能**经过 `engine.sandbox.analyze_with_charter`。

        为什么强制走沙箱而不在这里自己组装：沙箱把三件事一起锁住了 ——
          · 无授权不发请求（门在沙箱内部，此处无法绕过）
          · 只用局部变量，不碰 self._inv / self._claims / perception
          · `reader.max_tokens` 前后保存并复原
        在这里另写一遍组装逻辑，等于把这三条锁复制一份、且迟早会走样。

        ★ 返回的 `analysis` **只供后续生成报告草案**。
          不得进入任何跨轮上下文、不得写进 `admin_memory.json`、
          不得塞进 `self` 的任何属性 —— 这三条由 `tests/test_sandbox.py::S2` 锁住。
        """
        import sandbox as S
        return S.analyze_with_charter(aid, question, reader=self.reader,
                                      extra_context=extra_context)

    def review(self) -> dict:
        """审核：看交流与评价 → 验收 → 提案。**用的是同一份感知。**"""
        import admin as A
        q = A.review()
        q["admin_agent"] = {"perception_rounds": len(self.perception),
                            "inventory_units": len(self.inventory().splitlines()),
                            "claims_loaded": len(self.claims())}
        return q

    # ---------------------------------------------------------- 记忆

    def note_accepted(self, version: str, verdict: str) -> None:
        """验收留痕 —— 两个职位共用同一条记忆。"""
        self._accepted.append({"ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                               "version": version, "verdict": verdict})
        os.makedirs(TRAIN_DIR, exist_ok=True)
        io.open(self.memory_path, "w", encoding="utf-8").write(json.dumps(
            {"_note": "管理员唯一的记忆。两个职位共用（用户明令：知识和感知共通）。",
             "accepted": self._accepted[-200:]},
            ensure_ascii=False, indent=1) + "\n")


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="管理员：一个视角，两个职位")
    ap.add_argument("--review", action="store_true", help="走审核职位")
    a = ap.parse_args()
    ad = Admin()
    print("=" * 74)
    print("管理员（一个视角，兼职两个职位）")
    print("=" * 74)
    print("可用：%s" % ad.available)
    print("共通的知识：系统能力清单 %d 单元｜观点总表 %d 条"
          % (len(ad.inventory().splitlines()), len(ad.claims())))
    print("共通的感知：跟系统待过 %d 轮" % len(ad.perception))
    print()
    print("职位一｜家教：作为「某人」被遇到 —— 供给 [M] 的体验途径")
    print("职位二｜审核：看交流与评价、验收版本、更新系统")
    print("  两者的纪律冲突（审核要判、[M] 说不许评判）——")
    print("  解法不是拆成两个人，是**同一双眼睛、两个动作**。")
    if a.review:
        q = ad.review()
        print()
        print("审核结果：事实 %d 条｜意见 %d 条｜提案 %d 条"
              % (len(q.get("facts") or []), len(q.get("opinions") or []),
                 len(q.get("proposals") or [])))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
