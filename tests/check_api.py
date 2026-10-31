# -*- coding: utf-8 -*-
"""API 连通性体检 —— 从密钥到一次真实往返，逐层验证。

为什么要分层：用户问"有没有接上 DeepSeek"，这不是一个是非题 ——
    密钥取不到 / 取到了但网络不通 / 通了但理解层没用它 / 用了但渲染层被闸门全挡回去
是**四种完全不同的故障**，用户看到的现象却可能都是"像机器人在按表回答"。
所以逐层给证据，不合并成一个"正常/不正常"。

⚠️ 密钥只打印掩码，绝不打印全文。
"""
from __future__ import annotations

import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_ROOT, os.path.join(_ROOT, "engine"), os.path.join(_ROOT, "state")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import understand as U          # noqa: E402


def mask(s: str | None) -> str:
    s = (s or "").strip()
    return "(空)" if not s else "%s…%s（长度 %d）" % (s[:6], s[-4:], len(s))


def main() -> int:
    bad = 0
    print("=" * 78)
    print("API 连通性体检")
    print("=" * 78)

    # ---- ① 密钥来源
    print("\n① 密钥")
    env = os.environ.get("DEEPSEEK_API_KEY")
    print("   环境变量 DEEPSEEK_API_KEY：%s" % ("未设置" if not env else mask(env)))
    k = U.load_api_key()
    print("   load_api_key() 取到：%s" % mask(k))
    if not k:
        print("   ✗ 取不到密钥 —— 后面全部无法进行")
        return 1
    print("   ✓ 密钥可取")

    # ---- ② 真实 HTTP 往返（最小请求）
    print("\n② 真实 HTTP 往返（最小请求）")
    r = U.ApiReader()
    print("   端点：%s" % r.base)
    print("   模型：%s" % r.model)
    t0 = time.time()
    try:
        d, _ = r._post([{"role": "user", "content": "只回复两个字：收到"}], json_mode=False)
        dt = time.time() - t0
        content = (d.get("choices") or [{}])[0].get("message", {}).get("content", "")
        print("   ✓ 通了｜耗时 %.2fs｜返回：%r" % (dt, (content or "").strip()[:40]))
        print("   用量：%s" % (d.get("usage") or {}))
    except Exception as e:                                     # noqa: BLE001
        bad += 1
        print("   ✗ **不通**：%r" % e)
        print("     （网络、余额、密钥无效、或端点被挡，都会走到这里）")
        return 1

    # ---- ③ 理解层（读意图 + 标记）
    print("\n③ 理解层：把一句话映射成结构")
    import markers as M
    spec = M.load_marker_rules()["markers"]
    for t in ["我一定要得到那个结果，得不到我就难受", "你愿意了解我吗"]:
        try:
            res = r.read(t, None, spec)
            print("   「%s」" % t)
            print("      ok=%s intent=%s markers=%s 耗时=%.2fs err=%s"
                  % (res.ok, res.intent, res.markers or "无", res.latency_s, res.error))
        except Exception as e:                                 # noqa: BLE001
            bad += 1
            print("   「%s」✗ 异常：%r" % (t, e))

    # ---- ④ 渲染层
    print("\n④ 渲染层：把已决定的'意思'说成人话")
    try:
        from compose import compose
        from render import Renderer, make_brief
        rd = Renderer()
        print("   Renderer.available = %s" % rd.available)
        m = compose("我一定要得到那个结果，得不到我就难受", ["over_intention", "want_like_gap"])
        b = make_brief(m, "我一定要得到那个结果，得不到我就难受", "observe_only")
        sp = rd.render(b)
        print("   渲染结果：rendered=%s reason=%s" % (sp.rendered, sp.reason))
        print("   文本：%s" % (sp.text or "").replace("\n", " / ")[:80])
    except Exception as e:                                     # noqa: BLE001
        bad += 1
        print("   ✗ 异常：%r" % e)

    # ---- ⑤ 一轮完整对话：API 是否真的被调用
    print("\n⑤ 一轮完整对话（走管线，确认 API 真的参与）")
    import tempfile
    from pipeline import Pipeline
    d = tempfile.mkdtemp(prefix="ego_api_")
    p = Pipeline(ledger_path=os.path.join(d, "l.jsonl"), auto_audit=False,
                 character_path=os.path.join(d, "character.json"),
                 use_api=True, use_render=True)
    print("   pipeline.api_enabled = %s ｜ renderer 挂载 = %s"
          % (p.api_enabled, p.renderer is not None))
    if not p.api_enabled:
        bad += 1
        print("   ✗ **理解层的 API 没挂上** —— use_api=True 也拿不到 reader")
    res = p.turn("我一定要得到那个结果，得不到我就难受", None)
    print("   行为=%s" % res.behavior)
    print("   api_ok=%s api_intent=%s api_latency=%.2fs" % (res.api_ok, res.api_intent, res.api_latency))
    print("   仅规则=%s｜仅API=%s｜一致度=%s" % (res.only_rule or "无", res.only_api or "无", res.agreement))
    print("   输出：%s" % (res.output or "（空）").replace("\n", " / "))
    for n in res.notes:
        if "渲染" in n or "评定" in n or "API" in n:
            print("     台账：%s" % n[:120])
    if not res.api_ok:
        bad += 1
        print("   ✗ **这一轮理解层没有调用成功**（api_ok=False）")

    print("\n" + "=" * 78)
    print("总判定：%s" % ("API 已接上，且理解层与渲染层都在工作" if bad == 0
                          else "**有 %d 处不通 —— 见上面 ✗**" % bad))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
