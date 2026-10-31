# -*- coding: utf-8 -*-
"""实测：把理解层的 API 打开后，模型对这些输入到底怎么判？

为什么必须实测
────────────────────────────────────────────────────────────
用户问：「判断用户在说什么，不应该由 API 大模型来做吗？」
这是个事实问题，不是立场问题。而我上一轮已经**没看启动器就断言**"模型一步没碰过理解"，
结果是错的（launcher.py 在非离线模式下会传 --api）。
所以这次不再凭读代码推断，直接调 API 看它返回什么。

对照点：离线（规则版）对这几句的判定已知：
  「干嘛」      规则=ANSWER → SILENCE
  「有啥用」    规则=ANSWER → SILENCE
  「改不了」    规则=immutable（已修）
  「没控制住」  规则=voice_shift（已修）
如果 API 开着时这些能被接住，那说明理解层本来就该以模型为主、规则只是兜底；
如果 API 也接不住或乱判，那就说明"交给模型"解决不了这一类问题。
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_ROOT, os.path.join(_ROOT, "engine")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import markers as M            # noqa: E402
import understand as U         # noqa: E402

CASES = [
    "干嘛",
    "有啥用",
    "会难过吗",
    "我在想干嘛",          # ★ 反例：这是用户在说自己，不该判 META
    "我不知道要干什么",     # ★ 反例：同上
    "改不了",
    "没控制住",
    "我今天特别累，什么都不想干",   # ★ 反例：历史上被误判成 META 的那句
]


def main() -> int:
    r = U.ApiReader()
    print("API 可用:", r.available, "| 模型:", r.model, "| 端点:", r.base)
    if not r.available:
        print("拿不到密钥，测不了。")
        return 2

    rules = M.load_marker_rules()
    eng = M.MarkerEngine(rules)
    spec = rules["markers"]

    print("=" * 80)
    print("%-22s %-8s %-8s %-28s %s" % ("输入", "规则判", "API判", "API给的标记", "合并后"))
    print("=" * 80)
    for t in CASES:
        rule_int = M.rule_intent(t, M._load_meta())
        try:
            api = r.read(t, None, spec)
        except Exception as e:                       # 网络/解析异常也要看得见
            print("%-22s %-8s %-8s %s" % (t, rule_int, "错误", repr(e)[:60]))
            continue
        merged, how = U.resolve_intent(rule_int, api, t)
        print("%-22s %-8s %-8s %-28s %s (%s)" % (
            t, rule_int, (api.intent if api.ok else "不可用"),
            ",".join(api.markers) or "无", merged, how))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
