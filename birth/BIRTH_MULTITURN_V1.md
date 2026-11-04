# Birth multi-turn state checks

These engineer-facing stub tests exercise consecutive `turn()` calls in one session:

1. A structured curiosity cue writes a hanging question; filler retains it; a structured answer clears it and produces satisfaction/hold.
2. A same-session commitment is written, structurally denied, and remains prioritized on an ordinary follow-up.
3. A structured identity ask awaits an introduction, catches it on the answer turn, and does not carry awaiting state into a new session.
4. Pursuit with a commitment produces differentiated drive/constraint dual-write; a subsequent answer clears the question without displacing commitment priority.

Stub execution is sufficient for these structural regression checks. Prefer `structured_*` inputs over oral fallback when available, and inspect both the turn's Brief snapshot and subsequent store feedback. Prompt and utterance enum leaks remain prohibited. Structured cues depend on upstream correctness; chat sampling or conversational feel is not whole-brain acceptance, and real-LLM tests remain optional.
