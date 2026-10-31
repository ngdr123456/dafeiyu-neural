# -*- coding: utf-8 -*-
"""箭头 A5：张力 → 生长的证伪测试（T16）。

书里的依据（三条，逐字核对过）：
    [M-391]「人对意义的追寻会导致内心的**紧张而非平衡**。」
    [M-400]「也就是**存在的动力处于一个紧张的极化区**」
    [M-367]「努力发现生命的意义正是人**最主要的动力**。」

用户裁定（原话）：
    「弗兰克尔批判的核心是『存在主义真空（无目标、无张力的虚无空转）』。
     趋零必须坚决排除不计入生长；至于高张力过载，那是前置机制降负载的任务，
     若在承受高压后仍能完成结构重组，属于**创伤后成长**，不应在此处人为封顶。」
    「张力点位确认采用 (甲) **失效那一刻**的张力。」
    「（张力不可测时）**放行，但日志必须显式留痕** …… 严禁静默放行。」
    「report() 中同步暴露 not_grown 与 fail_tension。」

⚠️ 全程用临时 `devlevel.json`，不碰真实 state。
⚠️ 运行请带 `-B`。
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile

_ROOT_PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TMP = tempfile.mkdtemp(prefix="ego_devgrowth_")
sys.path.insert(0, os.path.join(_ROOT_PROJ, "engine"))

import devlevel as D              # noqa: E402

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


_SEQ = [0]


def _fresh() -> "D.DevLevel":
    """每个用例、每次调用一份**全新**的 devlevel 状态。

    ⚠️ 第一版路径写成 `devlevel_%d.json % len(RESULTS)` —— 那是"已完成的用例数"，
       在**同一个用例内部是常数**。于是同一个用例里两次 `_fresh()` 指向同一个文件，
       第二次 `DevLevel.__init__` 里的 `_load()` 把第一次的状态**读了回来**：
       计数继续累加（G4 期望 2 实际 5）、failed 态被继承（G6 被误判为拦下）。
       **`_fresh()` 必须真的 fresh** —— 用递增序号，不用外部状态。
    """
    _SEQ[0] += 1
    return D.DevLevel(path=os.path.join(_TMP, "devlevel_%03d.json" % _SEQ[0]),
                      rules=[])


def _fail(dl, tension: float, measured: bool = True) -> dict:
    """喂一次结构失效（|e| ≥ error_high）。"""
    return dl.update({"e": D.ERROR_HIGH + 0.1, "tension": tension,
                      "tension_measured": measured})


def _heal(dl, tension: float = 0.0, measured: bool = True) -> dict:
    """喂一次重组完成（|e| ≤ error_low）。"""
    return dl.update({"e": D.ERROR_LOW - 0.05, "tension": tension,
                      "tension_measured": measured})


def _cycle(dl, tension: float, measured: bool = True) -> dict:
    """走一次完整平衡化：先失效、后重组。

    ⚠️ 重组那一步**必须把 measured 透传下去**。
       第一版写成 `return _heal(dl)` —— 漏了参数，于是重组永远带
       `measured=True` + `tension=0.0`，被判成"张力趋零"。
       G1 看不出问题（判定用的是**失效那一刻**记下的 `fail_tension`，不看重组时的张力），
       只有 G6 因为要传 `measured=False` 才把它暴露出来。
    """
    _fail(dl, tension, measured)
    return _heal(dl, tension, measured)


# ══════════════════════════════════════════════════════════════
# G1：张力充足 → 计入生长
# ══════════════════════════════════════════════════════════════
@case("【G1】张力充足时，一次完整平衡化 → 计入生长")
def g1():
    dl = _fresh()
    before = dl.equilibration
    out = _cycle(dl, tension=5.0)
    assert dl.equilibration == before + 1, \
        "张力 5.0 竟然没计入生长（equilibration %d → %d）" % (before, dl.equilibration)
    assert dl.not_grown == 0, "不该有『不计入』的计数"
    assert "有动力" in (out.get("event") or ""), "事件描述没写明动力：%s" % out.get("event")
    assert out["fail_tension"] == 5.0, "fail_tension 应记为失效那一刻的 5.0：%s" % out


# ══════════════════════════════════════════════════════════════
# G2：张力趋零 → **不计入**生长
# ══════════════════════════════════════════════════════════════
@case("【G2】张力趋零时，同样的 e 序列 → 不计入生长")
def g2():
    dl = _fresh()
    before = dl.equilibration
    out = _cycle(dl, tension=0.5)                  # 0.5 ≤ TENSION_DRIVE(1.5)
    assert dl.equilibration == before, \
        "★ 张力趋零竟然还是计入了生长（equilibration %d → %d）" % (before, dl.equilibration)
    assert dl.not_grown == 1, "应记一次『不计入』，实际 %d" % dl.not_grown
    ev = out.get("event") or ""
    assert "不计入生长" in ev, "事件没写明不计入：%s" % ev
    assert "无值得为之努力的东西" in ev, "事件没引用 NO_TENSION 的判据原话：%s" % ev
    # 边界：正好等于门槛**不算**有动力（严格大于）
    dl2 = _fresh()
    b2 = dl2.equilibration
    _cycle(dl2, tension=D.TENSION_DRIVE)
    assert dl2.equilibration == b2, \
        "张力恰好等于 %.2f 时不该计入（判据是**严格大于**）" % D.TENSION_DRIVE


# ══════════════════════════════════════════════════════════════
# G3：不计入时**照记不静默**
# ══════════════════════════════════════════════════════════════
@case("【G3】不计入的那次必须进 history，不许静默丢弃")
def g3():
    dl = _fresh()
    n0 = len(dl.history)
    _cycle(dl, tension=0.3)
    assert len(dl.history) >= n0 + 2, \
        "失效与重组都该留痕，实际只多了 %d 条" % (len(dl.history) - n0)
    joined = json.dumps(dl.history, ensure_ascii=False)
    assert "不计入生长" in joined, "★ history 里找不到『不计入生长』—— 被静默丢弃了"
    # 落盘之后仍然在（不许只在内存里）
    dl.save()
    disk = json.load(io.open(dl.path, encoding="utf-8"))
    assert disk.get("not_grown") == 1, "落盘后 not_grown 丢了：%s" % disk.get("not_grown")
    assert "不计入生长" in json.dumps(disk.get("history"), ensure_ascii=False), \
        "落盘后 history 里的『不计入』没了"


# ══════════════════════════════════════════════════════════════
# G4：升级计数只累加"计入的"那些
# ══════════════════════════════════════════════════════════════
@case("【G4】3 次有动力 → 升级；2 次有动力 + 1 次无动力 → 不升")
def g4():
    # ① 三次都有动力 → 升一级
    dl = _fresh()
    lv0 = dl.level
    for _ in range(D.PER_LEVEL):
        _cycle(dl, tension=5.0)
    assert dl.level != lv0, \
        "%d 次有动力的平衡化应当升级，实际仍停在 %s" % (D.PER_LEVEL, dl.level)
    # ② 两次有动力 + 一次趋零 → **不升**（趋零那次被排除）
    dl2 = _fresh()
    lv1 = dl2.level
    for t in (5.0, 5.0, 0.4):
        _cycle(dl2, tension=t)
    assert dl2.equilibration == 2, \
        "只应计入 2 次，实际 %d" % dl2.equilibration
    assert dl2.not_grown == 1, "应有 1 次不计入，实际 %d" % dl2.not_grown
    assert dl2.level == lv1, \
        "★ 用无动力的平衡化凑够了升级 —— 次数被算进去了（%s → %s）" % (lv1, dl2.level)
    # ③ 再补一次有动力 → 此时才升
    _cycle(dl2, tension=5.0)
    assert dl2.level != lv1, "补足第 3 次有动力后应当升级"


# ══════════════════════════════════════════════════════════════
# G5：既有行为不被破坏（只失效不重组 = 过载，不算发展）
# ══════════════════════════════════════════════════════════════
@case("【G5】只失效不重组 → 计数不变（既有铁律不被破坏）")
def g5():
    dl = _fresh()
    e0, n0, p0 = dl.equilibration, dl.not_grown, dl.pending
    out = _fail(dl, tension=8.0)
    assert dl.equilibration == e0, "只失效不该增加平衡化计数"
    assert dl.not_grown == n0, "只失效不该增加『不计入』计数"
    assert dl.pending == p0 + 1, "pending 应当 +1"
    assert dl.failed is True, "应处于失效态"
    # 失效态下重复喂失效 → 不重复计数
    _fail(dl, tension=8.0)
    assert dl.pending == p0 + 1, "失效态下重复喂失效不该重复计数"
    # 张力不参与"失效"这一步的判断：张力 0 也会失效
    dl2 = _fresh()
    _fail(dl2, tension=0.0)
    assert dl2.failed is True, "张力为零时结构照样会失效（张力只影响**计入与否**）"


# ══════════════════════════════════════════════════════════════
# G6：张力不可测 → **放行**，但必须显式留痕
# ══════════════════════════════════════════════════════════════
@case("【G6】张力不可测时放行，但事件里必须写明『张力未测，默认放行』")
def g6():
    dl = _fresh()
    before = dl.equilibration
    out = _cycle(dl, tension=0.0, measured=False)
    assert dl.equilibration == before + 1, \
        "张力不可测时应当**放行**（防冷启动死锁），实际被拦下了"
    assert dl.not_grown == 0, "不可测不等于趋零 —— 不该记『不计入』"
    ev = out.get("event") or ""
    assert "[张力未测，默认放行]" in ev, \
        "★ 不可测时没写明放行理由 —— 这就是静默放行：%s" % ev
    # 失效那一步也要标明"未测"
    dl2 = _fresh()
    o2 = _fail(dl2, tension=0.0, measured=False)
    assert "未测" in (o2.get("event") or ""), \
        "失效事件没标出张力不可测：%s" % o2.get("event")


# ══════════════════════════════════════════════════════════════
# G7：report() 暴露 not_grown / fail_tension / tension_drive
# ══════════════════════════════════════════════════════════════
@case("【G7】report() 暴露 not_grown / fail_tension / tension_drive")
def g7():
    dl = _fresh()
    _cycle(dl, tension=0.4)
    r = dl.report()
    for k in ("not_grown", "fail_tension", "tension_drive"):
        assert k in r, "report() 缺 %s —— 界面与审计看不到" % k
    assert r["not_grown"] == 1, r["not_grown"]
    assert r["fail_tension"] == 0.4, r["fail_tension"]
    assert r["tension_drive"] == D.TENSION_DRIVE, r["tension_drive"]
    # 也确认 report 里没有任何"上沿"式的封顶（用户明令不设上沿）
    assert not any("hi" in k or "max" in k for k in r
                   if k.startswith("tension")), \
        "report 里出现了张力的上沿字段 —— 用户明令不设上沿"
    # 反向：高张力（8.0）照样计入 → 证明真的没有封顶
    dl2 = _fresh()
    b2 = dl2.equilibration
    _cycle(dl2, tension=8.0)
    assert dl2.equilibration == b2 + 1, \
        "★ 高张力（8.0）被拦下了 —— 用户明令『创伤后成长不应人为封顶』"


# ══════════════════════════════════════════════════════════════
def main() -> int:
    for name, fn in CASES:
        _run_one(name, fn)
    ok = sum(1 for _, p, _ in RESULTS if p)
    print("=" * 78)
    print("箭头 A5：张力 → 生长（T16）证伪测试")
    print("=" * 78)
    for name, passed, msg in RESULTS:
        print("  [%s] %s" % ("PASS" if passed else "FAIL", name))
        if not passed:
            print("         %s" % msg)
    print("-" * 78)
    print("结果: %d 通过 / %d 失败 / 共 %d"
          % (ok, len(RESULTS) - ok, len(RESULTS)))
    shutil.rmtree(_TMP, ignore_errors=True)
    return 0 if ok == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
