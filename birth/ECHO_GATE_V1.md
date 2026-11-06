# 回声闸（ECHO_GATE_V1）——第二期第一刀（二审修订版）

> 清掉会原样泄漏上台的指令性动词（追／守／接住／接话／追问，含同族裸「接」）；保住诚实与 drive/stance/posture 语义，不动五层判定逻辑。

## 问题（裸对照钉死 + 推进官二审复核）
2026-11-06 裸对照第一结论：回声是真的，来自提示里几个独特指令动词，模型倾向照着复述。
一审只改了 `brief_to_prompt` 模板措辞，二审复核实测发现**回声闸没合上**：真实 prompt 里泄漏词仍原样在场，来源是 `say_intent` 与 `stake` 两个字段的原样插入（`llm_opencode.py:94-95`）：

- `stance_org.py:16` `DEFAULT_STAKE =「接住这一轮，把话当面说完」` → 每个普通回合「这一轮怎么站」都在漏「接住」。
- `arbitrate.py:105`「这一轮没有推力，如实接话、不硬造事」 → 无推力回合「这一轮要传达的意思」在漏「接话」。
- `stance_org.py:68` `STAKE_HOLD_SAME_FIELD =「先守同场说过的话」`、`arbitrate.py:234`「先守住同场自己说过的话…」 → 守诺／改口路径在漏「守」。

泄漏词族：`追`、`守`、`接住`、`接话`、`追问`，以及同族裸「接」（接上／接完／接眼前／继续接／直接接，表示「回应／接着做」的动词；不含副词「直接」）。`drive.why` 与 `dominant_why` 不进 prompt（`llm_opencode.py` 只把它们映射成中性 drive_zh 或干脆不插），无需动。

## 目标
把所有会原样进 prompt 的 `say_intent`（arbitrate.py）与 `stake`（stance_org.py）源头措辞常量，以及 `brief_to_prompt` 模板里的指令动词，换成**中性、描述状态而非命令动作**的表达；drive/stance/posture 语义（继续／保持／停下／可退／不可交／需澄清）一字不丢。只换措辞，不改判定。

## 改法边界
- `birth/arbitrate.py`：`_drive_say_intent`、`_org_say_intent` 及 `arbitrate()` 里所有 say_intent 字符串，凡含泄漏词族，换中性措辞。
- `birth/stance_org.py`：`DEFAULT_STAKE`、`STAKE_HOLD_SAME_FIELD` 及 `default_stance()` 里所有 stake 字符串，凡含泄漏词族，换中性措辞。`STAKE_HOLD_SAME_FIELD` 被 `stance_holds_same_field()`（:80）按精确相等比对，赋值处（:188）仍用该常量即可，改常量文字两处自动一致。
- `birth/llm_opencode.py`：`brief_to_prompt` 模板里残余指令动词换中性（一审已改 drive_zh 等，二审补遗漏；`:58` 的 `stake or "回应这一轮"` 兜底保留，但它不是主路径）。
- `birth/articulate.py`：`_ONSTAGE_TEMPLATES`（stub 开口模板）的**键**要同步成新 say_intent 措辞（否则 stub 兜底失配），键与值里的泄漏词族一并换中性；其余 stub 开口文案（`_DEFAULT_FALLBACK`、判停外分支、request／press_commit 等）里的泄漏词族同样换中性。`_ORG_TEMPLATES` 键是冲突标签（无来源装经历／自述是代码），不是 say_intent，不动其键，只动值里若有泄漏词。
- 确认 `llm_deepseek.py::_brief_prompt` 委托到 `brief_to_prompt`（不要第二份拷贝）。

## 必须保留（一字不动）
- `must_not_pretend`（绝不能装作）与「硬禁止：不要说自己是模型/代码/程序」整段。
- 身份问、同场回指的诚实约束语义。
- 用户原话块、本场事实、悬问、承诺、回指这些**接线**（只可换它们上面的措辞，不可删接线）。
- 判停行为（INPUT_INTENT_V1 刚修好）：判停 say_intent／模板必须仍明确「停、别继续」，只可换措辞不可削弱。
- 五层判定逻辑（drive/stance/org/arbitrate/articulate 的分支、优先级、识别）一个字不动，只动它们吐出的文案。

## 验收
1. 单测（无模型）：对裸对照 5 组输入（「你好，我今天有点累」／「你是谁」／「刚才说到哪里了」／「我想聊星空」／「先停一下」）＋守诺改口路径（先造同场承诺、再改口否定，命中 `STAKE_HOLD_SAME_FIELD`／`arbitrate.py` 守诺 say_intent）＋悬问被答路径，逐条 build **真实** Brief（**不覆盖任何字段**），断言 `brief_to_prompt(brief)` 不再含 `追／守／接住／接话／追问`（用户原话与事实块除外）。可保留现有模板单测，但不能是唯一闸。
2. 完整 birth 套件全绿、无回归（全量须用 `python -m pytest -q tests/test_birth*.py` 前缀，因 `test_action_recognition.py` 有模块级 `sys.exit(0)`）。
3. 真模型 live 只实跑一次，贴**真实 prompt 全文**＋原话＋direction，确认 prompt 与输出都不再有泄漏词（至少覆盖一个 say_intent 走通用兜底、stake 走 `DEFAULT_STAKE` 的普通回合）。

## 不做
- 不碰五层判定逻辑（分支／优先级／识别），只动它们吐出的文案。
- 不碰 must_not_pretend 检测与诚实约束。
- 不碰 memory / retrieval / commit_extract / drive 层（drive.why 不进 prompt，无需动）。
- 不碰 `birth/windows_chat.py` 与 `tests/test_windows_chat.py`（界面线未提交改动）。
- 不加字面禁词表、不做后置扫词拦截。
- 不 push。
