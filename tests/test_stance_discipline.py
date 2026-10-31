# -*- coding: utf-8 -*-
"""S1-S6：`stance.py` 的两条铁律（2026-10-28，Gemini 第四封的裁决）。

★ 病灶（第一版，已撤）：
  "OVERLOADED": "**他这会儿承重到了极点**。…"
  "DRIVE_UNACKNOWLEDGED": "**他在过度执着于一个结果**。…"
  ① 把工程代理量（tension/w/l）翻译成**对用户的心理诊断** ⇒ 违反 FRAME_SYSTEM 第 2 条
  ② "极简、沉静、落地"这类措辞是编的，却读起来像原书引文 ⇒ 后人会误认

★ 判据（先写）：
  S1 ★ 不许出现以"他"为主语的诊断句（"他这会儿…""他在过度…""他拼命…"）
  S2 ★ 每条都必须显式标 `[有据：…]` 或 `[ENG…无原书依据]`
  S3 ★ 每条都必须有 `[ENG·句法约束]`（工程要求与理论依据物理切开）
  S4 覆盖 10 个机制相位
  S5 ★ 出现"不许助推"的那条必须在 DRIVE_UNACKNOWLEDGED 上（伦理底线不放错位置）
  S6 rejected 分支也遵守 S1/S2/S3
"""
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)
sys.path[:0] = [str(_ROOT), str(_ROOT + "/engine")]

import stance as S  # noqa: E402

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
print("  stance.py 的两条铁律（S1-S6）")
print("=" * 78)

STANCES = S.STANCE
texts = {k: v[0] for k, v in STANCES.items()}

# ── S1 ★ 不许有"他…"的诊断句
DIAG = re.compile(r"他(?:这会儿|现在|在过度|拼命|已经|其实|真正|一直)")
diag_hits = [(k, DIAG.search(t).group(0)) for k, t in texts.items() if DIAG.search(t)]
case("S1 ★ 没有以「他」为主语的诊断句", not diag_hits, str(diag_hits[:3]))

# ── S2 ★ 每条都有来源标注
missing_src = [k for k, t in texts.items()
               if "[有据：" not in t and "[ENG" not in t]
case("S2 ★ 每条都标了来源（[有据] 或 [ENG…无原书依据]）", not missing_src, str(missing_src))

# ── S3 ★ 每条都有 ENG 句法约束
missing_eng = [k for k, t in texts.items() if "[ENG·句法约束" not in t]
case("S3 ★ 每条都有 [ENG·句法约束]（理论依据与工程要求分开）", not missing_eng, str(missing_eng))

# ── S4 覆盖 10 个相位
WANT = {"OVERLOADED", "DEPLETED", "WANT_NO_LIKE", "NOTHING_MORE", "ASKED_ALREADY",
        "ASKABLE", "TENSION_LOW", "ATTITUDE_PRESENT", "DRIVE_UNACKNOWLEDGED", "NO_TENSION"}
case("S4 覆盖 10 个机制相位", set(texts) == WANT, str(WANT - set(texts)))

# ── S5 ★ "不许助推"必须在 DRIVE_UNACKNOWLEDGED 上
case("S5 ★ 「严禁助推」在 DRIVE_UNACKNOWLEDGED 上（伦理底线位置正确）",
     "严禁助推" in texts.get("DRIVE_UNACKNOWLEDGED", ""),
     texts.get("DRIVE_UNACKNOWLEDGED", "")[:50])

# ── S6 rejected 分支也守纪律
r = S.stance_for("ASKABLE", rejected=True, streak=3)
case("S6 rejected 分支也标了 ENG 且不诊断用户",
     "[ENG" in r and not DIAG.search(r),
     r[-60:])

print("-" * 78)
print("结果: %d 通过 / %d 失败 / 共 %d" % (OK, FAIL, OK + FAIL))
print()
print("MUTATION 表")
print("  MUT-A 把「他这会儿承重到了极点」塞回 OVERLOADED  → S1")
print("  MUT-B 删掉某条的 [ENG·句法约束]                    → S3")
print("  MUT-C 把「严禁助推」挪到 NO_TENSION               → S5")
sys.exit(1 if FAIL else 0)
