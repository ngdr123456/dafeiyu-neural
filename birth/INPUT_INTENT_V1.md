# 输入意图 V1

本刀修复 request 一律映射为 pursue，导致暂停或终止类话语反而继续追的问题。按言语行为的语义类拆分，不按关键词判断。

`InputSignal.act` 枚举及语义：

- `ask`：询问（语义不变）。
- `request`：任务请求，要我具体去做一件事，如去关窗、去查、去写。
- `pause`：要我暂停或缓一缓；与 scope 一起解释。
- `stop`：明确终止；与 scope 一起解释。
- `ack`：回应或确认，包括「已经够了／可以收了」这类收束。
- `tell`：陈述（语义不变）。
- `unknown`：无法判断（语义不变）。

`drive_signal_from_input` 依次执行纯枚举映射：

| 条件 | 结果 | why |
| --- | --- | --- |
| `None` / `degraded=True` | `None` | — |
| `addressee != "other"` | `None` | — |
| `ask` | `pursue/mid` | `输入信号｜问句｜{source}｜缺口在外，顺着答` |
| `request` | `pursue/mid` | `输入信号｜请求｜{source}｜缺口在外，顺着接` |
| `pause` + conversation | `hold/low` | `输入信号｜暂停｜{source}｜对方要我暂停` |
| `stop` + conversation | `hold/low` | `输入信号｜终止｜{source}｜对方要终止` |
| `pause/stop` + task | `pursue/mid` | `输入信号｜请求｜{source}｜接住具体任务` |
| `pause/stop` + unclear | `None` | — |
| `ack` / `tell` / `unknown` | `None` | — |

这一层不做文本判定、不加分数；`input_contract.py` 内不得出现中文停／别说类词表常量、`import re` 或子串匹配。语义判断只在 `input_sense.py` 的模型提示词里进行。

---

## 判停的优先级（drive.py）

`InputSignal.scope` 放在 dataclass 末尾、默认 unclear，旧位置构造与 act 值兼容，但旧信号未声明作用域时不猜停。模型从整句判断 conversation（停嘴／结束这场）、task（停音乐／动作／具体任务）、unclear（不确定）。ask/request 原语义不变。

非降级、`addressee == "other"` 且 **scope=conversation** 的 `pause` / `stop` 在 `infer_drive` 里前置为 **S1b**：

- 位置：S1（新场未接上）之后，S6／S7／§6／S8–S11 之前——本地「打开话题」「好奇」「回指」这些词形线索一律让位。
- 无同场承诺：`hold/low`，why = `输入信号｜暂停｜{source}｜对方要我暂停`（终止同理）。
- 有同场 `last_commitments`：`guard/mid`，why 仍以 `输入信号｜暂停｜`／`输入信号｜终止｜` 开头，并带那条未兑现的话。语义是「先停，但约不当没说过」，不是把承诺丢掉。
- `ask` / `request` **不前移**，仍留在 S15（S14 之后、MARKS 兜底之前）。原先「请求一律 pursue」的映射不变。
- task 的 pause/stop 在 S15 映射请求，why 不带暂停／终止前缀；同现有请求一样不会越过既有更早信号与 §6。不改 S1–S14 编号或相对顺序。

判停只读 `InputSignal` 的结构字段，不读用户原句；`drive.py` 不新增任何停／别说类词表。

## 仲裁：停 + 约定（arbitrate.py）

- `pause`、`stop` 各有一条 distinct `say_intent`，前缀分别是「对方在叫停：」「对方在收束这场：」，内容写死：先应一声就停住，不问候、不邀请继续、不问「要我做什么」、不开新话头。
- 同场承诺在场且本轮判停时：`commit_hold_with_drive = True`，`say_intent` = 停语义 + 「同场约定还在，说清它没消失」。通用守诺模板不得盖掉这一句停。
- **全局守卫（所有分支之后）**：凡 `drive.why` 以「输入信号｜暂停｜」「输入信号｜终止｜」开头，`say_intent` 一律取停文案，压过 org 冲突、stance 痛苦、filler＋悬问等更早命中的分支。真实 LLM 路径读的就是 `say_intent`，不能只靠 stub 模板停。
- **停优先含 org 冲突**：`dominant` 可为 org，`org_conflicts`／`must_not_pretend` 照记（诚实约束不丢），但 `say_intent` 必须是停，不得被改写成回答「是不是代码」。
- stub 模板与真实路 `say_intent` 同口径：同一结构前缀，两条路径都停；结构断言同时校验 `say_intent` 前缀与 stub 话术，不是只断言 stub。

## 开口：三条模板（articulate.py）

任务请求在真实 say_intent 中只接住这件事，能做说明办法、不能直说；stub 在 org 诚实分支之后、开新话题分支之前读取「输入信号｜请求｜」结构前缀，输出「收到，你要我做的这件事我接住了；我会先确认能怎么处理，做不到的会直说。」不声称已控制音乐，不邀请另开话题。不扫用户原句。对话停的全局优先不变。

stub 开口只按 `drive.why` 的结构前缀与 `say_intent` 的完整口径映射，**不扫用户原句**。判停命中时最先返回，压过话题／好奇／回指／招呼等一切上下文分支：

| 情形 | 台上话术 |
| --- | --- |
| `pause`，无承诺 | 行，先停一下，我不往下说了。 |
| `pause`，有承诺 | 行，先停一下，我不往下说了。同场里说好的那句还在，我不当它没了。 |
| `stop`，无承诺 | 好，就到这儿，我不往下说了。 |
| `stop`，有承诺 | 好，就到这儿，我不往下说了。同场里说好的那句还在，我不当它没了。 |

「有承诺」的判据是 `drive.why` 里带「同场还有没兑现的话」这一结构片段（由 S1b 写入），不是扫原句。guard+停必须先说停、再说约定；不得落「你回头想接着」这类邀请，也不得落到 `_DEFAULT_FALLBACK`。

## 测试口径

- 结构断言：`drive.direction` / `salience`、`drive.why` 前缀、`say_intent` 前缀、`Brief.commit_hold_with_drive`、stub `utterance` 是否等于上表模板。
- 不用「聊／继续／随便」这类字面禁词表去扫台上话；模板相等本身就是结构映射的证明。
- 覆盖：四句 pause／stop（「先停一下」「别说了，停一下」「不要说了」「到此为止吧」）；「不要说了，我不想听为什么」压过好奇 high；「停一下，刚才说到哪了」压过回指 mid；§6 承诺 + 停；「帮我关窗」仍 pursue/mid；「够了，先这样」「算了，不用了」收束话逐字不变。
- 全局守卫覆盖：悬问后「停」（pause）→「对方在叫停：」；悬问后「算了」（stop）→「对方在收束这场：」；「我只能面对这些，别说了」（stop）→ 停，不落「承认必要的痛苦还在」；org 冲突＋停 → 停，且 `org_conflicts`／`must_not_pretend` 仍含「自述是代码」。每条同时断言 stub `utterance` 等于停模板。

本文件取代 `birth/INPUT_SENSE_V1.md` 中 act 枚举与提示词判据部分；`INPUT_SENSE_V1.md` 其余内容不变，本次不改该文件。

## 作废与不做

**作废**（本刀改写）：

- 旧文「不改 articulate／台上话术」——本刀必须改开口，判了停之后台上要真的停住。
- 旧文「不动 S15 优先级位置」——pause／stop 已前移到 S1b；S15 只剩 ask／request 等其余信号。

**不做**：

- 不合 master、不 push、不动工作区未提交改动、不扩关键词表。
- 不新增字面禁词／正则堵嘴；不在 articulate 扫用户原句。
- 不动 S1–S14 的编号与相对顺序；不动 `must_not_pretend`；不碰 DeepSeek 遗留清单。
- 感知降级路径（无 key／超时 → `degraded=True`）仍是旧行为：没有可信信号就不判停。这条是已知限制，记账不藏。
