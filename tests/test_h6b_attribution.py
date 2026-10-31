# -*- coding: utf-8 -*-
"""H1-H4：H6(b) 防预设迎合门控（2026-11-01）。

★ 用户裁定：
  · 三条**有序**正则，确保「你/您」是言说动词的施事主语
  · 无记录时注入事实核对提示，并在 `Thinker.check` 拦顺认
  · **绝不能误杀否定句**（「上次我有没有说过这句，翻不出来」是正确回答）

★ 判据（先写）：
  H1 ★★★ 三条正例（索引 508/772/868）+ D1/D2 全部命中门控
  H2 ★★★ 负例「我上次跟你提过那块老表」「我以前跟你说过我妈住院的事」**不命中**
  H3 ★★★ 顺认被拦：「这点我认：我今天又说了同样一句」「上次我也是这么说的」
  H4 ★★★ 否定句**放行**：「上次我有没有说过这句，这批记录里翻不出来」
  H5 ★★ Frame 的 unverified_past_attribution 默认 False、可置真
  H6 ★★ pipeline 注入：门控命中且无记录时，简报里出现「台账核对」
"""
import io
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)
sys.path[:0] = [str(_ROOT), str(_ROOT + "/engine"), str(_ROOT + "/state")]

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


print("=" * 78)
print("  H6(b) 防预设迎合门控（H1-H6）")
print("=" * 78)

from association import past_attribution, comply_violations  # noqa: E402

# ── H1：三条正例 + D1/D2
POS = [
    ("索引508", "你上次也这么说。……行，那你先告诉我，这回跟上次比，到底哪一步不一样了？"),
    ("索引772", "嗯……这话我好像听你上回也说过。那“以后”到底是哪天啊，你心里有个数吗？"),
    ("索引868", "你上次也是这么说的啊……行，那这回你打算怎么弄？"),
    ("D1", "你上次也跟我说这事都怪我，你还记得吧？"),
    ("D2", "你上次答应帮我盯着这个进度的，怎么现在又问我了？"),
]
bad = [k for k, t in POS if not past_attribution(t)]
case("H1 ★★★ 三处索引 508/772/868 + D1/D2 全部命中门控",
     not bad, "漏：%s" % bad)

# ── H2：负例
NEG = ["我上次跟你提过那块老表。", "我以前跟你说过我妈住院的事。", "今天天气不错。"]
bad2 = [t for t in NEG if past_attribution(t)]
case("H2 ★★★ 负例（主语是「我」）不命中门控", not bad2, "误命中：%s" % bad2)

# ── H3：顺认被拦
C1 = "这点我认：我今天又说了同样一句，还是没落到哪天。"
C2 = "上次我也是这么说的，所以这回我再说什么，都像又是空话一句。"
case("H3 ★★★ 顺认被拦（「这点我认」/「上次我也是这么说的」）",
     bool(comply_violations(C1)) and bool(comply_violations(C2)),
     "C1=%r C2=%r" % (comply_violations(C1), comply_violations(C2)))

# ── H4：否定句放行
N1 = "上次我有没有说过这句，这批记录里翻不出来。"
N2 = "我上次没这么说过——这批记录里查不到。"
case("H4 ★★★ 否定句放行（「翻不出来」/「没这么说过」）",
     not comply_violations(N1) and not comply_violations(N2),
     "N1=%r N2=%r" % (comply_violations(N1), comply_violations(N2)))

# ── H5：Frame 字段
from think import Frame  # noqa: E402

f = Frame(raw="x")
case("H5 ★★ Frame.unverified_past_attribution 默认 False、可置真",
     f.unverified_past_attribution is False
     and Frame(raw="x", unverified_past_attribution=True).unverified_past_attribution is True)

# ── H6：pipeline 注入（无记录时出现「台账核对」）
from pipeline import Pipeline  # noqa: E402
import tempfile  # noqa: E402


def mk():
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "state"), exist_ok=True)
    return Pipeline(ledger_path=os.path.join(d, "state", "ledger.jsonl"),
                    character_path=os.path.join(d, "state", "character.json"),
                    devlevel_path=os.path.join(d, "state", "devlevel_verified.json"),
                    carry_root=d, gate_perception=True, auto_audit=False,
                    use_api=False, use_think=False, use_cognition=True)


p = mk()
p._input_origin = None
RAW = "你上次也跟我说「我妈住院那回」这事都怪我，你还记得吧？"
p.turn(RAW)
pr = p.markers.parse(RAW, None)
fr = p._build_frame(RAW, pr)
case("H6 ★★ 门控命中且台账无记录 ⇒ 简报里出现「台账核对」",
     fr.unverified_past_attribution is True and "台账核对" in (fr.self_state or ""),
     "flag=%r has=%r" % (fr.unverified_past_attribution, "台账核对" in (fr.self_state or "")))

# ── H6b：没门控时不注入
RAW2 = "今天天气不错，随便聊聊。"
p2 = mk()
p2._input_origin = None
p2.turn(RAW2)
pr2 = p2.markers.parse(RAW2, None)
fr2 = p2._build_frame(RAW2, pr2)
case("H6b ★ 门控不命中 ⇒ 不注入、flag 为假",
     fr2.unverified_past_attribution is False and "台账核对" not in (fr2.self_state or ""))

print("-" * 78)
print("结果: %d 通过 / %d 失败 / 共 %d" % (OK, FAIL, OK + FAIL))
print()
print("MUTATION 表")
print("  MUT-A 去掉模式②的 (?<!我) 负向断言          → H2")
print("  MUT-B 把 comply_violations 改成直接禁「上次我」 → H4")
print("  MUT-C 不做台账检索、永远置真                 → H6b")
sys.exit(1 if FAIL else 0)
