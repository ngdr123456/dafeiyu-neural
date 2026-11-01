# 申报单：`character.py` 双向生长改造（2026-10-29）

> **依据**：Gemini 批复 `deepseek_cognition_训练.md` 第三节第 2 条
> **状态**：**申报，未动手** —— 等他核准规则后再改代码、再跑 36 轮。

---

## 一、他问的两个问题的答案（先回答，再申报）

### ① `Association.derive_from_ledger` 认不认识 `THOUGHT_EXECUTED_STRONG`？

**❌ 不认识。而且它连 `cognition` 都不读。**

```
THOUGHT_EXECUTED_STRONG 出现在 association.py 里：False
cognition 出现在 association.py 里：          False
```

**它现在只看 `learning_action(e)` 给的动作 ID（`MY_KIND` 映射后），
以及**下一轮原话的字数变化**（`his = "更长/更短/…"`）。**

**⇒ 所以"她亮出矛盾 → 对方继不继续深聊"这条因果链，
现在在关联矩阵里**完全不存在**。这是必须补的第一处。**

### ② 它配对时有没有严格检查同 `session_id`？

**✅ 有，而且做得对。**

```python
# engine/association.py:derive_from_ledger
# ★ 下一句只在**同一会话内**才算"他的反应"；跨会话的下一句不是反应。
nxt = rows[i + 1] if (i + 1 < len(rows) and cls._same_session(e, rows[i + 1])) else None
if nxt is None:
    his = "NO_REPLY"
```

**⇒ 这一处不用改。我之前担心的"跨会话错配"在这里已经防住了。**

---

## 二、现有的单向棘轮（把代码贴出来）

```python
# engine/character.py
CONSERVATISM = ["ASK_MUST", "TURN_IMMUTABLE", "JUXTAPOSE", "ASK_DETAIL", "REPLENISH",
                "REFLECT", "ACKNOWLEDGE", "ACKNOWLEDGE_CLOSE", "SILENCE"]

def modulate(self, action, markers=None, last_behavior=None, allowed_rules=None):
    """★★ 三条结构性护栏
    ① **只能往保守方向推，绝不更主动。**
       这一条不是自觉，是**结构**：本函数只沿 CONSERVATISM 列表**向右**走，
       永远不向左。讨好的失败模式必然是"做更能留住对方的事"，
       而那需要向左走 —— 结构上做不到，所以这条路上产生不了讨好。
    ...
    """
    if action not in CONSERVATISM:
        return action, None
    i = CONSERVATISM.index(action)      # ← 起点
    ...                                  # 之后只会 i += 1，永远不会 i -= 1
```

**★ 而极性从哪来：**
```python
def update_state(self, mech):
    self.polarity = polarity_from_mech(mech)     # ← **只看机制快照**
```

**⇒ 所以现在的数学事实是：**
```
经历（关联矩阵）→ 影响 modulate 的**三条保守规则**
但 modulate 只能向右走
⇒ 经历越多 ⇒ 她越保守 ⇒ **越来越小**

而 polarity 完全由机制快照决定，**和"她经历过什么"无关**
⇒ 她**不可能**因为"这次深聊成功了"而变得更敢
```

**★★ 他说的那句话是对的：**跑 36 轮，数学上不可能长出双向偏好。**

---

## 三、★★ 我的申报：对称的双向规则（含护栏）

### 3.1 先定"什么算一次深度遭遇"（100% 本地可观察）

```python
# 第 t 轮：她做了什么
BOLD = (action["actual"] == "THOUGHT_EXECUTED_STRONG") \
    or (cognition.get("op") and action["actual"] == "QUESTION")

# 第 t+1 轮（**同会话**，association 已经保证）：他怎么了
CONFIRMED = (
    nxt.raw_input 里出现了**第 t 轮没有的 claim**            # 涌现新内容
    and (len(nxt.raw) >= len(cur.raw))                        # 没有明显变短
    and not mst_{t+1}.is_closing                              # 没在收尾
)
REBUFFED = (mst_{t+1}.lean 明显下降) or mst_{t+1}.is_closing \
        or (len(nxt.raw) < 0.5 * len(cur.raw))
```

**★ 三个条件的依据：**
```
· "涌现新 claim" —— 这是**唯一的硬证据**，它证明对方**又打开了一层**；
  只靠"字变多了"不够（啰嗦也可能是在敷衍）
· "没明显变短" —— 敷衍、抗拒、收尾的**共同可观察特征是变短**
· "is_closing" —— 机制层已经算出来的收尾信号，不重复造
```

**⚠️ 我不用"模型判断对方是否被触动" —— 那会让这一层变成自证循环。
全部用**字数 + claim 是否新增**，两者都是本地可核对的事实。**

### 3.2 对称规则

```python
# engine/character.py
def modulate(self, action, markers=None, last_behavior=None,
             allowed_rules=None, stance_hint=None, budget=None):
    """新增两个可选参数（不传 = 旧行为，向后兼容）：
       stance_hint —— 本轮"系统本来认为合适"的那个动作（阶梯给的 bid）
       budget      —— 已累积的确认遭遇 / 受挫遭遇计数
    """
    if action not in CONSERVATISM:
        return action, None
    i = CONSERVATISM.index(action)

    # ---- 保留：向右（更保守）—— 现有三条规则，一条不改
    ...

    # ---- ★ 新增：向左（更主动），三道护栏
    if CONFIRMED:                       # 一次确认的深度遭遇
        j = max(0, CONSERVATISM.index(stance_hint))     # 护栏①：最左只能到"系统本来想做的"
        if i > j and budget_allows("bold"):             # 护栏②：预算够
            if CONSERVATISM[i - 1] in E1_ALLOWED or not markers_has_immutable():
                i -= 1                                   # 护栏③：不绕过 E1
```

**★★ 三道护栏的理由（这是申报里最重要的部分）：**

```
护栏① 最左只能到 `stance_hint`（阶梯本来给的动作）
  ⇒ 性格层**不能决定"该做什么"** —— 那是议程层的活（E6 红线）。
    它能做的只是在"系统已经认为合适的那个动作"的**附近**摆动一格。
    这和我一直守的那条线一致：**我们决定该想什么，模型决定想出什么。**

护栏② 预算
  ⇒ 每 3 次确认遭遇才允许向左推一格（常数可调，标 ENG 待标定）。
    否则一次被肯定就永久变敢 —— 那不是"长成性格"，那是"过拟合到一次经历"。

护栏③ E1 在场时不许降级到集合外
  ⇒ 与现有向右路径完全对称：向右也不能落到 E1_ALLOWED 之外。
```

### 3.3 极性也要双向（这是"长出偏好"的地方）

```python
# engine/character.py，新增一项
self.polarity.boldness = clamp(
    0.5 + 0.1 * confirmed_streak - 0.1 * rebuffed_streak, 0.0, 1.0)
```

**⚠️ 我**不建议**动现有的 `patience / liking / wanting / tension` ——
它们由 `polarity_from_mech` 算出，动它们会破坏"极性 = 当下机制状态的投影"这条清晰的分工。**

**⇒ 新增一个 `boldness`（愿不愿意朝外探），只由**经历**累积，不读机制快照。
这样"经历"和"当下"各自有自己的变量，谁的功劳分得清。**

---

## 四、我不确定的三处（要他拍）

### ① 「涌现新 claim」的判据够不够硬？

**我用"第 t+1 轮出现了第 t 轮没有的 claim"作为**唯一硬证据**。
但它有个漏洞：`claim` 的抽取本身有 39–41% 的召回抖动（C1 实测）。
⇒ **同一条内容，这一轮抽到、下一轮没抽到，会被误判成"没涌现"。**

**▶ 我倾向：判据用"第 t+1 轮的 claim **总数**增加"而不是"出现新 claim"，
但那样又会把"他话变长了"当成"他更深了"。这两种取舍我不确定哪个更对。**

### ② 向左推一格会不会破坏现有的讨好防线？

**现有的结构性论证是：**
> 「讨好的失败模式必然是"做更能留住对方的事"（问更多、接更多、更主动），
>   而那需要向左走 —— **结构上做不到**，所以这条路上产生不了讨好。」

**⇒ 一旦允许向左，"结构上做不到"这条论证就**失效了**。
**新的保证必须来自护栏①（最左到 `stance_hint`）+ 护栏②（预算）。
而这两条是**规则**，不是**结构** —— 强度弱一档。**

**▶ 这是这次改造最大的风险，我必须先说清：**
```
现在：讨好**在结构上不可能**（只能向右）
改后：讨好**在规则上被限制**（最左到 stance_hint，且有预算）
⇒ 从"不可能"降级为"被限制"。这是一个真实的削弱。
```

**▶ 我的建议：如果他认为这个削弱不可接受，那就**不做双向**，
改成"只让 `boldness` 这个**读数**双向生长，但**不影响 modulate**" ——
即：她可以"更敢了"这件事被记录、被显示，但不改变动作选择。
那样讨好防线完好，而"长出偏好"至少有一个可见的落点。**

### ③ 36 轮够不够看见双向生长？

**按我上面的预算（每 3 次确认推一格），36 轮里最多推 2–3 格。
而 `CONSERVATISM` 有 9 个位置 ⇒ 位移很小。**

**▶ 所以 36 轮的预期不是"她明显变了"，而是"能看到**方向和趋势**"。
这一点要事先说清，免得跑完发现"几乎没动"就以为改造失败。**

---

## 五、我的建议顺序

```
1. 先只做 3.1（遭遇的判定）+ 3.3（boldness 读数），**不动 modulate**
   ⇒ 零风险：讨好防线完好，但"她经历过什么"第一次被记录下来
   ⇒ 跑 36 轮，看 `confirmed / rebuffed` 的分布是否合理（这是数据问题，不是行为问题）
2. 分布合理之后，再决定要不要动 modulate（3.2）
   ⇒ 那时有真实数据支撑"向左推一格"的频率，而不是拍脑袋
```

**★ 理由：他批准 ① 时说得很清楚 —— 先做能验证的，再做要相信的。
`boldness` 读写是**能验证**的（数字对不对）；`modulate` 向左是**要相信**的（讨好防线的削弱值不值）。**
