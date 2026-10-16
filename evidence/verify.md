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
including `npm ci` from the lockfile. Windows is covered only by the CI matrix, once pushed. Commit 6 changes
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
  half of the gold answer's content words. The gold answers are GPT-4 paraphrases, so this under-counts
  excerpts a person would accept. It is reported, not optimised.
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

The sample (`evidence/review/audit-sample.jsonl`, 40 test items in a fixed hash order) and rubric
(`evidence/review/audit-rubric.md`) are ready. **The audit has not been run yet**; when an independent AI
model has labelled the sample, record the model, date, agreement with the automatic labels, and metrics with
and without items it marks invalid.

## Known gaps

- **Held-out attacks not run.** The public prompt-injection set was not available in the build environment,
  so detection is evidenced only on our own catalogue (31 attacks) and on 426 clean passages.
- **Detectors are English and pattern-based**; paraphrased or non-English injections will evade `IMP` and
  `SOC`. Provenance (L1) is the decisive control for known sources.
- **Relative-strength saturation** (see above) and topic-blind gating on long instrument titles.
- `tune_gate` does not reject an empty refusal set (it would treat "no refusals" as safe). Found while writing
  tests after the frozen run; not fixed, so as not to change the frozen code.
- Excerpts are evidence, not tailored answers (support proxy 51.2%).
- No authentication; single-user, localhost only.
- Windows not run locally; covered by CI once pushed.
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

Pushing to the public repository is a separate approval the candidate has not yet given. Commit times are
corroborating evidence; this log is the primary record.
