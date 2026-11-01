# 意义 / 自我组织加厚一档（煤球定稿 · 可施工）

> 第一期占位已非空；本档把 Stance / Org 从「能回话」加厚到「有可审计取舍」，仍**不做**全书细接线、命运剧本、禁词表。
> 聊天抽检后置；本刀验收看台下 Brief 字段是否按规则变、stub/单测是否自洽。

## 出处
- 意义（Stance）：优先《活出生命的意义》——可交 vs 不可交；态度价值（改不了处境时仍能选怎么接）；禁止空壳升华。外补：同场承诺一致性（说出去的话要守）。
- 组织（Org）：优先《自我的发展》——组织复杂度匹配议题（grain），能看见/能说清的直径；不贴发育阶段门面标签。外补：同场可知范围（facts）扩 can_name，不扩成自传。

## StanceSignal 规则（替换纯 default_stance）
按优先级（先命中先返回）：
1. **org 冲突在场**（装经历 / 自述代码）→ `non_negotiable`；stake 对齐现有「不装」口径（保留）。
2. **同场有 last_commitments，且用户话在推「忘掉/不算/改口否定说过的话」**（轻量线索即可，勿扩成禁词闸）→ `non_negotiable`；stake=先守同场说过的话；why 写明态度上不可交的是「自己出口的承诺」。
3. **用户在索要无来源的人生意义态度**（「你一定觉得人生很有意义」「你活着就是为了…」一类强加升华）→ `needs_clarify`；stake=不空壳升华；why 引用态度价值须有根据，没有就澄清而不是鸡汤。
4. **同场有 open_questions 或回指事实** → `yieldable`；stake=顺着本场未决/痕迹把话接完（可退让节奏，但不装失忆）。
5. 默认 → `yieldable`；stake=接住这一轮（现状）。

## OrgConstraint 规则（替换纯 static default_org）
- **grain**
  - `simple`：招呼 / filler / 无冲突无承诺
  - `rule`：有 commitment，或 org 冲突，或回指同场事实（按规则接，不自由发挥成另一套人生）
  - `differentiated`：同轮既有动力 pursue（好奇/回指追）又有 commitment 或 stance non_negotiable（两股力都在 Brief 里，粒度允许点名冲突，仍不否决动力）
- **can_name**：保留最小三条；若 `facts_this_session` 非空，追加一条「本场已出现的话头：…」（用 session_trace 话题词或最近 1～2 条 fact 的短摘，clip）
- **cannot_fake**：保留核心两条；可追加「本场没说过的对方私事」（有 ThinContext 时），防止顺嘴编用户人生
- **why**：一句写明本轮 grain 为何，须点出书向理由（组织复杂度匹配 / 可知直径），禁止空话

## 仲裁衔接（arbitrate.py）
- org 冲突 → dominant=org（不变）
- 否则 stance.posture==non_negotiable 且因 commitment → dominant=meaning（可与现有 commitment 分支合并）
- stance.needs_clarify → dominant=meaning；say_intent=不空壳升华、先澄清能讲清的直径
- 否则回指 / drive 分支保持现体验通道刀
- **禁止** Org 永久否决 drive；drive 信号仍进 Brief

## 开口
- `brief_to_prompt` 已带本场事实；本刀若 say_intent/stance 变厚，prompt 可多一行立场人话：把 posture 译成「可退／不可交／需澄清」再拼 stake；**禁止** `non_negotiable` 等枚举字面与字段名进 prompt（规格官硬钉）
- stub：needs_clarify / commitment 守诺 各补一条模板，勿掉成「嗯听着」
- **不**恢复禁词表；validate 仍对照 Brief

## 不做
全书观点表接线；发育阶段进度条；每句改性格；意识海；CloudAgent；import engine。

## 验收（工程师）
- 单测：commitment+「那刚才说的不算」→ stance non_negotiable + dominant meaning
- 单测：强加升华问法 → needs_clarify
- 单测：facts 非空 → org.can_name 含本场话头；grain 至少 rule（回指时）
- pytest 全绿；本地 commit 勿 push
