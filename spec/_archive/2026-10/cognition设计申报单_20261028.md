# `engine/cognition.py` 设计申报单（2026-10-28）

> **依据**：Gemini 第四封《方向纠正令》第 3 条。
> **状态**：**设计稿，未动代码。**按规则 9，等用户批了再落地。
> **我的判断**：方向对；但他有一处工程判断要改（见第一节），我自己另有三处风险要报（见第四节）。

---

## 一、先修正他的一个工程判断：**不能"切换" schema，只能"并行新增"**

**他说：**

> 「只要我们把这套「L2 结构化原话抽取（字面偏移校验） + L4.5 跨轮认知状态机运算」
> 从"查押金"**切换到**「人的张力结构图谱」，系统就立刻拥有了真正的、且 100% 可本地核对的思考能力」

**⚠️ "切换到"这个动作会破坏已有验收。我核过：**

```python
# engine/relational_memory.py:11
PREDICATES = {"custodian", "contact", "location"}

# tools/trial_relational_memory.py:29-30
for i, (predicate, verb) in enumerate((("custodian", "由%s收着"),
                                       ("contact", "要联系%s"), ("location", "在%s"))):
```

**⇒ `trial_relational_memory.py` 逐条测这三个谓词，还带
`ablation_loses_selected_relation` / `unaffected_object_retained` 两个子判据。**
**⇒ 把 `PREDICATES` 换掉，「关系基础」这道验收门会**整体变红**，而它现在是绿的、
且刚续期过。**

**★ 所以我建议：**

```
relational_memory.py    → **不动**。它是"事实核对"装置（谁收着/联系谁/在哪），
                          继续被 trial_relational_memory 守着。
engine/cognition.py     → **新增**。它有自己的 schema、自己的抽取、自己的验收。
两者共用同一套"字面偏移校验"的实现（`_literal` 的逻辑），但**谓词集互不相交**。
```

**⇒ 这样两边都保得住，而且**正好符合"一个视角两个职位"的分工**：
`relational_memory` 管"事实"，`cognition` 管"张力结构"。**

---

## 二、数据契约：新增什么，不动什么

### 新增（都不碰已有字段）

```python
# engine/cognition.py

CLAIM_KINDS = ("WANT_MUST",      # 他想要／逼自己必须做的
               "COST_FEEL",      # 他实际承受的滋味／代价／身体状态
               "FIXED",          # 他认定已经无法改变／已发生的事
               "ACTION")         # 他实际采取的行动／退缩

@dataclass
class Claim:
    kind: str          # 上四类之一
    text: str          # 逐字片段（raw[start:end]）
    start: int
    end: int
    turn: int          # 来自第几轮
```

**校验（复用 `relational_memory._literal` 的同一套逻辑，不 import 它的谓词）：**

```python
def _literal_claim(item, raw) -> bool:
    return (type(item.get("start")) is int and type(item.get("end")) is int
            and 0 <= item["start"] < item["end"] <= len(raw)
            and isinstance(item.get("text"), str) and 0 < len(item["text"]) <= 200
            and raw[item["start"]:item["end"]] == item["text"]
            and item.get("kind") in CLAIM_KINDS)
```

**⇒ 一个字都不许编：抽出的 `text` 必须**严格等于** `raw[start:end]`。**

### 台账新增一个字段

```
LedgerEntry 新增 `cognition`（可选 dict），记录本轮的 claims + 选中的 Thought。
append-only，不回填历史（历史行该字段为空 ⇒ 分析时按 None 处理）。
```

**★ 这是唯一的结构性改动（台账多一个字段）。`state/ledger.py` 的
`ALLOWED_BEHAVIORS` 不动，`memory_scope` 位置不动。**

---

## 三、五个思考算子（每个都写"本地怎么 100% 确认"）

**共同前提：`Thought` 对象只包含**两条已校验的原话片段** + 一个算子 ID。
它**不生成任何新文字**（除了固定的连接语）。**

```python
@dataclass
class Thought:
    op: str            # 算子 ID
    quotes: list[str]  # 1–2 条**逐字**原话（来自已校验的 Claim.text）
    hint: str          # 一句固定的连接语（模板，不是生成）
```

### 算子 1：`CROSS_TURN_CONTRADICTION`（跨轮言行撞车）

```
触发：本轮有 ACTION 或 COST_FEEL，且历史最近 K 轮（K=6）有 WANT_MUST，
      **且两者的 subject 指向同一对象**（用同一套字面抽取的对象名，逐字比对）
结论：「第 {turn} 轮你说过「{past_want}」，刚才你说自己实际做的是「{action}」。这两句都在。」
本地确认：输出里**同时逐字出现** past_want 与 action 两个片段
```

**★ 我加的约束：**"同一对象"**（他没提）**。没有它，跨轮匹配会把任意两句凑在一起 ——
**这是这个算子最大的假阳性来源。**

### 算子 2：`WANT_VS_COST_GAP`（欲求-代价落差）

```
触发：机制层 phase == "WANT_NO_LIKE"，且本轮或近邻轮同时有 WANT_MUST 与 COST_FEEL
结论：「你抓的是「{want}」，你实际尝到的是「{cost}」。这两样并排放着。」
本地确认：输出里同时逐字出现 want 与 cost
```

### 算子 3：`HABITUATION_LOOP_BREAK`（原地兜圈子）

```
触发：同一情境签名（现有 `pr.signature_key`）连续出现 ≥3 次
结论：「「{repeated_claim}」这句，你已经第 {n} 次说了。」
本地确认：输出里逐字出现 repeated_claim，且含一个**客观计数词**（第…次/第三次/又）
```

**⚠️ 我不采用他原话里的「我们在这个圈子里已经转了三轮了」** ——
那读起来像评价（"你在兜圈子"）。改成**纯事实计数**（"这句你第 3 次说"），
让用户自己去反应。这符合 `FRAME_SYSTEM` 第 2 条（不诊断、不贴标签）。

**⚠️ 他也不该硬编 `novelty <= 0.73`** —— 我查了 `constants.py`，没有 0.73 这个常数。
**⇒ 用现有的 `pr.signature_key` 重复计数，不引入新阈值。**

### 算子 4：`IMMUTABLE_VS_ACTION_SPLIT`（死局与活口）

```
触发：本轮或近邻轮同时有 FIXED 与 ACTION
结论：「「{fixed}」这一半已经定了；「{action}」这一半是你自己做的。」
本地确认：输出里逐字出现 fixed 与 action
```

**★ 注意：已有的 `immutable` 标记走的是阶梯（TURN_IMMUTABLE 模板）。
这个算子与它**不冲突**：标记是"这句话里有不可改变的事"，算子是"把不可改变与他自己做的并列"。
但要防止两者同时输出 ⇒ **算子 4 触发时，阶梯的 TURN_IMMUTABLE 让位。**
这条要写进 `respond.choose()` 的优先级。**

### 算子 5：`CONCRETE_CURIOSITY`（初遇兜底）

```
触发：对话前 2 轮，或前四个算子都不满足
结论：退回现有 `_pick_concrete` / `_pick_anchor` 单点追问
⇒ 这就是**封板那一层的唯一保留用途**（Gemini 说的"放回第 5 级兜底"，我同意）
```

---

## 四、我自己要报的三处风险（他没提）

### 风险 ①：**span 可验，label 不可验** —— 这是同源问题的另一张脸

```
`raw[start:end] == text` 保证：抽出的字确实是用户说的。
但「这段字属于 WANT 还是 COST」是**模型的分类判断**。
⇒ 和 judge 的情况一模一样：**抽取者与生成者是同一个模型，同源。**
```

**⇒ 后果：她可能"想错"（把代价当欲望），然后并排展示两条**真原话**。
**⇒ 这不是编造（引文都是真的），是**误读**。**

**★ 缓解（我提议的）：**

```
① 算子输出永远是**两条原话并排**，不做单一断言
   ⇒ 用户看到两条原话，可以自己说"不是这样" —— 误读是**可纠正的**
② 同一片段若在两遍抽取里被分到不同 kind ⇒ **丢弃**（不猜）
③ 台账里同时记 `independent_semantics_verified: False`（沿用现有字段语义）
```

### 风险 ②：**五个算子一起上，假阳性会堆叠**

```
215 行历史 × 4 类 claim × 5 个算子 ⇒ 组合面很大。
而"跨轮撞车"最容易假阳性（任意两句都能凑）。
```

**★ 缓解：**
```
· 算子 1 必须"同一对象"（见上）
· 算子 3 必须有真实重复签名（不是语义相似）
· **每次只允许一个 Thought 胜出**，顺序：3（兜圈子）> 4（死局）> 1（撞车）> 2（落差）> 5（兜底）
  —— 理由：越具体、越可核对的越优先
· 台账记"哪些算子也触发了但被让位"，便于事后查假阳性
```

### 风险 ③：**它仍然是"结构化观察"，不是"思考"**

**这是我最想说的一句。**

```
他说的"像人一样思考"，本质上需要**决定哪一条观察重要**。
而五个算子是按固定优先级触发的 —— 那仍然是**规则**，不是判断。

⇒ 它比 `_pick_anchor` 强的地方是：**系统现在有了"认知对象"**
   （关于用户冲突结构的命题），而不只是 6 个浮点数 + 1 个名词。
⇒ 但它没有强到"自己决定该想什么"。
```

**★ 我不打算把这一层包装成"思考"。**
**⇒ 建议在 `spec/` 里如实写：这是「理论驱动的结构化观察层」，不是通用推理。**

**★ 检验它有没有用的唯一办法：看它产出的 Thought 有没有让输出变得更像人 ——
而这需要**人**来判（用户没时间）。所以在拿到人的判断之前，我只能测**
（a）Thought 触发率（b）输出是否逐字含两条引文（c）有没有新造事实。**

---

## 五、申报单（要用户批的五处）

| # | 改动 | 文件 | 风险 |
|---|---|---|---|
| **C1** | 新增抽取：4 类 claim，带 `start/end/text`，本地 `raw[start:end]==text` 校验 | `engine/cognition.py`（新）+ 一个抽取 prompt | 低（纯新增） |
| **C2** | 台账新增可选字段 `cognition` | `state/ledger.py` | 中（动台账结构）—— 需确认 append-only 兼容 |
| **C3** | 五个算子 + 优先级 + 让位记录 | `engine/cognition.py`（新） | 中（假阳性，见风险 ②） |
| **C4** | `Thought` 送进 `Frame`（新增一栏"你此刻想到的事"） | `engine/think.py` + `pipeline._build_frame` | 低（同 ① 的接法） |
| **C5** | 输出核对：本地检查输出里**逐字含** Thought 的引文 | `engine/action_observation.py` | 低（扩展已封板的那层，**但会动到封板层** ⇒ 需你确认破例） |

**★ C5 是唯一碰"封板层"的 —— 因为"嘴巴有没有执行这条思考"必须在那里核对。
它只**新增**一个 `actual` 标签（`THOUGHT_EXECUTED`），不改现有分支。**

---

## 六、我建议的落地顺序（最小可测）

```
第 1 步：只做 C1（抽取）+ 一个离线验收
   · 在 215 行历史原话上跑抽取，看 4 类 claim 的命中率与字面校验通过率
   · **不接进管线、不进台账、不影响任何现有测试**
   · 判据：字面校验通过率 100%（有一条不过就是 bug）；
           四类 claim 各自在多少行出现（若某一类 <5% 的行，说明 schema 设计有问题）
第 2 步：C1 通过后，做 C2 + C3（一个算子先上：算子 3，它最难假阳性）
第 3 步：算子 1/2/4，逐个上，每个都带"本地可核对"的验收
第 4 步：C4 + C5
```

**★ 我特意把"五个算子一起上"拆成四步 —— 因为一次上五个，出错时无法归因。**

---

## 七、需要用户裁定

```
① 同不同意"并行新增"而不是"切换 schema"（我改了他这一处）
② 同不同意 C2（台账加字段）
③ 同不同意 C5 破例碰封板层（只新增一个标签）
④ 同不同意先只做第 1 步（抽取 + 离线验收），不接管线
```
