# -*- coding: utf-8 -*-
"""沙箱：把**被授权的**总纲领条目，只组装进**一个** API 请求。

用户需求（原话）：
    「『读完即弃』不仅是不存盘，还要求：被授权的总纲领条目，只允许组装在
      单次专用的分析 API 请求中，这次请求的完整 Prompt 绝不能残留在
      管理员后续的常规会话上下文或主训练流里。」

────────────────────────────────────────────────────────────────
为什么这件事比看上去容易：**上下文残留在这个项目里没有容器**
────────────────────────────────────────────────────────────────
管理员共 4 个 API 调用点（judge / encounter / judge_issue / ask），
**每一处都是临时构造 `[{system}, {user}]` 两个消息、调完即弃** ——
没有任何"会话历史"被保留。所以"这次 Prompt 残留到后续会话"
不是要防的问题，是它压根没地方存。

真正要堵的只剩三条，都在本文件里：
  ① 不许把总纲领并进 `_inv` / `_claims` 缓存  → 本函数不接收也不碰 Admin
  ② 分析产物不许进任何后续 context            → 只 return，由调用方写报告
  ③ `reader.max_tokens` 只增不减（既有行为）  → 调用前后保存并复原

外加一条前置：**没有查看授权就不发请求**。
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)

ANALYZE_SYSTEM = """你是这个项目的**管理员**，正在做一次**离线的交叉判断**。

这次任务不是给对话打分，是拿更高一级的目标去照当前的现象。

⚠️ **输出必须严格包含以下两部分，缺一不可**（用户明令）：

## 一、偏差诊断
客观说明：当前这条**规律性异常**（引用它的证据与统计数字）与被授权的
**总纲领条目**之间，存在怎样的深层理论／目标冲突。

  · 是**冲突**、**无关**，还是**同向但被误解**？先给结论。
  · 若判为冲突，**必须引用纲领的原话**说明冲突落在哪一句上，不要泛泛而谈。
  · 只依据这次给你的纲领条目判断 —— 不要假装你还看过别的条目。
  · **依据不足就说依据不足**，那是合法答案，而且比编一个强。

## 二、调整建议（药方）
结合上面的诊断，给出**具体的后续处置建议**。要能落地，例如：
  · 建议在 `corpus/` 里补充**哪一类**情境样本（说清是什么情境、为什么缺它）
  · 建议在 `rules/` 里调整**哪一类**判定逻辑（说清改哪条规则、往哪个方向改）
  · 或者明确说「当前不需要调整，只需继续观察」，并说明理由

不要停在"建议加强""需要关注"这种话上。

────────────────────────────────────────────────────────
⚠️ **硬边界**：你的建议**纯属文本分析**。
   你**不具备**任何直接写回 `corpus/` 或 `rules/` 的物理权限 ——
   那不是权限不够，是根本没有那条代码路径。
   建议只供**用户**决策参考；改不改、怎么改，由用户定，由执行者动手。
────────────────────────────────────────────────────────
"""


def analyze_with_charter(aid: str, question: str, *, reader=None,
                         extra_context: str = "") -> dict:
    """只此一次：把被授权的总纲领条目组装进一个 API 请求。

    纲领部分的组装在**函数内部**完成 —— 调用方既不能注入、也不能省略。

    参数
      aid           异常编号。授权严格绑定它（一次一授权）
      question      要它回答的问题
      reader        可选，注入一个 API 读取器（测试用 stub）
      extra_context 可选背景（例如能力清单）。**不得含总纲领正文** ——
                    总纲领只能由本函数自己从 `charter` 取

    返回
      {"ok": bool, "analysis": str, "used": [charter_id, ...]}

    抛出
      PermissionError  没有有效查看授权（**不发任何请求**）
      ValueError       question 为空
    """
    import charter as C                                   # 局部导入，便于测试注入

    # ── ① 门在这里，不在调用方 ──────────────────────────────
    entries = C.readable_for_admin(aid)
    if not entries:
        raise PermissionError(
            "aid=%s 没有有效的查看授权 —— 沙箱拒绝执行，且不会发出任何请求" % aid)
    if not question or not str(question).strip():
        raise ValueError("question 为空")

    # ── ② 只用局部变量组装，不碰 Admin 的任何缓存 ────────────
    block = "\n\n".join(
        "【%s】%s\n%s" % (e.get("id"), e.get("title", ""), e.get("text", ""))
        for e in entries
    )
    used = [e.get("id") for e in entries]
    parts = []
    if extra_context:
        parts.append("【背景】\n%s" % extra_context)
    parts.append("【要判断的异常】\n%s" % question)
    parts.append("【可依据的总纲领（本次专用，仅此一次）】\n%s" % block)
    user = "\n\n".join(parts)

    if reader is None:
        from understand import ApiReader
        reader = ApiReader()

    # ── ③ 现场保存 max_tokens，无论如何都复原 ─────────────────
    saved = getattr(reader, "max_tokens", None)
    txt = ""
    try:
        try:
            d, _ = reader._post(
                [{"role": "system", "content": ANALYZE_SYSTEM},
                 {"role": "user", "content": user}], json_mode=False)
            txt = (((d.get("choices") or [{}])[0].get("message", {}) or {})
                   .get("content") or "").strip()
        except Exception as e:                             # noqa: BLE001
            # 调用失败**不吞**，但要保证下方的复原与留痕照常发生
            if saved is not None:
                reader.max_tokens = saved
            try:
                C.use_view(aid, used)                      # 读过了就要留痕
            except Exception:                              # noqa: BLE001
                pass
            raise RuntimeError("沙箱调用失败：%s" % repr(e)[:120])
    finally:
        if saved is not None:
            reader.max_tokens = saved

    # ── ④ 只记「读了哪几条」，**日志里不出现正文** ──────────────
    C.use_view(aid, used)

    # ── ⑤ 只 return。不写记忆、不写 perception、不进任何缓存 ────
    return {"ok": bool(txt), "analysis": txt, "used": used}
