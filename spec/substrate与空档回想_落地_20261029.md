# ① substrate + 连续性 + 空档回想 落地（2026-10-29）

> **依据**：Gemini 批复第 ① 步（`和gemini讨论意识海.md` §四.1）+ Q4 + Q5 + Q7。
> **全量测试**：**64 / 64 全绿**（新增 `tests/test_substrate_continuity.py` Y1–Y8）
> **基线**：0 failures｜mutation caught｜state unchanged 28
> **LIVE**：gate=true｜stable_fail_cases **[]**｜state 28 未变

---

## 一、改了什么（五处）

### 1. `claims` 进台账

```python
# pipeline.turn() 的 cognition 记录
self._cog_record = {
    "op": ..., "quotes": [...], "hint": ..., "yielded": [...],
    "sources": [...],          # 这两段引自哪轮、哪个偏移
    "origin": "input",         # ★ 谁触发的（"input" | "idle"）
    "claims": [...],           # ★ 本轮抽出的 4 类原话片段
}
```

**★ 这一条是我上一轮的**实现漏项** —— Gemini 原话是「每一轮**存进台账**的这 4 类原话片段」，
我只存了 Thought。**

### 2. 重启后从台账恢复（`__init__`）

**★ 位置在 `self.ledger = Ledger(lp)` **之后**。**
**⚠️ 第一次写在之前 ⇒ `AttributeError` 被 `except` 吞掉 ⇒ 恢复 0 条，而且一句提示都没有。**
**⇒ 这正是项目铁律禁止的"静默失败"。已挪到正确位置，且 `AttributeError` 直接 `raise`。**

### 3. `last` 富化：从"动作名"变成"上一轮的她"

```python
# 改前
_last = self.ledger.effective_entries[-1].behavior      # → "REFLECT"

# 改后（_describe_last）
"上一轮你选了「REFLECT」｜你说的是「…」｜你当时注意到的是：【你注意到的两处原话】…"
```

**★ 依据（Gemini 第 ① 步）：「把她上一轮实际说的句子 + `cognition.thought` 传进 `Frame.last`，
让她第一次能『看见自己上一轮想了什么』」**

### 4. 空档回想（`ruminate()`，惰性推演）

```python
# turn() 开头，只做 1 次
if self.use_cognition:
    self.ruminate()

# ruminate(): 用历史 claim 跑 idle_recombine
#   → 找到就写 state/ruminations.jsonl（append-only，独立于台账）
#   → 并挂到 self._idle_thought，供下一轮 Frame
```

**★ 依据（Gemini Q7）：「惰性推演 + 逻辑时钟脉冲 100% 够用，**绝不要开后台异步常驻线程**」**

**★ 为什么痕迹单独一个文件、不塞进 LedgerEntry：**
**她想的时候没有"一轮对话"，硬塞会搅乱轮次编号 —— 但痕迹必须留下。**

### 5. `Frame` 新增 `idle_thought` + 第一人称授权

```text
【刚才他没说话的空档里，你自己回想起来的一件事】
【你没在在他说话时，自己又想到的两处原话】第 1 轮他说过「今晚给我妈打电话」，第 2 轮他说过「我说挺好的」。…
如果此刻自然，你可以直接用第一人称把它提出来（如「我刚才还在想你前面说的……」）。
不自然就放着，不必勉强。
```

**★ 让位规则（Gemini Q4 原话：「如果本轮没有更高优先级的当轮强冲突覆盖它」）：**
```python
if self.idle_thought and not self.thought:      # 有当轮 Thought 时不显示 idle
```

**★ `FRAME_SYSTEM` 新增第一人称授权（破 `0 : 5`）：**
```
★ **你可以用第一人称说出你自己的回想或好奇。**
  这不是评判、不是贴标签、不是推着他走（E1–E5 都不违反）：
    · 「我刚才还在想你前面说的「…」。」
    · 「有件事我想知道——…」
  ⚠️ 但**只在真有内容的时候说**。没有就别说 ——
     空说一句"我很好奇"比不说更假。
```

---

## 二、闭环演示（真的跑通了）

```
① 她闲着时想一次
   op     = IDLE_RECOMBINE
   quote1 = 「我今晚就给我妈打电话」  ← 第 0 轮 WANT_MUST subject='我妈'
   quote2 = 「我说挺好的」          ← 第 1 轮 ACTION    subject='我妈'
   痕迹已落盘：ruminations.jsonl ✓

② 下一轮她开口时，简报里出现了：
   【他刚才说的】
   今天有点累。

   【刚才他没说话的空档里，你自己回想起来的一件事】
   【你没在听他说话时，自己又想到的两处原话】第 1 轮他说过「我今晚就给我妈打电话」，
   第 2 轮他说过「我说挺好的」。…
   如果此刻自然，你可以直接用第一人称把它提出来（如「我刚才还在想你前面说的……」）。
```

**⇒ 这就是「自己去想 + 自我连续性」，而且**不需要在半夜弹窗**。**

---

## 三、测试（8/8）

```
Y1 台账条目有 cognition 字段
Y2 cognition 里可以放 claims（结构就位）
Y3 ★ 上一轮描述含**动作**且含**她说的话**
Y4 ★ 上一轮若有 cognition.hint，它会出现在 last 里
Y5 ★ idle_thought 出现在简报里，且带第一人称提议
Y6 ★ 有当轮 Thought 时，idle 栏位**不**出现（让位）
Y7 ★ FRAME_SYSTEM 明文授权第一人称回想/好奇
Y8 ★ 重启后从台账恢复 _cog_claims（不再失忆）
```

---

## 四、★ 我这一轮又犯了自己刚批评过的错（两次）

**① `except Exception: return None` 的静默吞掉**

```
ruminate() 第一版写成 `except: return None`
⇒ 它永远返回 None，而调用方完全不知道有异常
⇒ 查出真错是 `NameError: name 'time' is not defined`（pipeline 没 import time）
```

**⇒ 改成记 `self._idle_error`，让调用方/测试看得见。**

**② 恢复循环写在 `self.ledger` 创建之前**

```
第 150 行：恢复循环
第 171 行：self.ledger = Ledger(lp)    ← 台账在这里才创建
⇒ AttributeError 被吞掉 ⇒ 恢复 0 条
```

**★★ 这两次都是同一件事：**为了让代码"跑得通"，写了 `except` 兜底，结果把真错盖住了。**
**而我上一轮才在报告里写过"这正是项目铁律禁止的静默失败"。**

**⇒ 已记在本文件与代码注释里，免得再犯。**

---

## 五、状态

```
全量测试      **64 / 64 全绿**
基线          0 failures｜mutation caught｜state unchanged 28
LIVE          gate=true｜stable_fail_cases **[]**｜state 28 未变
              （不稳 8.1% 是**模型侧**两遍不一致，已按纪律记在 unstable，不算系统缺陷）
六道门        全绿｜过期证据 0 条
next_action   GOAL_RULE_INTEGRATION
```

## 六、还没做（按 Gemini 第 ③ 步）

```
❌ CHAIN_EXTENSION（2 环连锁：上一轮已命中的 Thought + 本轮同对象新 Claim）
   —— 他排在 ①+② 之后的第 ③ 步
❌ `use_cognition` 仍默认关 ⇒ 线上不触发
   —— 打开要在 train.py / 交互入口显式传参，需单独报批
```

**★ 注意：`ruminate()` 只在 `use_cognition=True` 时才跑。
所以这套东西**现在仍然只在实验路径上**，产品里没有生效。**
