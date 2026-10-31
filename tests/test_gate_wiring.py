# -*- coding: utf-8 -*-
"""T33 联调：箭头 A1 感知门控**通电**后的端到端接线验证。

⚠️ 这个测试与 `test_devlevel_growth.py` / `test_attitude_freedom.py` / `test_paths.py`
   **不是一回事**：
       那三个直接调 `DevLevel` / `Mechanism` —— 验的是"零件对不对"
       **这个走 `Pipeline`** —— 验的是"零件接上了没有"
   门控造好之后一直没通电，接缝从没被端到端跑过。通电才是 T33 的全部内容。

断言分六组（用户批准的 12 项）
────────────────────────────────────────────────────────────
    G1 门控真的在过滤（不是"看见了忍住不用"）
    G2 自我规则按水平解锁
    G3 机制快照里带 dev 一节
    G4 态度句跨水平豁免
    G5 创造途径恒为 0（诚实缺位不许被"修好"）
    G6 行为差异（关 vs 开，确定性前提）

⚠️ 一处**方案里的错断言，已纠正**（探测实际字节时发现）：
   方案原写「起始 I-3：断言 self_rules() **不含 R1**」—— **这是错的**。
   `_RULE_UNLOCK = {'R1': 'I-1', 'R3': 'I-3/4', 'R2': 'I-4'}` 的语义是
   **"从该水平起可用"**，所以 I-3 时 R1 **已经在**。
   实测：I-1/I-2/I-3 → ['R1']｜I-3/4 → ['R1','R3']｜I-4 → ['R1','R2','R3']。
   照原方案写会**假失败**。这里按实测写。

G6 的确定性前提（用户要求钉死）
────────────────────────────────────────────────────────────
    · 同一串输入
    · `use_api=False` —— **离线规则引擎，不发任何网络请求**
    · 固定话题 id
    否则模型噪声会污染"关 vs 开"的 diff。
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

from pipeline import Pipeline, _gate_on          # noqa: E402

RESULTS: list = []
CASES: list = []


def case(name):
    def deco(fn):
        CASES.append((name, fn))
        return fn
    return deco


def _strip_literals(src: str) -> str:
    """把三引号串、普通字符串、注释替换成等长空白（保持行列号不变）。"""
    out = list(src)
    i, n = 0, len(src)
    DQ3 = chr(34) * 3
    SQ3 = chr(39) * 3
    while i < n:
        if src.startswith(DQ3, i) or src.startswith(SQ3, i):
            q = src[i:i + 3]
            j = src.find(q, i + 3)
            j = n if j < 0 else j + 3
            for k in range(i, j):
                if out[k] != "\n":
                    out[k] = " "
            i = j
        elif src[i] == "#":
            j = src.find("\n", i)
            j = n if j < 0 else j
            for k in range(i, j):
                out[k] = " "
            i = j
        elif src[i] in (chr(34), chr(39)):
            q = src[i]
            j = i + 1
            while j < n and src[j] != q:
                if src[j] == "\\":
                    j += 1
                j += 1
            j = min(j + 1, n)
            for k in range(i, j):
                if out[k] != "\n":
                    out[k] = " "
            i = j
        else:
            i += 1
    return "".join(out)


def fresh(gate: bool | None, **kw) -> tuple:
    """★ 走 Pipeline —— 通电与不通电的唯一区别就是这个参数。"""
    d = tempfile.mkdtemp(prefix="ego_gate_")
    p = Pipeline(ledger_path=os.path.join(d, "ledger.jsonl"),
                 auto_audit=False, use_api=False,        # ★ 离线，确定性
                 gate_perception=gate,
                 devlevel_path=os.path.join(d, "devlevel.json"), **kw, carry_root=d)
    return p, d


INPUTS = ["大家都这样，我也没办法。", "这不公平。", "我不知道该怎么办。",
          "他们应该对我好一点。", "我总是做不好。"]


# ══════════════════════════════════════════════════════════════
@case("【G1】门控真的在过滤：通电后标记按水平过滤，且是「根本没进入检测」")
def g1():
    p, d = fresh(True)
    try:
        assert p.devlevel is not None, "通电后必须建出 DevLevel"
        # 跑一轮，门控会在 pipeline 里刷新 markers.visible
        p.turn(INPUTS[0], "T08")
        assert p.markers.visible is not None, "通电后 markers.visible 必须被门控接管"
        assert set(p.markers.visible) == set(p.devlevel.visible()), \
            "pipeline 里的可见集必须等于 devlevel 算出来的"
        # 核心：存在带 level_hint 的标记，它**不在**可见集里
        gated = [m["id"] for m in p.devlevel.rules if m.get("level_hint")]
        hid = [m for m in gated if m not in p.markers.visible]
        assert gated, "前提失效：规则里应有带 level_hint 的标记"
        assert hid, ("★ 必须至少有一个带 level_hint 的标记不可见 —— "
                     "否则证明不了门控在过滤。带 hint 的：%s" % gated)
        # 而这些被挡掉的标记，本轮也没出现在识别结果里
        #   ⚠️ 实际字段是 `markers_fired`（第一版写成 `decision["markers"]` —— 没这个字段）
        assert not (set(hid) & set(p.ledger.entries[-1].markers_fired or [])), \
            "被门控挡掉的标记不该出现在识别结果里"
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ══════════════════════════════════════════════════════════════
@case("【G1-b】不通电时 devlevel 是 None（默认关，回退通道）")
def g1b():
    p, d = fresh(False)
    try:
        assert p.devlevel is None, "显式关掉时不该建 DevLevel"
        r = p.turn(INPUTS[0], "T08")
        assert r.markers, "不通电时管线照常工作"
        assert "dev" not in (p._last_mech or {}), "不通电时机制快照里不该有 dev"
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ══════════════════════════════════════════════════════════════
@case("【G2】自我规则按水平解锁（★ 按实测，不是按方案初稿）")
def g2():
    p, d = fresh(True)
    try:
        dl = p.devlevel
        got = {}
        for lv in ("I-1", "I-2", "I-3", "I-3/4", "I-4", "I-5"):
            dl.level = lv
            got[lv] = set(dl.self_rules())
        # 实测：R1 从 I-1 起就可用（_RULE_UNLOCK 的语义是"从该水平起"）
        assert got["I-1"] == {"R1"}, "I-1 应只有 R1，实际 %s" % got["I-1"]
        assert got["I-3"] == {"R1"}, "I-3 仍只有 R1，实际 %s" % got["I-3"]
        assert got["I-3/4"] == {"R1", "R3"}, "I-3/4 应加 R3，实际 %s" % got["I-3/4"]
        assert got["I-4"] == {"R1", "R2", "R3"}, "I-4 应三条齐，实际 %s" % got["I-4"]
        # ★ A2 的设计要求：**没介入时要说清是"不需要"还是"还行使不了"**
        q, dq = fresh(True)
        try:
            q.turn(INPUTS[0], "T08")
            notes = " ".join(q.ledger.entries[-1].notes or [])
            assert "A2" in notes, "台账 notes 里应有 A2 的说明：%s" % notes[:160]
            assert "当前可行使" in notes, \
                "A2 提示要说清「当前可行使」哪几条：%s" % notes[:160]
        finally:
            shutil.rmtree(dq, ignore_errors=True)
        # 单调不减
        order = ["I-1", "I-2", "I-3", "I-3/4", "I-4", "I-5"]
        for a, b in zip(order, order[1:]):
            assert got[a] <= got[b], "规则集必须随水平单调不减：%s ⊄ %s" % (got[a], got[b])
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ══════════════════════════════════════════════════════════════
@case("【G3】机制快照里带 dev 一节，且 visible_n 与实际一致")
def g3():
    p, d = fresh(True)
    try:
        p.turn(INPUTS[0], "T08")
        snap = p._last_mech or {}
        assert "dev" in snap, "通电后机制快照必须带 dev 一节：%s" % sorted(snap)
        dev = snap["dev"]
        for k in ("level", "equil", "self_rules", "visible_n"):
            assert k in dev, "dev 一节缺字段 %s：%s" % (k, dev)
        assert dev["visible_n"] == len(p.markers.visible), \
            "visible_n 必须等于实际可见标记数：%s vs %s" % (dev["visible_n"],
                                                        len(p.markers.visible))
        assert dev["level"] == p.devlevel.level
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ══════════════════════════════════════════════════════════════
@case("【G4】态度句跨水平豁免（A4）：高 level_hint 也照样可见")
def g4():
    p, d = fresh(True)
    try:
        dl = p.devlevel
        pe = dl.path_exempt()
        assert "attitude_clause" in pe, "态度句必须在豁免集里：%s" % pe
        # 直接问：给一个远高于当前水平的 hint，但身份是 attitude_clause
        assert dl.can_see("I-6", "attitude_clause") is True, \
            "态度句必须无条件放行（箭头 A4）"
        # 反证：同一个高强度 hint，但换一个**不在**豁免集里的标记 → 应被挡
        other = next((m["id"] for m in dl.rules
                      if m.get("level_hint") == "I-6" and m["id"] not in pe), None)
        if other is None:
            other = next((m["id"] for m in dl.rules
                          if m.get("level_hint") and m["id"] not in pe), None)
        if other:
            hi = next(m["level_hint"] for m in dl.rules if m["id"] == other)
            dl.level = "I-1"
            assert dl.can_see(hi, other) is False, \
                "非豁免标记在高 hint 下必须被挡（%s / %s）" % (other, hi)
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ══════════════════════════════════════════════════════════════
@case("【G5】创造途径恒为 0 —— 通电也不许把它「修好」（T17 红线）")
def g5():
    p, d = fresh(True)
    try:
        for t in INPUTS:
            p.turn(t, "T08")
        snap = p._last_mech or {}
        assert float(snap.get("path_creative") or 0.0) == 0.0, \
            "path_creative 必须恒为 0：%s" % snap.get("path_creative")
        assert int(snap.get("path_cre") or 0) == 0, \
            "path_cre 必须恒为 0：%s" % snap.get("path_cre")
        # 源码级：不许出现非 0 的赋值
        src = io.open(os.path.join(_ROOT, "engine", "mechanism.py"),
                      encoding="utf-8").read()
        for line in src.splitlines():
            s = line.strip()
            if s.startswith("path_creative=") and "0.0" not in s:
                raise AssertionError("path_creative 被赋了非 0 值：%s" % s)
            if s.startswith("path_cre=") and "_cnt_cre" not in s:
                raise AssertionError("path_cre 被赋了别的值：%s" % s)
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ══════════════════════════════════════════════════════════════
@case("【G6】★ 行为差异：同一输入、离线、门控关 vs 开")
def g6():
    """确定性前提：同输入 + use_api=False + 固定话题 id。"""
    off, d1 = fresh(False)
    on, d2 = fresh(True)
    try:
        roff = [off.turn(t, "T08") for t in INPUTS]
        ron = [on.turn(t, "T08") for t in INPUTS]
        assert len(roff) == len(ron) == len(INPUTS)
        # ① 不通电时，识别结果与门控无关（可见集是 None）
        assert off.markers.visible is None, "不通电时 visible 应是 None"
        assert on.markers.visible is not None, "通电时 visible 应是集合"
        # ② 通电后，被挡掉的标记确实不进识别结果
        #   ⚠️ `hidden()` 返回的是 [{"id":…,"label":…,"needs":…}]，不是 id 列表
        blocked = [h["id"] for h in (on.devlevel.hidden() or [])]
        for r in ron:
            assert not (set(blocked) & set(r.markers)), \
                "被挡掉的标记 %s 出现在了识别结果里" % (set(blocked) & set(r.markers))
        # ③ 台账轮数一致（门控不该改变"跑了几轮"）
        assert off.ledger.turns() == on.ledger.turns() == len(INPUTS)
        # ④ 两条路径都留下了可审计的记录
        assert all(e.counterfactual for e in off.ledger.entries), "关：反事实不可为空"
        assert all(e.counterfactual for e in on.ledger.entries), "开：反事实不可为空"
    finally:
        shutil.rmtree(d1, ignore_errors=True)
        shutil.rmtree(d2, ignore_errors=True)


# ══════════════════════════════════════════════════════════════
@case("【G9】★ 升水平后 markers.visible 必须刷新（mutation M3 抓出的缺口）")
def g9():
    """M3 把 `self.markers.visible = self.devlevel.visible()` 改成 `pass`，
    这条**当时没被抓到** —— 因为构造时已经塞过一次 visible，
    刷新那一行只在**水平变化**时才起作用，而我的测试从没让水平在轮内变过。

    这里补上：逼出两次升水平（I-3 → I-3/4 → I-4），
    **I-4 的可见数是 10，I-3/I-3/4 都是 9** —— 差 1 个，可观测。
    """
    from devlevel import ERROR_HIGH
    p, d = fresh(True)
    try:
        p.turn(INPUTS[0], "T08")                    # e=0.01 ≤ ERROR_LOW，可完成平衡化
        assert p.devlevel.level == "I-3", p.devlevel.level
        n0 = len(p.markers.visible)
        assert n0 == 9, "I-3 应有 9 个可见，实际 %d" % n0

        # 显示接线探针：计数凑到 PER_LEVEL-1，并通过公开 update 观测本场失效。
        # 这不是自然生长的证据；跨场防伪另有真实 Pipeline 回归。
        for _ in range(2):
            p.devlevel.equilibration = (p.devlevel.equilibration // 3) * 3 + 2
            p.devlevel.update({"e": ERROR_HIGH, "tension": 99.0,
                               "tension_measured": True})
            p.turn(INPUTS[0], "T08")
        assert p.devlevel.level == "I-4", \
            "两次升水平后应到 I-4，实际 %s（equil=%d）" % (p.devlevel.level,
                                                        p.devlevel.equilibration)
        # ★ 核心：管线里的可见集必须跟着刷新到 10
        assert len(p.markers.visible) == 10, \
            ("★ 升到 I-4 后 markers.visible 必须刷新成 10 个，实际 %d —— "
             "这正是 pipeline.py 里「门控刷新」那一行在管的事" % len(p.markers.visible))
        assert set(p.markers.visible) == set(p.devlevel.visible()), \
            "刷新后两者必须一致"
        # 机制快照里的 visible_n 也要跟上
        assert (p._last_mech or {}).get("dev", {}).get("visible_n") == 10, \
            "机制快照的 visible_n 也要刷新：%s" % (p._last_mech or {}).get("dev")
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ══════════════════════════════════════════════════════════════
@case("【G7】_gate_on 的优先级与大小写（通电入口的唯一判据）")
def g7():
    saved = os.environ.get("EGO_GATE_PERCEPTION")
    try:
        for v, want in (("1", True), ("true", True), ("TRUE", True), ("True", True),
                        ("tRuE", True), ("on", True), ("ON", True), ("yes", True),
                        ("  1  ", True),
                        ("0", False), ("false", False), ("off", False),
                        ("no", False), ("", False), ("banana", False), ("2", False)):
            os.environ["EGO_GATE_PERCEPTION"] = v
            assert _gate_on() is want, "EGO_GATE_PERCEPTION=%r 应为 %s" % (v, want)
        os.environ.pop("EGO_GATE_PERCEPTION", None)
        assert _gate_on() is False, "未设置时应为关"
        # 显式参数优先
        os.environ["EGO_GATE_PERCEPTION"] = "1"
        assert _gate_on(False) is False, "显式 False 必须压过环境变量"
        assert _gate_on(True) is True
    finally:
        if saved is None:
            os.environ.pop("EGO_GATE_PERCEPTION", None)
        else:
            os.environ["EGO_GATE_PERCEPTION"] = saved


# ══════════════════════════════════════════════════════════════
@case("【G8】源码级：_gate_on 全项目只定义一处（单一事实来源）")
def g8():
    hits = []
    for sub in ("engine", "tests", "tools"):
        dd = os.path.join(_ROOT, sub)
        if not os.path.isdir(dd):
            continue
        for f in sorted(os.listdir(dd)):
            if not f.endswith(".py"):
                continue
            src = io.open(os.path.join(dd, f), encoding="utf-8").read()
            for line in src.splitlines():
                if line.startswith("def _gate_on(") or line.strip().startswith("def _gate_on("):
                    hits.append("%s/%s" % (sub, f))
    assert hits == ["engine/pipeline.py"], \
        "★ _gate_on 只能定义在 engine/pipeline.py 一处，实际：%s" % hits
    # train.py 必须是**导入**，不是自己抄一份
    tr = io.open(os.path.join(_ROOT, "engine", "train.py"), encoding="utf-8").read()
    assert "from pipeline import Pipeline, _gate_on" in tr, \
        "train.py 必须从 pipeline 导入 _gate_on"


# ══════════════════════════════════════════════════════════════
@case("【G10】★ T33 接线范围必须是**冻结**的 19 条（方案甲）")
def g10():
    """用户裁定：
       > 「接线清单是 T33 的工程交付基准，**不能因单元通电成功而在报表里自我蒸发**。」

    第一版 consensus.py 的判据是 `if 运行状态 == "生效中": continue` ——
    5 个单元一通电，属于它们的 12 条就从清单里消失了（19 → 7）。
    """
    import subprocess
    r = subprocess.run([sys.executable, "-B",
                        os.path.join(_ROOT, "engine", "consensus.py")],
                       capture_output=True, text=True, encoding="utf-8")
    out = (r.stdout or "") + (r.stderr or "")
    assert "T33 接线范围（冻结）" in out, "控制台应打印冻结的接线范围：\n%s" % out[-400:]
    assert "19 条命中" in out, "冻结的接线范围必须是 19 条：\n%s" % out[-400:]
    # 报告文件里也要有那一节，且标题写明"冻结"
    rep = io.open(os.path.join(_ROOT, "spec", "共识核报告.md"),
                  encoding="utf-8").read()
    assert "T33 接线范围（**冻结**，不随运行状态变化）" in rep, "报告缺少冻结小节"
    assert "合计 19 条命中" in rep, "报告里冻结小节应写 19 条"
    assert "不随通电变化" in rep, "报告要明说这一节不随通电变化"
    # 而「运行状态」一节反映**当前真实状态** ——
    #   ⚠️ 这里**不许写死具体数字**：翻正是「验收关闭时」才做的动作，
    #      盘上现在是 96/5/2（未翻正）还是 101/0/2（已翻正）都合法。
    #      冻结节才是不随它变的那一半 —— 上面那两条断言锁的正是它。
    import re as _re
    m = _re.search(r"\| 生效中 \| (\d+) \|", rep)
    assert m, "运行状态一节缺少「生效中」行"
    m2 = _re.search(r"\| 已建未启用 \| (\d+) \|", rep)
    assert m2, "运行状态一节缺少「已建未启用」行"
    assert int(m.group(1)) + int(m2.group(1)) == 101, \
        "生效中 + 已建未启用 应等于 101（103 减 2 个仅落账）：%s + %s" % (m.group(1), m2.group(1))
    # 源码级：判据不许是"当前值"
    src = io.open(os.path.join(_ROOT, "engine", "consensus.py"),
                  encoding="utf-8").read()
    #   ⚠️ 判据必须是**显式常量** `S.DEV_UNIT_IDS`，不是「带 status 键」这种间接判据，
    #      也不是「当前值 == 生效中」。前者会因给老单元加个字段而悄悄扩大范围，
    #      后者会让交付基准在通电时蒸发。
    #   ⚠️ 必须**直连导入**：`from system_map import DEV_UNIT_IDS`
    #      （用户第二次点名 —— `import system_map as S` 再取属性只算做了一半）
    assert "from system_map import DEV_UNIT_IDS" in src, \
        "判据必须 `from system_map import DEV_UNIT_IDS` 直连导入"
    assert "S.DEV_UNIT_IDS" not in src, "不许用运行期属性查找"
    assert "_by_unit" not in src, "★ 不许再用「带 status 键」那种间接判据"
    assert 'r["运行状态"] == "生效中"' not in src, \
        "★ 判据不许再用「当前值 == 生效中」——那会让交付基准蒸发"
    # 且常量本身必须是显式 7 个 id，并与 _DEV_UNITS 表同源
    sys.path.insert(0, os.path.join(_ROOT, "engine"))
    import system_map as _S
    assert len(_S.DEV_UNIT_IDS) == 7, "DEV_UNIT_IDS 应为 7 个"
    assert tuple(u[0] for u in _S._DEV_UNITS) == _S.DEV_UNIT_IDS, \
        "DEV_UNIT_IDS 必须与 _DEV_UNITS 表逐条同源"


# ══════════════════════════════════════════════════════════════
@case("【G11】★ 给**老单元**加 status 键，冻结节必须逐字不变（用户第二次点名）")
def g11():
    """冻结节判据必须是**显式 id 集合**，不是「带 status 键」。

    这条测试就是那条判据的反证：给一个老单元（marker:opposed_pair）加一个
    纯粹的 status 字段 —— 没改任何真实状态 —— 冻结节必须**逐字不变**。

    ⚠️ 第一版判据用「带 status 键」，这种改动会让接线范围**悄悄膨胀**，
       而没人会注意到。用户两次点名要这条。
    """
    sys.path.insert(0, os.path.join(_ROOT, "engine"))
    import system_map as S
    import consensus as _C

    def run():
        import importlib
        importlib.reload(_C)
        buf, old = io.StringIO(), sys.stdout
        sys.stdout = buf
        try:
            _C.main()
        finally:
            sys.stdout = old
        return buf.getvalue()

    _orig = S.collect
    base = run()                      # 基线
    assert "19 条命中" in base, "基线就该是 19 条：\n%s" % base[-300:]

    def patched():
        out = _orig()
        for u in out:
            if u["id"] == "marker:opposed_pair":     # 一个**老**单元
                u["status"] = "已建未启用"            # 只加字段，不改真实状态
        return out

    S.collect = patched
    try:
        import importlib
        importlib.reload(_C)
        buf, old = io.StringIO(), sys.stdout
        sys.stdout = buf
        try:
            _C.main()
        finally:
            sys.stdout = old
        after = buf.getvalue()
    finally:
        S.collect = _orig
        import importlib
        importlib.reload(_C)

    assert "19 条命中" in after, \
        ("★ 给老单元加 status 键后，冻结节**变了** —— 说明判据还是间接的：\n%s"
         % after[-400:])
    # 逐字：那一行的命中数必须完全一致
    import re as _re
    n0 = _re.search(r"T33 接线范围（冻结）：(\d+) 条命中", base)
    n1 = _re.search(r"T33 接线范围（冻结）：(\d+) 条命中", after)
    assert n0 and n1 and n0.group(1) == n1.group(1) == "19", \
        "冻结节必须逐字不变：基线 %s，加字段后 %s" % (n0 and n0.group(1), n1 and n1.group(1))
    # 判据本身必须是直连导入的常量
    src = io.open(os.path.join(_ROOT, "engine", "consensus.py"), encoding="utf-8").read()
    assert "from system_map import DEV_UNIT_IDS" in src, \
        "必须 `from system_map import DEV_UNIT_IDS` 直连导入（单一事实来源）"
    assert "S.DEV_UNIT_IDS" not in src, "不许再用 S.DEV_UNIT_IDS 这种运行期属性查找"


# ══════════════════════════════════════════════════════════════
@case("【G12】★ 防环境泄漏：test_*.py 里每个构造点必须**显式传** gate_perception")
def g12():
    """用户裁定：
       > 「环境泄漏防呆仍无证据。需要关态的测试一律**显式传 False** 或
       >   setUp 清掉 EGO_GATE_PERCEPTION……今天 16/16 全绿证明不了这件事 ——
       >   它防的是环境变量被 `setx` 后**全部测试静默切形态**。」

    这条就是那个防呆：**任何 test_*.py 里的 Pipeline()/Trainer() 都必须显式传
    `gate_perception=`**，不许依赖环境变量。
    """
    import re as _re
    bad = []
    td = os.path.join(_ROOT, "tests")
    for f in sorted(os.listdir(td)):
        if not (f.startswith("test_") and f.endswith(".py")):
            continue
        raw = io.open(os.path.join(td, f), encoding="utf-8").read()
        #   ⚠️ 必须先**剥掉字符串与注释**再扫。
        #      第一版没剥 —— 于是这条测试把**自己的 docstring**（里面举例写了
        #      `Pipeline()/Trainer()`）当成了构造点，**自己把自己判失败**。
        #      判据要扫代码，不是扫文字。
        src = _strip_literals(raw)
        for m in _re.finditer(r"(Pipeline|Trainer)\(", src):
            i = m.end(); depth = 1
            while i < len(src) and depth:
                if src[i] == "(": depth += 1
                elif src[i] == ")": depth -= 1
                i += 1
            if "gate_perception" not in src[m.start():i]:
                bad.append("%s:%d %s()" % (f, src[:m.start()].count("\n") + 1, m.group(1)))
    assert not bad, ("★ 这些构造点没显式传 gate_perception —— "
                     "环境变量一 setx，它们会静默切形态：\n    " + "\n    ".join(bad))


# ══════════════════════════════════════════════════════════════
@case("【G13】★ 防环境泄漏：把 EGO_GATE_PERCEPTION 设成 1，关态路径必须不受影响")
def g13():
    """G12 是源级；这条是**运行期实跑**。

    做法：在 `EGO_GATE_PERCEPTION=1` 的环境下，用 `gate_perception=False`
    显式建 Pipeline —— 它必须**仍然是关态**（devlevel is None）。
    再反证：不传参数时，它必须**真的通电**（否则环境变量根本没生效，防呆是假的）。
    """
    saved = os.environ.get("EGO_GATE_PERCEPTION")
    os.environ["EGO_GATE_PERCEPTION"] = "1"
    try:
        p_off, d1 = fresh(False)
        try:
            assert p_off.devlevel is None, \
                "★ 环境变量=1 时，显式传 False 必须仍然关态 —— 这是回退通道"
        finally:
            shutil.rmtree(d1, ignore_errors=True)
        p_on, d2 = fresh(None)
        try:
            assert p_on.devlevel is not None, \
                "★ 反证失败：不传参数时环境变量应生效（否则这条防呆是假的）"
        finally:
            shutil.rmtree(d2, ignore_errors=True)
    finally:
        if saved is None:
            os.environ.pop("EGO_GATE_PERCEPTION", None)
        else:
            os.environ["EGO_GATE_PERCEPTION"] = saved


# ══════════════════════════════════════════════════════════════
@case("【G15】★ 真实落盘：跑一轮真实 Pipeline 之后，devlevel.json **必须存在**")
def g15():
    """用户裁定（2026-10-02）：
       > 「补齐测试防呆：在 tests/test_gate_wiring.py 中新增**真实文件落盘断言**（G15），
       >   必须通过**真实 Pipeline 调用**验证物理文件生成，
       >   **严禁仅靠人工 mock e 绕过落盘检查**。」

    为什么必须有这条（本项目第 4 次「测试全绿≠真生效」）：
      `save()` 原来挂在 `if ev:` 里，而 `ev` 只在「结构失效」或「平衡化完成」时非空。
      `e >= ERROR_HIGH(0.60)` **构造上不可达**（见 spec/阈值可达性审计.md 第 4 条）
      ⇒ `ev` 恒 None ⇒ `save()` 从不被调用 ⇒ **文件从不生成**。
      而当时 19/19 全绿 —— 因为 G1~G14 全部**人为喂 e**（如 G9 直接置 failed=True），
      **没有一条验过"真实跑一轮之后，文件在不在"**。

    ⚠️ 本条**故意不喂任何 e、不置任何标志** —— 只跑一次真实 turn()。
    """
    import json
    import tempfile
    d = tempfile.mkdtemp(prefix="ego_g15_")
    dp = os.path.join(d, "devlevel.json")
    try:
        assert not os.path.exists(dp), "前提失效：跑之前文件不该存在"
        p = Pipeline(ledger_path=os.path.join(d, "l.jsonl"), auto_audit=False,
                     use_api=False,                      # 离线，确定性
                     gate_perception=True, devlevel_path=dp, carry_root=d)
        assert p.devlevel is not None, "门控未通电"
        # ★ **一次真实 turn，不喂 e、不置标志**
        p.turn(INPUTS[0], "T08")
        assert os.path.exists(dp), \
            ("★ 真实跑一轮后 devlevel.json **仍未生成** —— "
             "落盘没有接在真实路径上（只读显示在真机上会永远显示「尚未开始」）")
        o = json.load(io.open(dp, encoding="utf-8"))
        # 稳态四字段（用户指定的格式）
        assert o.get("level") == "I-3", "稳态 level 应为 I-3：%r" % o.get("level")
        assert o.get("equilibration") == 0, o.get("equilibration")
        assert o.get("not_grown") == 0, o.get("not_grown")
        assert isinstance(o.get("updated"), str) and len(o["updated"]) >= 10, \
            "updated 应是真实时间戳：%r" % o.get("updated")
        # 每个真相必须存在（面板依赖这四个键）
        for k in ("level", "equilibration", "not_grown", "updated"):
            assert k in o, "面板依赖的键缺 %s：%s" % (k, sorted(o))
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
    print("T33 联调：箭头 A1 感知门控通电（走 Pipeline）")
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
