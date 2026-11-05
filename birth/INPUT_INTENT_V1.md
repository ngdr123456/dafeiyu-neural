# 输入意图 V1

本刀修复 request 一律映射为 pursue，导致暂停或终止类话语反而继续追的问题。按言语行为的语义类拆分，不按关键词判断。

`InputSignal.act` 枚举及语义：

- `ask`：询问（语义不变）。
- `request`：任务请求，要我具体去做一件事，如去关窗、去查、去写。
- `pause`：要我暂停或缓一缓，可以是停嘴，也可以是停下手上的事。
- `stop`：明确终止，结束这场对话，不要再继续。
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
| `pause` | `hold/low` | `输入信号｜暂停｜{source}｜对方要我暂停` |
| `stop` | `hold/low` | `输入信号｜终止｜{source}｜对方要终止` |
| `ack` / `tell` / `unknown` | `None` | — |

这一层不做文本判定、不加分数；`input_contract.py` 内不得出现中文停／别说类词表常量、`import re` 或子串匹配。语义判断只在 `input_sense.py` 的模型提示词里进行。

本文件取代 `birth/INPUT_SENSE_V1.md` 中 act 枚举与提示词判据部分；`INPUT_SENSE_V1.md` 其余内容不变，本次不改该文件。

不做：不合 master、不 push、不动工作区未提交改动、不扩关键词表、不改 articulate／台上话术、不动 S15 优先级位置（仍在 S14 之后、MARKS 兜底之前）、不碰 DeepSeek 遗留清单。
