# 跨场薄记忆（MEMORY_V1）

> 出生必备「薄记忆」从同场扩到跨场的最小持久层。非长期人格、非意识海。

## 问题
`ThinContextStore` 原只在进程内；`/new` 或重开 REPL 后她对 Mark 一无所知。

## 落盘
- 本地 JSON；默认 `~/.dafeiyu/birth_memory.json`
- 环境变量 `BIRTH_MEMORY_PATH` 或 CLI `--memory-path` 可改
- 测试必须传 `tmp_path`，绝不写真实 home
- 场结束／`new_session` 时写入本场：`facts`、`commitments_pending`、`commitments_resolved`、`open_questions`
- 容量：最近 N 场（默认 5）；facts 默认最近 40 条、已结历史与候选各默认最近 20 条（`max_commits`），悬问默认 10 条。未兑现债独立用 `max_pending_commits`（默认 1000），精确去重后全量保留，绝不沿历史容量截尾。
- 未结债超过独立上限时 `append_session` 在写盘前抛 `OverflowError`，`new_session` 尚未清空现场；原 JSON 与当前场都保留，须提高容量或明确核对销账后重试。上限是实际资源取舍，不宣称无限存储；不会自动删除旧债。version 1 JSON 不新增必填字段，旧文件继续读。
- 具体异常为 `PendingCommitmentCapacityError(OverflowError)`；REPL 捕获后留在原场，提示核对销账再 `/new`，不因未捕获异常退出。直接 API 调用者须保留 store 并处理该异常。
- 每次导出合并 prior pending 与同场 pending，因此会话历史淘汰不会淘汰续存的债；prior resolved 与本场 resolved 精确去重合并后再按历史容量截尾。候选在导出、写盘、读盘都只留 target 仍在 pending 的项，销账同步清对应候选。

## 读入（结构字段）
新场开局灌入 `ThinContext.prior_session: PriorSessionTrace`：
- `facts` / `commitments_pending` / `commitments_resolved` / `open_questions` / `ended_at`
- **不**拼进 `say_intent`；**不**把上场未兑现承诺塞进同场 `last_commitments`（§6 guard 仍只看同场）

## Drive 线索
| flag | 含义 |
|------|------|
| `drive_prior_commit_pending` | 上场有未兑现承诺 → 可作线索；filler 时 soft hold；**不强制开口提** |
| `drive_prior_callback_pending` | 用户像在回指上场且 `prior_session` 有痕迹 → pursue（后于 §6） |
| `drive_prior_press_pending` | 用户话压到上场未兑现承诺 → pursue／mid；复用 `Brief.press_commit`；文案取自 `prior.commitments_pending`；**不**并进同场 `last_commitments`（§6 不自动跨场 guard） |

`drive_bypass` 与 §6（同场 `last_commitments`）优先顺序不变。跨场兑现只认用户明示已兑现，按独立认账身份销账；主题重叠或接受开口草稿本身不能销 prior 债，详见 COMMIT_DEBT_IDENTITY_V1。

## 回指与亲历闸
- 跨场回指 pursue **依据结构**（`prior_session.has_trace()`），不是「上次」关键词本身；无痕迹时说「上次」不构成跨场回指
- validate 装经历：`prior_session.facts` 并入来源；有来源的回指／复述不误拦；无痕迹仍按现闸

## CLI
- REPL（`python -m birth` 无参）**默认开**持久；`--no-memory` 关
- 单轮模式**默认关**
- 台下字段名（`prior_session` / `PriorSessionTrace` / `drive_prior_*` / `commitments_pending` 等）不得漏上台（validate `_ENUM_LEAKS` 已补）

## 不做
长期人格层；意识海；CloudAgent；扩用户对话禁词表；改台上话术／听感标准。
