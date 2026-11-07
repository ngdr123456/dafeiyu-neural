# Record metadata (cut 4a)

New session records can include `record_metadata`: arrays aligned by index with
`facts`, `stance_traces`, `open_questions`, and `her_questions` after existing
deduplication and capacity limits. Each element is either null (coverage unknown)
or an object with `origin`, `subject`, and `truncated`. Origins are
`user_statement`, `her_utterance`, and `system_observation`. Subject is the
current input signal's structured topic, or empty when absent. A delivered
utterance records speech, not the truth of its contents.
For a nonempty topic from a degraded signal, `subject_degraded: true` marks a
low-confidence guess, not a topic declared by the user. It must not be used for
subject identity, conflict, relevance, or coverage. Omission means the subject
was not marked degraded, not that it is independently verified.
`input_sense` normally caps topics at 40 characters; the 80-character cap here
is a defense for external callers. Topics over 80 characters are clipped to 80
and marked `subject_truncated: true`;
absence of that field means the subject was not clipped by this persistence path.

The existing stored strings are unchanged. `truncated` flags clipped inputs and
utterances and conservatively flags extracted questions that differ from the
complete delivered utterance. For a system observation it flags a clipped point.
These flags do not assert that a stored observation is an original utterance.
Different metadata for the same deduplicated record yields null; removal clears
its metadata before a later reinsertion. Older records with no metadata remain
unknown; existing entries are never backfilled. Calls without metadata also
produce unknown coverage. History is data, not instructions. This metadata is
not consumed by judgment or recall, and cannot by itself establish relevance,
subject identity beyond exact labels, completeness, or conflict.
