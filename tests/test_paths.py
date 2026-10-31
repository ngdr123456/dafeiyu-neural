# -*- coding: utf-8 -*-
"""箭头 A3（T17）：三条意义途径的证伪测试（P1~P6）。

书里的依据（逐字核对过）：
    [M-570]「正如意义疗法所宣扬的，找到生命之意义有三个主要途径。」
    [M-435]「我们可以用三种不同的方式来发现生命之意义」
    [M-578]「**首要的是创造性地去改变**让我们遭受磨难的境遇。
            但最要紧的还是要知道如何承受不可避免的痛苦。」
    [M-391]「人对意义的追寻会导致内心的紧张而非平衡。」

用户裁定（原话）：
    「弗兰克尔的『创造途径』是指主体在现实世界中完成具体作为、改变客观境遇。
     本系统作为纯对话 Agent，既无实体干预物理世界，
     也无权在对话中随意代入『替用户创造』。」
    「（甲）本质上依然是给『凡是开口说话就算创造』穿上了一层算法马甲，
     会让绝大多数轮次沦为假阳性，彻底稀释了这一指标的严肃性。」
    「path_creative 明确固定为 0.0，path_cre 累计记 0；
     标明该项在纯对话形态下『暂无可观察量，诚实缺位』。」
    「累计计数变量名统一为 path_cre、path_exp、path_att。」
    「恪守机制层纪律，所有新增字段必须是数值，严禁携带字符串。」

⚠️ 运行请带 `-B`。
"""
from __future__ import annotations

import ast
import io
import os
import sys

_ROOT_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT_PROJ, "engine"))

import mechanism as M              # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []
CASES: list[tuple[str, object]] = []


def case(name: str):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


def _run_one(name: str, fn) -> None:
    try:
        fn()
        RESULTS.append((name, True, ""))
    except AssertionError as e:
        RESULTS.append((name, False, str(e) or "断言失败"))
    except Exception as e:                         # noqa: BLE001
        RESULTS.append((name, False, "%s: %s" % (type(e).__name__, e)))


def _mk() -> "M.Mechanism":
    return M.Mechanism()


def _st(m: "M.Mechanism"):
    """跑一次 step 拿到落点快照。

    签名按**实际**的 `Mechanism.step(markers, raw, channel, context_key, ...)` ——
    第一版我只传了一句话，报 missing 3 required positional arguments。
    锚点必须照实际签名写，不能凭印象。
    """
    return m.step([], "我特别渴望被认可，一想到就坐不住。", "chat", "t1")


# ══════════════════════════════════════════════════════════════
# P1：体验途径 —— 与指向同源
# ══════════════════════════════════════════════════════════════
@case("【P1】体验途径：注意力朝外时成立，累计 +1；朝内时不成立")
def p1():
    m = _mk()
    m.note_orientation("外")
    m.note_paths(has_attitude=False)
    st = _st(m)
    # 落点在**下一轮**生效（与指向同理），所以这里先告知再取快照
    assert st.path_experiential in (0.0, 1.0), \
        "path_experiential 必须是数：%r" % (st.path_experiential,)
    # 再走一轮，此时上一轮的"外"已生效
    st2 = _st(m)
    assert st2.path_experiential == 1.0, \
        "上一轮朝外，本轮 path_experiential 应为 1.0，实际 %r" % st2.path_experiential
    assert st2.path_exp >= 1, "体验途径累计应 ≥1：%s" % st2.path_exp
    # 朝内 → 不成立
    m2 = _mk()
    m2.note_orientation("内")
    m2.note_paths(has_attitude=False)
    st3 = _st(m2)
    st4 = _st(m2)
    assert m2._cnt_exp <= 1, "朝内不该累加体验途径：%s" % m2._cnt_exp


# ══════════════════════════════════════════════════════════════
# P2：态度途径 —— 由 has_attitude 决定，累计 +1
# ══════════════════════════════════════════════════════════════
@case("【P2】态度途径：has_attitude=True 时成立，累计 +1")
def p2():
    m = _mk()
    m.note_orientation("外")
    m.note_paths(has_attitude=True)
    assert m._cnt_att == 1, "态度途径应累加 1，实际 %s" % m._cnt_att
    st = _st(m)
    st2 = _st(m)
    assert st2.path_attitudinal == 1.0, \
        "上一轮命中态度句，本轮 path_attitudinal 应为 1.0，实际 %r" % st2.path_attitudinal
    assert st2.path_att == 1, "态度途径累计应为 1：%s" % st2.path_att
    # 未命中 → 0.0，且不累加
    m2 = _mk()
    m2.note_orientation("外")
    m2.note_paths(has_attitude=False)
    st3 = _st(m2)
    st4 = _st(m2)
    assert st4.path_attitudinal == 0.0, "没命中态度句却亮了：%r" % st4.path_attitudinal
    assert m2._cnt_att == 0, "没命中却累加了：%s" % m2._cnt_att


# ══════════════════════════════════════════════════════════════
# P3：态度途径**不重复判断 immutable 门控**（那层在标记层）
# ══════════════════════════════════════════════════════════════
@case("【P3】机制层不重判 immutable 门控（门控属于标记层，不在这里）")
def p3():
    src = io.open(os.path.join(_ROOT_PROJ, "engine", "mechanism.py"),
                  encoding="utf-8").read()
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "note_paths")
    body = ast.get_source_segment(src, fn)
    # 不得在机制层再查 immutable / mutability —— 那层门控在 markers.json 里
    for bad in ("immutable", "mutability"):
        assert bad not in body, \
            "★ note_paths 里重复判断了 %s —— 门控应在标记层，不该在这里" % bad
    # 而标记层**确实**做了那层门控（反向确认它没被绕过）
    mk = io.open(os.path.join(_ROOT_PROJ, "rules", "markers.json"),
                 encoding="utf-8").read()
    # 原文照抄（含 markdown 星号），不凭记忆
    assert "且**仅在 mutability=IMMUTABLE 时**计入方向" in mk, \
        "标记层的 immutable 门控不见了 —— 那条 _note 是依据，不许删"


# ══════════════════════════════════════════════════════════════
# P4：三条途径**互不排斥**（同一轮可以同时亮两条）
# ══════════════════════════════════════════════════════════════
@case("【P4】三条途径互不排斥：同一轮可同时走体验与态度")
def p4():
    m = _mk()
    m.note_orientation("外")            # 体验成立
    m.note_paths(has_attitude=True)     # 态度也成立
    _st(m)
    st = _st(m)
    assert st.path_experiential == 1.0 and st.path_attitudinal == 1.0, \
        "★ 两条途径被做成了互斥：体验=%r 态度=%r" % (st.path_experiential,
                                                     st.path_attitudinal)
    # 三个字段是**独立标志**，不是一个分类枚举 —— 所以不存在"只能有一个为 1"
    assert st.path_creative == 0.0, "创造恒 0（见 P5）"


# ══════════════════════════════════════════════════════════════
# P5：创造途径 —— 诚实缺位，恒为 0
# ══════════════════════════════════════════════════════════════
@case("【P5】创造途径恒为 0：无可观察量，诚实缺位（不是漏了）")
def p5():
    m = _mk()
    # 无论怎么喂，创造途径都不该亮、不该累加
    for kind in ("外", "内", "无"):
        for att in (True, False):
            m.note_orientation(kind)
            m.note_paths(has_attitude=att)
            st = _st(m)
            assert st.path_creative == 0.0, \
                "★ 创造途径竟然亮了（orientation=%s, attitude=%s）—— 形式主义" % (kind, att)
            assert st.path_cre == 0, "★ 创造途径累计竟然动了：%s" % st.path_cre
    # 而且**没有任何输入能改变它**：note_paths 不接受创造参数
    src = io.open(os.path.join(_ROOT_PROJ, "engine", "mechanism.py"),
                  encoding="utf-8").read()
    fn = next(n for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.FunctionDef) and n.name == "note_paths")
    args = [a.arg for a in fn.args.args]
    assert args == ["self", "has_attitude"], \
        "★ note_paths 多出了参数 %s —— 创造途径不该有输入口" % args
    # 诚实留痕：注释里必须写明"为什么恒 0"，不许含糊
    body = ast.get_source_segment(src, fn)
    # ⚠️ 别写死字面 —— 第一版找「无可观察量」，而 docstring 写的是「没有可观察量」，
    #    子串对不上就误报。按**语义要件**判，不按我记忆里的措辞判。
    assert "可观察量" in body, "note_paths 里没说明创造途径为何没有可观察量"
    assert any(k in body for k in ("如实标缺", "诚实缺位", "恒为 0", "恒 0")), \
        "note_paths 里没写明这是**刻意标缺**（而不是漏了）"
    assert "纯对话" in body or "无实体" in body, \
        "note_paths 里没写明原因（纯对话形态 / 无实体干预现实）"


# ══════════════════════════════════════════════════════════════
# P6：机制层纪律 —— 新增字段全是数，严禁字符串
# ══════════════════════════════════════════════════════════════
@case("【P6】新增字段全是数值，严禁携带字符串（机制层铁律）")
def p6():
    m = _mk()
    m.note_orientation("外")
    m.note_paths(has_attitude=True)
    st = _st(m)
    d = st.to_dict()
    KEYS = ["path_creative", "path_experiential", "path_attitudinal",
            "path_cre", "path_exp", "path_att"]
    for k in KEYS:
        assert k in d, "落点快照缺字段 %s" % k
        v = d[k]
        assert isinstance(v, (int, float)) and not isinstance(v, bool), \
            "★ %s 不是数值（%r）—— 违反机制层『只有数没有文字』" % (k, v)
        assert not isinstance(v, str), "★ %s 是字符串：%r" % (k, v)
    # 全快照扫一遍：新增字段之外也不许出现这几条途径的**文字**表述
    for k, v in d.items():
        if isinstance(v, str):
            for word in ("创造途径", "体验途径", "态度途径"):
                assert word not in v, \
                    "★ 快照字段 %s 里带了途径文字 %r —— 机制层不许有文字" % (k, word)
    # 变量命名按用户裁定：path_cre / path_exp / path_att
    for k in ("path_cre", "path_exp", "path_att"):
        assert k in d, "命名不符（用户裁定用 %s）" % k
    assert "path_out" not in d, "★ 出现了易混淆的 path_out（用户明令不用它）"


# ══════════════════════════════════════════════════════════════
def main() -> int:
    for name, fn in CASES:
        _run_one(name, fn)
    ok = sum(1 for _, p, _ in RESULTS if p)
    print("=" * 78)
    print("箭头 A3（T17）：三条意义途径 证伪测试")
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
