# ego-dialogue 第一期旁路模块（煤球规格摘要）

## 目标
在**旁路包**落地「出生必备」最小闭环：感知/对象感 + 动力层 + 体验通道（薄情境可积累）+ 仲裁 → ThoughtBrief + 开口只 articulation。
旧 engine/turn 可并存；**不要**继承 DeepSeek 六层、禁词闸门、boldness、假「已实现」映射。

## 已定原则
- 出生即有脑子；对话抽检非陪练训练结构。
- 三本书＝优先资源库；外补须标明出处。
- 台上：流畅人话。台下：神经表/Brief（工程师通道）。禁止自述「我是代码」。
- 无命运剧本；欲望可含好奇/身体想象；意义/组织最小非空（能回话、不能无依据装经历）。
- 薄情境**提前共享**给动力/意义/自我组织；开口后事实/承诺**回流**薄情境（不做每句改性格；不顶置长期性格记忆）。
- 不另立「意识海」层；冲突/两难在仲裁。OrgConstraint 约束表达粒度，**不是**永久否决动力；主导可以是 drive|meaning|org。

## 工程师通道类型（建议 Python dataclasses / TypedDict，可调）
```
DriveSignal { direction?: 'pursue'|'guard'|'hold'; salience?: 'low'|'mid'|'high'; why: str }
StanceSignal { posture: 'yieldable'|'non_negotiable'|'needs_clarify'; stake: str; why: str }
OrgConstraint { grain: 'simple'|'rule'|'differentiated'; can_name: list[str]; cannot_fake: list[str]; why: str }
ThinContext { session_ok: bool; open_questions: list[str]; last_commitments: list[str]; facts_this_session: list[str] }
ThoughtBrief { dominant: 'drive'|'meaning'|'org'; drive?: DriveSignal; stance: StanceSignal; org: OrgConstraint; context: ThinContext; say_intent: str; must_not_pretend: list[str] }
```

## 第一期实现范围
1. 包名建议 `birth` 或 `brain_v1`（独立旁路，勿大改旧 pipeline）。
2. `ThinContext` 读写：同场积累；显式 new session 才清空；开口后可 `append_fact` / `append_commitment`。
3. 动力层最小：根据用户话 + ThinContext 产出 DriveSignal（可留空 direction）；允许好奇类 why；禁止装饰分数当性格。
4. 最小非空 Stance/Org：默认能回话；must_not_pretend 含「无来源装经历」「自述是代码」。
5. 仲裁最小：冲突时写明一条主导规则 → ThoughtBrief。
6. 开口：函数 `articulate(brief) -> str` 先可 stub（模板拼 say_intent）+ 预留 LLM 钩子；校验对照 Brief，不用禁词表。
7. 一条可跑的 CLI/demo：输入「你好」走完整闭环，打印台上 utterance + 可选 `--debug` 打印台下 Brief。
8. 少量单元测试（pytest）：回流写入、留空动力、must_not_pretend 进 Brief。

## 刻意不做
恢复禁词/boldness；全书细接线；对话自动成长跑批；把 Brief 默认甩进台词。

## 验收
台上听着顺；话跟 Brief 一致；`--debug` 时工程师通道可见信号。
