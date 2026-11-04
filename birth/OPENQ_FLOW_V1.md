# 悬问回流（煤球定稿 · 可施工）

> 动力/仲裁已能读 `open_questions`（filler 时短暂捡起），但写入侧几乎只靠旧路径。本刀：台上开口若向对方抛出**可接的问句**，薄写入 `append_open_question`；宁缺毋滥。

## 规则
`extract_open_question(utterance) -> str | None`：
- 句末或句中有明确问对方的问号/「吗／呢／要不要／要不要先」且不是自问身份口径套话
- 排除：纯反问挡身份（「我是不是代码」类）、纯寒暄（「在吗」若是用户侧已有）
- 命中 → clip≤40 写入；与 commitments 一样去重
- pipeline 在事实回流后调用；若本轮已 resolve/clear 悬问，仍允许写入**新的**台上问句

## 验收
- 钩子开口「星空你想从哪头聊起？」→ open_questions 非空
- 「嗨，我在呢。」→ 不增加
- filler 不当作回答，悬问继续挂起
- pytest；commit 勿 push


## 收放（resolve／clear）
与承诺 resolve 对称：**宁缺毋滥**，拿不准不清。勿禁词堵嘴。

- **回答 resolve**：`turn(..., structured_openq_answered=True/False)` 优先；仅 None 时，薄检查同场有挂起且用户话与首条悬问有主题 token 重叠。命中调用现有 `resolve_open_question`，并清好奇挂起；仅 flag 而无条目时清 flag。False 明确否决兜底。filler 只短暂接话，不再自动 resolve 或追加同一轮问句。旧 `Brief.openq_resolve` 路径仍供结构化仲裁使用。
- 兜底排除 filler、改口否定、开题／放下及问句；中文相邻双字或英文整词重叠并非语义理解，可能误判复述，也会漏掉代词、同义改写、短答和非首条悬问。上游应优先提供结构化判断。
- 回答命中置本轮 `drive_openq_satisfied_pending`，无同场承诺时 hold/low，回复稳住、不追问原悬问；有 `last_commitments` 时只消解悬问并保持 §6 guard，不产生满足 hold。回合末清本轮 flag；org、身份与意义路径仍按原优先级处理。
- **clear**：读 Brief 结构化字段 `openq_clear`（arbitrate 在同场悬问＋用户明示放下（`先搁下／换个话题…`）或真开新话头（`我想聊…` 等，复用 drive `_extract_open_topic`）时置 True，与 `OPENQ_CLEAR_FLAG` 同义）。**禁止** pipeline 再扫放下词表；**闲聊／改口否定／身份问勿误清**
- **好奇新挂起**：读 Brief.`openq_curiosity_hang`（arbitrate 对齐 drive 好奇 pursue/high 置位）；写入前 `clear` 旧悬问（替换，防堆黏），并置 ThinContext.`curiosity_hang_pending`＝True；默认只挂 clip 文案，**不强制**「待接的话头：」前缀（drive／stub 已读 flag）。前缀仅无 flag 时的人类可读／旧快照兜底（`drive_cues_from_context`）；resolve／clear／new_session 均清 False。**禁止** pipeline 再扫 `CURIOSITY_MARKS` 中文词表
