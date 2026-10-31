# -*- coding: utf-8 -*-
"""并集映射：把每条观点对到系统上，产出「已实现／未实现／明确不实现」。

它在整个闭环里的位置
────────────────────────────────────────────────────────────
    观点总表（书里说了什么）  ×  系统能力清单（系统做了什么）
                    ↓  本模块
    每条观点的归宿  +  未实现清单（= 下一步要补的东西）

用户要的「并集完整」在这里落地：**不许有"没提到"**。
每条观点必须落进三个状态之一：
    已实现    —— 且能指出**对应哪个单元**（对应不上就是没实现）
    未实现    —— 这是要补的清单，最有用的一栏
    明确不实现 —— 必须写理由。**理由写不出来，它就该是"未实现"。**

一个必须守住的判断（第一片数据就撞上了）
    211 条里 167 条 `operational=否` —— 因为《活出生命的意义》第一部分是
    **作者在集中营的亲身经历叙述**，不是可实现的心理主张。
    用户的满分标准是「参照数据对**心理学和生物学的抽象分析**」，
    所以经历叙述**不该硬塞进系统，但也不许悄悄丢掉**（丢了并集就漏项）。
    处理办法只有一个：标「明确不实现」并写明它是"临床观察的来源"而非"待实现的判据"。
    ⚠️ 这条判断很容易被滥用成"实现不了的就说不实现" —— 所以 `why_not` 必须
       **指向这条观点在系统里的真实用途**（比如"它是 ASK_DETAIL 的临床依据"），
       写不出这种用途的，一律退回「未实现」。

⚠️ 谁在判
    判"实现了吗"的是模型 —— 它只是**提出对应关系**，不是最终事实。
    所以每条映射都要保留 `mapped_by` 与 `mapped_at`，并且**允许人推翻**。
    这不是形式主义：将来发现某条映射是错的，要能查出它是哪一批、什么时候判的。
"""
from __future__ import annotations

import io
import http.client
import json
import urllib.error
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
# 打包成 exe 后 `__file__` 指向解包出的临时目录 —— 于是 rules/corpus 找不到，
# 而且**台账会写进临时目录、退出就丢**。所以允许用 EGO_ROOT 指定项目根，
# 由启动器（exe）在导入任何引擎模块之前设置。
# 不设 EGO_ROOT 时行为与从前完全一致（源码运行时就是这个分支）。
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)
for _p in (_ROOT, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

MAP_SYSTEM = """你在做一件机械的对应工作：判断书里的某条观点，**现有的系统有没有实现它**。

给你两样东西：
  【系统有什么】每一行是一个已实现的单元：id ｜ 它做什么 ｜ 依据
  【待判的观点】每条有 id、主张、原文摘句

对每一条，你只能说三种结论之一：

  A. 已实现 —— 并且**必须指出对应哪个单元 id**。
     判据要严：单元与观点必须是**同一件事**。
     "沾边""有点像""精神上一致"都不算。指不出具体 id 就不算已实现。
  B. 未实现 —— 系统里没有对应的东西。**这是最有用的结论，不要怕给。**
  C. 明确不实现 —— 它压根不是"该被系统实现的东西"。
     ⚠️ 用这一条必须写明 `why_not`，而且要指向**它在系统里的真实用途**
        （例：它是某条规则在临床上的来源／它是一个历史事实，不产生任何判据）。
        写不出这种用途的，**退回 B（未实现）**。
     ⚠️ 不许把"实现起来难"当成 C。难但该做的，是 B。

只输出 JSON 数组，每项：
{"id":"M-001","status":"已实现|未实现|明确不实现","maps_to":["单元id"],"why_not":"","note":"一句话理由"}

────────────────────────────────────────────────────────
【关于清单第 4 列「运行状态」】
────────────────────────────────────────────────────────
清单里**部分**单元后面还有一列状态，例如：

    dev:PERCEPTION_GATE ｜ 按系统自己的发展水平过滤标记… ｜ [E] E-900… ｜ 已建未启用

这一列由**代码**从单元表带出，**不是你生成的**，含义是：

    生效中     —— 真实训练里跑得到，且影响行为
    已建未启用 —— 代码写了，但真实训练里不会执行（开关没开）
    仅落账     —— 每轮算出来并落进台账，但不影响任何决定
    （没有这一列 = 原 96 个单元，一直生效中）

⚠️ **这一列不参与你的匹配判断。**
   你只判一件事：**这条观点与这个单元是不是同一件事。**
   不要因为某个单元标着「已建未启用」就把它判成未实现，也不要因为它
   标着「生效中」就放宽标准。**是否启用是工程接线问题，不是实现问题。**
   判「已实现」的唯一要求仍然是：指得出具体单元 id，且是同一件事。

⚠️ **JSON 字符串里绝对不要出现 ASCII 双引号（"）**。
   要引用别人的话或强调某个词，请用中文引号「」。理由：
   你这个错误我已经实测撞到过 —— 一个 note 写成
   `"note":"系统中没有"意义构成命运"这一层内容。"` 就会让整批 JSON 解析失败、
   8 条结果全部丢掉。**改用「」即可，句意不受任何影响。**

不要输出别的字。"""


def inventory_text(items: list[dict] | None = None) -> str:
    if items is None:
        import system_map as S
        items = S.collect()
    lines = []
    # ⚠️ 第 4 列（运行状态）**只在单元带 status 时才输出**。
    #    原 96 个单元没有 `status` 键 → 它们的行**一个字节都不变**。
    #    这是用户明令：「原 96 个单元的输出必须逐字不变」——
    #    T19 重判要拿它当对照基准，格式一动对照就废了。
    #    状态由**代码**从单元表带出（见 system_map.py 的 `_DEV_UNITS`），
    #    **不是模型生成的**；且**不参与匹配判断**（见 MAP_SYSTEM 的说明）。
    for x in items:
        # ★ 方案 (A)（用户裁定，2026-10-02）：**带 status 键的新单元放开 52 字截断**，
        #   依据列**完整输出**。
        #
        #   缘由：`dev:SELF_RULES` 的依据列是 200 字，绑了 5 条 [E] 原文
        #   （E-049／E-499／E-364／E-837／E-1623），却被截到 52 字 ——
        #   **后面 4 条出处模型根本看不见**，匹配时等于少了一大半证据。
        #   用户原话：「必须在跑 E 之前改好……确保模型在评估 E 时能完整看到
        #   SELF_RULES 绑定的 E-049 / E-499 / E-364 / E-837 / E-1623 完整出处。」
        #
        #   ⚠️ 原 96 个单元**没有 status 键** → 走老分支、**逐字不变**
        #      （用户明令维持 SHA 一致）。
        st = x.get("status")
        if st:
            line = "%s ｜ %s ｜ %s ｜ %s" % (x["id"], (x["what"] or "")[:44],
                                            (x["basis"] or ""), st)
        else:
            line = "%s ｜ %s ｜ %s" % (x["id"], (x["what"] or "")[:44],
                                      (x["basis"] or "")[:52])
        lines.append(line)
    return "\n".join(lines)


def _repair(txt: str):
    """试着修**模型在 JSON 字符串里塞 ASCII 双引号**造成的解析失败。

    实测原文（批次 70）：
        "note":"系统中没有"意义构成命运、命运独特"这一层内容。"
    这里 `"意义构成命运、命运独特"` 的双引号没转义，整批 8 条全丢。

    修法：对容易出问题的几个键，把值里的裸双引号转义。做得很保守 ——
    只在**确实解析失败**之后才用，且失败就返回 None（不猜）。
    ⚠️ 这跟提示词里那句「不要用 ASCII 双引号，请用「」」是两道防线，
       不是一道：提示词降低概率，这道保住已经花掉的 API 成本。
    """
    import re as _re
    if not txt:
        return None
    fixed = txt
    for key in ("why_not", "note", "map_note", "claim"):
        pat = _re.compile(r'("%s"\s*:\s*")(.*?)("(?=\s*[,}\]]))' % key, _re.S)
        def _esc(m):
            inner = m.group(2).replace('\\"', '"').replace('"', '\\"')
            return m.group(1) + inner + '"'
        try:
            fixed = pat.sub(_esc, fixed)
        except Exception:                          # noqa: BLE001
            pass
    try:
        return json.loads(fixed[fixed.find("["):] if "[" in fixed else fixed)
    except Exception:                              # noqa: BLE001
        return None


# ── 网络异常分类（用户裁定：只有这两类触发熔断）
#
# ⚠️ 判据按**异常类型**，不按错误字符串里有不有"ssl"字样 ——
#    按字面搜词会同时漏掉真网络错、误伤别的错（这个坑我在别处踩过）。
_NET_ERRORS = (urllib.error.URLError, http.client.IncompleteRead,
               ConnectionError, TimeoutError)


def _is_net_error(e: BaseException) -> bool:
    """是不是网络异常。`ssl.SSLError` 是 `OSError` 的子类，`URLError` 常把它包在里面。"""
    if isinstance(e, _NET_ERRORS):
        return True
    cause = getattr(e, "reason", None) or getattr(e, "__cause__", None)
    for x in (cause, e):
        if isinstance(x, _NET_ERRORS):
            return True
        if isinstance(x, OSError) and "ssl" in type(x).__module__.lower():
            return True
    return False


NET_FAIL_LIMIT = 5      # 连续几批网络异常就熔断（用户裁定）


class Mapper:
    def __init__(self, reader=None):
        if reader is None:
            from understand import ApiReader
            reader = ApiReader()
        self.reader = reader
        self.calls = 0
        self.errors: list[str] = []
        # ── 熔断计数（用户裁定，2026-10-02）
        #
        # 缘由：批 31 起网络挂掉（SSL EOF），脚本又硬撞了 46 批 × 3 次 =
        #      138 次无效请求才跑完。**没有熔断，一次网络抖动就白烧几十批。**
        #
        # 用户裁定的范围（严格照办）：
        #   · 连续 **5 批**出现网络异常（URLError、IncompleteRead）→ 停止并给出提示
        #   · **不做自动重试，不做退避**
        #   · ⚠️「返回 0 条」**不算**网络异常，不触发熔断 ——
        #     那是推理模型烧光输出预算的已知情况（empty content），不是网络问题。
        self.net_fails = 0          # **连续**网络失败批数
        self.net_fail_total = 0     # 累计（只用于报告）

    @property
    def available(self) -> bool:
        return bool(self.reader and self.reader.available)

    def map_batch(self, claims: list[dict], inv: str) -> dict:
        """判一批。返回 {id: {status, maps_to, why_not, note}}。

        ⚠️ 实测坑（记在这里免得再踩）：deepseek-flash 是**推理模型**。
           一批给 20 条时，它的 completion 预算（4096）会被 reasoning tokens
           **全部吃光**，`finish_reason=length`，正文长度为 0。
           症状是"判了 0 条"，而且看不出原因 —— 因为我把异常吞了（已修）。
           两道处理：①批次默认降到 8 条；②空正文时把预算翻倍重试。
           这与 understand.py 里 `read()` 的做法一致（那里早就处理过同一件事）。
        """
        body = "\n".join(
            "%s ｜ %s ｜ 原文：%s" % (c["id"], (c.get("claim") or "")[:56],
                                    (c.get("quote") or "")[:52])
            for c in claims)
        user = "【系统有什么】\n%s\n\n【待判的观点】\n%s\n\n请输出 JSON 数组。" % (inv, body)
        msgs = [{"role": "system", "content": MAP_SYSTEM},
                {"role": "user", "content": user}]
        txt = ""
        for attempt in range(3):
            self.calls += 1
            try:
                d, _ = self.reader._post(msgs)
            except Exception as e:                 # noqa: BLE001
                self.errors.append(repr(e)[:90])
                if _is_net_error(e):
                    self.net_fails += 1
                    self.net_fail_total += 1
                return {}
            ch = (d.get("choices") or [{}])[0]
            txt = ((ch.get("message", {}) or {}).get("content") or "").strip()
            if txt:
                self.net_fails = 0      # ★ "连续"的断开条件：**拿到正文**就算通了
                break
            # 空正文 → 推理吃光了预算。翻倍再来。
            fr = ch.get("finish_reason")
            self.errors.append("空正文(attempt=%d, finish=%s) → 预算翻倍重试"
                               % (attempt + 1, fr))
            try:
                self.reader.max_tokens = min(self.reader.max_tokens * 2, 16384)
            except Exception:                      # noqa: BLE001
                pass
        if not txt:
            self.errors.append("三次都空正文 —— 这条批次放弃了")
            return {}
        try:
            if txt.startswith("```"):
                txt = txt.strip("`")
                txt = txt[txt.find("["):]
            obj = json.loads(txt)
        except Exception as e:                     # noqa: BLE001
            obj = _repair(txt)
            if obj is None:
                self.errors.append("解析失败:%s｜尾部=%s" % (repr(e)[:50], txt[-60:]))
                return {}
            self.errors.append("解析失败但修复成功（%s）" % repr(e)[:40])
        out = {}
        valid_ids = {x.split(" ｜")[0] for x in inv.splitlines()}
        for it in obj if isinstance(obj, list) else []:
            cid = it.get("id")
            st = it.get("status")
            if st not in ("已实现", "未实现", "明确不实现"):
                continue
            mt = [m for m in (it.get("maps_to") or []) if m in valid_ids]
            why = str(it.get("why_not") or "")[:160]
            # ── 只记不改判（用户裁定，2026-10-02）
            #
            # 目的：M 重判后出现「明确不实现 → 未实现」93 条，**100% 新 why_not 为空**，
            #      无法从数据上区分它们是"真翻盘"还是"模型想保持明确不实现但漏写理由
            #      → 被下面那条硬规则退回"。DB/E 的 1648 条是**首次判定、没有旧结论可保护**，
            #      更需要知道哪些是被降级的。
            #
            # ⚠️ 用户明令：**降级规则本身和最终 status 的结果一律不变。**
            #    这里只是把"模型原本说了什么"和"有没有被改"记下来，不改任何判断。
            #    M 已经判过的那批**不补记**（没有这两个字段就是"没记过"）。
            _raw_status = st
            _downgraded = ""
            # 硬规则：说"已实现"却指不出单元 → 不算
            if st == "已实现" and not mt:
                st, why = "未实现", "判为已实现但指不出对应单元"
                _downgraded = "已实现但指不出单元"
            # 硬规则：说"明确不实现"却没理由 → 退回未实现
            if st == "明确不实现" and not why:
                st = "未实现"
                _downgraded = "明确不实现但没写理由"
            out[cid] = {"status": st, "maps_to": mt, "why_not": why,
                        "note": str(it.get("note") or "")[:120],
                        "raw_status": _raw_status, "downgraded": _downgraded}
        return out


def apply_map(book: str, results: dict) -> int:
    """把映射结果写回观点总表。**原字段一个不丢。**"""
    import claims as C
    cs = C.load(book)
    n = 0
    for c in cs:
        r = results.get(c["id"])
        if not r:
            continue
        c["status"] = r["status"]
        c["maps_to"] = r["maps_to"]
        if r["why_not"]:
            c["why_not"] = r["why_not"]
        c["mapped_by"] = "model+ règles"
        c["mapped_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        if r.get("note"):
            c["map_note"] = r["note"]
        # ★ 只记不改判的两个字段（用户裁定）。**不动 status / maps_to / why_not 的算法。**
        if "raw_status" in r:
            c["raw_status"] = r["raw_status"]
        if "downgraded" in r:
            c["downgraded"] = r["downgraded"]
        n += 1
    with io.open(C.path(book), "w", encoding="utf-8") as f:
        for c in cs:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    return n


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="并集映射：观点 → 系统")
    ap.add_argument("--book", default="M")
    ap.add_argument("--sample", type=int, default=0, help="只判前 N 条（试点用）")
    ap.add_argument("--batch", type=int, default=8,
                    help="每批条数。默认 8 —— 20 条会让推理模型把输出预算烧光（实测）")
    a = ap.parse_args()
    import claims as C
    cs = C.load(a.book)
    todo = [c for c in cs if c.get("status") == "未实现" and not c.get("mapped_at")]
    if a.sample:
        todo = todo[:a.sample]
    print("=" * 72)
    print("并集映射｜待判 %d 条｜批次 %d" % (len(todo), a.batch))
    print("=" * 72)
    mp = Mapper()
    if not mp.available:
        print("API 不可用 —— 映射需要判断，离线做不了。")
        return 2
    inv = inventory_text()
    print("系统能力清单：%d 个单元" % len(inv.splitlines()))
    allr: dict = {}
    for i in range(0, len(todo), a.batch):
        chunk = todo[i:i + a.batch]
        # ★ 显示修正（用户裁定，2026-10-02）：**把错误绑定到它所属的那一批**。
        #
        #   原来的打印是 `mp.errors[-2:]` —— 那是**全局最后两条**，可能来自不同批次，
        #   日志读起来像"这一批出了两个错"。实测在 E 的跑批里就撞到过：
        #      批 141：**0 条**｜错误：IncompleteRead；URLError(SSLEOFError…)
        #   看起来是一批两个错，其实前一条属于更早的批次。
        #
        #   ⚠️ **只改显示，不动任何判定逻辑** —— 只在调用前后切一段 `errors` 窗口。
        _err_before = len(mp.errors)
        r = mp.map_batch(chunk, inv)
        _batch_errs = mp.errors[_err_before:]
        allr.update(r)
        # ★ 每批立刻写盘。第一版是**跑完才写** —— 31 批跑 5 分钟，
        #   中途任何一次失败就全丢，而那是纯 API 成本。
        #   增量落盘之后，重跑只会重判没判过的那些（apply_map 只认 mapped_at 为空的）。
        # ★ 熔断（用户裁定）：连续 5 批网络异常 → 停，并说清楚停在哪儿。
        #   ⚠️ 判据是 `net_fails`（只数网络异常），**"返回 0 条"不算** ——
        #      空正文是推理预算问题，不是网络问题，不该触发熔断。
        if mp.net_fails >= NET_FAIL_LIMIT:
            print()
            print("  ★ **熔断**：连续 %d 批网络异常，已停止。" % mp.net_fails)
            print("     本批错误：%s" % ("；".join(_batch_errs) or "（本批无记录）"))
            print("     近两次错误：%s" % ("；".join(mp.errors[-2:]) or "（无）"))
            print("     已判 %d 条，**每批都已落盘** —— 网络恢复后直接重跑本命令，"
                  % sum(1 for x in allr))
            print("     脚本只会重判还没判过的（apply_map 只认 mapped_at 为空的）。")
            print("     累计网络失败 %d 次。" % mp.net_fail_total)
            return 3
        if r:
            apply_map(a.book, r)
        else:
            # ★ 判 0 条必须说出**为什么**。
            #   第一版只打印"判了 0 条"，于是 5 批全空转、白烧 API，
            #   而我完全不知道原因 —— 又一次"抑制了验证输出"。
            print("  批 %2d：**0 条**｜本批错误：%s"
                  % (i // a.batch + 1,
                     "；".join(_batch_errs) or "（本批无错误记录，需查）"),
                  flush=True)
            continue
        from collections import Counter
        cc = Counter(v["status"] for v in r.values())
        print("  批 %2d：判了 %2d 条 %s" % (i // a.batch + 1, len(r), dict(cc)),
              flush=True)
    from collections import Counter
    print("\n本批结论分布：%s" % dict(Counter(v["status"] for v in allr.values())))
    print("下一步看：python engine/claims.py")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
