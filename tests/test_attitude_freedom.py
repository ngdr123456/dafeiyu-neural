# -*- coding: utf-8 -*-
"""箭头 A4：态度自由 vs 觉察受限（T18）的证伪测试（A4-1 ~ A4-6）。

裁决：[spec/冲突裁决表.jsonl] 的 **C3「自由与决定」**
    ruling      分层裁决：概率层服从机制；单例层服从自由
    upper_basis [E-154]「在人格问题上，有两个主要的方面**抵抗着结构的论述**，
                        它们是**自我意识和自由体验**」（主）
                [E-172]「人格在其构成方面是独特的；它**不可能由逻辑原则的具体事例
                        或一系列逻辑类别构成**」（辅）

用户裁定（原话）：
    「态度是面对绝境时的主体姿态（M-227），属于**存在主义维度的基本自由**，
     不属于受认知复杂性限制的智力技能。因此它应当**跨越发展阶段，
     在任何水平下均可被觉察**。」
    「豁免属于**系统治理策略**，不是语言学词表特征。严禁修改纯净的
     rules\\markers.json 数据文件，豁免逻辑完全收敛在 devlevel.py 内部。」
    「坚决不采用引入随机概率的方案，保持系统因果逻辑与测试的严格确定性。」

⚠️ 全程用临时 devlevel 路径，不碰真实 state。
⚠️ 运行请带 `-B`。
"""
from __future__ import annotations

import ast
import io
import json
import os
import sys
import tempfile

_ROOT_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TMP = tempfile.mkdtemp(prefix="ego_a4_")
sys.path.insert(0, os.path.join(_ROOT_PROJ, "engine"))

import devlevel as D              # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []
CASES: list[tuple[str, object]] = []

# 真实标记表（照实际 rules/markers.json 读，不凭记忆写）
_MARKERS = json.load(io.open(
    os.path.join(_ROOT_PROJ, "rules", "markers.json"), encoding="utf-8"))
_RULES = _MARKERS.get("markers") or []


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


def _dl(level: str | None = None) -> "D.DevLevel":
    """按指定水平造一个 DevLevel（用真实的 marker 表）。"""
    d = D.DevLevel(path=os.path.join(_TMP, "dl_%s.json" % (level or "start")),
                   rules=_RULES)
    if level:
        d.level = level
    return d


def _hint_of(mid: str):
    for m in _RULES:
        if m.get("id") == mid:
            return m.get("level_hint")
    raise AssertionError("标记表里没有 %s" % mid)


# ══════════════════════════════════════════════════════════════
# A4-1：豁免标记不受 level_hint 门控
# ══════════════════════════════════════════════════════════════
@case("【A4-1】态度句在低水平下仍可见（态度自由，跨阶段）")
def a4_1():
    hint = _hint_of("attitude_clause")
    assert hint == "I-4", "前提变了：attitude_clause 的 level_hint 现在是 %r" % hint
    # I-3 低于 I-4 —— 若不豁免，绝对看不见
    d = _dl("I-3")
    assert D.IDX["I-3"] < D.IDX["I-4"], "前提不成立：I-3 不该 ≥ I-4"
    assert "attitude_clause" in d.visible(), \
        "★ I-3 时看不见态度句 —— 态度被发展门控挡住了（违反 M-227）"
    assert "attitude_clause" not in [h["id"] for h in d.hidden()], \
        "★ 态度句被列进了『还看不见』清单"
    # 更低水平也一样
    d2 = _dl(D.LEVELS[0])
    assert "attitude_clause" in d2.visible(), \
        "★ 最低水平 %s 下看不见态度句" % D.LEVELS[0]
    # 而且**不是靠改 level_hint** 达成的（数据文件不许动）
    assert _hint_of("attitude_clause") == "I-4", \
        "★ markers.json 的 level_hint 被改了 —— 用户明令不许动那个文件"


# ══════════════════════════════════════════════════════════════
# A4-2：非豁免标记照旧被门控（A1 不被破坏）
# ══════════════════════════════════════════════════════════════
@case("【A4-2】非豁免标记照旧按水平门控（A1 的确定性不被破坏）")
def a4_2():
    # 找一个 level_hint **高于**起始水平的非豁免标记
    higher = [(m["id"], m["level_hint"]) for m in _RULES
              if m.get("level_hint") in D.IDX
              and D.IDX[m["level_hint"]] > D.IDX["I-3"]
              and m["id"] not in D._PATH_EXEMPT]
    assert higher, "找不到高于 I-3 的非豁免标记，测试前提不成立"
    mid, lv = higher[0]
    d = _dl("I-3")
    assert mid not in d.visible(), \
        "★ %s（需要 %s）在 I-3 竟然可见 —— A1 的门控被破坏了" % (mid, lv)
    assert mid in [h["id"] for h in d.hidden()], "%s 应列在 hidden 里" % mid
    # 到了那一级就该看见（同一句话：水平变了，可见性跟着变 —— 这是 A1 的证伪点）
    d2 = _dl(lv)
    assert mid in d2.visible(), \
        "★ 到了 %s 反而看不见 %s —— 门控坏了" % (lv, mid)
    # 恰好等于自己级别的，可见
    same = [(m["id"], m["level_hint"]) for m in _RULES
            if m.get("level_hint") == "I-3" and m["id"] not in D._PATH_EXEMPT]
    if same:
        assert same[0][0] in _dl("I-3").visible(), \
            "%s（恰好 I-3）在 I-3 应可见" % same[0][0]


# ══════════════════════════════════════════════════════════════
# A4-3：豁免**只对态度途径**
# ══════════════════════════════════════════════════════════════
@case("【A4-3】豁免只针对态度途径，不许外溢到别的标记")
def a4_3():
    assert D._PATH_EXEMPT == frozenset({"attitude_clause"}), \
        "★ 豁免集合被扩大了：%s" % sorted(D._PATH_EXEMPT)
    assert _dl().path_exempt() == ["attitude_clause"], \
        "path_exempt() 返回 %s" % _dl().path_exempt()
    # 逐条确认：除 attitude_clause 外，没有任何标记靠豁免绕过门控
    higher = [m["id"] for m in _RULES
              if m.get("level_hint") in D.IDX
              and D.IDX[m["level_hint"]] > D.IDX["I-3"]]
    for mid in higher:
        if mid == "attitude_clause":
            continue
        assert mid not in _dl("I-3").visible(), \
            "★ %s 也被豁免了 —— 豁免外溢" % mid


# ══════════════════════════════════════════════════════════════
# A4-4：visible 与 hidden 仍然互斥且并集完整
# ══════════════════════════════════════════════════════════════
@case("【A4-4】visible ∩ hidden = ∅ 且 visible ∪ hidden = 全部标记")
def a4_4():
    for lv in (D.LEVELS[0], "I-3", D.LEVELS[-1]):
        d = _dl(lv)
        v = d.visible()
        h = {x["id"] for x in d.hidden()}
        allids = {m["id"] for m in _RULES}
        assert not (v & h), \
            "%s：%s 同时出现在 visible 与 hidden 里" % (lv, sorted(v & h))
        assert v | h == allids, \
            "%s：并集不完整，漏了 %s" % (lv, sorted(allids - (v | h)))


# ══════════════════════════════════════════════════════════════
# A4-5：ungated 与 path_exempt 是两类，不许混
# ══════════════════════════════════════════════════════════════
@case("【A4-5】ungated（拦不了）与 path_exempt（不该拦）是两类")
def a4_5():
    d = _dl("I-3")
    ung = set(d.ungated())
    exe = set(d.path_exempt())
    # ① ungated 的语义不变：仍是「level_hint 为空」
    assert ung == {m["id"] for m in _RULES if not m.get("level_hint")}, \
        "ungated() 的语义被改了：%s" % sorted(ung)
    # ② 两类**不重叠**
    assert not (ung & exe), "两类混在一起了：%s" % sorted(ung & exe)
    # ③ immutable 在 ungated 里，**不在** path_exempt 里
    assert "immutable" in ung, "immutable 应属 ungated（level_hint 为空）"
    assert "immutable" not in exe, \
        "★ immutable 被放进 path_exempt 了 —— 它是『拦不了』不是『不该拦』"
    # ④ 豁免的那个**确实有** level_hint（这正是它区别于 ungated 的地方）
    assert _hint_of("attitude_clause") is not None, \
        "attitude_clause 没有 level_hint —— 那它就属于 ungated，不需要豁免"


# ══════════════════════════════════════════════════════════════
# A4-6：源码级 —— 裁决与依据被引用；无随机化；数据文件未被改
# ══════════════════════════════════════════════════════════════
@case("【A4-6】源码级证明：依据留痕、无随机、数据文件未动")
def a4_6():
    src = io.open(os.path.join(_ROOT_PROJ, "engine", "devlevel.py"),
                  encoding="utf-8").read()
    # ① 裁决与依据必须写在注释里，将来谁读代码都知道依据在哪
    for k in ("C3", "E-154", "E-172", "M-227", "A4"):
        assert k in src, "devlevel.py 里没留 %s 的依据" % k
    assert "抵抗着结构的论述" in src, "没引用 E-154 的原文"
    # ② **豁免路径不得引入随机**（用户明令：保持系统因果逻辑与测试的严格确定性）
    #
    #    ⚠️ 判据要**精确**，不能按词黑名单 ——
    #       第一版写 `assert "random" not in src`，结果撞上 devlevel.py 里
    #       **本来就有的** `random.Random(7)`（只在 `__main__` 的 `--simulate`
    #       CLI 模拟里用，种子固定，正常运行从不执行）。那与 A4 无关，误报。
    #       正确判据：**门控这条路径上的函数**里不许出现随机调用。
    tree = ast.parse(src)
    GATE_FNS = {"can_see", "visible", "hidden", "ungated", "path_exempt"}
    for n in ast.walk(tree):
        if not (isinstance(n, ast.FunctionDef) and n.name in GATE_FNS):
            continue
        body = ast.get_source_segment(src, n)
        for bad in ("random", "rnd.", "shuffle", "choice(", "uniform("):
            assert bad not in body, \
                "★ %s 里出现了随机（%r）—— 门控必须确定性" % (n.name, bad)
    # ③ can_see 的新参数是**可选**的（向后兼容）
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "can_see")
    assert [a.arg for a in fn.args.args] == ["self", "level_hint", "marker_id"], \
        "can_see 签名变了：%s" % [a.arg for a in fn.args.args]
    defaults = fn.args.defaults
    assert len(defaults) == 1, "marker_id 必须是可选参数（向后兼容）"
    assert isinstance(defaults[0], ast.Constant) and defaults[0].value is None, \
        "marker_id 的默认值应为 None"
    # ④ 不传 marker_id 时，行为与从前完全一致
    d = _dl("I-3")
    assert d.can_see("I-4") is False, "不传 id 时 I-3 不该看得见 I-4（旧行为）"
    assert d.can_see("I-3") is True
    assert d.can_see(None) is True
    # ⑤ rules/markers.json **一个字节没动** —— 对着**钉死的常量**比，不对着快照比
    #
    #    ⚠️ 第一版是跟 `backups\打包前_最终源码\rules\markers.json` 比的。
    #       那份快照**每次打包都会被刷新** —— 刷新之后这条断言就等于
    #       拿文件跟自己比，**永远通过**。（跟 test_admin_escalation 的 C1 同一个坑。）
    #       现在改成对着 `tests\_baseline_files.json` 里的常量哈希比：
    #       它变了就说明有人动了不该动的纯数据文件。
    bp = os.path.join(_ROOT_PROJ, "tests", "_baseline_files.json")
    assert os.path.exists(bp), "缺少常量基线 tests/_baseline_files.json"
    base = json.load(io.open(bp, encoding="utf-8"))
    import hashlib
    for rel, d in base["文件"].items():
        fp = os.path.join(_ROOT_PROJ, rel)
        assert os.path.exists(fp), "%s 不见了" % rel
        got = hashlib.sha256(io.open(fp, "rb").read()).hexdigest()
        assert got == d["sha256"], (
            "★ %s 被改动了（期望 %s，实际 %s）\n"
            "         这是个纯数据文件，改动要你批。**不要去刷新基线哈希** —— "
            "先查是谁、为什么改的。\n         原因记录：%s"
            % (rel, d["sha256"][:20], got[:20], d.get("为何钉死", "")))
    # ⑥ report() 暴露
    r = _dl().report()
    assert r.get("path_exempt") == ["attitude_clause"], r.get("path_exempt")


# ══════════════════════════════════════════════════════════════
def main() -> int:
    for name, fn in CASES:
        _run_one(name, fn)
    ok = sum(1 for _, p, _ in RESULTS if p)
    print("=" * 80)
    print("箭头 A4：态度自由 vs 觉察受限（T18）证伪测试")
    print("=" * 80)
    for name, passed, msg in RESULTS:
        print("  [%s] %s" % ("PASS" if passed else "FAIL", name))
        if not passed:
            print("         %s" % msg)
    print("-" * 80)
    print("结果: %d 通过 / %d 失败 / 共 %d"
          % (ok, len(RESULTS) - ok, len(RESULTS)))
    import shutil
    shutil.rmtree(_TMP, ignore_errors=True)
    return 0 if ok == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
