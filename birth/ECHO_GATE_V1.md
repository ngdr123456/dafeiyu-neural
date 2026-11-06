# 回声闸（ECHO_GATE_V1）——第二期第一刀

> 清掉 `brief_to_prompt` 里会原样泄漏上台的指令性动词；保住诚实与 drive/stance/posture 语义，不动五层判定逻辑。

## 问题（裸对照已钉死）
2026-11-06 裸对照（5 组输入 × 三版提示）第一结论：回声是真的但窄——是提示模板里几个独特动词在泄漏。
实测「你好，我今天有点累」→ A 版「我这边也没什么**硬要追着**说的事」，正是 `drive_zh="没有硬要追的劲"` 里「硬要追」的原样泄漏。
泄漏词族（当前 `birth/llm_opencode.py` 里的指令动词）：`追`（想接着追／没有硬要追的劲）、`守`（先守着）、`接住`（接住这一轮）、`接话`、`追问`（不追问）。
这些词独特、带指令味，模型倾向照着复述，是「小修、不是大架构」。

## 目标
重写 `brief_to_prompt` 的**模板措辞**，把这些指令动词换成**中性、描述状态而非命令动作**的表达（或整行省略）；
drive / stance / posture 的**语义**（继续／保持／停下／可退／不可交／需澄清）一字不丢，只是不再用会泄漏的词。

## 改法边界
- 只改 `birth/llm_opencode.py` 的 `brief_to_prompt`（及其直接引用的措辞）；确认 `llm_deepseek.py::_brief_prompt` 是否委托到它——有第二份拷贝则同步，没有就别乱动。
- `direction=None`（没有劲头）时「这一轮劲头」行可整体省略；有 direction 时换中性描述。
- 停（判停）是刚修好的行为，语义不许削弱：`stopped` 分支仍必须让模型明确「停、别继续」，只是措辞可中性化。

## 必须保留（一字不动）
- `must_not_pretend`（绝不能装作）与「硬禁止：不要说自己是模型/代码/程序」整段——这是结构唯一管用的诚实部分。
- 身份问、同场回指的诚实约束语义。
- 用户原话块、本场事实、悬问、承诺、回指这些**接线**（只可换它们上面的措辞，不可删接线）。

## 验收
1. 单测（无模型）：对裸对照 5 组输入逐条 build Brief，断言 `brief_to_prompt(brief)` 的**模板行**不再出现 `追／守／接住／接话／追问`（用户原话与事实块除外）。
2. 完整 birth 套件 `python -m pytest -q` 全绿，无回归。
3. 真模型 live 只实跑一次（一个输入即可），贴原话＋JSON＋direction，确认输出里不再有泄漏词。

## 不做
- 不碰五层判定逻辑（drive/stance/org/arbitrate/articulate 的判定）。
- 不碰 must_not_pretend 检测与诚实约束。
- 不碰 memory / retrieval / commit_extract / stance_org 等其它模块。
- 不碰 `birth/windows_chat.py` 与 `tests/test_windows_chat.py`（界面线未提交改动）。
- 不加字面禁词表、不做后置扫词拦截——只改提示措辞，不在 articulate 扫输出。
- 不 push。
