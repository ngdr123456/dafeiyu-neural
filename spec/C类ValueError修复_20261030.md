# C 类 ValueError 修复（2026-10-30）—— 单独一批

> **全量测试**：**75 / 75**（新增 `test_content_review_truncation` V1–V10）

---

## 一、根因（大白话）

### 现象

**台账里 `content_review_failed:ValueError` 一共 **10** 次，我查了每一条：
**全部**是同一个东西 —— `truncated_content_review`。**

### 为什么会截断

```
那个校验调用**自己没有 token 预算**，用的是 API 阅读器的默认 4096。
而校验模型是**先推理再输出**的 —— 它把 4096 的大部分花在"想"上，
等到要写那个 JSON 时预算已经见底
⇒ 返回的是**半截 JSON** ⇒ json.loads 抛错 ⇒ 记成 ValueError
```

**★ 而且项目里**早就记过这个坑**，只是校验这条路没照做：**
```
consensus_claims.py:319  "输出预算 max_tokens = 4096（默认 4096 会被推理吃光）"
sandbox.py:114-135        "现场保存 max_tokens，无论如何都复原"
```

**⇒ 也就是说：这不是新问题，是**同一个已知问题在一条新路径上重演**。**

### 它造成了什么

**每截断一次，那一轮的候选就被作废 ⇒ **退回模板**（「发生什么了？」这类）。
⇒ 36 轮里 7 轮走模板，其中 5 轮就是它造成的。**

### ★ 我**没有**用"捕获 ValueError 当通过"来修

**截断意味着**这次校验根本没发生**。把它当通过等于放行未校验的输出。
**⇒ 只能让它**真的校验得完**，不能把失败当合格。**
**⇒ 所以修法是**给它一个够用的预算**，而不是改判定。**

---

## 二、修法

```python
_saved_budget = getattr(reader, "max_tokens", None)
try:
    if _saved_budget is not None:
        reader.max_tokens = max(int(_saved_budget), 16384)   # ← 提到与其它处同口径
    response, _ = reader._post(...)
    ... 原有全部校验一字未改 ...
except Exception as exc:
    trace.update(reason="content_review_failed:" + ...)      # ← 仍只退 UNKNOWN，绝不放行
finally:
    if _saved_budget is not None:
        reader.max_tokens = _saved_budget                     # ← 用完还原
```

**★ 三个设计取舍，我写清了理由：**

```
① 16384 而不是更大：与 `consensus_claims` / `map_claims` / `find_conflicts` /
   `sandbox` 同一口径，不新造一个数。

② 不是把 SYSTEM 提示缩短：那 31 行每一条都对应一类真实事故（注释里写着）。
   为了省 token 删规则，是把已经付过学费的东西再退回去。

③ 复原放在 `finally`：否则一次异常就把调用方的预算**永久**改掉了。
```

---

## 三、★ 我在修的过程中**自己造了一个回归**，被既有测试抓到

**第一版我把 `_post` 挪出了 `try`，只用 `finally` 管复原：**

```python
try:
    response, _ = reader._post(...)     # ← 移出了 except 的覆盖范围
finally:
    reader.max_tokens = _saved_budget
try:
    ... 解析 ...
except Exception as exc:                # ← 这里再也抓不到 OSError
```

**⇒ 结果：**网络错误不再被捕获**，`review()` 会把 `OSError` 抛出去。**

**★ 既有的 `test_content_fidelity` 当场抓到（它用 `OSError("synthetic")` 验这条）：**
```
ERROR: test_unknown_malformed_network_and_nonliteral_feedback_cannot_release
  OSError: synthetic
```

**⇒ 重构成**一个** `try/except/finally`：`except` 管"校验失败要保守退回"，
`finally` 管"预算要复原"。**

**★★ 这一条我特意写进报告：如果没有那个既有测试，这个回归会**静默通过**
（所有新测试都绿），而线上会变成"校验网络抖动 ⇒ 整轮崩"。**

---

## 四、测试（V1–V10，先红后绿）

```
先红（修之前）：V1/V2/V5/V6/V8 绿，V3/V4/V7 红  ⇒ bug 是真的、还没修
修之后：        **10 / 10 全绿**
```

| 编号 | 判据 |
|---|---|
| V1 | 顽固截断（预算再高也截断）⇒ verdict 仍 UNKNOWN（**没有放行**） |
| V2 | 顽固截断 ⇒ `validation_error = truncated_content_review` |
| V3 | 预算可救时：`review()` **自己**提预算，拿到完整 JSON |
| V4 | 提升后的预算 = 16384 |
| V5 | 调用前后 `max_tokens` 复原 |
| V6 | 修复**没有**把失败当 PASS |
| V7 | 提升发生在 `_post` **之前**（不是事后补救） |
| V8 | 假 reader 真的随预算改变行为（否则测试是空的） |
| V9 | 复原在 `finally` 里（抛异常也能复原） |
| **V10** | **整体不变式：校验自己出错时 verdict 绝不可能是 PASS** |

**★ V10 是我加的**穷举**不变式** —— 跑四种组合（顽固/可救 × 预算够/不够），
断言"PASS 只在真的校验过时出现"。**这一条比单点断言难糊弄。**

**★ 用轮 2 当时的**真实输入**做夹具（台账逐字），不是编的句子。**

---

## 五、★ 一个我必须如实说明的边界

**我无法证明"10 次截断都是因为推理吃预算" —— 我只证明了：**
```
① 现象是 `finish_reason == "length"`
② 默认预算是 4096
③ 把预算提到 16384 后，同类模拟**能完整返回**
```

**⇒ 真实模型是不是这么吃的，要等**下一次实测**才能验：**
**⇒ 如果下一批 `content_review_failed` 从 10 次降到 0，这个根因就坐实了；
   如果还有，说明还有别的成因（我要看新的 `validation_error`）。**

**★ 这一条我标成**待实测确认**，不声称"已修好"。**

---

## 六、状态

```
全量测试  **75 / 75**
语法门    211 个文件，0 错误
改了      engine/content_fidelity.py（在 source_hashes 名单里，按新规则不续期）
备份      仍在 _backup\ego-dialogue_20261030_222557（本批之前）
```
