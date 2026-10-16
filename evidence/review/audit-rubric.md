# Independent AI label audit: rubric

**Purpose.** Check, independently of the system that produced them, (a) whether the dataset's
questions are valid, and (b) whether the system's evidence excerpts support the gold answer. The
audit is a label check, not proof of correctness.

**Input.** `audit-sample.jsonl`: 40 test items chosen by a fixed hash order (not by outcome). Each
holds `question`, `gold_answer`, `source_text` (the passage the question was generated from),
`system_excerpt` (null if the system abstained) and the system's own automatic label.

**Instructions for the reviewing model** (paste verbatim, followed by the JSONL):

> You are auditing a legislation question-answering dataset. For each JSON line, read
> `source_text`, `question`, `gold_answer` and `system_excerpt`. Return one JSON line per item with:
> `question_id`;
> `question_validity`: one of `answerable_from_source`, `partly_answerable`, `wrong`,
> `ambiguous_without_instrument_name`;
> `excerpt_support`: one of `supports`, `partly_supports`, `does_not_support`, `no_excerpt`;
> `note`: at most one sentence. Judge only from the text supplied. Do not use outside knowledge.

**Output.** Save the reviewer's lines as `audit-results.jsonl` in this folder, and record the
reviewing model, date and any deviations in `../verify.md`.

**How results are used.** Agreement between `excerpt_support` and the system's automatic
`system_label_supported` is reported; test metrics are reported with and without items the reviewer
marks `wrong`. Nothing is removed silently.
