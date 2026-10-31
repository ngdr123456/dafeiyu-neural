# -*- coding: utf-8 -*-
"""跨场累积（D-011）：未解张力的持久化与衰减注入。

用户裁定（2026-10-02，第 5 步）红线：
> 「新增的跨场累积测试**必须使用 tmp_path 或临时目录隔离**，
>   **严禁自动化测试读写项目根目录下的真实 `state/mechanism_carry.json`**。」

**本文件的每条用例都先记下真实文件的"存在与否 + mtime"，
结束时再比一次 —— 任何一条碰了真实文件，直接判失败。**
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "engine"))

import carry                                   # noqa: E402
import constants as C                          # noqa: E402
from pipeline import Pipeline                  # noqa: E402

RESULTS: list = []
CASES: list = []
REAL = os.path.join(_ROOT, "state", "mechanism_carry.json")


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


def _snap_real():
    if not os.path.exists(REAL):
        return ("absent", None)
    st = os.stat(REAL)
    return ("present", (st.st_size, st.st_mtime_ns))


def _root():
    d = tempfile.mkdtemp(prefix="ego_carry_")
    os.makedirs(os.path.join(d, "state"), exist_ok=True)
    return d


def _pipe(root, tag="p"):
    d = tempfile.mkdtemp(prefix="ego_carryp_")
    return Pipeline(ledger_path=os.path.join(d, "l.jsonl"), auto_audit=False,
                    use_api=False, gate_perception=True,
                    devlevel_path=os.path.join(d, "dev.json"), carry_root=root)


# ══════════════════════════════════════════════════════════════
@case("【C1】★ 真实 state/mechanism_carry.json 全程不被碰（红线）")
def c1():
    """★ **双向物理断言 + 每步即时检查**。

    为什么必须这样写（第一版是假绿的，mutation 抓不住）：
      第一版只在**最后**查一次 `_snap_real()`，而它自己中间调了 `carry.clear(root)` ——
      mutation 让 `path()` 忽略 root、写真实路径时，
        ① `write()` 确实在真实路径建了文件
        ② 但紧接着的 `clear()` **又把那个文件删了**
        ③ 最后那次断言看到的是**已经恢复干净的现场** ⇒ 必过。
      **测试自己擦掉了自己的证据。**

    修法（用户裁定的三条，逐条落地）：
      ① **每步即时检查**：每次写/读/清之后立刻查真实路径
      ② **双向**：真实路径必须**不存在**，且临时路径必须**存在且内容合法**
         —— 让 mutation 两头都撞墙：写真实 → ① 拦；不写真实 → ② 拦
      ③ 核对有没有全局 fixture 顺手 unlink（本文件无 fixture，见文件尾）
    """
    before = _snap_real()
    root = _root()
    tmp_path = carry.path(root)

    def both_ways(step: str, tmp_should_exist: bool):
        # ① 真实路径必须不存在（存在 = 隔离破了）
        # ① 真实路径必须**未被改动**。
        #    ⚠️ 原来是「真实路径必须**不存在**」—— 那条断言在 2026-10-03 真实训练之后
        #       **自己变成了错的**：训练合法地建了 state/mechanism_carry.json（tension=8.5），
        #       于是 C1 报「隔离破了」，而其实什么都没破。
        #       **该断的是"我没碰它"，不是"它不在"**（同 test_proposal_log 的 Z8）。
        assert _snap_real() == before, \
            "★ [%s] 真实 carry 被改动了 —— 隔离破了" % step
        # ② 反向：临时路径该有时必须有（否则 mutation 可能只是"没写"）
        if tmp_should_exist:
            assert os.path.exists(tmp_path), \
                "★ [%s] 临时路径应有文件却没有 —— 写盘没走隔离路径" % step
            d = json.load(io.open(tmp_path, encoding="utf-8"))
            assert d.get("schema") == 1 and "tension" in d, \
                "★ [%s] 临时路径文件内容不合法：%s" % (step, sorted(d))

    try:
        p = _pipe(root)
        both_ways("构造 Pipeline 后", False)
        for t in ["我一定要得到那个结果", "我恨他们", "这一切都没有意义了"]:
            p.turn(t, "T08")
            both_ways("turn 之后", os.path.exists(tmp_path))

        carry.write(9.9, True, root)
        both_ways("write 之后", True)                 # ← 第一版缺这一步

        v = carry.decayed_tension(root)
        assert abs(v - 9.9) < 0.05, "读回的值不对：%.4f" % v
        both_ways("decayed_tension 之后", True)

        carry.clear(root)
        both_ways("clear 之后", False)
        assert not os.path.exists(tmp_path), "clear 应删掉**临时**路径的文件"
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ══════════════════════════════════════════════════════════════
@case("【C2】落盘格式：字段锁定为 tension / unfinished / at / schema")
def c2():
    root = _root()
    try:
        carry.write(3.5, True, root)
        p = carry.path(root)
        assert os.path.exists(p), "文件没生成"
        d = json.load(io.open(p, encoding="utf-8"))
        for k in ("tension", "unfinished", "at", "schema"):
            assert k in d, "★ 缺字段 %s：%s" % (k, sorted(d))
        assert d["schema"] == 1, d["schema"]
        assert abs(float(d["tension"]) - 3.5) < 1e-9, d["tension"]
        assert d["unfinished"] is True
        # at 必须是 ISO-8601 且**带时区**
        at = datetime.fromisoformat(d["at"])
        assert at.tzinfo is not None, "★ at 没带时区：%r" % d["at"]
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ══════════════════════════════════════════════════════════════
@case("【C3】衰减严格按自然时间：dt_h = 秒/3600，decay = 0.5**(dt_h/HALF_LIFE_H)")
def c3():
    root = _root()
    try:
        # 手工写一个"24 小时前"的 carry → 应当正好衰减一半
        p = carry.path(root)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        at = datetime.now(timezone.utc) - timedelta(hours=C.HALF_LIFE_H)
        io.open(p, "w", encoding="utf-8").write(json.dumps(
            {"tension": 8.0, "unfinished": True, "at": at.isoformat(),
             "schema": 1}, ensure_ascii=False))
        got = carry.decayed_tension(root)
        assert abs(got - 4.0) < 0.02, \
            "★ %s 小时前存的 8.0 应衰减到约 4.0，实际 %.4f" % (C.HALF_LIFE_H, got)
        # 两个小时半衰期 → 四分之一
        at2 = datetime.now(timezone.utc) - timedelta(hours=2 * C.HALF_LIFE_H)
        io.open(p, "w", encoding="utf-8").write(json.dumps(
            {"tension": 8.0, "unfinished": True, "at": at2.isoformat(),
             "schema": 1}, ensure_ascii=False))
        got2 = carry.decayed_tension(root)
        assert abs(got2 - 2.0) < 0.02, "两个半衰期应到约 2.0，实际 %.4f" % got2
        # 反证：刚存的**不该**衰减
        carry.write(8.0, True, root)
        assert abs(carry.decayed_tension(root) - 8.0) < 0.01, "刚存的不该衰减"
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ══════════════════════════════════════════════════════════════
@case("【C4】时钟回拨不许放大张力")
def c4():
    root = _root()
    try:
        p = carry.path(root)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        future = datetime.now(timezone.utc) + timedelta(hours=48)
        io.open(p, "w", encoding="utf-8").write(json.dumps(
            {"tension": 5.0, "unfinished": True, "at": future.isoformat(),
             "schema": 1}, ensure_ascii=False))
        got = carry.decayed_tension(root)
        assert got <= 5.0 + 1e-9, "★ 时钟回拨把张力**放大**了：%.4f" % got
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ══════════════════════════════════════════════════════════════
@case("【C5】注入：第二场的 _tension 初值 = 衰减后的携带值")
def c5():
    root = _root()
    try:
        carry.write(4.25, True, root)
        p2 = _pipe(root)
        assert abs(p2.mech._tension - 4.25) < 0.01, \
            "★ 第二场 _tension 初值应为 4.25，实际 %.4f" % p2.mech._tension
        # 反证：把 carry 清掉，第二场必须回到 0.0（与从前完全一致）
        carry.clear(root)
        p3 = _pipe(root)
        assert p3.mech._tension == 0.0, "清掉之后应为 0.0，实际 %r" % p3.mech._tension
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ══════════════════════════════════════════════════════════════
@case("【C6】判据：unfinished=False → 清空；True 且 tension>0 → 写；坏文件 → 当没有")
def c6():
    root = _root()
    try:
        # False → 清空
        carry.write(5.0, True, root)
        assert carry.update_from_snapshot({"unfinished": 0.0, "tension": 5.0}, root) == "cleared"
        assert not os.path.exists(carry.path(root)), "unfinished=False 应清空"
        # True 且 tension>0 → 写
        assert carry.update_from_snapshot({"unfinished": 1.0, "tension": 3.0}, root) == "written"
        assert os.path.exists(carry.path(root))
        # True 但 tension=0 → 什么都不做
        carry.clear(root)
        assert carry.update_from_snapshot({"unfinished": 1.0, "tension": 0.0}, root) == "kept"
        assert not os.path.exists(carry.path(root)), "tension=0 不该写盘"
        # 坏文件 / schema 不符 → 当没有（**不猜**）
        p = carry.path(root)
        io.open(p, "w", encoding="utf-8").write("{坏 JSON")
        assert carry.read(root) is None and carry.decayed_tension(root) == 0.0
        io.open(p, "w", encoding="utf-8").write(json.dumps(
            {"tension": 9.0, "unfinished": True, "at": "2026-01-01T00:00:00+00:00",
             "schema": 99}, ensure_ascii=False))
        assert carry.read(root) is None, "schema 不符应返回 None（不许猜）"
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ══════════════════════════════════════════════════════════════
@case("【C7】默认值向后兼容：不传 carry_root 时，首场行为与从前一致")
def c7():
    """⚠️ 这条**故意不传 carry_root** —— 但因此它会去读真实路径。
    所以先确认真实文件**不存在**，跑完立即确认仍不存在；存在则跳过（不冒险）。"""
    if os.path.exists(REAL):
        return                      # 真实文件在场 → 跳过，绝不碰
    d = tempfile.mkdtemp(prefix="ego_carryd_")
    try:
        # ⚠️ 本用例**故意不传 `carry_root`** —— 它测的就是"不传时的默认行为"。
        #    （批量脚本曾给它加上 carry_root=d，**恰好把这条测试的用意抹掉了**。）
        #    `gate_perception` 仍要显式传 —— 那是 G12 的红线，与本条无关。
        p = Pipeline(ledger_path=os.path.join(d, "l.jsonl"), auto_audit=False,
                     use_api=False, gate_perception=False)
        assert p.mech._tension == 0.0, \
            "真实 carry 不存在时，首场 _tension 应为 0.0（向后兼容）"
        # ★ C7 的安全性证明（用户裁定：只读不写）
        #   C7 **只构造 Pipeline、不调 turn()** —— 写盘发生在 turn() 里，
        #   所以本条**不可能**产生写盘。这里把它钉死：
        #     ① 真实路径仍不存在
        assert not os.path.exists(REAL), \
            "★ C7 在真实路径留下了文件 —— 违反铁律：自动化测试不许写真实 state/"
        #     ② 构造过程本身也没建任何东西（临时目录里不该有 carry）
        assert not os.path.exists(carry.path(d)), \
            "★ C7 不该产生任何 carry 文件（它只构造，不跑轮）"
        #     ③ 反向确认"确实读了真实路径"（否则这条测试是空转）
        assert carry.path(None) == REAL, \
            "不传 carry_root 时，路径解析应指向真实 state/（本条的前提）"
    finally:
        shutil.rmtree(d, ignore_errors=True)


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
    print("跨场累积（D-011）")
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
