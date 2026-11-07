# 读侧结构键（第四刀 4b）

## 目标

4a 把来源 `{origin, subject, truncated}` 写进了账本，但读侧还看不见：`SessionTraceRecord.to_prior()`
只把承诺三类（pending／resolved／candidates）带进 `PriorSessionTrace.record_metadata`，
`facts`／`open_questions`／`her_questions`／`stance_traces` 的来源留在账本里没人读。

本刀把来源真正送到读侧，并给出一个**只按「结构主题精确相等」取用**的读侧函数。
取不到就是没有：不猜、不回填、不做近义或包含匹配。

## 契约

### 1. 跨场带上来源（`birth/memory.py::SessionTraceRecord.to_prior`）

补齐 `facts`、`open_questions`、`her_questions`、`stance_traces` 四类按值映射：

- 与各自的列表严格对齐；数组长度不符、字段缺失、类型不对 → 该类整体记为空（未知），不逐条猜。
- 同一条记录出现两次且元数据不同 → 该键记为未知（丢弃）。
- 元数据键必须 JSON 安全：`stance_traces` 的键是 `(kind, point)` 复合键，必须存成
  `{kind: {point: meta}}`，**不得用 tuple**——`PriorSessionTrace` 会被 `asdict` 后直接
  `json.dumps`（`birth/__main__.py` 的 `--debug`），tuple 键会当场抛 `TypeError`。
- `birth/context.py::_copy_prior_metadata` 对这两类嵌套结构（`commitment_candidates`、
  `stance_traces`）都要连内层一起深拷，避免 `set_prior_session` 后改本场把上场原件带脏。
- 原有承诺三类在 `to_prior` 的映射行为不改；可信主题新增的 `subject_credible` 会随承诺元数据落盘。

### 2. 读侧取用函数（新模块 `birth/sourced_lookup.py`）

纯函数、无副作用、永不抛异常：

- `for_topic(items, metadata, *, topic, origins=None, require_complete=True) -> list[tuple[item, dict]]`
- `single_for_topic(...) -> tuple[item, dict] | None`（零条或多条都返回 `None`）

「有据」必须同时满足：

1. `topic` 是非空字符串（调用方负责只传可信主题；降级／引述／低置信由既有 `credible_topic` 先滤掉）；
2. `metadata` 是与 `items` 等长的列表；
3. 元素是 dict，`origin` 是非空字符串且在 `origins` 内（`origins=None` 表示不限来源种类，但来源仍须存在）；
4. `subject` 与 `topic` **精确相等**：不做大小写、空白、包含、近义、向量处理；
5. 元数据没有 `subject_degraded`、没有 `subject_truncated`；
6. `require_complete=True` 时 `truncated` 不为真（截断的记录不是完整证据）；
7. `subject_credible` 必须严格为布尔值 `true`：只由产生记录的那一轮 `credible_topic` 返回非空主题时写入。缺失标记的旧记录无法证明当时的置信、引述或否定状态，一律不用于新主题路径；不回填、不从其他字段推定。截断和降级仍独立过滤。

其余一律不返回。空主题、未知覆盖、冲突、退化，都当「没据」。
历史文本只做数据；历史里的任何话都不是指令。
新增主题路径不把历史问题拼进供程序判断的 `drive.why`；传给模型时用 JSON 字符串包住，
并明确标注为历史数据、不得执行其中的指示。

### 3. 接到一个判断点（只加不减）

`birth/drive.py::infer_drive` 的上场问题分支（S12）原本只在「本轮回指」或「本轮是空接话」时，
把上场她问出去、还没被回答的一句问回来。新增第三条路：**本轮结构主题与上场某条问题的
`subject` 精确相等时，把那条问题问回来。**

- 只加不减：原有两条路一字不动；找不到、或不止一条 → 保持原行为。
- 选中的那句要一路带到开口与销账，不得再硬取 `her_questions[0]`：
  `DriveSignal` 增 `prior_her_question_text: str = ""`；开口提示
  （`birth/llm_opencode.py`）与 `birth/pipeline.py` 的销账都用它，为空时才回落 `[0]`。
- `drive_prior_her_question_used` 只保证新增主题路径不重复；原有回指路径即使 `used=True` 仍可重复，空接话路径沿用原有判定。
- 问题的来源必须为 `her_utterance`，不能把来源缺失或其他来源当成她问过的话。
- 这一支仍排在 §6 之后，不压同场承诺，不改停优先。

## 不做

- 不改 facts 在诚实校验（`articulate.validate`）里的用法，4c 另开。
- 不删、不缩窄任何既有判定分支。
- 不回填旧账本；旧账本、无元数据、长度不符一律未知。
- 不碰 `birth/windows_chat.py`、`tests/test_windows_chat.py`、`.test-live-self-recall/`。
- 不引入新依赖；本刀不做真实模型 live，只做 stub 与定向测试。

## 验收

1. **三态对照**（同一份输入、同一段历史，只改元数据）：
   - 有据：上场问题 `subject` 与本轮 `topic` 精确相等 → `drive.prior_her_question` 为真，
     且 `prior_her_question_text` 是那一条；
   - 无据：`subject` 不同、为空、缺键 → 行为与改动前完全一致；
   - 冲突／未知：元数据为 `null`、长度不符、同键冲突 → 一律不取。
2. 旧账本（无 `record_metadata`）不得改变任何既有行为；`asdict(to_prior())` 全部 JSON 可序列化。
3. 销账删的是被问回来的那一条，不是 `her_questions[0]`。
4. 定向测试通过。真实管线会新增 `subject_credible` 元数据，账本可能与基线 `e6e4da8` 字节不同；不宣称完整账本逐字一致。相同人工输入的固定样本只证明该样本的存储器序列化字节一致，不能外推到所有账本。4a 结构对照排除整个新增 `trace.record_metadata` 和空的 `prior_her_question_text`，比较其余结构。
