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
- filler 捡悬问回归仍绿
- pytest；commit 勿 push


## 收放（resolve／clear）
与承诺 resolve 对称：**宁缺毋滥**，拿不准不清。勿禁词堵嘴。

- **resolve**：读 Brief 结构化字段 `openq_resolve`（arbitrate 在 filler+悬问 路径置 True；与 `OPENQ_RESOLVE_FLAG` 同义）。**禁止**只靠 say_intent 中文子串；改口文案不静默失效
- **clear**：仅可检验的换题——真开新话头（`我想聊…` 等）或用户明示放下（`先搁下／换个话题…`）；**闲聊／改口否定／身份问勿误清**
- **好奇新挂起**：新「待接的话头」写入前 `clear` 旧悬问（替换，防堆黏）
