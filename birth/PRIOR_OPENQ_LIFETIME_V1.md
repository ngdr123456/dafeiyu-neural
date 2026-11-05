# PRIOR_OPENQ_LIFETIME_V1

## 出处与缺陷

出处是出生必备第 3 条体验通道。PRIOR_OPENQ_V1 的已知缺陷：跨场「答没答」没有结构化来源时落到字面重叠，误删比漏问重。

## 旧判断实测

直接调用 `answered_open_question`，问题为「我还不确定你是谁。你愿意告诉我，你是谁吗？」：

| 用户的话 | 实际判定 | 说明 |
| --- | --- | --- |
| 我告诉你一件事 | True | 「告诉」重叠，误判为回答 |
| 我还不确定你是谁 | True | 把她的问题原样丢回，仍误判 |
| 我叫Mark | False | 回答了是谁，却漏判 |
| 我是Mark | False | 回答了是谁，却漏判 |
| Mark | False | 回答了是谁，却漏判 |
| 我告诉你，我叫Mark | True | 旧 t4 用的输入；因「告诉」重叠判中，不是理解了回答 |

## 原则与寿命

跨场只认 `structured_openq_answered is True` 才删；没结构一个字不删。不加词表、相似度或编辑距离。

继承来的悬问只活一场：`export_session_trace` 用精确文本过滤仍留在 `prior_session.her_questions` 的条目，用过没用过都一样放掉；本场新问句照常导出。第一性原理：问一次没回应可以再问一遍，第三场还揪着同一句就是粘人。

改 t4：旧断言把字面重叠造成的消账当作正确行为；那就是误删行为，不是退让。

## 测试清单

- A：无结构的「我告诉你一件事」保留 q1。
- B：无结构的「我叫Mark」保留 q1。
- C：显式 `structured_openq_answered=True` 消掉 q1。
- D：第二场重复记录相同 q1 时，导出及第三场 prior 均不含 q1。
- E：第二场产生不同的新问句 q2，第三场 prior 仍含 q2。

## 不做与边界

不动同场路径、used 时机、S1–S14、articulate／must_not；不 push。

过滤是精确文本，只动 `her_questions`；同场 `answered_open_question` 仍可能误判，但只影响一场。stub 的通用追问可能被抽成新问句，本刀不修。
