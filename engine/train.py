# -*- coding: utf-8 -*-
"""受控输入的经历训练器。
项目固定语料和题面的作者身份未经独立验证；模型生成输入不能冒充真人。
训练台账和性格写 state/train，门控发展与机制 carry 依现行管线共享根状态。
训练师评价是模型意见，不构成独立的人类评审或心理阶段证明。
"""
from __future__ import annotations

import io
import json
import os
import random
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

# ★ 评价记录的**版本号**。管理员判定的严重度 3 缺陷就是它引起的：
#
#   我把「管理员可见率」算在整份 eval.jsonl 上，得到 93.9%，然后向管理员报告
#   "修复不完全"。**实际上那 9 条不可见记录全在修复前的旧数据里** ——
#   修复后那 120 轮是 100%。数据是好的，是我的统计集合错了。
#   而管理员基于我那个错数字，做了一次"暂不验收"的判断。
#
#   所以：**任何会改变行为的改动，都要把 +1 提上去**，评价脚本必须按它过滤。
#   跨版本混算出来的率，没有一个是可以相信的。
EVAL_SCHEMA = 11


# ------------------------------------------------------------------ 输入来源

def load_corpus() -> list[dict]:
    """项目固定诊断语料，作者身份未经独立验证。"""
    sys.path.insert(0, os.path.join(_ROOT, "tests"))
    try:
        import corpus_probe                       # type: ignore
    except Exception:                             # noqa: BLE001
        return []
    out = []
    for text, expect, gap, note in getattr(corpus_probe, "CASES", []):
        out.append({"text": text, "expect": sorted(expect or []),
                    "gap": gap, "note": note, "source": "hand_corpus"})
    return out


def load_topics() -> list[dict]:
    """项目题面库，保留题面编号；编号不证明语义上的跨情境。"""
    p = os.path.join(_ROOT, "corpus", "topics.json")
    if not os.path.exists(p):
        return []
    with io.open(p, encoding="utf-8") as handle:
        d = json.load(handle)
    out = []
    for t in d.get("topics", []):
        stem = (t.get("stem") or "").strip()
        if stem:
            out.append({"text": stem, "expect": [], "gap": "题面",
                        "note": t.get("dilemma") or "", "source": "topic_stem",
                        "topic_id": t.get("id")})
    return out


def load_sequences(path: str | None = None) -> list[dict]:
    """可核对序列池（2026-10-28，用户裁定「按甲来」）。

    `path` 只为测试可注入 —— 不传时读 `corpus/sequences.json`。

    为什么需要它：训练池 36 条全是开放式半句，6 轮训练**没有一轮**产出可核对目标
    （decision 全 NOT_OFFERED），于是动作不可确认、经验层学不到东西。

    为什么必须是序列、不能是"自足输入"（实测两条，都已验证）：
      ① `relational_memory.project()` 故意把当前输入排除在可引用来源之外
         （`sources` 过滤掉 `current:` 前缀）⇒ 当前输入里的断言**不能被引用**；
      ② 同一输入里既断言又查询，断言句会被判 unsafe ⇒ 降级 UNKNOWN
         （那道语义护栏是故意的，不动）。
      ⇒ 断言必须先在**历史行**里，后来的轮次才引用得到。

    ⚠️ 本文件里的条目**不是**开放式题面，是"用户陈述事实 + 后来查询"的序列。
       它们不改判据、不改机制，只是让训练输入里**存在**可核对的关系。
    """
    p = path or os.path.join(_ROOT, "corpus", "sequences.json")
    if not os.path.exists(p):
        return []
    with io.open(p, encoding="utf-8") as handle:
        d = json.load(handle)
    out = []
    for seq in d.get("sequences", []):
        turns = []
        for t in seq.get("turns") or []:
            text = (t.get("text") or "").strip() if isinstance(t, dict) else ""
            if text:
                turns.append({"text": text, "expect": [], "gap": "序列",
                              "note": seq.get("kind") or "", "source": "sequence",
                              "topic_id": seq.get("id")})
        if len(turns) >= 2:
            out.append({"id": seq.get("id"), "turns": turns})
    return out


SYNTH_SYSTEM = """你在扮演一个正在做自我探索问卷的普通人。
下面给你一个半句题面，你用**第一人称**把它接着写完 —— 一到两句，
要像真人在说话：可以有犹豫、有口语、有具体的细节，也可以答得含糊。
不要解释，不要总结，直接写你说的话。"""


def synth_inputs(reader, stems: list[str], n: int) -> list[dict]:
    """模型扮演用户 —— 生成更多样的说法。

    ⚠️ 自证循环警告：这些输入是模型生成的，之后又由同一个模型（当大脑）回应。
       所以它们带 source=synth，管理员审核时应降权。不许拿它当唯一依据。
    """
    out = []
    for stem in stems[:n]:
        item = stem if isinstance(stem, dict) else {"text": stem}
        s = item["text"]
        try:
            d, _ = reader._post([{"role": "system", "content": SYNTH_SYSTEM},
                                 {"role": "user", "content": s}], json_mode=False)
            txt = ((d.get("choices") or [{}])[0].get("message", {})
                   .get("content") or "").strip()
            if txt and len(txt) < 200:
                out.append({"text": txt, "expect": [], "gap": "合成",
                            "note": "模型扮演用户（自证循环，须降权）",
                            "source": "synth", "topic_id": item.get("topic_id")})
        except Exception:                          # noqa: BLE001
            continue
    return out


# ------------------------------------------------------------------ 训练师（AI）

TUTOR_SPEAK_SYSTEM = """你在扮演一个正在做自我探索的普通人，跟一个对话程序聊天。
给你一个半句题面或上一轮的对话，你**用第一人称**接着写 —— 一到两句。
要像真人在说话：可以有犹豫、口语、具体细节，也可以答得含糊、跑题、反问它。
不要解释、不要总结、不要旁白，直接写你会说出口的那句话。"""

TUTOR_JUDGE_SYSTEM = """你在给一个对话程序的回应打分并指出问题。你是**外部评价者**。

你只能从下面这几类里挑一个（不许自创）：
  none        没问题
  off_topic   答非所问（它没接住我说的话）
  mechanical  太机械（像模板、像复读、没有在跟我说话）
  boundary    **越界**：它给了建议、评判了什么重要、安慰我、诊断我、或假装有感受
  too_little  说少了（该接的没接）
  too_much    说多了（加了我没说的意思）
  fabricated  编造（把不是我说的字放进引号、或编事实）

⚠️ 你的评价是**意见，不是依据**。它只用来指出"该去看哪里"，
   不会被直接拿去改系统。所以：
   · 必须有具体证据（引用它原话里的片段）
   · 不确定就选 none —— 别为了显得有用而找茬
   · 不要因为"风格不合你口味"就判 mechanical

只输出 JSON，不要别的字：
{"problem":"...","why":"一句话","severity":1|2|3,"evidence":"它原话里的片段"}"""


class _ObservedReader:
    """Record response metadata without changing the frozen Admin methods."""
    def __init__(self, reader):
        self.reader = reader
        self.last_response = {}

    def __getattr__(self, name):
        return getattr(self.reader, name)

    def _post(self, *args, **kwargs):
        self.last_response = {}
        self.response_attempts = []
        structured = kwargs.get("json_mode", True)
        if structured and args:
            # Keep the shared Admin methods intact; qualify their legacy labels.
            messages = [dict(message) for message in args[0]]
            policy = ("\n【读数的证据边界】上述Hz等标签是历史格式，数字都是工程代理，"
                      "不是生理测量或主观体验。e是通道压力代理，不是语义正确性或发展证据。"
                      "不能仅凭零读数判定没理解，不能凭低压力判升级。"
                      "判断错误必须指向原话、实际回应或可追溯的操作。")
            if messages and messages[0].get("role") == "system":
                messages[0]["content"] += policy
            args = (messages,) + args[1:]
        original_budget = self.reader.max_tokens if hasattr(self.reader, "max_tokens") else None
        try:
            for attempt in range(2):
                diagnostic = {"attempt": attempt + 1}
                try:
                    response, elapsed = self.reader._post(*args, **kwargs)
                    diagnostic["transport_attempts"] = list(getattr(self.reader, "last_transport_attempts", []))
                    choice = (response.get("choices") or [{}])[0]
                    content = (choice.get("message") or {}).get("content") or ""
                    diagnostic.update(finish_reason=choice.get("finish_reason"),
                                      content_chars=len(content.strip()), usage=response.get("usage") or {})
                    if structured:
                        obj = json.loads(content)
                        from admin_agent import PROBLEMS
                        if (not isinstance(obj, dict) or obj.get("problem") not in PROBLEMS
                                or not isinstance(obj.get("why"), str)
                                or not isinstance(obj.get("evidence"), str)
                                or type(obj.get("severity")) is not int
                                or obj["severity"] not in range(4)):
                            raise ValueError("Invalid evaluation schema")
                    diagnostic["ok"] = True
                    self.response_attempts.append(diagnostic)
                    self.last_response = diagnostic.copy()
                    return response, elapsed
                except Exception as exc:
                    diagnostic["transport_attempts"] = list(getattr(self.reader, "last_transport_attempts", []))
                    diagnostic.update(ok=False, error_type=type(exc).__name__)
                    self.response_attempts.append(diagnostic)
                    self.last_response = diagnostic.copy()
                    if attempt == 1 or not structured:
                        raise
                    if original_budget is not None and (diagnostic.get("finish_reason") == "length"
                                                        or diagnostic.get("content_chars") == 0):
                        self.reader.max_tokens = max(original_budget, min(original_budget * 2, 8192))
        finally:
            if original_budget is not None:
                self.reader.max_tokens = original_budget


class Tutor:
    """训练师（家教）—— **不再是另一个实现，只是管理员的一个职位。**

    用户明令：
        「管理员兼职家教的位置，这两个职位不是分开的。」
        「不是一个职位两个视角啊，是一个视角兼职两个职位。」
        「你不要把这两个界限划这么明显，管理员的知识和感知是共通的。」

    ⚠️ 这里原来有 59 行**独立实现**（自己的说话提示词、自己的判分体系）。
       那是错的：两个实现 = 两份知识、两份感知，而用户要的是**一份**。
       现在整个类委托给 `engine/admin_agent.py::Admin`，同一双眼睛。
    """

    def __init__(self, reader=None, seed_context: str = ""):
        from admin_agent import Admin
        if reader is None:
            from understand import ApiReader
            reader = ApiReader()
        self._ad = Admin(reader=_ObservedReader(reader))
        self.ctx = seed_context

    @property
    def available(self) -> bool:
        return self._ad.available

    @property
    def calls(self) -> int:
        return self._ad.calls

    @property
    def errors(self) -> list:
        return self._ad.errors

    def speak(self, prompt: str, last=None) -> str:
        """家教职位：作为"某人"说一句。"""
        result = self._ad.encounter("%s\n\n%s" % (self.ctx, prompt), last)
        self.last_generation_diagnostic = dict(self._ad.reader.last_response)
        return result

    def judge(self, user_text: str, sys_output: str, mech: dict | None = None) -> dict:
        """家教 + 审核同一双眼睛：看到的东西 + 知道的读数一起判。

        `mech` 是本轮机制读数。**训练循环应当把它传进来** ——
        不传的话这次判断就退化成"只看输出"，而那正是共通要避免的。
        """
        result = self._ad.judge(user_text, sys_output, mech)
        result["api_diagnostic"] = self._ad.reader.last_response.copy()
        result["api_attempts"] = list(getattr(self._ad.reader, "response_attempts", []))
        result["signal_policy"] = "engineering_proxies_not_semantic_or_development_measurements"
        if not result.get("ok"):
            result["error"] = self._ad.errors[-1] if self._ad.errors else "unknown"
        return result

class TrainingControl:
    """训练的外部控制：**暂停／继续／停止**，以及每轮回调。

    为什么需要它：用户要一个能实时看见进程、并能**暂停/继续**的界面
    （原话：「首先是现在我们正在做的进程，实施逐轮」＋「能：暂停/继续训练」）。
    训练循环必须能被打断，否则界面只能干看着。

    用 `threading.Event` 而不是标志位轮询 —— 暂停时线程真的阻塞，不空转。
    """

    def __init__(self):
        import threading
        self._go = threading.Event()
        self._go.set()                     # 默认不暂停
        self.stopped = False
        self.on_turn = None                # callable(record: dict) —— 每轮结束后调用
        self.errors = []

    def pause(self) -> None:
        self._go.clear()

    def resume(self) -> None:
        self._go.set()

    @property
    def paused(self) -> bool:
        return not self._go.is_set()

    def stop(self) -> None:
        self.stopped = True
        self._go.set()                     # 停止时也要放行，否则卡在暂停里退不出去

    def wait(self) -> None:
        """在每个回合开始前调用。暂停时在这里阻塞。"""
        self._go.wait()

    def emit(self, rec: dict) -> None:
        if self.on_turn:
            try:
                self.on_turn(rec)
            except Exception as e:             # noqa: BLE001
                # 界面出错不许拖垮训练 —— 但也不许静默。
                self.errors.append(repr(e)[:80])


class Trainer:
    def __init__(self, out_dir: str | None = None, use_api: bool = True,
                 use_think: bool = True, use_render: bool = False,
                 use_sequences: bool = False,
                 use_cognition: bool | None = None,
                 on_log=None, gate_perception: bool | None = None):
        self.dir = out_dir or TRAIN_DIR
        # ★ 2026-10-28：可核对序列默认**不加载**（见 run() 里的注释）。
        #   它是回归测试的料，不是对话训练主池。
        self.use_sequences = use_sequences
        # ★ 2026-10-29（Gemini 第 ① 步批准）：**线上默认开启，离线默认关闭。**
        #
        #   规则：`use_cognition is None` ⇒ 跟 `use_api` 走
        #     · `use_api=True`（真实训练/对话）⇒ 开启「意识海 + 去助手化」
        #     · `use_api=False`（`--offline` 与全部离线单测）⇒ 关闭
        #   显式传 True / False 时以参数为准（回退通道永久保留）。
        #
        #   ⚠️ 为什么默认必须跟 `use_api` 绑死：
        #      认知层每轮多 2 次抽取调用，`--offline` 下根本调不通；
        #      而 66 个离线单测全部传 `use_api=False` ⇒ 一条都不会误触。
        #   ⚠️ 为什么不直接默认 True：那会让 `--offline` 也去调 API，
        #      是"静默失败"的另一种形态（看起来在跑，其实每轮都在降级）。
        self.use_cognition = bool(use_api) if use_cognition is None else bool(use_cognition)
        os.makedirs(self.dir, exist_ok=True)
        self.ledger = os.path.join(self.dir, "ledger.jsonl")
        self.character = os.path.join(self.dir, "character.json")
        self.progress_file = os.path.join(self.dir, "progress.json")
        self.use_api = use_api
        self.use_think = use_think
        self.use_render = use_render
        # ★ 箭头 A1 的通电开关。**None = 交给 _gate_on 读环境变量**
        #   （用户在 T33 定的：界面不加开关，通电靠 EGO_GATE_PERCEPTION）。
        #   显式传 True/False 时以参数为准 —— 回退通道永久保留。
        self.gate_perception = gate_perception
        # ★ 消息出口。**窗口版 exe 里 print() 会被静默丢弃**，
        #   所以每条消息都要另给界面一份，否则用户看不见"退化成固定语料"这种事。
        self.on_log = on_log
        self.log: list[str] = []
        # ★ 训练师的评价写**另一个文件**，不进台账。
        #   理由：台账是**系统自己的记忆**（它的过去）；训练师的评价是**外部意见**。
        #   把意见混进记忆，等于让它把别人的评判当成自己的经历 —— 那是另一回事。
        self.eval_file = os.path.join(self.dir, "eval.jsonl")

    # ---- 内部
    def _pipe(self):
        # ⚠️ **不在这里抄一份 _gate_on** —— 它在 pipeline.py 里唯一定义，
        #    这里只导入。单一事实来源（T17 立的规矩）。
        from pipeline import Pipeline, _gate_on
        return Pipeline(ledger_path=self.ledger, auto_audit=False,
                        character_path=self.character,
                        use_api=self.use_api, use_think=self.use_think,
                        use_render=self.use_render,
                        # ★ 2026-10-29（Gemini 正式批准这把钥匙）：
                        #   `use_cognition` **默认仍是 False** ——
                        #   现有单元测试与六道门禁完全不受影响。
                        #   只有显式 `--cognition` 才启动：
                        #   当轮算子 + 空档回想 + 2 环连锁 + 第一人称授权。
                        #
                        #   ⚠️ 为什么默认关：每轮多 2 次抽取调用，且它改变"她该想什么"。
                        #     按项目规矩：默认关、可显式开、留痕。
                        use_cognition=self.use_cognition,
                        gate_perception=_gate_on(self.gate_perception))

    def _say(self, s: str) -> None:
        self.log.append(s)
        print(s, flush=True)
        # ★ 也给界面一份。
        #   打包成**窗口版 exe** 后 `sys.stdout` 是 None，`print()` **静默丢弃** ——
        #   于是「⚠️ 训练师要 API，当前不可用 → 退回固定输入驱动」这类话
        #   用户永远看不见。那是最难查的一种失败：**看起来在跑，其实变了样**。
        if self.on_log:
            try:
                self.on_log(s)
            except Exception:                      # noqa: BLE001
                pass

    # ---- 主流程
    def run(self, rounds: int = 1, session_len: int = 6, source: str = "corpus",
            synth_n: int = 0, seed: int | None = None, tutor: bool = False,
            control: "TrainingControl | None" = None, strict: bool = False, max_turns: int | None = None) -> dict:
        """跑 rounds 轮训练。每轮 = 若干个 session，每个 session 若干轮对话。

        两种驱动方式：
          · tutor=False —— **固定输入**：从项目语料/题面里抽话。来源声明不代替独立验证。
          · tutor=True  —— **训练师驱动**：AI 扮演人，接着上一句往下说，
            并在每轮后给出评价。更接近真实对话，但**评价是意见**（见 Tutor）。
        """
        from input_provenance import training_origin
        from pipeline import _gate_on
        from admin_evidence import source_fingerprint
        run_source = source_fingerprint(_ROOT)
        rnd = random.Random(seed)
        self.strict = strict
        self.run_id = str(time.time_ns()) + "_" + str(os.getpid())
        target = rounds * session_len * 3
        if max_turns is not None:
            if not isinstance(max_turns, int) or isinstance(max_turns, bool) or max_turns < 1:
                raise ValueError("max_turns must be a positive integer")
            target = min(target, max_turns)
        failure = None
        failure_diagnostic = None
        # 训练师（可选）。它的评价与是否可用都要在结果里说清，不许静默降级。
        tt = None
        if tutor:
            from understand import ApiReader
            rd = ApiReader()
            if rd.available:
                tt = Tutor(rd)
            else:
                self._say("  ⚠️ 训练师要 API，当前不可用 → 退回固定输入驱动")
                if strict:
                    return {"ok": False, "reason": "tutor_api_unavailable", "turns_added": 0}
        pool: list[dict] = []
        if source in ("corpus", "all"):
            pool += load_corpus()
        sequences: list[dict] = []
        if source in ("topics", "all"):
            pool += load_topics()
        # ★ 可核对序列（2026-10-28 加；2026-10-28 晚改为**显式开关**）
        #
        #   它原来的用途：每场先放一条"断言 → 更正 → 查询"的完整序列，
        #   保证训练里能产出"逐字引用核对通过"这种**可本地确认**的动作。
        #
        #   ⚠️ 但它有两个后果，实测都发生了：
        #     ① `session_len == 3` 时 `picks` 一上来就被序列填满
        #        （`while len(picks) < session_len` 一次都不执行）
        #        ⇒ 100% 抽到 S01–S05（押金/楼层），**训练池被彻底污染**；
        #     ② 那 5 条序列全是"某物在某地/某人" ⇒ 会把系统往
        #        「查押金、背资料放几楼」的记账员方向训。
        #
        #   ⇒ 默认**不加载**，只在显式 `--sequences` 时加载。
        #     它的真正归宿是**回归测试**（`tests/test_sequence_pool.py`），
        #     不是对话训练主池。
        if getattr(self, "use_sequences", False) and source in ("topics", "all"):
            sequences = load_sequences()
            if sequences:
                self._say("  可核对序列：%d 条（--sequences 显式开启）" % len(sequences))
        if synth_n:
            from understand import ApiReader
            rd = ApiReader()
            if rd.available:
                stems = load_topics()
                self._say("  合成输入：模型扮演用户 %d 条（自证循环，已标记降权）" % synth_n)
                pool += synth_inputs(rd, stems, synth_n)
        if not pool:
            self._say("  没有训练输入 —— 中止")
            return {"ok": False, "reason": "no_inputs"}

        done = self._load_progress()
        start = done.get("turns", 0)
        self._say("=" * 72)
        self._say("训练开始｜输入池 %d 条｜已有 %d 轮｜目标 %d 轮"
                  % (len(pool), start, target))
        self._say("=" * 72)

        t0 = time.time()
        sessions_run = 0
        sessions_started = 0
        sessions_with_turns = 0
        rounds_run = 0
        turns_run = 0
        evals = 0
        for r in range(rounds):
            complete_in_round = 0
            for s in range(3):                      # 每轮 3 个 session
                if failure or (control and control.stopped) or turns_run >= target:
                    break
                # ★ 序列优先（2026-10-28）：先放一条完整序列，再用随机题面填满。
                #   ⚠️ 只在 `session_len` 够长时用 —— 必须保住「每场恰好 session_len 轮」
                #      这个不变量：`sessions_added` / `rounds_added` 与
                #      `target = rounds*3*session_len` 都依赖它。
                #      第一版没加这道判断，3 轮序列把 2 轮的一场撑成 3 轮，
                #      于是 rounds/sessions 计数全错（test_training_interruptions 抓到）。
                #   ⚠️ 也不许截断序列 —— 截掉最后一轮就等于截掉查询，整条序列白跑。
                usable = [s for s in sequences if len(s["turns"]) <= session_len] if sequences else []
                picks: list[dict] = list(rnd.choice(usable)["turns"]) if usable else []
                # ★★ 2026-10-29 修一个隐藏 Bug（Gemini 查出来的，我确认）：
                #
                #   原来这里是 `while len(picks) < session_len: picks.append(rnd.choice(pool))`
                #   ⇒ **同一场会话的每一轮都从题库随机抽了一道完全不同的新题**，
                #     然后作为【题面/上下文】传给家教（`tt.speak(seed_txt, hist)`）。
                #   ⇒ 家教每轮看到顶上的题面换了，当然每轮都被迫切话题。
                #   ⇒ 这就是「这批语料第 3 轮就换题」的真正原因 ——
                #     不是我分析的"语料本身如此"，而是**训练器每轮在换题**。
                #
                #   ⇒ 修法（家教模式）：一场会话**共用一个种子题面**，
                #     让她能在同一个处境里连聊 6 轮（那才是"意识海"需要的深水区）。
                #   ⚠️ 只在 `self.tutor` 存在时这么做：
                #     非家教模式下 `picks` 里的每一条**本身就是用户输入**，
                #     复制同一个 item 会变成让她连续回答同一句话，那是另一种坏。
                # ★★ 2026-10-29 修一个隐藏 Bug（Gemini 查出来的，我确认）：
                #   原来同一场会话的每一轮都从题库随机抽了**不同的**新题面传给家教，
                #   ⇒ 家教每轮看到题面变了，当然每轮都被迫切话题。
                #   ⇒ 这就是「这批语料第 3 轮就换题」的真正原因。
                #   ⇒ 修法：家教模式下，一场会话**共用一个种子题面**。
                #   ⚠️ 只在 `tt`（训练师可用）时这么做：
                #     非家教模式下 `picks` 的每一条**本身就是用户输入**，
                #     复制同一个 item 会变成让她连续回答同一句话，那是另一种坏。
                if tt is not None and not usable and pool:
                    _seed = rnd.choice(pool)
                    picks = [_seed] * session_len
                else:
                    while len(picks) < session_len:
                        picks.append(rnd.choice(pool))
                sessions_started += 1
                session_start = turns_run
                p = self._pipe()
                if strict and (not p.api_enabled or (self.use_think and p.thinker is None)):
                    failure = "pipeline_api_unavailable"
                    break
                hist: list[tuple[str, str]] = []
                for item in picks:
                    if turns_run >= target:
                        break
                    # ★ 暂停/停止闸门。放在**每一轮开始前**，所以暂停是干净的：
                    #   已跑完的那一轮完整落盘，不会断在半路。
                    if control is not None:
                        control.wait()
                        if control.stopped:
                            self._say("  ⏹ 收到停止指令，在完整的一轮之后停住")
                            break
                    text = item["text"]
                    generated = False
                    # 训练师驱动：由它决定这一句说什么（接上一轮往下）
                    if tt is not None:
                        seed_txt = item["text"]
                        said = tt.speak(seed_txt, hist)
                        if said:
                            text = said
                            generated = True
                        elif strict:
                            failure = "tutor_generation_failed"
                            failure_diagnostic = dict(getattr(tt, "last_generation_diagnostic", {}) or {})
                            failure_diagnostic["stage"] = "tutor_generation"
                            break
                    origin = training_origin(item, text, generated=generated,
                                             model=getattr(getattr(getattr(tt, "_ad", None), "reader", None), "model", None),
                                             fallback=bool(tt and not generated))
                    origin["run_id"] = self.run_id
                    origin["session_id"] = sessions_started - 1
                    try:
                        res = p.turn(text, item.get("topic_id"), input_origin=origin)
                    except Exception as e:          # noqa: BLE001
                        import traceback
                        failure_diagnostic = {"error_type": type(e).__name__,
                            "frames": [{"file": os.path.basename(frame.filename), "line": frame.lineno,
                                        "function": frame.name} for frame in traceback.extract_tb(e.__traceback__)]}
                        if isinstance(e, PermissionError):
                            failure_diagnostic.update(file=getattr(e, "filename", None),
                                                      winerror=getattr(e, "winerror", None))
                        # ★ 2026-10-29（Gemini 要求）：把**异常详情**打出来。
                        #
                        #   为什么：`test_pending_nonblocking` 的 N3 断言"台账新增 == 90"，
                        #   偶尔跑出 89 就是因为这里 `continue` 吞掉了一轮。
                        #   只打 `type(e).__name__` 的话永远只能猜是哪个文件锁；
                        #   打出 `repr(e)` + 最后几个 frame，就能一眼看到是
                        #   `character.json` 并发写、还是 `carry` 的 `os.replace` 冲突。
                        #   ⚠️ 这不是给用户看的，是给**查这个 bug 的人**看的 —— 所以不美化。
                        _fr = (failure_diagnostic or {}).get("frames") or []
                        _tail = " ← ".join(
                            "%s:%s:%s" % (f.get("file"), f.get("line"), f.get("function"))
                            for f in _fr[-3:])
                        self._say("  ✗ 一轮失败：%s: %s"
                                  % (type(e).__name__, repr(e)[:200]))
                        if _tail:
                            self._say("      位置：%s" % _tail)
                        if isinstance(e, PermissionError):
                            self._say("      ★ 文件锁：filename=%r winerror=%r"
                                      % (getattr(e, "filename", None),
                                         getattr(e, "winerror", None)))
                        if strict:
                            failure = "turn_failed:" + type(e).__name__
                            break
                        continue
                    turns_run += 1
                    mark = "·" if res.output and "不作回应" not in res.output else "∅"
                    if res.character_note:
                        mark = "★"
                    # 训练师评价（意见层，写另一个文件）
                    ev = None
                    if tt is not None:
                        # ★ 把**内部读数**一起交给管理员。
                        #
                        #   用户明令：「管理员的知识和感知是共通的」。
                        #   感知共通落到实处就是这一行：家教看到的（输出）
                        #   与审核知道的（机制快照）**一起**进同一个判断。
                        #
                        #   ⚠️ 第一版这里写的是 `tt.judge(text, res.output)` ——
                        #      没传 mech。那等于把管理员砍成两半，让它退化成"只看输出"。
                        #      实测差别（同一句读起来得体的回应）：
                        #        只看输出 → boundary   严重度 1
                        #        也看内部 → mechanical 严重度 2（"内部喜好/敏化全为0，只是在复读"）
                        ev = tt.judge(text, res.output or "", res.mech)
                        evals += 1
                        if ev.get("problem") and ev["problem"] != "none":
                            mark = {"boundary": "‼", "fabricated": "‼"}.get(ev["problem"], "?")
                        self._record_eval(dict(item, input_origin=origin), text, res, ev)
                    hist.append((text, res.output or ""))
                    self._say("  %s [%s] %s → %s%s"
                              % (mark, res.behavior, text[:22],
                                 (res.output or "").replace("\n", " ")[:40],
                                 ("  ｜训练师：" + ev["problem"] + " " + ev["why"][:24])
                                 if ev and ev.get("problem", "none") != "none" else ""))
                    # ★ 把这一轮交给界面（用户要"实时逐轮"）。
                    #   一次给全：谁说的、它怎么回、管理员怎么判、以及**内部读数**
                    #   —— 界面要能把"看到的"和"知道的"并排摆出来。
                    if control is not None:
                        _m = res.mech or {}
                        control.emit({
                            "n": turns_run, "round": r + 1,
                            "said": text, "output": res.output or "",
                            "input_origin": origin, "topic_id": item.get("topic_id"),
                            "api_ok": res.api_ok, "notes": res.notes,
                            "behavior": res.behavior, "markers": res.markers or [],
                            "tutor": ev or {},
                            "mech": {"w": _m.get("w"), "l": _m.get("l"),
                                     "a": _m.get("a"), "e": _m.get("e"),
                                     "tension": _m.get("tension"),
                                     "orientation": _m.get("orientation"),
                                     "phase": _m.get("phase"),
                                     "dev": _m.get("dev")},
                            "char_note": getattr(res, "character_note", None),
                            "ts": time.strftime("%H:%M:%S"),
                        })
                    if strict and (not res.api_ok or (ev is not None and not ev.get("ok"))
                                   or any("关系学习降级" in n or "大脑作答退回" in n or
                                          "反馈记录降级" in n for n in res.notes)):
                        failure = "api_or_pipeline_degraded"
                        break
                session_turns = turns_run - session_start
                sessions_with_turns += int(session_turns > 0)
                if session_turns == session_len:
                    sessions_run += 1
                    complete_in_round += 1
            if complete_in_round == 3:
                rounds_run += 1
            label = "完成" if complete_in_round == 3 else "中断或部分完成"
            self._say("  ── 第 %d 轮%s（累计 %d 轮对话）" % (r + 1, label, turns_run))

            if failure or (control and control.stopped) or turns_run >= target:
                break

        # 训练完刷新性格（这一步才让它"长"）
        grown = self._regrow() if turns_run else dict(done.get("growth") or {},
                updated=False, skip_reason="no_new_experience")
        baseline_sessions, baseline_rounds, corrections = self._counter_baseline(done)
        if control and control.stopped and not failure:
            failure = "user_stopped"
        complete = turns_run == target and not failure and not grown.get("error")
        prog = {"turns": start + turns_run, "sessions": baseline_sessions + sessions_run,
                "rounds": baseline_rounds + rounds_run,
                "last_run": time.strftime("%Y-%m-%d %H:%M:%S"),
                "seconds": round(time.time() - t0, 1), "pool": len(pool),
                "source": source, "tutor": bool(tt), "evals": evals,
                "growth": grown, "turns_added": turns_run, "requested_turns": target, "failure": failure,
                "failure_diagnostic": failure_diagnostic,
                "gate_perception": _gate_on(self.gate_perception),
                "gate_observed_in_turn": bool(p.devlevel) if turns_run else None,
                "run_id": self.run_id, "eval_schema": EVAL_SCHEMA,
                "recovery_policy": "bounded_retry_v1", "strict": strict, "tutor_errors": tt.errors if tt else [],
                "sessions_added": sessions_run, "rounds_added": rounds_run,
                "sessions_started": sessions_started, "sessions_with_turns": sessions_with_turns,
                "counter_policy": "completed_dialogue_units_v1", "legacy_zero_turn_corrections": corrections,
                "source_fingerprint": run_source, "source_unchanged_during_run": run_source == source_fingerprint(_ROOT),
                "training_complete": complete, "outcome": "completed" if complete else "failed" if failure else "partial"}
        self._save_progress(prog)
        # ★ 每次跑完留一条**运行记录**（追加，不覆盖）。
        #
        #   为什么：`progress.json` 只存**最后一次**，于是"历史操作记录"没有数据源 ——
        #   用户点开软件想问"我以前跑过几次、各跑了多少轮、结果怎样"，答不上来。
        #   界面要能一目了然地看到历史，就得先有历史。
        self._append_run_log(prog)
        if os.path.abspath(self.dir) == os.path.abspath(TRAIN_DIR):
            try:
                from action_plan import write_report
                next_action = write_report(_ROOT)
                self._say("目标行动：" + next_action["next_action"]["title"])
            except (OSError, ValueError) as exc:
                self._say("行动方案重算失败：" + type(exc).__name__)
        self._say("=" * 72)
        self._say("训练结束｜新增 %d 轮｜共 %d 轮｜性格：%s"
                  % (turns_run, prog["turns"], grown.get("summary", "?")))
        return {"ok": complete, **prog}

    def _counter_baseline(self, done):
        """Correct only provable legacy zero-turn credits; never rewrite runs."""
        sessions, rounds = done.get("sessions", 0), done.get("rounds", 0)
        corrections = list(done.get("legacy_zero_turn_corrections") or [])
        applied = {item["run_id"] for item in corrections}
        path = os.path.join(self.dir, "runs.jsonl")
        if os.path.exists(path):
            with io.open(path, encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    if (row.get("run_schema") == 2 and row.get("turns_added") == 0 and row.get("failure")
                            and row.get("run_id") and row["run_id"] not in applied):
                        s, r = row.get("sessions", 0), row.get("rounds", 0)
                        if type(s) is int and type(r) is int and s >= 0 and r >= 0 and s <= sessions and r <= rounds:
                            sessions -= s
                            rounds -= r
                            corrections.append({"run_id": row["run_id"], "sessions_removed": s,
                                                "rounds_removed": r, "basis": "zero_recorded_turns"})
                            applied.add(row["run_id"])
        return sessions, rounds, corrections

    def _record_eval(self, item: dict, said: str, res, ev: dict) -> None:
        """把训练师的评价写进 eval.jsonl —— **与台账分开存**。

        为什么分开：台账是**系统自己的记忆**（它经历过什么）；
        评价是**外部意见**（别人怎么看它）。把意见混进记忆，
        等于让它把别人的评判当成自己的经历。
        """
        m = getattr(res, "mech", None) or {}
        rec = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"),
               # ★ 版本隔离（管理员判定的严重度 3）：没有它，跨版本混算会污染
               #   所有"率"，而那种污染已经害过一次验收判断。
               "eval_schema": EVAL_SCHEMA, "recovery_policy": "bounded_retry_v1", "turn_id": getattr(res, "turn_id", None),
               "mech": m,
               "input": said,
               "input_source": (item.get("input_origin") or {}).get("kind", item.get("source", "?")),
               "input_origin": item.get("input_origin"),
               "topic_id": item.get("topic_id"),
               "behavior": getattr(res, "behavior", ""),
               "planned_behavior": getattr(res, "planned_behavior", None),
               "action_observation": getattr(res, "action_observation", None),
               "markers": getattr(res, "markers", []),
               "output": getattr(res, "output", ""),
               "character_note": getattr(res, "character_note", None),
               # ★ 埋点（管理员判定后加，严重度 2）：
               #   它要的是分清「没产生 mech」还是「产生了但被丢掉」。
               #   留这两个字段就能分清，而且**长期有效** —— 以后同类问题不必再查一遍。
               "mech_keys": len(m),
               "mech_carried": bool(m.get("_carried")),
               # ★ 2026-10-29（Gemini 批复第 ② 项）：补记 `signature_key`。
               #
               #   为什么必须补：`cognition_ops` 的算子 3（`HABITUATION_LOOP_BREAK`，
               #   「同一情境第 N 次」）需要它。实测 `signature_key` 在 eval.jsonl 里
               #   **零行有值** ⇒ 那个算子**结构上永远不可能被验证**。
               #
               #   ⚠️ 这是**只加字段、不改行为**：取值来自 `res` 或 input_origin，
               #      取不到就是 None，不影响任何现有分支。
               "signature_key": (getattr(res, "signature_key", None)
                                 or (item.get("input_origin") or {}).get("signature_key")),
               "tutor": ev or {}}
        try:
            with io.open(self.eval_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:                          # noqa: BLE001
            if getattr(self, "strict", False):
                raise

    def _regrow(self) -> dict:
        """跑一次完整 learn()，让性格从这一批新经历里长出来。"""
        try:
            from association import Association
            from character import Character
            from experience import load_ledger
            a = Association.derive_from_ledger(
                self.ledger, out_path=os.path.join(self.dir, "association.jsonl"))
            rows = load_ledger(self.ledger)
            snaps = [r["mech"] for r in rows if r.get("mech")]
            ch = Character(self.character)
            ch.learn(a, mech=snaps[-1] if snaps else None)
            return {"polarity": ch.polarity.to_dict(),
                    "milestones": [m.text for m in ch.milestones],
                    "pairs": len(a.pairs),
                    "summary": "极性 %s｜里程碑 %d 条"
                               % (ch.polarity.to_dict(), len(ch.milestones))}
        except Exception as e:                     # noqa: BLE001
            return {"error": repr(e)[:120], "summary": "刷新失败"}

    # ---- 进度
    def _load_progress(self) -> dict:
        if os.path.exists(self.progress_file):
            try:
                with io.open(self.progress_file, encoding="utf-8") as handle:
                    return json.load(handle)
            except Exception:                      # noqa: BLE001
                pass
        return {}

    def _append_run_log(self, prog: dict) -> None:
        """把这一次训练追加进运行记录（`state/train/runs.jsonl`）。

        与 `progress.json` 的区别：
          · `progress.json` = **当前进度**（覆盖写，只留最后一次）
          · `runs.jsonl`    = **运行历史**（追加写，一条不丢）
        界面上的「历史操作」读的是后者。
        """
        try:
            os.makedirs(self.dir, exist_ok=True)
            g = prog.get("growth") or {}
            rec = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                   "turns_added": prog.get("turns_added", 0),
                   "turns_total": prog.get("turns", 0),
                   "failure": prog.get("failure"), "gate_perception": prog.get("gate_perception"),
                   "rounds": prog.get("rounds_added", 0), "sessions": prog.get("sessions_added", 0),
                   "rounds_total": prog.get("rounds", 0), "sessions_total": prog.get("sessions", 0),
                   "run_schema": 3, "run_id": prog.get("run_id"),
                   "training_complete": prog.get("training_complete"), "outcome": prog.get("outcome"),
                   "requested_turns": prog.get("requested_turns"), "sessions_started": prog.get("sessions_started"),
                   "counter_policy": prog.get("counter_policy"), "failure_diagnostic": prog.get("failure_diagnostic"),
                   "tutor_errors": prog.get("tutor_errors"),
                   "legacy_zero_turn_corrections": prog.get("legacy_zero_turn_corrections"),
                   "source_fingerprint": prog.get("source_fingerprint"),
                   "source_unchanged_during_run": prog.get("source_unchanged_during_run"),
                   "source": prog.get("source", ""), "tutor": prog.get("tutor", False),
                   "seconds": prog.get("seconds", 0), "evals": prog.get("evals", 0),
                   "eval_schema": EVAL_SCHEMA,
                   "level": (g.get("polarity") or {}).get("level") or g.get("level"),
                   "milestones": len(g.get("milestones") or []),
                   "summary": g.get("summary", "")}
            with io.open(os.path.join(self.dir, "runs.jsonl"), "a",
                         encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:                          # noqa: BLE001
            # 运行记录写不上不该拖垮训练 —— 但也不静默。
            self._say("  ⚠ 运行记录没写成（历史操作会缺一条）")

    def _save_progress(self, d: dict) -> None:
        from behavior_learning import atomic_json
        atomic_json(self.progress_file, d)


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="训练运行器")
    ap.add_argument("--rounds", type=int, default=1)
    ap.add_argument("--session-len", type=int, default=6)
    ap.add_argument("--source", default="corpus", choices=["corpus", "topics", "all"])
    ap.add_argument("--synth", type=int, default=0, help="模型扮演用户的条数（自证循环）")
    ap.add_argument("--tutor", action="store_true",
                    help="训练师驱动：AI 扮演人接着往下说，并在每轮后给评价（意见层）")
    ap.add_argument("--offline", action="store_true")
    # ★ 2026-10-28：可核对序列（押金/楼层）**默认关闭**。
    #   它会污染训练池（session_len==3 时 100% 命中），且会把系统往记账员方向训。
    #   它的归宿是回归测试 tests/test_sequence_pool.py，不是对话训练。
    # ★ 2026-10-29：跨轮思考层（当轮算子 + 空档回想 + 2 环连锁）。**默认关闭**。
    # ★ 2026-10-29：默认**开启**（非离线时）。保留 `--no-cognition` 供显式关闭对比。
    ap.add_argument("--no-cognition", dest="cognition", action="store_false",
                    help="关闭跨轮思考层（默认在非离线时开启）")
    ap.add_argument("--cognition", dest="cognition", action="store_true",
                    help="显式开启跨轮思考层（非离线时本来就是开的）")
    ap.set_defaults(cognition=None)
    ap.add_argument("--sequences", action="store_true",
                    help="加载 corpus/sequences.json（可核对序列；默认关闭）")
    ap.add_argument("--seed", type=int, default=20260920)
    a = ap.parse_args()
    t = Trainer(use_api=not a.offline, use_think=not a.offline,
                use_sequences=a.sequences,
                use_cognition=a.cognition)
    r = t.run(rounds=a.rounds, session_len=a.session_len, source=a.source,
              synth_n=a.synth, seed=a.seed, tutor=a.tutor)
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
