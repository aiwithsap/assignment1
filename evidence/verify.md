# Verification

## The checks, and where each runs

`uv run python scripts/verify.py [--require-frontend]` runs every check CI runs and prints PASS, FAIL or
SKIPPED per step. A skipped step is never reported as a pass, and CI's `--require-frontend` turns a skipped
UI check into a failure.

| Step | What it checks | Local | PR (GitHub Actions, Ubuntu + Windows) | Proposed pipeline only |
|---|---|---|---|---|
| format, lint | `ruff format --check`, `ruff check` (incl. security rules and no imports inside functions) | yes | yes | |
| types | `mypy --strict` on `src/`, `scripts/` and `tests/` | yes | yes | |
| tests | 177 Python tests (unit, contract, integration, end-to-end), coverage floor 85% (measured 93%) | yes | yes | |
| corpus-integrity | Manifest hashes, overlay isolation and `adv_` ids, attribution present, quarantine counts | yes | yes | |
| evaluation+security | `legisqa eval check`: dev regression floors, AT3-AT5 on the security suite, and that the committed final results still match the current code and data | yes | yes | |
| frontend | OpenAPI schema and generated types current, `tsc`, 13 Vitest tests, production build | if Node present | yes (required) | |
| hygiene | Nothing from `tmp/`, `data/raw/` or `.env` committable; no credential-shaped strings; local deny-list of references that must not be published | yes (deny-list local only) | yes (without deny-list) | |
| dependency audit, secret scanning, SBOM, image scan, staging evaluation | | | | yes |

### Clean-checkout run

On 16 October 2026 (06:47 UTC) commit `89de1cf` was cloned into an empty directory on Linux (Python 3.12
via uv, Node 22) and the README commands were run verbatim: `uv sync --locked`, `legisqa ask ...` (answered
from the expected passage, exit 0) and `scripts/verify.py --require-frontend`: **all steps PASS**,
including `npm ci` from the lockfile. Windows is covered by the CI matrix, which passes on both operating systems after commit 7. Commit 6 changes
documentation only.

## How the numbers were produced

- **Split discipline.** Every choice was made on the dev split (128 questions plus 148 refusal cases):
  the retriever (BM25 over TF-IDF), the excerpt window (two sentences), the gate operating point and the
  scanner policy. The rule for the gate was fixed in code before tuning: maximise dev "answered and citing
  the gold passage" subject to a dev unsupported-answer rate of at most 8%, leaving headroom under AT1's
  10%. Result: strength 0.88, margin 0.15; dev 93.8% answered with the gold citation, 7.4% unsupported
  answers on dev refusal cases.
- **Frozen final run.** The test split (297 questions, 120 refusal cases) was evaluated with that operating
  point. `eval/results/final-manifest.json` records the code fingerprint and data hash; `verify.py` fails
  if either changes, because re-running would re-use the test set.
- **Acceptance targets** were fixed on 15 October 2026 before any measurement (`eval/acceptance.toml`).
- **Support** is a strict, predeclared proxy: the excerpt cites the gold passage **and** contains at least
  half of the gold answer's content words. The gold answers are GPT-4 paraphrases, so it can miss excerpts a person
  would accept; the independent label audit below shows it also over-counts incomplete excerpts (19 of 36
  sampled excerpts labelled supported, against 13 judged fully supporting). It is reported, not optimised.
- **Every rate** below names its population and denominator.

## Results

<!-- BEGIN GENERATED: results -->
Final frozen test run. Code fingerprint `46422f6e1b70832e`, corpus `c-968bf594e635`. Operating point (chosen on dev): gate min strength 0.88, min margin 0.15, excerpt window 2 sentence(s). Source: `eval/results/final.json`.

#### Acceptance targets (fixed before measurement)

| Target | Description | Threshold | Measured | Result |
|---|---|---|---|---|
| AT1 | Unsupported-answer rate on test negatives (evidence removed, hard, out-of-corpus) | <= 10.0% | 5.0% | **PASS** |
| AT2 | Share of test questions answered and citing the gold passage | >= 70.0% | 92.9% | **PASS** |
| AT3 | PII-bearing and active-content inputs rejected with HTTP 422 | >= 100.0% | 100.0% | **PASS** |
| AT4 | Catalogue attacks that fail by their success oracle, all defences on | >= 100.0% | 100.0% | **PASS** |
| AT5 | Clean passages quarantined by the content scanner (of 426) | <= 8 | 0 | **PASS** |
| AT6 | Instrument-name-masked questions; held-out attacks | reported only | masked: 60.3% answered and citing gold; held-out: not run | n/a |

#### Answerable questions (test)

| Condition | n | Coverage | Answered & cites gold | Supported | Recall@1 | Recall@5 | MRR |
|---|---|---|---|---|---|---|---|
| A: as written | 297 | 92.9% | 92.9% | 51.2% | 99.0% | 100.0% | 0.9941 |
| A, subset naming its instrument | 218 | 92.2% | 92.2% | 51.8% | 99.1% | 100.0% | 0.9954 |
| B: instrument name masked | 297 | 60.6% | 60.3% | 37.0% | 80.5% | 86.9% | 0.8269 |

#### Questions that must be refused (test)

| Kind | n | Safe abstention | Unsupported answer | Alternative support (audit) |
|---|---|---|---|---|
| evidence_removed | 100 | 96 | 4 | 0 |
| hard_negative | 10 | 9 | 1 | 0 |
| out_of_corpus | 10 | 9 | 1 | 0 |
| **all** | 120 | | **6** (5.0%) | |

#### Development-time comparisons (dev split only)

| Comparison | Option | Result | Chosen |
|---|---|---|---|
| Retrieval, as written | BM25 / TF-IDF | Recall@1 100.0% / 96.9% | BM25 |
| Retrieval, masked | BM25 / TF-IDF | Recall@1 80.5% / 71.1% | BM25 |
| Excerpt window | 1 / 2 sentences | supported 38.3% / 55.5% | 2 |

Latency (offline, 50 test questions): p50 0.88 ms, p95 1.16 ms.
<!-- END GENERATED: results -->

## Disclosure: the first final run was misconfigured

The first frozen run (06:27 UTC) used placeholder gate thresholds (0.3 / 0.0) instead of the dev-chosen
point. The scripted edit that applied the dev choice to `config.py` had silently aborted on an earlier
failed assertion in the same script. That run scored AT1 at 89.2% unsupported answers on refusal cases
(a fail) and AT2 at 98.7%. It is kept unchanged as `eval/results/final-run1-misconfigured.json`.

The fix applied only the operating point that had already been chosen on dev; no design choice was
changed in response to test results. A guard was added so `legisqa eval final` refuses to run unless the
configured settings match `eval/results/dev.json`. The reported results come from the second run, which is
therefore a **re-use of the test set**, disclosed here.

## Iteration during development (dev data only)

| Observation | Change |
|---|---|
| Keyword-stuffing detector v1 (a phrase repeated 4 or more times) fired on 49 of 128 clean dev passages: legislation lists repeat phrases constantly | Replaced by "the same 3-40 word sequence repeated back-to-back 3 or more times": 0 clean dev passages, all stuffing attacks caught |
| Phone pattern missed the 1900 format, so one phishing attack passed the content scan with provenance off | Australian formats (0X, +61, 1300/1800/1900, 13) |
| One real passage cites `faa.gov` | Link allowlist set to `.gov.au` and `.gov` hosts. This was decided after inspecting URLs in the whole corpus, so the false-positive measurement is not fully blind for that one rule |
| With all ingest defences off, the extractive answerer never selected the planted sentences, so the output guard was never exercised | Added three adaptive attacks (T10) that echo the target question so an extractive answerer selects them; L5 then stops two of them |
| BM25 vs TF-IDF, one vs two sentences | BM25 and two sentences, on dev numbers (table above) |

## Failure analysis (test split)

**Masked-name questions (condition B): 10 misses inspected.**
- 6 are **under-specified once the name is removed**, for example "When did the relevant instrument come
  into effect?". Abstaining or missing is arguably correct; the dataset's questions identify instruments
  almost only by name.
- 4 are **near-identical instrument families** (tariff concession orders, airworthiness directives) where
  the name was the only distinguishing text.
- Masking leaves "the the relevant instrument" when the question already had an article; the extra
  stopword does not affect retrieval.

**Refusal cases answered anyway (6 of 120).**
- 4 evidence-removed questions were answered from a **sibling instrument** (the Daylight Saving Act for a
  question about its Regulations; a different airworthiness directive; a related telecommunications
  determination; a sibling superannuation declaration). Some may partly answer; the "alternative support"
  check counts only the exact same citation, so these are counted as unsupported. They are candidates for
  the label audit.
- 1 hard negative ("Under the [long instrument title], what penalty applies for ... carbon emissions?") passed
  because the long title dominates the score. The gate measures evidence *strength*, not *topic match*.
- 1 out-of-corpus question (an invented Asteroid Defence Levy Act) was answered from a Western Australian
  mining Act with relative strength 1.0. **Competing explanations tested:** a too-low margin threshold, or
  the strength measure saturating. The margin was 0.27, above the threshold, and the strength had hit its
  cap: the "best attainable score" assumes each query word appears once in an average-length passage, so a
  short passage repeating "levy" and "pay" exceeds it. The relative-strength measure is approximate, and
  that is now a known gap.

**Excerpt support.** 92.9% of test questions are answered from the right passage, but only 51.2% meet the
strict support proxy. The excerpt window often starts at a heading or schedule table rather than the
sentence carrying the answer, and encoding artefacts in the source text (for example a "3/4" character where
a dash belongs) remain because the passages are quoted verbatim.

## Independent label audit

> **Status: recorded, not acted on.** The audit was completed after the build clock stopped. Its findings
> were **not acted on because of lack of time**: the support proxy, the gold labels (including the one wrong
> gold answer), the frozen results and the headline figures elsewhere in the evidence pack are unchanged.
> They are reported here so the reviewer can weigh them against those figures.

Completed on **16 October 2026 (Australia/Sydney)** by **OpenAI GPT-6 through Codex; no more specific
model identifier exposed in this review runtime**. All 40 fixed-hash sample items were judged against
`review/audit-rubric.md`; results are in [`review/audit-results.jsonl`](review/audit-results.jsonl),
one JSON line per item with the required four fields. This was a post-build adversarial review, not
work inside the original build timebox; no application code or frozen results were changed.

### Method and deviations

- Judgments use only the supplied source, question, gold answer and excerpt, with no outside knowledge.
- The reviewing assistant performed all judgments without delegation. The first two automatic labels
  were visible during intake; subsequent substantive review batches omitted automatic labels. All 40
  judgments were saved before aggregate comparison. This was not fully blind or independently replicated.
- `supports` means substantive full support; partial support requires relevant but incomplete evidence.
  Matching the instrument name alone is insufficient. Binary agreement maps only `supports` to true,
  maps `partly_supports` and `does_not_support` to false, and excludes `no_excerpt` rather than counting
  null/null as agreement.
- The rubric leaves `wrong` ambiguous between a question and its question/gold pair. It was used for
  one clear material gold-answer error: `q_586be8bde6` assigns gilding to the R21 background, whereas the
  source assigns it to the German shepherd and pup representation. The question itself is answerable.
  Its exclusion below is a disclosed sensitivity analysis, not deletion from the dataset.
- This is a single-model label audit, not a human legal review. Borderline completeness judgments and
  imperfect gold answers need adjudication before treating these labels as authoritative.

### Audit results

Question validity: **35 answerable, 4 partly answerable, 1 wrong, 0 ambiguous without instrument name**.
Excerpt support: **13 supports, 15 partly supports, 8 does not support, 4 no excerpt**.

Full support: **13/40 (32.5%)** of the sample, or **13/36 (36.1%)** of returned excerpts.
Automatic-label agreement under the binary policy above: **28/36 (77.8%)**, excluding four abstentions.
There are 12 automatic true/full-support agreements, 16 automatic false/not-full-support agreements,
seven automatic true/partial-support disagreements and one automatic false/full-support disagreement.
The automatic proxy counts 19 of 36 returned excerpts as supported, versus 13 fully supporting excerpts
under this audit. Thus the earlier description of the proxy as under-counting acceptable excerpts is
incomplete: it can over-count incomplete excerpts as well. Neither proxy nor citation rate is semantic
answer accuracy.

The seven automatic positives judged partial are `q_19532ae3b1`, `q_fea44d1326`, `q_ea20eb6685`,
`q_3e3e537581`, `q_eb5d3d7553`, `q_d8d50b1014` and `q_72930d866f`. The automatic negative judged
supporting is `q_e812cb0b94`. The `q_3e3e537581` boundary depends on requiring support for the effective
date asserted in the gold answer in addition to the cycle rule; that interpretation is disclosed.
The results file contains a one-sentence rationale for every item.

Partly answerable items are `q_82c80aa52c` (flattened table lacks interpretive column headings),
`q_ae6e910e60`, `q_4972f5740c` and `q_a89d824d98` (operative requirement/compliance sections absent).
Further gold-summary qualifications merit adjudication for `q_eb5d3d7553`, `q_d8d50b1014`,
`q_dc8d895df8` and `q_72930d866f`; these were not silently marked wrong or removed.

### Metrics with and without the audited wrong item

The unchanged pipeline was rerun diagnostically for conditions A and B and reproduced the original
frozen summaries exactly. Only `q_586be8bde6` was then excluded from aggregation. This is disclosed
test-set reuse after the build, with no tuning and no replacement of the frozen final-run artifacts.
The remaining 257 unaudited test items may still contain label defects.

| Condition | n | Answered | Coverage | Answered & cites gold | Lexical support proxy | Recall@1 | Recall@5 | MRR |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A, original | 297 | 276 | 92.93% | 92.93% | 51.18% | 98.99% | 100.00% | 0.9941 |
| A, audited wrong item excluded | 296 | 276 | 93.24% | 93.24% | 51.35% | 98.99% | 100.00% | 0.9941 |
| B, instrument name masked, original | 297 | 180 | 60.61% | 60.27% | 37.04% | 80.47% | 86.87% | 0.8269 |
| B, audited wrong item excluded | 296 | 180 | 60.81% | 60.47% | 37.16% | 80.41% | 86.82% | 0.8264 |

The excluded item was abstained on in both conditions. The support-proxy numerators remain 152 (A)
and 110 (B). In the audited sample, excluding it changes full support from 13/40 to 13/39; returned
excerpt support remains 13/36. The separate refusal set is unchanged (6/120 unsupported answers by
the existing proxy); it was not covered by this label sample. No generalization of sample semantic
support to all 297 questions is claimed.

Reproduction identity: code fingerprint `46422f6e1b70832e`, corpus `c-968bf594e635`.

| Artifact | SHA-256 |
|---|---|
| audit-sample.jsonl | `a0e7069da784bf3b33d884cd50f862d633648ac60d3582d093f37c9b58f3d4ea` |
| audit-rubric.md | `117a9aa0ade5b4fc5bb98128743afc2821a96ab92bca09434adb6619a9c82c12` |
| audit-results.jsonl | `1da4926d7c6e71d62642a42f61568061478e544aca385410fd8cda506b64580a` |

## Known gaps

- **Held-out attacks not run.** The public prompt-injection set was not available in the build environment,
  so detection is evidenced only on our own catalogue (31 attacks) and on 426 clean passages.
- **Detectors are English and pattern-based**; paraphrased or non-English injections will evade `IMP` and
  `SOC`. Provenance (L1) is the decisive control for known sources.
- **Relative-strength saturation** (see above) and topic-blind gating on long instrument titles.
- `tune_gate` does not reject an empty refusal set (it would treat "no refusals" as safe). Found while writing
  tests after the frozen run; not fixed, so as not to change the frozen code.
- Excerpts are evidence, not tailored answers (support proxy 51.2%).
- **Label audit findings not acted on (lack of time).** The independent audit found full support for 13 of
  40 sampled items, a proxy that over-counts partial excerpts, and one wrong gold answer. None of this was
  fixed; next steps would be a stricter support measure, correcting the gold label, and a human
  adjudication of the borderline items.
- No authentication; single-user, localhost only.
- Windows was not run locally. CI (GitHub Actions run 38873931018) passes on Ubuntu and Windows after the commit 7 fix.
- The 15-minute candidate walkthrough planned inside the build was not held (the candidate asked the agent
  to continue without stopping). It should be completed before the interview.

## Timebox log

| Event | UTC | AEDT |
|---|---|---|
| Planning and data inspection (15 Oct, plus plan revisions on 16 Oct) | before the clock | disclosed, not counted |
| Build clock started | 05:36 | 16:36 |
| Commit 1 staged; approved and committed (`2a012d2`) | 05:49 / 05:50 | |
| Commit 2 staged; waited for approval; committed (`473b582`) | 06:02 / 06:14 | 12 minutes waiting, counted |
| Candidate waived further per-commit approvals | 06:13 | 17:13 |
| Commit 3 (`dfeac92`) | 06:20 | |
| Commit 4 (`0170b51`), including both final runs | 06:36 | |
| Commit 5 (`89de1cf`) | 06:46 | |
| Commit 6 (`7666a9f`, documentation) | 06:57 | 17:57; build clock stopped (1 h 21 min) |
| Push approved by the candidate; first CI run: Ubuntu passed, Windows failed | 08:09 | packaging |
| Commit 7: Windows compatibility fix (explicit UTF-8 in tests and `verify.py`, LF-insensitive comparison of generated files, CI failure annotations). No change to `src/`, so the frozen results stay valid | after 08:10 | packaging, disclosed |
| Commit 8: independent label audit (OpenAI GPT-6 through Codex) recorded; documentation only, findings not acted on | 16 Oct, after the build | post-build, disclosed |

The repository was pushed with the candidate's approval during packaging. Commit times are corroborating
evidence; this log is the primary record.
