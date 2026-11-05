# ThoughtBrief 形态检查 V1

这是工程师侧的台上／台下分离检查。
从真实 `turn` 取得台下 `ThoughtBrief`，判断字段形态与一致性。

## 检查点

1. `dominant` 只能是 `drive`、`meaning`、`org`。
2. `drive` 必须存在；`direction` 是 `pursue`、`guard`、`hold` 或 `None`。
3. `stance.posture` 是 `yieldable`、`non_negotiable` 或 `needs_clarify`。
4. `org.grain` 是 `simple`、`rule` 或 `differentiated`。
5. `must_not_pretend` 非空，每项都是非空字符串。
6. `dominant` 为 `org` 时，`drive` 存在且 `drive.why` 非空（硬闸 3）。

## 覆盖回合

- 日常陈述：`drive` 主导，方向允许为 `None`。
- 动力主导：`drive` 主导，方向为 `pursue`。
- 守诺：同场三轮均检查形态，末轮 `meaning` 主导且立场为 `non_negotiable`。
- 身份问引发的组织冲突：`org` 主导，且保留有理由的 `drive`。

每个测试开始重置 stub、LLM hook 和同场状态。
测试使用真实回合，守诺的三轮保留同场上下文。

## 边界

本检查只断言 Brief 字段及枚举，不检查台上台词。
它不是听感验收，也不是禁词或中文词表匹配。
它不改变行为代码或对话行为。
真实回合不符合预期时，先停下报告，不改行为或预期凑绿。
