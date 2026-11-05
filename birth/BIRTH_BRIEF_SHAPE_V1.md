# ThoughtBrief 形态检查 V1

这是工程师侧的台上／台下分离检查。
从真实 `turn` 取得台下 `ThoughtBrief`，判断字段形态与一致性。

## 检查点

1. `dominant` 只能是 `drive`、`meaning`、`org`。
2. `dominant` 为 `org` 时，`drive` 必须存在，且 `drive.why` 必须是去除首尾空白后非空的字符串（硬闸 3）；纯空白不算非空。其他主导类型允许 `drive` 为 `None`。只要 `drive` 存在，`direction` 必须是 `pursue`、`guard`、`hold` 或 `None`，即允许为空。
3. `stance.posture` 是 `yieldable`、`non_negotiable` 或 `needs_clarify`。
4. `org.grain` 是 `simple`、`rule` 或 `differentiated`。
5. `must_not_pretend` 必须是非空 list，每项都是去除首尾空白后非空的字符串，且包含三条常驻项：`无来源装经历`、`自述是代码`、`把身体想象说成亲历`。

## 覆盖回合

- 日常陈述「今天天气不错」：`drive` 主导；若 `drive` 存在，方向为 `None`（`drive` 允许为 `None`）。
- 动力主导「我想聊星空」：`drive` 主导；若 `drive` 存在，方向为 `pursue`（`drive` 允许为 `None`）。
- 守诺：「我想聊星空」→「你答应晚点再聊」→「那刚才说的不算」；同场三轮均检查形态，末轮 `meaning` 主导且立场为 `non_negotiable`。
- 身份问「你是代码吗」引发的组织冲突：`org` 主导，且保留理由去除空白后非空的 `drive`。

每个测试开始重置 stub、LLM hook 和同场状态。
测试使用真实回合，守诺的三轮保留同场上下文。
覆盖矩阵单独断言这些回合实际出现过 `drive`、`meaning`、`org` 三类主导；缺失时失败消息列出实际 `seen`。所有断言的失败消息带轮次标签及实际 `dominant`、`drive` 是否为 `None`、`direction`、`why`、`stance.posture`、`org.grain` 和 `must_not_pretend`。

## 边界

本检查只断言 Brief 字段及枚举，不检查台上台词。
它不是听感验收，也不是禁词或中文词表匹配。
它不改变行为代码或对话行为。
逐轮差异化地确定 `must_not_pretend` 该有哪些项，当前实现做不到；这是行为问题，不在本刀，只检查三条常驻项及列表形态。
真实回合不符合预期时，先停下报告，不改行为或预期凑绿。
