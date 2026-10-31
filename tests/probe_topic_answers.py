# -*- coding: utf-8 -*-
"""取材体检：真实用户会怎么答这些题面？

为什么要做这个（承 tests/corpus_probe.py 的结论）：
  corpus_probe 实测规则召回 90% —— **规则本身不严**。
  但台账里真实轮次的零命中率是 67%。两个数字差得这么远，只能是**语料不同**：
  我在 corpus_probe 里写的是"标记特征明显的句子"，
  而真实用户答的是**题面（未完成的两难句）**，语域可能完全不同。

  这个脚本就测这件事：让模型**扮演一个普通的、没有受过训练的说话人**，
  用口语、短句、想到什么说什么去答题面，然后把答案过一遍标记引擎。
  模型在这里仍然只是**造语料的工具**，它的回答不会进入系统输出。

  结论决定下一步该改哪里：
    · 若答语大量零命中 → 问题在**取材方式**（题面/语域），改题面，不改规则
    · 若答语大量命中   → 问题在**真实用户的表达**，得另找原因（可能是轮次太少）

用法：
    python tests\\probe_topic_answers.py            # 12 个话题
    python tests\\probe_topic_answers.py 20         # 指定条数
"""
from __future__ import annotations

import collections
import io
import json
import os
import sys
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "engine"))

from markers import MarkerEngine            # noqa: E402
from understand import load_api_key, DEFAULT_BASE  # noqa: E402

W = 78
MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-flash")
BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", DEFAULT_BASE)

PERSONA = (
    "你是一个普通的成年人，没学过心理学。请用**最平常的口语**回答下面这句没写完的话，"
    "就像跟朋友随口聊天那样：短句，想到什么说什么，不要总结、不要升华、不要讲道理、"
    "不要写作文、不要用书面语。**只写 1–3 句**，不要解释你在做什么。"
)


def ask_model(stem: str) -> str:
    key = load_api_key()
    if not key:
        raise RuntimeError("找不到 DEEPSEEK_API_KEY")
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "system", "content": PERSONA},
                     {"role": "user", "content": stem}],
        "temperature": 0.9,
        "max_tokens": 2048,
    }).encode("utf-8")
    req = urllib.request.Request(
        BASE_URL.rstrip("/") + "/chat/completions", data=body,
        headers={"Content-Type": "application/json", "Authorization": "Bearer %s" % key})
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.loads(r.read().decode("utf-8"))
    return (d["choices"][0]["message"]["content"] or "").strip()


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    eng = MarkerEngine()
    topics = json.load(io.open(os.path.join(_ROOT, "corpus", "topics.json"),
                               encoding="utf-8"))["topics"]
    # 均匀取样，覆盖 36 个话题的全表
    step = max(1, len(topics) // n)
    picked = topics[::step][:n]

    print("═" * W)
    print("  取材体检　｜　模型扮演普通说话人答题面　｜　%d 个话题" % len(picked))
    print("═" * W)

    zero = 0
    counter: collections.Counter = collections.Counter()
    rows = []
    for t in picked:
        try:
            ans = ask_model(t["stem"])
        except Exception as e:                                  # noqa: BLE001
            print("  [跳过 %s] %s" % (t["id"], e))
            continue
        pr = eng.parse(ans, t["id"])
        counter.update(pr.markers)
        if not pr.markers:
            zero += 1
        rows.append((t["id"], t["stem"], ans, pr.markers))

    for tid, stem, ans, ms in rows:
        print("\n  【%s】%s" % (tid, stem))
        print("     答：%s" % ans.replace("\n", " "))
        print("     标记：%s" % ("、".join(ms) if ms else "**（零命中）**"))

    tot = len(rows)
    print("\n" + "─" * W)
    print("  总计 %d 条　零命中 %d 条（%.0f%%）" % (tot, zero, 100.0 * zero / tot if tot else 0))
    print("\n  各标记命中情况：")
    for m in sorted(x["id"] for x in eng.rules["markers"]):
        print("    %-18s %d" % (m, counter.get(m, 0)))
    print("─" * W)
    print("""
  怎么读这个结果：
    · 零命中率高 → 普通说话人答这些题面时**本来就不带那些语言特征**。
      那么"命中率低"不是规则的错，改规则等于对着想象中的语料调参。
      该改的是**取材方式**：题面得把话引到可观察的措辞上，或换一种问法。
    · 若某标记常年 0 而它的话题被问过很多次 → 那个标记可能根本无法由题面引出，
      应在 spec 里标注为"需要专门问法"，而不是留在表里装样子。
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
