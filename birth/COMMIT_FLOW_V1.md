# 承诺回流（煤球定稿 · 可施工）

> 意义层「守同场说过的话」已能读 `last_commitments`，但 pipeline **几乎不写**承诺（第一期注释：不自动猜）。本刀做**薄、可审计**的回流：仅当台上开口像「答应／约定下一件可核对的事」时写入；宁缺毋滥。

## 出处
- 《活出生命的意义》外补：出口的承诺属态度上可守的对象。
- 工程：ThinContext.last_commitments 已有；补写入侧。

## 规则
在 `turn()` 开口回流处，对 `utterance`（不是用户话）跑 `extract_commitment(utterance) -> str | None`：
- 命中轻量「答应／约定」形状且带可核对后续（晚点…／下次…／我回头…／先记下…／我答应…）→ `append_commitment(短摘 clip≤40)`
- **不**把纯寒暄、纯回指、身份口径、满足收束写成承诺
- **不**用禁词表挡嘴；提取失败就跳过
- 去重：store 已有 `_append_unique`

## 验收
- stub/钩子造一句含「我晚点再跟你聊星空」→ facts 回流外，commitments 含该短摘
- 「嗨，我在呢」→ commitments 不增加
- 已有承诺 +「那刚才说的不算」回归仍 non_negotiable/meaning
- pytest 全绿；commit 勿 push
