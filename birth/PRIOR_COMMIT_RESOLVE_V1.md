# PRIOR_COMMIT_RESOLVE_V1

## 出处与实测

出处：出生必备第 3 条，以及 PRIOR_OPENQ_LIFETIME_V1 的同类缺口。

实测 prior「我答应你周末讲那个故事」，用户说「你上次答应我的事呢」，她回「好，我晚点再跟你聊你周末。」（`press_commit` 为真、`commit_deliver_intent` 为假）。旧代码的 pending 变成 `[]`，resolved 增了这条：一句推脱把债记成还了。

## 原则与规则

债和悬问不同，悬问可以放过，债不能自己没。认不出她是否真交付，就只认用户明说「已经了了」；宁可债多留，不许凭空销。

跨场销账保留两个前置：`prior.commitments_pending` 非空且 `drive_prior_press_pending` 为真；证据只用 `user_marks_commitment_done(user_text)`，不再用 `utterance_covers_pending_commitment`，不加词表或相似度。

原 `test_prior_press_fulfill_resolves_pending` 改名为 `test_prior_press_dodge_does_not_resolve_pending`：旧断言把推脱当交付，是误销行为，不是退让。

## G/H/I/J/K/L/M 清单

- G：催问周末的故事，推脱仍保留 prior 债。
- H：只提「月亮」，保留 prior 债。
- I：用户说「你上次答应的事已经补了」，销掉该 prior 债。
- J：推脱或只提主题不销 prior；第二轮同场提取的推脱承诺使 §6 guard 挡住 prior press，prior 债仍在。
- K：未兑现的 prior 债跨第二场带到第三场。
- L：第二场用户明说已补，第三场不再携带该债。
- M：第三场携带 prior 债和第二场新债，prior 在前。

## 边界

仍认不出她是否真交付；`_FULFILL_USER_MARKS` 只是既有小线索，不是语义判断。不给 prior 加 `commit_deliver_intent` 生产逻辑，那是另一刀；同场路径不动；债不会因为一次推脱被销账；跨场携带由导出的 pending 列表保证。推脱句可能被同场 `extract_commitment` 记成新承诺，下一轮 §6 guard 会先于 prior press；本刀只保证 prior 债不被销，不改同场路径。
