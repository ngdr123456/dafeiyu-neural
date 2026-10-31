# -*- coding: utf-8 -*-
"""把机制相位翻译成一句**输出形式约束**（不诊断用户）。

★ 2026-10-28 **第二版（第一版越界，已撤）**：

  第一版是这样写的：
      "OVERLOADED": "**他这会儿承重到了极点**。极简、沉静、落地：不追问…"
      "WANT_NO_LIKE": "**他拼命想要的，和他实际尝到的，不是一回事**。…"
      "DRIVE_UNACKNOWLEDGED": "**他在过度执着于一个结果**。…"

  两处错：

  ① **越界诊断。** `pipeline.py` 的 `signal_basis` 已声明 tension / w / l 只是
     **工程代理量**，不是对真人的生理测量或临床诊断。而第一版把这些代理量
     直接翻译成了对用户的**心理断言**。一旦模型顺着那句提示对用户说出
     「你现在承重到了极点／你太执着于结果了」，当场违反 `FRAME_SYSTEM` 第 2 条
     （**不诊断、不贴标签**）。

  ② **伪造理论口吻。** 「极简、沉静、落地」这类措辞是我编的，但它读起来像原书的话。
     后人读代码会以为那是三本书里的引文。

  ⇒ 第二版两条铁律（由 `tests/test_stance_discipline.py` 守着）：
     · **主语归己**：只说「本轮回应要求什么形式」，不说「他怎么样」。
     · **显式分栏**：`[有据：…]` 只放原书／行为库真有的话；
       `[ENG·句法约束]` 放我写的工程要求。两者在字符串上**物理切开**。

★ 纪律：`[有据]` 里每一句都必须能在 books/ 或 rules/ 里找到出处；
  找不到就写 `[ENG·无原书依据]`，不许硬套一个来源。
"""
from __future__ import annotations

#: 相位 → (标注了来源的指令, 建议字数上限)
#:
#: 每条格式：`【对应行为】<行为 ID>[有据：<出处>]｜[ENG·句法约束] <工程要求>`
STANCE: dict[str, tuple[str, int]] = {
    "OVERLOADED": (
        "【对应行为】ACKNOWLEDGE（承认）[有据：M-意义疗法师不作价值评判]｜"
        "[ENG·句法约束] 不追问，不复述整句，只用一句 ≤24 字的话接住他原话里的核心词。",
        24),
    "DEPLETED": (
        "【对应行为】REPLENISH（补当下）[有据：D-当下分子负责此时此地的体验]｜"
        "[ENG·句法约束] 不顺着抽象道理往下接，"
        "只问他眼前、手边或今天一件看得见摸得着的具体小事（≤40 字）。",
        40),
    "WANT_NO_LIKE": (
        "【对应行为】REFLECT（并置观察）[有据：D-想要回路与喜欢回路是两回事]｜"
        "[ENG·句法约束] 只把他「想要」与「实际感受」两句**原话**平铺摆在一起，"
        "不加任何渲染或解释（≤40 字）。",
        40),
    "NOTHING_MORE": (
        "【对应行为】REPORT_OWN_STATE（报告自身状态）[有据：M-我自成一派]｜"
        "[ENG·句法约束] 如实说出你这边没有更多想问的了，把球停住，不硬找话题（≤30 字）。",
        30),
    "ASKED_ALREADY": (
        "【对应行为】ACKNOWLEDGE（不连问→改为承认）[ENG·无原书依据，回合间防连问兜底]｜"
        "[ENG·句法约束] 上一轮刚问过细节，本轮**禁止再带问号**；"
        "只做 ≤20 字的简短承认或陈述自身状态。",
        24),
    "ASKABLE": (
        "【对应行为】ASK_DETAIL（问细节）[有据：M-生命向每个人提出问题]｜"
        "[ENG·句法约束] 直接揪住【具体锚点】或【具体画面】里的那个词问一句"
        "「当时怎么回事」，**禁止先复述整句做铺垫**（≤40 字）。",
        40),
    "TENSION_LOW": (
        "【对应行为】ASK_DETAIL（问细节）[有据：M-倾听具体问题]｜"
        "[ENG·句法约束] 围绕他话里的具体词提一个单句问题，或做极简承认；"
        "**严禁把原话换语序还回去**（≤40 字）。",
        40),
    "ATTITUDE_PRESENT": (
        "【对应行为】ACKNOWLEDGE（承认态度分量）[有据：M-第三条意义途径：态度]｜"
        "[ENG·句法约束] 不褒奖（不说「很好」「进步了」），不复述整句，"
        "只用 ≤24 字承认这句话的分量。",
        24),
    "DRIVE_UNACKNOWLEDGED": (
        "【对应行为】ASK_MUST / REFLECT[有据：E-过度意向时不许助推]｜"
        "[ENG·句法约束] **严禁助推**！只许就他话里的「必须／一定」反问一句"
        "「非得如此吗？」，或仅作原话引用（≤40 字）。",
        40),
    "NO_TENSION": (
        "【对应行为】REPLENISH / SILENCE [有据：M-无张力不是健康状态]｜"
        "[ENG·句法约束] 不长篇复述；要么就具体小事问一句，要么 ≤20 字简短回应，"
        "无话可问则直接输出沉默标记。",
        35),
}

_DEFAULT_BUDGET = 40


#: 已经"收敛到底"的动作 —— 到这几个就不再是探照了
_CONVERGED = ("REFLECT", "ACKNOWLEDGE", "ACKNOWLEDGE_CLOSE", "SILENCE")


def stance_for(phase: str, rejected: bool = False, streak: int = 0,
               final_bid: str | None = None, char_note: str | None = None,
               last_encounter: str = "", boldness: float | None = None) -> str:
    """把相位翻成一句**输出形式约束**。

    ★ 2026-10-30（架构病灶 3：**控制流旁路脑裂**，这是本轮最重要的一处修复）

      **病灶**：`pipeline` 花了大力气跑 `Responder.choose` + `mcond` +
      `Character.modulate(R1–R4)` 算出 `bid`，然后拿它去渲染**模板**
      `ren.output`。但在大脑模式下（>95% 轮次）模板输出**被直接丢弃**，
      而 `Frame.stance` 调的是 `stance_for(mst.phase)` ——
      **只读原始相位，完全不看 `bid`**。

      ⇒ 后果：`R4` 因受挫把 `ASK_DETAIL` 收敛成 `REFLECT` 时，
        模板轨在**刹车**，大脑轨的 `stance` 却还在按 `ASKABLE` **踩油门**
        （"张力已起，他还在讲，你有话可问。直接盯住他话里那个具体的词问一句"）。
      ⇒ **整个 `Character.modulate`（R1–R4）在大脑模式下被 100% 旁路架空。**

    ★ 修法：`final_bid` 落在收敛集里（说明性格层踩了刹车）时，
      **用收敛姿态覆盖相位姿态** —— 模板轨和大脑轨同时减速。
    """
    # ---- 性格层踩了刹车 ⇒ 覆盖相位姿态（Stage 4 的同构注入）
    #
    #   ⚠️ 2026-10-30 实测抓到的坑：第一版只判 `final_bid in _CONVERGED`，
    #      而 `REFLECT` 是**阶梯的默认兜底**（不是"性格踩刹车"），
    #      ⇒ 于是**每一轮**的 stance 都变成「性格收敛」，
    #      `test_frame_anchors` F6 当场抓到（它期望无相位时给"别复述整句"的兜底）。
    #   ⇒ 判据必须是**`char_note` 非空**（= 性格层 R1–R4 **真的介入了**），
    #      而不是"最终动作恰好落在收敛集里"。
    # ★ 2026-10-30（Gemini 破案 2 根因 B）：**严厉禁令只给真碰壁**。
    #
    #   病灶：原来判 `char_note and final_bid in _CONVERGED`，
    #   而 `Character.modulate` 不只有 **R4（刚碰壁）**，还有 **R1/R2/R3**
    #   （耐心递减、动作平滑等常规轮换）——
    #   当用户明明在积极深聊（CONFIRMED、根本没碰壁），
    #   只因为 R1/R2/R3 的常规介入，stance 就也下"**不要追问、不要亮新的矛盾**"
    #   ⇒ 直接把她的第一人称好奇心按死（实测：第一人称想要 0/36）。
    #
    #   ⇒ 只有 **真碰壁** 才收敛：
    #     ① `last_encounter == "REBUFFED"`（R4 的触发源）
    #     ② 或 `boldness < 0.42`（低笃定，同样是 R4 的触发源）
    #     其余情况（R1/R2/R3 的常规平滑）**不下全局禁令**。
    _real_rebuff = (last_encounter == "REBUFFED") or (
        boldness is not None and boldness < 0.42)
    if char_note and final_bid in _CONVERGED and _real_rebuff:
        why = ("（%s）" % char_note) if char_note else ""
        return ("【性格收敛%s】这一轮不要追问、不要翻旧账、不要亮新的矛盾。"
                "只用一句简短的话，平实地接住或承认他刚说的事。"
                "如果他刚说完一件很重的事，你宁可不说话也不要凑一句。"
                % why).strip()
    return _stance_by_phase(phase, rejected, streak)


def _stance_by_phase(phase: str, rejected: bool = False, streak: int = 0) -> str:
    """把相位翻成一句**输出形式约束**。`rejected` / `streak` 来自她自己的失败读数。

    ⚠️ 这里说的是「本轮回应要求什么形式」，**不说「用户处于什么心理状态」**。
       后者是诊断，`FRAME_SYSTEM` 第 2 条明令禁止。

    ⚠️ 2026-10-28 修：第一版这里写成 `base = STANCE.get(...)`，
       取到的是**整个 tuple**，于是 `base + "\\n" + tail` 抛
       `TypeError: can only concatenate tuple (not "str") to tuple`。
       现在显式取 `[0]`。
    """
    base = STANCE.get(phase or "", ("", _DEFAULT_BUDGET))[0]
    if rejected:
        tail = ("[ENG·上一轮的受阻事实] 上一轮你**想说的话没能说出去**（被闸门退回了%s）。"
                % ("，已连续 %d 轮" % streak if streak > 1 else ""))
        tail += ("这可以如实当成本轮的内容（「刚才有句话到嘴边我咽回去了」），"
                 "或者干脆沉默 —— 不要靠拼一句安全的复读来糊弄过去。")
        return (base + "\n" + tail) if base else tail
    return base or ("[ENG·句法约束] 读不到机制姿态 —— 按你平时的方式说，"
                    "但**别复述整句**，也别替他判断。")


def word_budget(phase: str) -> int:
    """这一轮的建议字数上限（提醒用，不是闸门）。"""
    return STANCE.get(phase or "", ("", _DEFAULT_BUDGET))[1]
