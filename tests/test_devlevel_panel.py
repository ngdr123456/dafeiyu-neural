# -*- coding: utf-8 -*-
"""T33 只读显示：**面板依赖的键名必须与 `DevLevel.save()` 写出的对得上**。

用户裁定（T33）原话：
> 「贴一份 `DevLevel.save()` 真实写出的 JSON 样例，并加测试：用 `save()` 写临时文件，
>   断言 `level`、`equilibration`、`not_grown`、`updated` 四个键都在。
>   **键名对不上，面板会静默显示错。**」

为什么这条必须有测试：
`training_studio.py::_refresh_devlevel_file()` 用 `d.get("equilibration", "—")` 这类
**带缺省值的取法** —— 键名一旦改了，**不会报错，只会安静地显示「—」**。
那是本项目最怕的一类失败：**坏得看不出来**。

本测试把"写"和"读"两边钉在一起：
    D1  save() 写出的 JSON 里，那四个键都在
    D2  读出来的值类型正确、且与写进去的一致
    D3  面板的取法对**缺键**是安全的（不会抛异常）
    D4  面板的三种文案互不混同（尚未开始 / 读取失败 / 正常）
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "engine"))

import devlevel as D                          # noqa: E402

RESULTS: list = []
CASES: list = []

# ★ 面板从文件里取的那四个键 —— 与 training_studio.py 逐一对应
PANEL_KEYS = ("level", "equilibration", "not_grown", "updated")


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


def _saved(**over) -> dict:
    """真跑一次 save()，返回读回来的 dict。"""
    d = tempfile.mkdtemp(prefix="ego_dl_")
    try:
        p = os.path.join(d, "devlevel.json")
        dl = D.DevLevel(p)
        for k, v in over.items():
            setattr(dl, k, v)
        dl.save()
        with io.open(p, encoding="utf-8") as f:
            return json.load(f)
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ══════════════════════════════════════════════════════════════
@case("【D1】save() 写出的 JSON 里，面板依赖的四个键都在")
def d1():
    o = _saved(equilibration=2, not_grown=1)
    missing = [k for k in PANEL_KEYS if k not in o]
    assert not missing, ("★ 面板会静默显示错 —— 这些键不在 save() 的输出里：%s\n"
                         "  实际键：%s" % (missing, sorted(o)))


# ══════════════════════════════════════════════════════════════
@case("【D2】四个键的值类型正确，且与写进去的一致")
def d2():
    o = _saved(equilibration=7, not_grown=3)
    assert o["level"] == D.START_LEVEL, o["level"]
    assert o["equilibration"] == 7, o["equilibration"]
    assert o["not_grown"] == 3, o["not_grown"]
    assert isinstance(o["updated"], str) and len(o["updated"]) >= 10, o["updated"]
    # 反证：改一个值，读回来必须跟着变（防"写死"）
    o2 = _saved(equilibration=9)
    assert o2["equilibration"] == 9, o2["equilibration"]


# ══════════════════════════════════════════════════════════════
@case("【D3】面板的取法对缺键安全 —— 不抛异常、有缺省")
def d3():
    """面板用 `d.get(k, 缺省)`；给一个**只有部分键**的 dict 必须不炸。"""
    for partial in ({}, {"level": "I-4"}, {"equilibration": 1}):
        lv = partial.get("level") or "—"
        eq = partial.get("equilibration", "—")
        ng = partial.get("not_grown", 0)
        up = partial.get("updated") or "—"
        assert lv and eq != "" and ng is not None and up
    # 源码级：确认面板用的确实是带缺省的取法，不是 d["k"]
    src = io.open(os.path.join(_ROOT, "engine", "training_studio.py"),
                  encoding="utf-8").read()
    seg = src[src.index("def _refresh_devlevel_file"):src.index("def _refresh_stats")]
    for k in ("equilibration", "not_grown", "updated"):
        assert 'd["%s"]' % k not in seg, \
            "面板不该用 d[%r]（缺键会抛异常），要用 .get()：%s" % (k, k)


# ══════════════════════════════════════════════════════════════
@case("【D4】三种文案互不混同：尚未开始 / 读取失败 / 正常")
def d4():
    """用户裁定：**文件损坏不能伪装成「没跑过」**。

    ⚠️ 本用例在 T24-C 之后改过一次断言方式：
       第一版断言的是**代码结构**（`if not os.path.exists(p):` 之后接 `try:`），
       而 T24-C 为了"观测窗那行独立算"把结构改成了「先读出来、再按 `d is None` 分支」。
       **结构变了、行为没变** —— 但旧断言直接 `index()` 找不到就报错。
       ⇒ 改成断言**行为特征**：两条文案由 `err` **互斥选择**。
    """
    src = io.open(os.path.join(_ROOT, "engine", "training_studio.py"),
                  encoding="utf-8").read()
    seg = src[src.index("def _refresh_devlevel_file"):src.index("def _refresh_stats")]
    assert "尚未开始" in seg, "缺「尚未开始」"
    assert "读取失败" in seg, "★ 缺「读取失败」—— 损坏会被当成没跑过"
    # ★ 两条文案必须**由 `err` 互斥选择**（不是并列写死的两句）
    assert '"读取失败：%s" % err if err else "尚未开始"' in seg, \
        ("★ 两条文案没有用 `err` 互斥选择 —— "
         "损坏与没跑过可能混同（那正是第一版犯的错）")
    # 损坏时 `err` 必须被赋值（否则永远走「尚未开始」那一支）
    assert "err = type(e).__name__" in seg, "★ except 分支没记下 err"
    # 且用的是 with（用户要求）
    assert "with io.open" in seg, "应用 with 打开文件"
    # lbl_rules 在文件视图里必须留空（不许把时间戳塞进去）
    assert 'self.lbl_rules.config(text="")' in seg, \
        "lbl_rules 在文件视图里必须留空（同一控件不许两种含义）"
    assert "上次落盘" in seg and "lbl_devsub" in seg, "时间戳应并进 lbl_devsub"
    # ★ T24-C：观测窗那行必须**不受 `d is None` 的 return 影响**
    i_ret = seg.index("if d is None:")
    i_win = seg.index("win = self._window_line(eq)")
    assert i_win < i_ret, \
        ("★ 观测窗那行算在 `if d is None: ... return` **之后** —— "
         "没跑过训练就看不到观测窗（T24-C 修掉的那个缺陷会复活）")
    assert ("self._window_line(eq)" in seg[i_ret:]) or ("+ win)" in seg[i_ret:]), \
        "「尚未开始」分支里必须也带上观测窗那行（算好的 win）"


# ══════════════════════════════════════════════════════════════
def main() -> int:
    for name, fn in CASES:
        try:
            fn()
            RESULTS.append((name, True, ""))
        except AssertionError as e:
            RESULTS.append((name, False, str(e) or "断言失败"))
        except Exception as e:                          # noqa: BLE001
            RESULTS.append((name, False, "%s: %s" % (type(e).__name__, e)))
    ok = sum(1 for _, p, _ in RESULTS if p)
    print("=" * 78)
    print("T33 只读显示：键名与文案")
    print("=" * 78)
    for name, passed, msg in RESULTS:
        print("  [%s] %s" % ("PASS" if passed else "FAIL", name))
        if not passed:
            print("         %s" % msg)
    print("-" * 78)
    print("结果: %d 通过 / %d 失败 / 共 %d"
          % (ok, len(RESULTS) - ok, len(RESULTS)))
    return 0 if ok == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
