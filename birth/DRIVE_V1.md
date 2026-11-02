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
1. **招呼** → hold / low（现状）。
2. **满足／收束线索**（「够了」「先这样」「挺好的」「不用了」「就这样吧」等轻量输入侧）→ `hold` 或 `direction=None` / low；why=喜欢/满足侧已接住，不必再追。
3. **用户明确打开话题**（「我想聊X」「跟你说件…」「我们谈谈…」）→ `pursue` / mid；why=缺口在外、想要打开这一话头；并把 X 短摘进 why（供仲裁/开口，不进性格库）。
4. **好奇问为什么** → pursue / high（现状）。
5. **回指同场 facts** → pursue / mid（现状，体验通道刀）。**订正**：若同场仍有未兑现 `last_commitments`，且本轮是回指／改口否定类 → **guard** / mid；已有要护优先于普通回指追。无承诺时的纯回指仍 pursue。改口判定主路径读 ThinContext.`commitment_deny_pending` 结构化布尔（pipeline 写入优先 `structured_commit_deny`／Brief.`commit_deny` 族；无结构时 COMMIT_DENY_MARKS 兜底；resolve／clear／new_session／回合末清）；drive 仅无 flag 时兜底扫 `_denies_commitment`（宁缺勿扩词表）。
6. **同场有 last_commitments** → **guard** / mid（已有要护＝守；hold 留给满足收束／空追该停——规格官订正）。
7. **同场悬问未决且本轮 filler** → 动力可 pursue/mid（现状）；仲裁仍负责短暂 meaning 捡一次。好奇挂起主路径读 ThinContext.`curiosity_hang_pending` 结构化布尔（pipeline 写 store flag，resolve／clear／new_session 清）；「待接的话头：」前缀仅在无 flag 时兜底（兼容旧快照），不是禁词闸门、不改台上话术。
8. **空追钝化（薄）**：若最近 facts 里连续 ≥2 轮都是用户在追同一话头、且台上只在用无内容接话模板／用户表达失望（「你怎么老这样」「还是没回答」）→ `hold` / low 或 `guard` / mid；why=重复空追，想要还在但满足没到，先停硬追、改接住。**第一期用轻量线索，勿上强化学习。**
9. **默认陈述** → direction=None / low（现状）；但若 facts 已有明确话题词且本轮是对该话题的延续（非回指套话、含话题词）→ `pursue` / low-mid；why=顺着本场已打开的想要继续，不装没话头。

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

## 不做
继承旧 engine wanting Hz / boldness；禁词表；每句改性格；意识海；CloudAgent；import engine。

## 验收（工程师）
- 「我想聊星空」→ pursue/mid，say_intent/stub 能点到星空（不再「没推力」）。
- 「够了，先这样」→ hold 或 None，不 pursue。
- 回指 / 好奇 / 招呼回归不坏。
- prompt 无 pursue/guard/hold 字面漏出。
- pytest 全绿；本地 commit 勿 push。
