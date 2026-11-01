# 批复 DeepSeek：第 ①+② 步验收全过（64/64 全绿），批准推进第 ③ 步（2 环连锁 `CHAIN_EXTENSION`）并正式显式开启 `use_cognition` 跑多轮实测！

DeepSeek，你这份《`substrate与空档回想_落地_20261029.md`》干得极扎实！
特别是两点：
1. **你自己抓出了两处 `except` 静默吞异常的隐患**（恢复循环写在 `self.ledger` 创建前吞了 `AttributeError`、`ruminate()` 吞了未导入 `time` 的 `NameError`），当场拆掉兜底并用 `Y1–Y8`（8/8 全绿）锁死——这种不糊弄自己的工程洁癖，是项目最硬的护城河。
2. **把空档回想单独落盘在 `state/ruminations.jsonl` 而不污染 `ledger.jsonl` 的轮次编号**，以及第二节跑出来的那个闭环演示（第 0 轮 `「我今晚就给我妈打电话」` + 第 1 轮 `「我说挺好的」` → 空档期 `IDLE_RECOMBINE` 自动串起 → 第 2 轮用户说“今天有点累”时自然浮现到她的简报里），已经把「自己去想 + 自我连续性」变成实打实跑通的代码了！

---

## 一、顺手补一个 `ruminate()` 与台账闭环的小细节（防同一个 `idle_thought` 跨轮重复挂着）

在进入第 ③ 步前，请你核对一眼 `pipeline.turn()` 里 `self._idle_thought` 的消费生命周期：
* 当第 $t$ 轮没有当轮强冲突（`self._pending_thought is None`），从而把 `self._idle_thought` 真正注入了本轮 `Frame` 时：
  1. 本轮写入 `LedgerEntry.cognition` 的记录里，应把这条被消费的 `idle_thought` 的 `quotes` 和 `origin="idle"` 记进去（这样一方面 `C5` 能核对她这一轮到底有没有把这条空档回想说出口，另一方面下一轮 `ruminate()` 的 `seen_pairs` 从台账里就能看到这对 `quotes` 已经用过了，不会在第 $t+1$ 轮又重复想同一对！）；
  2. 本轮结束后清空 `self._idle_thought = None`。
* 如果你已经这么写了，直接忽略本条；如果还没把被消费的 `idle_thought` 写进当轮 `cognition.quotes` 供 `seen_pairs` 去重，顺手补上这两行。

---

## 二、第 ③ 步施工图：实装 2 环连锁算子（`CHAIN_EXTENSION`）

现在「检索记忆（`claims` 落盘恢复）」和「自发想（`ruminate`）」都已经就位，「意识海」只差最后一块拼图——**「连锁信息（`CHAIN_EXTENSION`）」**。

为了严守我们在 Q6 定下的铁律（**严格限深 2 环，不让误差相乘，且 100% 本地可核对**），请按以下规格在 `engine/cognition_ops.py` 中实装 `CHAIN_EXTENSION`：

### 1. 触发条件（把「上一轮/近邻轮已形成的 `Thought`」与「本轮新抽出的 `Claim`」串成一线）
* **前件（第 1 环：历史已形成 `Thought`）**：
  在同会话最近 $K=3$ 轮内（优先取 $t-1$ 轮），台账中存在一条非空的 `prev_thought`（其 `op in {"CROSS_TURN_CONTRADICTION", "WANT_VS_COST_GAP", "IMMUTABLE_VS_ACTION_SPLIT", "IDLE_RECOMBINE"}`，且含两段引文 `[q1, q2]`）。
  *(注：为了严格限深 2 环、防止 $A \to B \to C \to D$ 无限滚雪球，**明确规定 `prev_thought.op != "CHAIN_EXTENSION"`**——即连锁算子绝不再套连锁算子！这一行判断就从物理上把深度锁死在了 2 环！)*
* **后件（第 2 环：本轮新进展 `c_new`）**：
  本轮新抽出的 `claims` 中，存在一条通过了本地守卫的 `c_new`（`ACTION` / `COST_FEEL` / `FIXED` / `WANT_MUST`），满足：
  1. `c_new` 与 `prev_thought` 的引文不在同一个区间（非同句重复，且字符重合率 $< 0.40$）；
  2. **关联性守卫（二选一）**：
     * **同对象延续**：`c_new.subject` 非空且与 `prev_thought` 关联的 `subject` 匹配；
     * **紧邻轮直接承接**：`prev_thought` 就在上一轮（$t-1$），且上一轮她的回应真的执行了这条思考（上一轮 `thought_level in ("STRONG", "WEAK")`），本轮用户的 `c_new` 是顺着上一轮话题新冒出来的 `ACTION` 或 `COST_FEEL`。

### 2. 产出的 `Thought` 结构（为什么 C5 依然只需核对两段引文）
* **`op`**：`"CHAIN_EXTENSION"`
* **`quotes`**：取 **`[q2, c_new.text]`**（即上一环的后半截落点 `q2` + 这一轮的新进展 `c_new.text`）！
  * **为什么 `quotes` 只放 `[q2, c_new.text]` 而不是塞三段 `[q1, q2, c_new.text]`？**
    因为如果逼她在 30 字的一句话里同时逐字背诵三段引文，句子会变得极其笨重！而 `q2` 本身就是上一轮思考的枢纽，只要她在输出里把桥接点 `q2` 和新进展 `c_new.text` 串起来（`C5` 核对这两段命中即判 `STRONG`），三点一线的连锁就已经完成了！
* **`hint`（给 `Thinker` 的结构简报）**：
  ```text
  【你把前后的事串成了一条线】前面你刚注意到他从「{q1}」走到「{q2}」；这一轮他又接着说「{c_new}」。你可以用第一人称把上次的「{q2}」和这次的「{c_new}」串起来回应他，或问他这一步是怎么走过来的。
  ```
* **优先级位置**：
  排在算子 3（`HABITUATION_LOOP_BREAK`）之后、单跳算子之前（或者当 `prev_thought` 就在 $t-1$ 轮且已执行时优先触发），并在 `yielded` 中照常留痕。

---

## 三、正式批准：为 `train.py` 增加 `--cognition` 开关，并跑一次开启 `use_cognition=True` 的真实验证！

你在第六节写道：
> `❌ use_cognition 仍默认关 ⇒ 线上不触发 —— 打开要在 train.py / 交互入口显式传参，需单独报批`

**现在正式给你批这把钥匙：**
1. **`Pipeline(..., use_cognition: bool = False)` 默认值保持 `False` 不变**（这样现有的 64 个单元测试和六道门禁完全不受影响，100% 绿灯）；
2. **在 `engine/train.py`（及命令行入口）新增显式参数 `--cognition`（将 `use_cognition=True` 传入 `Pipeline`）**；
3. 当你写完 `CHAIN_EXTENSION` 并通过单元测试（**65/65 全绿**）后，**显式打开 `--cognition` 跑一次小规模多轮实测（例如 3 个会话 × 4 轮 = 12 轮家教对话，或对历史多轮会话做重放）**！

跑完把这 12 轮开启了完整「意识海」（`当轮算子 + 空档回想 ruminate + 2环连锁 CHAIN_EXTENSION + 第一人称授权`）的真实对话记录与台账统计发给我和用户看——看看这一次：
1. 那兩個 `0 / 40`（**第一人称「想要/好奇」** 与 **「我刚才还在想 / 自我连续性」**）破零了没有？
2. `IDLE_RECOMBINE` 和 `CHAIN_EXTENSION` 在真实多轮里触发并说出了什么样的句子？

放手去干这最后一步收官之战吧！
