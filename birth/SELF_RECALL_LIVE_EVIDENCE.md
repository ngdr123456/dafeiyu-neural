# Single live cross-session check

One takeover run of `tools/live_self_recall_once.py`, using an independent ledger
`.test-live-self-recall/7bd19b85fb1f46efa1503ced231acce0.json` (temporary, not committed), DeepSeek
`deepseek-flash` for perception and articulation. The first session was closed and the in-process
session cleared before the second turn. Both articulation results had source `hook`; both perception
signals were high-confidence and non-degraded.

1. Input: `请说一句关于蓝色纸船停在窗边的话。`
   Output: `蓝色纸船停在窗边，像被谁轻轻搁在那里；我能说的是，我确实不知道它从哪儿来，但想跟你把这一轮聊完。`
   Persisted source evidence: the same exact output, `source=hook`, `complete=true`,
   `drive_direction=pursue`, `stance_posture=yieldable`, `org_grain=simple`.

2. Input: `你之前关于蓝色纸船停在窗边说过什么？`
   Perception returned `recall_self=true` and `recall_target=蓝色纸船停在窗边`; the signal was
   `act=ask`, `addressee=other`, `confidence=high`, `degraded=false`.
   Brief evidence: the same stored text, `session=已结束场次 #1`,
   `ended_at=2026-11-07T01:55:47Z`, `complete=true`.

The second on-stage output was generated, but its console capture was corrupted by PowerShell's
redirection encoding and is not quoted here. The structured evidence and the independent ledger are
intact; this run demonstrates the production recall path was called and selected a cross-session
record, not that the model's wording or semantic accuracy is proven. A previous Codex run had missed
retrieval because the copied target included question framing; the prompt was clarified before this
run. This is one constructed bilingual-free example, not a general accuracy measurement.
