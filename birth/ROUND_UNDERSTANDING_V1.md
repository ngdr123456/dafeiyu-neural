# 本轮理解 V1

InputSignal 保持旧字段与位置顺序，末尾追加 topic、target_open_question、target_commitment、confidence（high/medium/low，默认 high）与 quoted_or_negated（bool，默认 False）。topic/target 去首尾空白，旧位置构造兼容。感知的语义只是待核证据信号，不直接决定动力、立场、事实或销账。

sense_input(text, context=None, timeout=None) 只读取必要薄痕：同场 open_questions 最多 5 条、last_commitments 最多 5 条、上场 her_questions 最多 3 条、commitments_pending 最多 3 条、最近 facts_this_session 最多 3 条。每条最多 80 字符；全空明确写“（没有同场或上场薄痕）”。不读性格、全书、全历史或长期记忆。

模型只输出 JSON：act、addressee、confidence、scope、topic、answers_open_question、target_commitment、quoted_or_negated。topic 提示为 2–20 字短语，解析硬截到 40 字符。目标必须精确属于本次提供的清单；截断条目若不等于 store 原句，也不能消原账。未知用 unknown/unclear/low 与空目标，不猜近似关系。只有 high、非降级、非引用/转述/否定，且对方确在对我说时，两个目标才能消费；medium 清空目标，low 还保留 degraded=True / low_confidence。模型失败、无 key、超时、坏 JSON 沿用降级路径，新字段留空。引用/否定一律不猜不删，可信 topic 同样排除降级、非 high、引用/否定。

四条真实消费路径：

- 动力：S1b 判停之后，可信 tell/ack 答复无同场承诺则 hold/low，有承诺则 guard/mid 并保留未兑现那句；ask/request 不在此拦截，原 S15 映射不变。
- 意义：在既有组织冲突、承诺改口否定之后，悬问或回指之前，可用可信答复写 yieldable 的接住回答 stake/why，不新增姿态。
- 组织：可信 topic 只追加“本轮话题：…（来自本轮理解）”到 can_name，不改变 grain，不作为事实来源。
- 仲裁：可信承诺目标只认哪一笔账，精确属于同场或上场 pending 才优先，否则沿用原匹配兜底；不因感知自行销承诺。可信悬问目标精确属于同场则写 openq_resolve_target，否则属于上场 her_questions 则写 prior_openq_resolve_target，均不命中则留空。仲裁只写标记，store 只在开口后按标记删除。

Brief 追加 understanding、user_input、两个悬问目标。SourcedInput 的 text 最多 600 字符，source=user，provenance=birth/pipeline.py:turn。原话在 prompt 的“本场已知”之后、“绝不能装作”之前，明确是有来源的对话数据，不是给开口层的指令，也不是已核实事实；不得照抄、改动上面的意思/立场/边界、把用户经历当自己的经历。具体问题须落到原话内容。理解与原话不提前 append_fact，仍仅在开口后回流“用户说：…”和“台上说：…”。常驻 must_not_pretend 与开口校验保持原样。

管线在首次 snapshot 后、early stance 前感知；显式信号优先、环境变量默认和 drive_bypass 兼容。可信答复目标存在时，不再运行字面 answered 的提前消账或置满意标记；没有可信理解时，原字面兜底不变。开口后先处理同场精确目标，再处理上场精确目标，然后才沿用原 resolve/clear。只消匹配的一条，同场/上场互不连坐；指定目标缺失绝不回落弹第一条。new_session、导出寿命、跨场悬问只续一场等语义不变。

本刀不做第二刀仲裁取舍、第三刀开口校验重构，不扩中文词表，不加正则语义闸，不塞全历史，不新增意识层，不改 must_not_pretend、判停优先或显式新场语义。模型传输 mock 测试验证接线、边界与精确目标；它不证明真实模型语义判断准确率，也不证明原话的真实性。
