# 上场多笔债的身份（COMMIT_DEBT_IDENTITY_V1）

> 底层缺口：动力层的输入是上场未了账，但账上的债没有身份——drive／arbitrate／articulate／pipeline 六处都只取 `prior_session.commitments_pending[0]`。用户点名第二笔时，认账、开口话题、消账全落在最老那笔。

## 问题

上场留下两笔未兑现：A「我答应你周末讲那个故事」、B「我答应你明天聊月亮」。

用户说「月亮的事呢」：

- 判催债是对的（主题命中 B），
- 但 why、stub 话题、say_intent 话题、`pressed_frame`、`resolve_prior_commitment` 都取 `[0]`，于是回答和消账都落在 A。
- 用户明确说「月亮的事已经补了」，被销掉的是 A，B 还在——账错了对象。

## 原则

**债有身份。** 本轮用户话点到哪一笔的主题，就认哪一笔；点不到（只说「你上次答应我的事呢」）才落最老一笔，保持现状。

- 认账只看账上那笔债的文案主题词是否出现在用户话里，不扫用户句式的禁词表。
- 一笔都没命中 → `None`，由调用方回落 `[0]`，不猜。
- 命中多笔时：命中词数多者优先；同数取更长词；再同取更早入账（稳定，便于测试）。

## 接线点（全部走同一个认账函数）

新增 `commit_extract.match_pending_commitment(user_text, prior) -> str | None`，返回账上被点到的那一笔原文。

1. `drive.py` S12a 与兜底 5a：why 用认出的那一笔（认不出才 `[0]`）。指纹前缀「上场承诺｜」不变。
2. `arbitrate.py` 催债分支：`say_intent` 的话题取自认出的那一笔；同时写 `ThoughtBrief.pressed_commitment`。
3. `types.ThoughtBrief` 增字段 `pressed_commitment: str = ""`（工程师通道；不上台）。
4. `articulate.py` stub 催债模板：话题优先读 `brief.pressed_commitment`，没有才回落 `[0]`。
5. `commit_extract.pressed_frame`：`prior_press` 的目标优先读 `brief.pressed_commitment`。
6. `pipeline.py` 上一场消账：`match=` 用 `brief.pressed_commitment`（没有才 `[0]`），只销被点名那一笔，其余留在账上。

`user_presses_prior_pending` 的判定改为先调认账函数：认得出 → True；认不出仍走既有「跨场回指＋催答应／约定壳」分支，行为不变。

**题眼不再取「前三字」伪词。** 账上文案抠主题词时，原实现额外追加 `compact[:3]`（如「你明天」「你周末」），它不是词，会盖住真正在尾部的题眼。本刀一并去掉：认账和开口话题都取账上真实的内容词（「月亮」「故事」）。旧行为「聊你周末」变为「聊故事」，台上句式本身不变，只是话题词落在债的题眼上。

## 不做

- 不改同场 `last_commitments` 的 §6 口径（仍只看同场）。
- 不改「催债不立新债」（COMMIT_IDENTITY_V1）：认出的那笔销账后，台上新应下的约定仍进候选，不回填成 pending。
- 不加禁词、不改台上句式、不做语义模型或向量匹配；认账只用账上主题词。
- 不动输入判停、感知、仲裁主导层规则。

## 验收（单测）

1. 两笔债 A、B，用户点名「月亮」→ `brief.pressed_commitment == B`，drive why 与 stub 话术都是 B，A 未被销。
2. 两笔债 A、B，用户泛指「你上次答应我的事呢」→ 仍落 A（最老一笔），两笔都还在。
3. 两笔债 A、B，用户说「月亮的事已经补了」→ 只销 B，A 仍在账上。
4. 单笔债行为与改前一致。
5. 全量 `tests/test_birth_*.py` 不回归。
