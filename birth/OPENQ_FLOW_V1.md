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
