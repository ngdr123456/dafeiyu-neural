# 开口拒收回流薄体验（REJECT_FEEDBACK_V1）

> 工程师通道：LLM／hook 草稿被 validate／`_accept_draft` 拒，或 generate 空／抛错落入 stub 时，把「话没出去」写回同场 `ThinContext` 结构字段。非性格层、非长期人格、非意识海。

## 问题
拒收后只 stub 兜底上台时，薄情境看不到「草稿被闸」——下轮 drive／仲裁无法读结构线索。

## 字段（同场；不拼 `say_intent`；不落盘跨场 JSON）
| 字段 | 含义 |
|------|------|
| `articulate_reject_count` | 同场累加：每次被拒的草稿记 +1（按短标签条数累加） |
| `last_reject_reasons` | 短标签／枚举码列表（`substrate_self`／`lived_bio`／`enum_leak`／`press_commit_shape`／`empty_backend`／`llm_error`…）；容量截断；**不存原文灾难句／异常全文** |
| `articulate_reject_recovered` | **选定策略**：本轮曾拒但最终已出话（含 stub 兜底）→ `True`；**不**清算 `articulate_reject_count`（跨轮累加供 soft hold）。另一选项「接受后清 count」未采用。 |

`new_session`／`/new`／跨场落盘前清场：上述字段归零；`export_session_trace` **不含**拒收痕迹。

## 写入路径
1. `articulate._accept_draft` 拒收时 `_note_reject(短标签)`
2. generate 空／None／抛错且最终落入 stub 前：若尚无 validate 拒收标签，记 `empty_backend`／`llm_error`（不拼异常全文；级联中途空输出但最终 LLM 成功则不记）
3. `pipeline.turn` 在 `articulate` 返回后 `take_reject_feedback()` → `store.record_articulate_rejects` → `mark_articulate_uttered`

## 2026-11-06 实际消费者与边界

出处：总规格「开口只 articulation」及底层结构核对中的催诺形状误拒。`_accept_draft` 仍先走 validate；催债草稿可被既有 extract_commitment 提取则保持兼容，否则必须有明确 pressed_commitment、用账上主题词可核对地触及目标、排除既有守诺口径与约定/推迟形状（复用 _GUARD_COMMIT_UTTER、_COMMIT_SHAPES，不新增词表）才可接受。接受草稿不是兑现证据：prior 只认用户明示已兑现，同场仍有既有交付/候选闸，推迟承诺形状继续进候选不立新债。

validate 实际覆盖空稿、长度、内部标识泄露与若干无来源断言形状；请求与对话停模板用定向测试核对不误拒。本次不扩禁词/正则，不改变一般语义保证边界；can_name 仅为提示约束。主题覆盖与有限守诺形状不等于语义理解，未见过的推脱、反话与引用仍可能通过接受闸；这不会授权销 prior 债。真实模型行为未运行不能声称验收通过，stub/hook 绿灯只证明确定性链路。

## Drive 可选读（S14）
同场 `articulate_reject_count ≥ 2` 且 filler、无 `commitment_deny_pending`、无催答应（`user_presses_commitment`）→ `hold`／`low`，why 指纹 `开口拒收回流｜同场多次`。

- **不**逼台上自述「我被闸了」／系统受限脚本
- `drive_bypass`、§6 同场承诺 guard 优先顺序不变
- 不压后续好奇／开话题 MARKS 兜底

## 台上漏检
`articulate_reject_count`／`last_reject_reasons`／`articulate_reject_recovered`／`articulate_reject`／`reject_count`／`开口拒收回流｜` 进 validate 漏检与 `_ENUM_LEAKS` 对拍。

## 不做
扩用户对话禁词表／regex 堵嘴；改台上话术／听感；扩 `must_not_pretend`；台上自述「我是代码」；性格层／意识海；CloudAgent；拒收痕迹跨场持久化。
