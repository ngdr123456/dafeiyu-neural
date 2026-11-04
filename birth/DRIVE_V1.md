# 动力层加厚一档（煤球定稿 · 可施工）

> 在现有 `infer_drive`（招呼 hold / filler 留空 / 好奇 pursue / 回指 pursue / 承诺 guard）之上加厚，对齐《贪婪的多巴胺》：**想要 ≠ 喜欢／满足**；预期与落空会改推力。仍禁止装饰分数当性格；不上台播报追守停。

## 出处
- 优先《贪婪的多巴胺》：想要（seeking）推动追逐；喜欢／满足是另一路；预期落空会难受、重复空追会钝化。
- 外补：同场 ThinContext 作为「预期是否被接住」的薄证据（非长期性格）。

## 槽位不变
`DriveSignal { direction?: pursue|guard|hold; salience?: low|mid|high; why: str }`
- `direction=None` 仍合法（没推力）。
- **禁止** 新增 0～1 分数、Hz、wanting 数值门面。

## 规则优先级（先命中先返回；org 身份冲突不在动力层拦截，信号仍可产出）
1. **招呼** → hold / low。主路径读 ThinContext.`drive_greet_pending`（pipeline 写；上游 `structured_drive_greet` 或无结构时 GREETINGS 兜底写入）；GREETINGS 仅无 flag 时 drive 内兜底（不扩词表）。
2. **满足／收束线索** → `hold` / low；why=喜欢/满足侧已接住，不必再追。主路径读 ThinContext.`drive_hold_pending`（pipeline 写；上游 `structured_drive_hold` 或无结构时 SATISFIED_MARKS 兜底写入）；SATISFIED_MARKS 仅无 flag 时 drive 内兜底（不扩词表）。

   悬问被用户回答时另置本轮 `drive_openq_satisfied_pending`，无同场承诺则 hold/low，why「悬问被接住|喜欢/满足侧到了，不必再追」。同场有 `last_commitments` 则只消解悬问、保持 guard；此信号不抢 org、身份及意义路径。结构化输入与薄兜底的边界见 `OPENQ_FLOW_V1.md`；这只是 wanting 与 liking 的薄区分，不推断主观体验。
3. **用户明确打开话题**（「我想聊X」「跟你说件…」「我们谈谈…」）→ `pursue` / mid；why=缺口在外、想要打开这一话头；并把 X 短摘进 why（供仲裁/开口，不进性格库）。主路径读 ThinContext.`drive_open_topic_pending`（pipeline 写；上游 `structured_drive_open_topic` 或无结构时 OPEN_TOPIC_PREFIXES 兜底写入）；OPEN_TOPIC_PREFIXES 仅无 flag 时 drive 内兜底（不扩词表）。
4. **好奇问为什么** → pursue / high。主路径读 ThinContext.`drive_curiosity_pending`（pipeline 写；上游 `structured_drive_curiosity` 或无结构时 CURIOSITY_MARKS 兜底写入）；CURIOSITY_MARKS 仅无 flag 时 drive 内兜底（不扩词表）。与同场 `curiosity_hang_pending`（S3 挂起）不同。
5. **回指同场 facts** → pursue / mid（现状，体验通道刀）。主路径读 ThinContext.`drive_callback_pending`（pipeline 写；上游 `structured_drive_callback` 或无结构时 `is_session_backref`／BACKREF_MARKS 兜底写入）；stub 回指亦先读该 flag；why「回指同场｜本场已有痕迹接」+ facts／say_intent 仅无 flag 时兜底（不扩词表）。**须后于 §6**：同场 `last_commitments` 非空时不得以回指 pursue 压过 guard；写入侧有承诺时不置 callback flag。**订正**：若同场仍有未兑现 `last_commitments`，且本轮是回指／改口否定类 → **guard** / mid；已有要护优先于普通回指追。无承诺时的纯回指仍 pursue。改口判定主路径读 ThinContext.`commitment_deny_pending` 结构化布尔（pipeline 写入前移 `structured_commit_deny`／early stance 守诺结构（`structured_deny_from_stance`）；真无结构时 COMMIT_DENY_MARKS 兜底；resolve／clear／new_session／回合末清）；drive 仅无 flag 时兜底扫 `_denies_commitment`（宁缺勿扩词表）。
6. **同场有 last_commitments** → **guard** / mid（已有要护＝守；hold 留给满足收束／空追该停——规格官订正）。

关系性等待与话题悬问分开：开口确实在问对方的看法时，`structured_want_seen_hang=True`（或极薄开口指纹）置 `want_seen_pending`；不写话题悬问。`structured_want_seen=False` 表示仍未接住，filler 也可触发 pursue/mid，why「想被看见｜还在等对方回应」；`structured_want_seen=True` 或 `structured_want_seen_answered=True` 表示已接住，清等待并 hold/low，why「被看见了｜接住这份回应，先停在这里」。answered 显式值优先，False 否决口语兜底。无结构时只识别「我听到你／我理解你」且排除 filler 和问句，宁可漏判。setter 清除及新场清除等待；本轮满足信号回合末清除。§6 承诺 guard 优先，org、身份及意义仲裁仍优先；可与话题悬问共存，互不消解。

开口回流采用方案 A：本轮置关系性等待，或 drive why 为「想被看见｜」时，跳过台词的 `extract_open_question`，防止默认或想被看见的模板误写话题悬问；真实 `openq_curiosity_hang` 分支仍优先写入话题。模板话术不变。
7. **同场悬问未决且本轮 filler** → 动力可 pursue/mid（现状）；仲裁仍负责短暂 meaning 捡一次。好奇挂起主路径读 ThinContext.`curiosity_hang_pending` 结构化布尔（pipeline 写 store flag＋挂 openq clip，不强制「待接的话头：」前缀；resolve／clear／new_session 清）；「待接的话头：」前缀仅在无 flag 时兜底（兼容旧快照），不是禁词闸门、不改台上话术。
8. **空追钝化（薄）**：若最近 facts 里连续 ≥2 轮都是用户在追同一话头、且台上只在用无内容接话模板／用户表达失望（「你怎么老这样」「还是没回答」）→ `hold` / low 或 `guard` / mid；why=重复空追，想要还在但满足没到，先停硬追、改接住。失望主路径读 ThinContext.`drive_disappoint_pending`（pipeline 写；上游 `structured_drive_disappoint` 或无结构时 DISAPPOINT_MARKS 兜底写入）→ guard/mid；空台钝化主路径读 ThinContext.`drive_empty_stage_pending`（pipeline 写；上游 `structured_drive_empty_stage` 或无结构时 _EMPTY_STAGE_MARKS／近两轮空台判定兜底）→ hold/low。DISAPPOINT_MARKS／_EMPTY_STAGE_MARKS 仅无 flag 时 drive 内兜底（不扩词表）。**须后于 §6**：同场 `last_commitments` 非空时不得以空追／失望压过 guard；写入侧有承诺时不置 S8 flag。**第一期用轻量线索，勿上强化学习。**
9. **默认陈述** → direction=None / low（现状）；但若 facts 已有明确话题词且本轮是对该话题的延续（非回指套话、含话题词）→ `pursue` / mid；why=顺着本场已打开的想要继续，不装没话头。主路径读 ThinContext.`drive_topic_continue_pending`（pipeline 写；上游 `structured_drive_topic_continue` 或无结构时话题词扫 facts 兜底写入）；话题词扫 facts 仅无 flag 时 drive 内兜底（不扩词表）。**须后于 §6**：同场 `last_commitments` 非空时不得以话题延续 pursue 压过 guard；写入侧有承诺时不置 S10 flag。

## 与意义／组织
- 动力不加「人生意义」；空壳升华仍归 Stance needs_clarify。
- Org 冲突时动力信号**仍写入 Brief**，仲裁 dominant=org；动力不装死。
- guard：本档主要用于「已有要护」（承诺）；空追该停优先 hold（可退到 guard 仅当对方在硬推越界）。不与 org 永久否决混用。

## 开口／仲裁
- `_drive_say_intent` 补：
  - 打开话题 pursue → 「接住对方新打开的话头，可以顺着问一句，不抢着下结论」
  - 满足 hold → 「对方示意够了或先收束，稳住、不继续加码追」
  - 空追 hold/guard → 「这一轮先停硬追，老实接住对方的不满或缺口，不装已经答完」
- `brief_to_prompt`：可选一行「这一轮劲头：…」**必须人话**（想接着追／先守着／先停下），禁止 pursue 等枚举字面（对齐规格硬钉习惯）。
- stub：打开话题时点到 X；满足/收束时不继续追问模板。

## 工程师旁路（非出生默认）
`BIRTH_DRIVE_BYPASS`／`BIRTH_DRIVE_NEUTRAL`（1/true/yes/on）、`turn(..., drive_bypass=True)` 或 `ThinContext.drive_bypass` 可强制动力层固定 `hold`／low（why「工程师旁路」），用于拔掉动力接线看下游；默认关，出生路径零行为变化；旁路非听感验收。

## 上场未兑现被催（S12a；MEMORY）
用户话压到 `prior_session.commitments_pending`（主题 token 重叠，或跨场回指＋既有催答应／约定壳）→ `drive_prior_press_pending` → pursue／mid；why 指纹「上场承诺｜用户催兑现（…）」。须后于 §6；**不**把 prior pending 并进 `last_commitments`。arbitrate 复用 `press_commit`，stub 话题取自 prior pending。详见 `MEMORY_V1.md`／`COMMIT_FLOW_V1.md`。

## 开口拒收回流 soft hold（S14；可选读）
同场 `ThinContext.articulate_reject_count ≥ 2` 且本轮 filler、无 `commitment_deny_pending`、无催答应 → `hold`／low；why 结构指纹「开口拒收回流｜同场多次」。详见 `REJECT_FEEDBACK_V1.md`。不逼台上自述系统受限；§6／drive_bypass 优先；不压后续好奇／开话题 MARKS 兜底。

## 不做
继承旧 engine wanting Hz / boldness；禁词表；每句改性格；意识海；CloudAgent；import engine。

## 验收（工程师）
- 「我想聊星空」→ pursue/mid，say_intent/stub 能点到星空（不再「没推力」）。
- 「够了，先这样」→ hold 或 None，不 pursue。
- 回指 / 好奇 / 招呼回归不坏。
- prompt 无 pursue/guard/hold 字面漏出。
- pytest 全绿；本地 commit 勿 push。
