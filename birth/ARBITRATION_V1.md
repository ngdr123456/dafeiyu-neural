# 三层信号进入仲裁 V1

唯一跨书最小取舍规则：诚实硬闸 > 同场承诺／态度（意义）> 动力方向；组织只收粒度，不单独争主导。来源：可施工规格第 5 层；意义取《活出生命的意义》，组织取《自我的发展》，动力取《贪婪的多巴胺》。同场承诺一致性、悬问不过夜为外补。沿用现有分支顺序，判停优先覆盖表达，诚实冲突仍记在组织主导字段。

## 真实生产与消费

| 层 | 生产者 | 输出 | 消费者 |
| --- | --- | --- | --- |
| 动力 | infer_drive | direction、salience、why | arbitrate 保留信号并转为动力人话；开口层读 Brief.drive 和 say_intent |
| 意义 | default_stance | posture、stake、why、hold_same_field | arbitrate 选择澄清／守诺等分支；开口层消费立场与约束 |
| 组织 | default_org | grain、can_name、cannot_fake、why、conflicts | arbitrate 优先读 conflicts，grain 只约束粒度；开口层读 org_conflicts、边界与 say_intent |

turn 在三层产出后把原对象交给 arbitrate，输出 ThoughtBrief，再交 articulate。brief_to_prompt（DeepSeek 亦共用）消费 say_intent、立场、动力人话、组织边界、实际焦点与原话；CLI debug 单独消费取舍理由。

## 新字段

- OrgConstraint.conflicts：组织层本轮已经识别出的不能假装命中项。非空时仲裁不重扫原话；空时兼容旧构造，才调用既有 detect_org_conflict。不扩词表。
- ThoughtBrief.dominant_why：谁压过谁、牺牲什么以及出处。只进 debug，不进开口 prompt。理论漏支写“仲裁未写明取舍（工程师需修复）”。
- ThoughtBrief.focus：本轮要回应的实际内容短摘，不作为主导或销账的唯一闸。
- ThoughtBrief.focus_source：本轮理解／本轮原话／同场悬问／同场承诺／上场承诺／同场事实／无实质内容。

默认焦点依次取：可信理解话题、非 filler 原话、第一条同场悬问、第一条同场承诺话题、第一条上场承诺话题、剩余原话、空。原话／痕迹摘录最多 60 字；理解沿用可信话题契约。承诺话题提取不到则取原句。守同场承诺、认账或交付分支覆盖为相应同场承诺。同场多笔时优先取理解／原话点名的 `recognized_same`，识别不出才回落第一条。上场催兑现覆盖为 pressed_commitment 话题；同场催答应覆盖为事实话题或“这事”。不因此改原有 say_intent。

## 组织不永久否决动力

- `dominant=org` 只在诚实硬闸命中时出现。
- `Brief.drive` 仍在，真实生产路径 `why` 非空；`dominant_why` 明说「动力仍在 Brief，不被否决」。
- 组织分支的 `say_intent` 先保留诚实口径，再带实际焦点；**不追加 `_drive_say_intent` 人话**，因为 `MEANING_ORG_V1` 规定 org 冲突不双写，且既有测试要求如此。

判停沿用 INPUT_INTENT_V1 与规格硬闸3：say_intent 先停住，组织冲突、dominant 与同场约定保留既有语义。

## 失败与边界

缺失 drive 归一为 why="动力层未给出信号" 的 DriveSignal；缺失 stance／org 用默认构造。无可信 understanding 时焦点回落原话；org.conflicts 为空时保留旧检测兜底。无焦点时 focus_source="无实质内容"，prompt 不打印空焦点行。旧 Brief 新字段默认空，debug 不打印空理由。

本刀测试验证生产到仲裁、Brief、prompt/debug 的接线，不证明真实模型会遵守提示，也不证明焦点理解准确。stub 仍按既有结构选择模板，不能把模板通过当成实际内容回答质量通过。

不做第三刀开口校验重构、体验回流、性格成长、全书接线、禁词表或句式补丁。
