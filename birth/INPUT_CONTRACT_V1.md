# 输入信号契约 V1

此前使用「帮我」「给我」等固定词组区分问句和请求的方案被否定：固定词组仍是词表，不是理解。

现有来源的边界：`birth/pipeline.py` 的 `turn` 接收的 `structured_drive_*` 在当前代码中只有测试通过 kwargs 传入，生产入口没有调用方。`ThinContext` 的 drive flags 由 `turn` 调用 `birth/drive.py` 的 `should_set_drive_*` 写入，无结构 cue 时依靠 MARKS 等既有兜底。`birth/openq_extract.py` 用问号、「吗」「呢」「要不要」等标记及 token 重叠处理悬问；`birth/session_trace.py` 提供会话痕迹与回指辅助。`birth/retrieval.py` 是独立 sidecar，提供相似度候选，不是意图或事实来源。

这里仅建立 `InputSignal` 契约和 `turn` 的真实传参路径。普通入口传 `None`，不产输入信号。不从原始文本判断 ask/request/tell/ack，不用正则、短语或标记，不调模型，不将检索相似度当意图或事实，不声称理解，不改台上话术，也不加分数。

`InputSignal` 是 frozen dataclass：`act` 为 ask/request/ack/tell/unknown，`addressee` 为 other/self/unclear；`source` 标识生产者，`provenance` 指向可追溯位置。两者去空白后均不得为空，即使 `degraded=True` 也需说明来源和位置；非法枚举或空白来源、位置抛 `ValueError`。`degraded` 默认为 False，`reason` 默认为空字符串。降级信号不产生动力线索；非 ask/request 同样不产生线索。转换按 act 工作，保留 addressee 供上游表达，不额外推断。

`turn` 将信号传入 `infer_drive` 并在 `TurnResult` 中返回。S15 位于 S1–S14 之后、MARKS 兜底之前，已有优先级保持不变；普通入口的 `input_signal=None`，行为与基线一致。

接口可接未来可追溯的模型、解析器或上游调用方。现有普通入口没有这样的生产者，因此一般问句或请求不会因此获得新的动力线索，这是有意保留的边界；已有规则仍按原样运行。

验收时逐个运行：

```text
python -m pytest -q tests/test_birth_input_contract.py
python -m pytest -q tests/test_birth_brief_shape.py
python -m pytest -q tests/test_birth_drive_structured.py
python -m pytest -q tests/test_birth_phase1.py
python -m pytest -q tests/test_birth_body_imagine.py
python -m pytest -q tests/test_birth_identity_ask.py
python -m pytest -q tests/test_birth_multiturn_loop.py
python -m pytest -q tests/test_birth_cli_repl.py
```
