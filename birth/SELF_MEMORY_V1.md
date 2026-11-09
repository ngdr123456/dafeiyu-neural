# 自指记忆第一刀（SELF_MEMORY_V1）——第二期第二刀

> 2026-11-08 注：本文描述当时的落盘阶段，「只写不接读侧」是阶段边界，并非当前全貌。现在 `birth/self_recall.py` 已有有界读路径，可在符合请求条件时读取同场与已结束场次的自身发言，并区分无匹配、多条、不完整等结果；本文其余实施与验收文字保留为历史记录。文档修订不改变运行行为。


> 把她真实说出口、通过校验的那句话，从「事实账」里拆出来单独成一本账，每条带情境索引（动力方向／意义姿态／组织粒度／来路）。只落盘、可读回，不进 prompt、不进任何判定层——消费者是后续的选择器刀，本刀不接。

## 问题（第二期宗旨 + 裸对照钉死）
第二期中心：让活人感从她自己的真实历史里长出来，不从通用模型编造的人设里长出来（两条腿：诚实 + 自指记忆）。历史裸对照第 3 条曾写：「裸模型最像活人，正因为它愿意编——它没有自己的过去，只能借通用人设编造。」这只是当时的解释，不再作为活人感必然等于说谎的施工事实；诚实与来源区分仍须保留。

现状：她的发言已经以 `台上说：…` 的裸文本混在 `facts` 里（`pipeline.py` `_STORE.append_fact(f"台上说：{_clip(utterance)}")`），与「用户说：…」混在一起、无结构、无情境索引，且一起被 `max_facts=40` 老化和裁剪。她没有一个属于自己的、结构化的历史。

## 目标
建一本「她自己的话」的账：每条 = 她这轮真正交付的那句 + 情境索引（drive 方向／stance 姿态／org 粒度／来路）。只落盘、可读回，不进 prompt、不进动力层、不进任何判定层。这是第二期自指记忆的落盘层，同时给第三期微调备料。

## 改法边界
- `birth/types.py`：新增 `HerUtterance` dataclass，字段 `text: str`、`drive_direction: str`、`stance_posture: str`、`org_grain: str`、`source: str`。句长由 `text` 推出，不必落盘。
- `birth/context.py` `ThinContextStore`：新增内部集合 `self._her_utterances: list[HerUtterance]`（对齐 `_resolved_commitments` 的「只积累、`new_session()` 清空、`export_session_trace()` 导出」模式，**不放进 `ThinContext`／`snapshot()`**，故判定层读不到）；新增 `append_her_utterance(entry)`（追加，按容量上限 `_clip_list` 语义保留最近 N 条，**不按 text 去重**——每轮一条，重复也各算一条）；`new_session()` 清空；`export_session_trace()` 多导出一个 `her_utterances` 键（元素转 dict）。
- `birth/pipeline.py`：在确认出话之后（与 `_STORE.append_fact(f"台上说：{_clip(utterance)}")` 同点，即输出已交付），把本轮 `utterance` 连同情境索引写入 voice ledger；`text` 取 clip 后的 `utterance`，空串不写。情境取自 `brief`：`drive_direction = brief.drive.direction or ""`、`stance_posture = brief.stance.posture or ""`、`org_grain = brief.org.grain or ""`；`source = last_articulate_source()`（即 `result.articulate_source`）。
- `birth/memory.py`：`SessionTraceRecord` 加 `her_utterances` 字段；`append_session()` 增 `her_utterances` 形参并落盘（新增容量 `max_utterances`，默认 200，沿用 `_clip_list` 保留最近 N）；`list_sessions()` 读回；`is_empty()` 计入该字段。**不进 `PriorSessionTrace`**（不进 prompt、不进动力层；跨场读取走 `list_sessions()`，留给选择器刀）。
- 保留 `append_fact(f"台上说：…")` 完全不动（facts 仍是 prompt 里的事实通道），voice ledger 是**并行新通道**，不是替换。

## 必须保留（一字不动）
- 五层判定逻辑（drive/stance/org/arbitrate/articulate 的分支、优先级、识别）。
- `must_not_pretend` 与诚实约束。
- 既有 facts／承诺／悬问／回指全部接线（voice ledger 只是新增一条只进不出的落盘通道）。
- `append_fact(f"台上说：…")` 现状（voice ledger 不取代 facts）。

## 验收
1. 单测（无模型）：`turn(text, new_session=True, stub=True)` 后，voice ledger 有且只有一条 entry，`entry.text == result.utterance`，且 `drive_direction/stance_posture/org_grain/source` 与 brief／result 一致（断言**具体值**，不只非空；至少覆盖一条 drive=None 的空串回退）。
2. 拒收仍入账的是最终上台句：走一次 articulate 拒收后兜底的路径（复用现有拒收机制，如 `set_llm_hook` 返回灾难句或 reject_self_id），断言 voice ledger 记的是**最终交付的 `utterance`**、`source` 对应该兜底来源。
3. 落盘读回：`export_session_trace()` 含 `her_utterances`；`BirthMemoryStore.append_session(**trace)` 后 `list_sessions()[-1].her_utterances` 与场内一致；跨场 `latest_prior()` 得到的 `PriorSessionTrace` **没有** `her_utterances`（证明不进 prompt）。
4. 容量：写满 `max_utterances` 后只保留最近 N 条（对齐 `_clip_list` 语义）。
5. 完整 birth 套件全绿、无回归（`python -m pytest -q tests/test_birth*.py`）。
6. 真模型 live 只实跑一次，贴原话 + JSON + direction，确认 voice ledger 那条的 `text` 与台上原话一致、情境索引正确。

## 不做
- 不进 prompt、不进动力层、不进任何判定层（voice ledger 只落盘，消费者是后续的选择器刀）。
- 不接选择器、不算声音距离、不做变异配额（后续刀）。
- 不碰五层判定逻辑、must_not_pretend、诚实约束。
- 不碰 `birth/windows_chat.py` 与 `tests/test_windows_chat.py`（界面线有未提交改动，与脑线无关）。
- 不改既有 facts／承诺／悬问的容量与语义（「加记忆长度」若涉及这些既有通道，另开刀）。
- 不加字面禁词表、不做后置扫词。
- 不 push。
