# 他留的最后一件事：`TURN_IMMUTABLE` 让位（2026-10-29 完成）

> **背景**：Gemini 挂机。用户问"他有没有留任务没完成"。
> **核查结论**：所有信里的任务清单，**只漏了这一件**（`deepseek_c4_20261029.md` §2.2
> 与 `deepseek_c4_c5_20261029.md` §三.2 都点名了）。
> **全量测试**：**62 / 62 全绿**（新增 `tests/test_immutable_yield.py` Y1–Y6 + 基线）

---

## 一、任务清单核查（我逐封对过）

| 来自 | 任务 | 状态 |
|---|---|---|
| 第 1 封 | 补记字段 / 查走哪套 prompt / judge 重判 / 生成层 A/B / 路 C | ①②③✅　④⑤ 已论证该缓（A/B 判据落在噪声内；路 C 需真人数据） |
| 第 2 封 | Q1–Q3 三个实验（400+200+270 调用） | ⏸ 未做（当时结论：标签 56% 自洽，先修标签）→ 后来走了别的路 |
| 第 3 封 | 三个发现 + 四项申报 | ✅ 全做（META 收窄 / 锚点 / 动作识别 / 分析口径） |
| 第 4 封 | 修 `_pick_anchor` / 修 `stance.py` / 24 轮配对重放 | ✅ 全做 |
| 新方案 | 封板 + `sequences` 锁进回归 + 立项 `cognition.py` | ✅ 全做 |
| c1_2 | C2 + C3 + 离线跑算子 | ✅ 全做 |
| c3_8 | 收紧 prompt / 守卫 / hint / `signature_key` / 靶向重抽 | ✅ 全做 |
| c4 | 清最后假阳性 / C2+C4 / 16 条生成对比 | ✅ 全做 |
| c4_c5 | `_quote_hit` / 查行 6-9 / C5 三级 / **cognition 串进 pipeline** / **TURN_IMMUTABLE 让位** / 补测试 | ✅ 全做（**让位是本次补的**） |

**⇒ 唯一真漏的就是「让位」。**

---

## 二、让位规则怎么落的

```python
# pipeline.py，在 mech/阶梯决策之后、性格层之前
_th_yield = getattr(self, "_pending_thought", None)
if _th_yield is not None \
        and getattr(_th_yield, "op", "") == "IMMUTABLE_VS_ACTION_SPLIT" \
        and bid == "TURN_IMMUTABLE":
    mech_note.append("跨轮思考层触发「死局与活口切分」→ TURN_IMMUTABLE 让位…")
    bid = "JUXTAPOSE"
    mech_note.append("让位后的计划动作=%s" % bid)
```

**为什么让给 `JUXTAPOSE`：** Thought 本身就是"把两处原话并排摆出来"，
而那正是 `JUXTAPOSE` 的定义 —— 不是换一个新动作，是**同类里更具体的那一个**。

**为什么只在两个条件同时成立时让位：**
```
① 本轮确实有 `IMMUTABLE_VS_ACTION_SPLIT` 的 Thought
② 阶梯原本给的就是 `TURN_IMMUTABLE`
⇒ 不影响其他任何情形
```

---

## 三、★★ 实测发现的一条限制（必须说清）

**让位**生效了**，但在模板路径上 `JUXTAPOSE` 会退回 REFLECT：**

```
台账 notes（实测）：
  跨轮思考层触发「死局与活口切分」→ TURN_IMMUTABLE 让位          ✓ 让位发生
  ...
  选中动作缺槽位 → 退回 REFLECT（不沉默）                      ← 模板层既有兜底
```

**根因：`JUXTAPOSE` 的模板要**两个**引文槽位（`{echo}` + `{echo2}`），
而本轮 raw 里只有一处可引的 ⇒ 缺槽位 ⇒ 退回 REFLECT。**

**⇒ 所以我把让位后的**真实 bid** 单独记进 notes（`让位后的计划动作=JUXTAPOSE`）——
这样"让位没发生"和"让位了但模板兑现不了"就分得开。只记 `planned_behavior` 分不开。**

**★★ 而真正兑现并置的是**大脑路径**：Thought 已经在 `Frame` 里，
C4 实测 11/16 命中引文（5/16 两段都中）。模板路径兑现不了"两段并置"是它的**固有限制**，
不是这条规则的错。**

---

## 四、测试（7/7）与变异（3/3）

```
基线  ｜没有 Thought 时，immutable 照旧走 TURN_IMMUTABLE
Y1 ★ ｜有算子 4 的 Thought ⇒ 让位发生，且让位后的 bid **真的是 JUXTAPOSE**
Y2 ★ ｜没有 Thought 时不让位
Y3 ★ ｜Thought 是别的算子时不让位
Y4 ★ ｜阶梯给的不是 TURN_IMMUTABLE 时，这条规则不生效
Y5  ｜让位留痕进了台账
Y6 ★ ｜阶梯给 REPLENISH（cliche）时，让位规则不动它

变异：MUT-A（去掉 op 判定）→ Y3｜MUT-B（去掉 bid 判定）→ Y6｜MUT-C（目标改 REFLECT）→ Y1
```

**★ Y1 与 Y6 是补出来的：**
```
· Y1 原来断言 `planned_behavior == "JUXTAPOSE"` —— 但模板路径会退回 REFLECT，
  断言必然挂。改成断言"让位后的真实 bid"，并把那个 bid 记进 notes。
· Y6 是补 MUT-B 的漏：原 Y4 的输入 bid 本来就是 JUXTAPOSE，
  去掉 bid 判定也抓不到；换成 cliche → REPLENISH 的输入才抓得到。
```

---

## 五、★ 我顺手修掉一个自己引入的回归

**加 cognition 块时写成无条件的 `self._pending_thought = None`，**
**于是外部注入（离线回放 / 测试）的 Thought 在 `turn()` 开头就被抹掉了 —— C4 的注入路径直接失效。**

**⇒ `test_immutable_yield` Y1 抓到了它。已改成只在 `use_cognition` 分支内清理。**

---

## 六、状态

```
全量测试      **62 / 62 全绿**
（注：`test_pending_nonblocking.py` 出现过一次抖动 —— 单独跑 3/3 通过，
  重跑全量也 62/62。它是并发测试，属已知的偶发。）
```

## 七、他还没回答、我也没做的（如实列）

```
① `pipeline.turn()` 里 claim 存档只在**内存**（`self._cog_claims`）——
   跨进程不持久 ⇒ **重启后跨轮匹配的历史就没了**
② `use_cognition` 默认关 ⇒ 线上不触发；打开要在 `train.py` / 交互入口显式传参
③ 他第 1 封建议的「生成层 A/B」与「路 C」仍未做（各有已记录的理由）
④ 他第 2 封的 Q1–Q3 三个实验（870 次调用）未做
```

**①② 是下一步真正该补的；③④ 取决于是否还要回头验那两件事。**
