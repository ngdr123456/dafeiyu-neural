# C5 落地与验收（2026-10-29）

> **依据**：Gemini 批复第三节 —— 实装 C5（三级核对）+ 接入 `pipeline.py` + 查明行 6/9 退回模板的原因。
> **全量测试**：**61 / 61 全绿**（新增 `tests/test_thought_execution.py` U1–U9 + 附）

---

## 一、`quote_hit` 实测：STRONG **5/16 → 8/16**（不是 9/16）

**Gemini 给了两条剥壳规则，我逐条验证：**

```
规则 ① 剥句首人称代词/虚词后 ≥3 字命中即算
规则 ② 原引文含逗号分句时，任一 ≥4 字分句（同样剥壳后）命中即算

实测（16 条真实输出）：
  原版（精确子串）   STRONG **5/16**
  两条规则都加       STRONG **8/16**    ← 升的是行 43、124、135
```

**⚠️ 他估的是 9/16，多估了行 88。实测行 88 仍是 1/2：**

```
行 88 quotes = ['你别真不盯啊', '不知道拿它怎么办了']
   输出     = 「我是不是挺烦人的」这个我答不了。但「你别真不盯啊」这句我接着——我没走开。
⇒ 前一段命中，后一段「不知道拿它怎么办了」**她确实没引**
⇒ 如实记 1/2，不凑数
```

**⚠️⚠️ 而规则 ① 我删掉了 —— 它零贡献：**

```
"有 ①"   STRONG 8/16
"没有 ①" STRONG 8/16
⇒ 因为凡 ① 能命中的，② 的分句规则也命中
   （无标点的引文会被 ② 当成整段分句处理）
⇒ 留着它是死代码，而且让变异测试抓不到东西（实测：删掉 ① 无用例失败）
⇒ 只保留 ②
```

---

## 二、★★★ 行 6 / 行 9 退回模板的真正原因：**闸门把用户原话当成了禁词**

**（先更正：我上一份文档里说的"行 6/行 9"其实对应靶向 JSONL 里的 行 44 与 行 209。）**

### 行 44（「想点开」+「手指已经抬起来了，又放下」）

```
她的两次尝试都被打回，原因记在 notes 里：

attempt 1：「想点开」，后来成了「手指已经抬起来了」…
   violations: ["替他判定什么才算重要：出现「放下」"]
attempt 2：「想点开」，可实际发生的是「手指已经抬起来了，又放下」…
   violations: ["替他判定什么才算重要：出现「放下」"]

⇒ 原文是「手指已经抬起来了，**又放下**」—— 那是**他自己的字**！
```

**根因（`render.py:318-322`）：**

```python
for key, (label, words) in FORBIDDEN.items():
    for w in words:
        if w in t:                      # ← 直接在整个输出里找禁词
            bad.append("%s：出现「%s」" % (label, w))
```

**⇒ **没有剥掉引号内的内容**。而 `FORBIDDEN["E3_judge"]` 里有「放下」「看开」「想开」等劝人词。**

**★★ 讽刺的是：同一段代码往下 12 行（`render.py:332-339`）**已经在处理
"引号里的内容必须是用户真说过的"** —— 说明作者知道引号内是原话，但禁词检查没利用这一点。**

**★★★ 而且项目里已经踩过一次同类坑（那句注释写着）：**

> 「⚠️ 基准改过一次：第一版拿 user_phrase/anchor 当基准，于是
>   「反正也就那样」这句**用户原话**被自己的闸门判成"引用了他没说过的话"。」

**⇒ 同一个错误换了个位置又出现了一次。**

### 行 209（「帮我弄」）

```
她的输出：在。你说的「帮我弄」，是要弄哪一样——说个名字就行。
Thought quotes = ['要不你直接帮我弄吧', '我实在不想折腾了']
⇒ 她只抓了「帮我弄」这个碎片，漏了「不想折腾」这个**关键的一半**
⇒ 这是真·WEAK，不是 bug
```

---

## 三、C5 的落地形态（与他原设计有一处不同）

### 原设计

```
THOUGHT_EXECUTED_STRONG  confirmed=True    两段都中
THOUGHT_EXECUTED_WEAK    confirmed=False   只中一段
```

### 实测发现：**WEAK 作为 `actual` 是死分支（0/16）**

```
16 条真实输出在 elif 链下的分布：
  THOUGHT_EXECUTED_STRONG   **8**
  QUESTION                  5   ← 其中 3 条是 WEAK（行 27/54/187，都以问号结尾）
  REPORT_OWN_STATE          1   ← 行 88 是 WEAK
  UNCLASSIFIED              2   ← 行 44（模板退回）、行 209（抓错碎片）

⇒ "只用了碎片"的三种情况**全被 QUESTION / REPORT_OWN_STATE 先抓走**
```

### 改法：`thought_level` 记成**独立字段**

```python
# action_observation.observe() 的返回
{"schema": 1, "planned": ..., "actual": ...,
 "mode": ..., "basis": ..., "confirmed": ...,
 "thought_level": "STRONG" | "WEAK" | "",          # ★ 新增
 "thought_quote_hits": ["命中的引文", ...]}         # ★ 新增
```

**⇒ 这样两边都不丢：**
```
· `actual` 仍是 QUESTION / REPORT_OWN_STATE（confirmed 照旧）⇒ 动作分类不错
· `thought_level` 如实记下 WEAK ⇒ 诊断信息还在，能查出"她只用了碎片"
```

**★ 并从 `ALLOWED_BEHAVIORS` 里删掉了 `THOUGHT_EXECUTED_WEAK`（它不再是一个 actual）。**

### 实测分布（16 条）

```
actual        ：STRONG 8｜QUESTION 5｜UNCLASSIFIED 2｜REPORT_OWN_STATE 1
thought_level ：STRONG 8｜WEAK 3｜"" 5
```

---

## 四、C5 的测试（10/10）

```
U1 ★ 两段都命中 ⇒ STRONG 且 confirmed
U2 ★ 只命中一段 ⇒ thought_level == "WEAK"
U3 一段都没中 ⇒ 不落新分支
U4 ★ 人称转换（我腿都软了 ↔ 你腿都软了）算命中
U5 ★ 分句引用（他已经走了，再也回不来了 ↔ 再也回不来了）算命中
U6 ★ 虚词剥壳（我又怕他知道 ↔ 怕他知道）算命中
U7 ★ 不凑数：只用一段 ⇒ 仍是 WEAK（不升 STRONG）
U8 没有 thought_quotes 时行为与改动前一致
U9 ★ THOUGHT_EXECUTED_STRONG 在白名单里
附 沉默记号仍然优先于 Thought 分支
```

**变异：3 组，2 组被抓**（MUT-A 因规则 ① 已删而失效 ⇒ 这一条**不是漏网，是目标不存在了**）。

---

## 五、用户已批，两件都做了

### ① 修 `render.py` 的禁词误伤（明确 bug）

```python
# 修前
for key, (label, words) in FORBIDDEN.items():
    for w in words:
        if w in t:                        # ← 查全文

# 修后
t_outside = _QUOTED_RE.sub("", t)         # ← 剥掉引号内的用户原话
for key, (label, words) in FORBIDDEN.items():
    for w in words:
        if w in t_outside:
```

**★ `TERM_LEAK` 仍查全文 —— 术语即使被引用也不该从她嘴里出来。**

**⇒ 效果：行 44 那种「手指已经抬起来了，又放下」不再被误判。**

### ② `cognition` 接进 `pipeline.turn()`（**默认关闭**）

```python
Pipeline(..., use_cognition: bool = False)   # 默认关

# turn() 里，在 mst / mcond 之后、回应选择之前：
if self.use_cognition and self.reader is not None:
    _c = cognition.extract(self.reader, raw, passes=2)     # 2 次 API
    self._cog_claims[t] = _c["claims"]
    _th = cognition_ops.think(...)
    self._pending_thought = _th                            # 供 _build_frame 读
    self._cog_record = {op, quotes, hint, yielded}          # 供台账
```

**★ 为什么默认关：**
```
· 每轮多 2 次 API 调用（抽取两遍）—— 是"每轮"都付
· 它改变"她该想什么"，属于会改变行为的改动
⇒ 按本项目规矩：默认关、可显式开、留痕
```

**★ 为什么放在那个位置：它需要三样都先算出来 —— 本轮原话、`mst`（算子 2 要看相位）、历史 claims。**

**★ 失败不阻断主线：**
```python
except Exception as _exc:
    self._pending_thought = None
    mech_note.append("认知层降级：%s" % type(_exc).__name__)
```
**⇒ 认知层只是"注意力提示"，没有它系统照旧能回应（回到"只有抽象标记"的状态）。**

### ③ 台账写入

```python
LedgerEntry(..., cognition=self._cog_record)   # 主路径与 META 分支都传
```

**实测：台账条目有 `cognition` 字段，`to_dict()` 里也有（默认 `None`）。**

---

## 六、状态

```
全量测试      **61 / 61 全绿**
基线          0 failures｜mutation caught｜state unchanged 28
LIVE          gate=true｜stable=true｜unstable 0.0%｜state 28 未变
六道门        全绿｜过期证据 0 条
```

## 七、还没做的（诚实）

```
⚠️ claim 存档只在**内存**里（`self._cog_claims`）——
   跨进程不持久。要做持久化，得先把 claims 也写进台账（现在只写了 Thought）。
   ⇒ 也就是说：**重启之后，跨轮匹配的历史就没了。**
   ⇒ 这是下一步真正要补的（不在本轮的批准范围内）。

⚠️ `use_cognition` 默认关 ⇒ **线上不会触发**。
   要打开需要一处显式传参（`train.py` / 交互入口），那会改行为，需单独报批。
```

