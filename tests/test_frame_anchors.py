# -*- coding: utf-8 -*-
"""F1-F6：Frame 接入具体支点（2026-10-28，改动 ①，用户已批）。

★ 病灶：`_pick_anchor` 与 `_pick_concrete` 只活在 renderer 路径，
  而 renderer 在训练中从不执行 ⇒ 她从来没拿到过具体支点 ⇒ 只说"没听出什么"+原话
  ⇒ 只能把原话换个语序还回去（= 回声）。

★ 判据（先写）：
  F1 有具体锚点时，Frame.anchor 非空且**逐字出现在原话里**
  F2 有体验词时，Frame.concrete 是那一小句（如「风挺凉」）
  F3 ★ 没有体验词时，Frame.concrete **不得**接近整句（守卫）
  F4 简报里出现三栏标题
  F5 取不到就空着，不补假锚点（"不许编"）
  F6 stance 来自机制相位；无相位时给一句"别复述整句"的兜底
"""
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)
sys.path[:0] = [str(_ROOT), str(_ROOT + "/engine")]

from pipeline import Pipeline  # noqa: E402

OK = 0
FAIL = 0


def case(name, cond, why=""):
    global OK, FAIL
    if cond:
        OK += 1
        print("  [PASS] 【%s】" % name)
    else:
        FAIL += 1
        print("  [FAIL] 【%s】%s" % (name, why))


def build(raw):
    d = tempfile.mkdtemp()
    p = Pipeline(ledger_path=os.path.join(d, "state/ledger.jsonl"),
                 character_path=os.path.join(d, "state/character.json"),
                 devlevel_path=os.path.join(d, "state/devlevel_verified.json"),
                 carry_root=d, gate_perception=True, auto_audit=False,
                 use_api=False, use_think=False)
    p._input_origin = None
    p.turn("随便说一句先垫上。")
    pr = p.markers.parse(raw)
    return p._build_frame(raw, pr, mst=None)


print("=" * 78)
print("  Frame 接入具体支点（F1-F6）")
print("=" * 78)

# ── F1 ★ 锚点逐字出现在原话里
raw = "那天晚上我坐在楼下，风挺凉的。"
fr = build(raw)
case("F1 ★ 有锚点时 Frame.anchor 非空且逐字出现在原话里",
     bool(fr.anchor) and fr.anchor in raw,
     "anchor=%r" % fr.anchor)

# ── F2 体验词那一小句
case("F2 ★ 有体验词时 concrete 是那一小句",
     "风" in fr.concrete and len(fr.concrete) < len(raw),
     "concrete=%r｜raw len=%d" % (fr.concrete, len(raw)))

# ── F3 ★ 没有体验词时，concrete 不得接近整句
raw3 = "你说我这是不是有点毛病啊。"
fr3 = build(raw3)
case("F3 ★ 无体验词时 concrete 不接近整句（守卫生效）",
     (not fr3.concrete) or len(fr3.concrete) <= 0.6 * len(raw3),
     "concrete=%r（原话 %d 字）" % (fr3.concrete, len(raw3)))

# ── F4 三栏标题都在
txt = fr.user_text()
case("F4 简报里有三栏标题",
     "画面或触感" in txt and "具体锚点" in txt and "行动姿态" in txt,
     "画面或触感=%s 具体锚点=%s 行动姿态=%s"
     % ("画面或触感" in txt, "具体锚点" in txt, "行动姿态" in txt))

# ── F5 取不到就空着
raw5 = "嗯。"
fr5 = build(raw5)
case("F5 取不到就空着，不补假锚点",
     fr5.anchor == "" or fr5.anchor in raw5,
     "anchor=%r" % fr5.anchor)

# ── F6 stance 兜底
case("F6 stance 有兜底（无相位时提醒别复述整句）",
     "别复述整句" in (fr5.stance or ""),
     "stance=%r" % (fr5.stance or "")[:40])

print("-" * 78)
print("结果: %d 通过 / %d 失败 / 共 %d" % (OK, FAIL, OK + FAIL))
print()
print("MUTATION 表")
print("  MUT-A 去掉 concrete 的 60% 守卫        → F3")
print("  MUT-B 不传 anchor（恒空）              → F1")
print("  MUT-C 简报里删掉三栏                    → F4")
sys.exit(1 if FAIL else 0)
