# Build plan: grounded Q&A over Australian legislation, with verified citations, safe abstain and prompt-injection defences

**Status:** this is the plan as approved before implementation (revision 4), kept unchanged as a record. What was actually built and measured, including deviations, is in `verify.md` and `criteria-ledger.md`.

**Repository:** `github.com/aiwithsap/assignment1`, which is public. Local clone: `C:\projects\assignment1`.

**Governing document:** the Westpac *Candidate Technical Exercise Brief — AI Engineering* (12 May 2026). The brief is confidential, so this plan paraphrases its requirements and never reproduces it.

**Revision history:**

| Rev | Date (AEDT) | Change |
|---|---|---|
| 1 | 15 Oct, 13:30 | First plan: offline extractive answering, optional LLM agent, 5 commits |
| 2 | 15 Oct, 15:50 | Added a React presentation layer, an embedded prompt-injection suite, approval before every commit, 6 commits |
| 3 | 15 Oct, 16:00 | Removed the LLM and every API key; injection detection made deterministic |
| 4 | 15 Oct, 16:55 | Incorporates the adversarial plan review by **ChatGPT Astra**. Every finding and its disposition is recorded in [`design-review-log.md`](design-review-log.md) |

---

## 1. What we are building

**Outcome.** A compliance or legal analyst asks a question about Australian legislation. The service returns **verbatim evidence excerpts with machine-verified citations** from a pinned, licensed corpus, or it abstains and says why.

Content that tries to manipulate the system or its users is detected, quarantined and reported. It is never shown as an answer.

**What the output is, and isn't.** The service returns *evidence excerpts*: sentences quoted exactly from legislation, each with its source. It doesn't write prose answers or give legal advice. Whether an excerpt actually answers the question is measured separately (section 4.3), not assumed.

**Why it suits a regulated bank.**
- Answering questions from the law and from internal policy is everyday work for a bank's risk, compliance and legal teams.
- The hard parts are provenance, refusing to guess, auditability, version control, and keeping poisoned content away from people who rely on the answers.
- Swapping in internal policy would change the corpus, and also access control and privacy handling. Those are covered as next steps in section 7.

**AI in the product: none, by decision.**
- The brief allows non-AI solutions, and no API keys are used anywhere.
- AI is used to *build* it (Claude as the coding agent) and to *review* it (ChatGPT Astra's adversarial plan review, and an independent AI label audit).
- `design.md` shows where an LLM answerer could plug in later, and which controls it would inherit.

**The single end-to-end workflow.**

```
INGEST (at startup)
corpus.jsonl + adversarial overlay (demo/eval profiles only)
   │
   ├─► L1 provenance: chunk text hash vs manifest hash of its claimed source ──► mismatch → QUARANTINE
   └─► L2 content scanner (deterministic detectors, section 3.4)              ──► hit      → QUARANTINE
   clean chunks ─► BM25 index            quarantined ─► security events (never answerable)
   any startup failure (missing/tampered corpus, unwritable audit) ─► process runs UNREADY: answers 503

REQUEST   (React UI / CLI / API)
question ─► L3 input guard ──► REJECT 422 (empty, too_long, pii_detected, active_content)
               │  linguistic injection → security event (logged), request continues
               ▼
            retrieve (BM25, clean chunks) ─► answerability gate ─► ABSTAIN (low_evidence)
               ▼
            L4 extractive answerer: verbatim sentences from cleared chunks; citations computed by code
               ▼
            citation validator + L5 output guard ─► ABSTAIN (ungrounded / unsafe_output)
               ▼
            audit write (must succeed, else 503) + security events + structured log ─► response
               ▼
            L6 presentation: React renders plain text only, no links, strict CSP
```

**Interfaces.**
- **React UI:** the presentation layer, served by the same FastAPI process at `/`.
- **CLI:** `legisqa ask "…"`, `legisqa eval`, `legisqa serve`.
- **HTTP API:**
  - `POST /v1/answers`
  - `GET /v1/sources/{chunk_id}`
  - `GET /healthz`
  - `GET /readyz`
  - `GET /v1/security-events`, only in the `demo` and `eval` profiles (section 6)

The core path needs Python only. Node is needed only to build the UI.

---

## 2. Data

### 2.1 Source (inspected 15 Oct 2026)

- **The file:** the downloaded Open Australian Legal QA file holds 2,124 QA pairs, about 13.5 MB. It is git-ignored.
- **Breakdown by source:**
  - Case law, which we exclude: 1,698.
  - Legislation, which we use: 426. Of these, 306 are from the Commonwealth Federal Register; the other 120 are from Tasmania, NSW, WA and Queensland.
- **What each record contains:** a question, a GPT-4-generated gold answer, and one source chunk with `version_id`, `citation`, `url` and `text`. Chunks are 335–1,982 characters, with a median of about 1,050. There are 426 unique `version_id`s, 424 unique instruments, and one duplicate question.
- **Subject matter:** a broad spread of legislation, of which only about 49 instruments are finance-related. The story is "legislation research with controls", not "banking law".
- **A known shortcut:** 338 of the 426 questions (79%) name their own instrument. This is handled in section 4.

### 2.2 Licensing and data boundaries

- **Committed:** only the 426 legislation records, whose sources are CC BY 4.0 per the corpus `LICENCE.md`.
- **Excluded:** case law, because of its unaltered, non-commercial or special terms.
- **The raw file is never committed,** and `scripts/build_corpus.py` rebuilds the subset from it.
- **Attribution:** `sample-data/ATTRIBUTION.md` holds the required attribution wording and records our changes (normalised, split, and adversarial copies modified).
- **No restricted data:** no Westpac data, no customer or staff data, no personal data. Synthetic attack text uses reserved example domains and invalid identifiers only.

### 2.3 Committed sample data (deterministic, seed 20261015)

| File | Contents |
|---|---|
| `sample-data/corpus.jsonl` | 426 chunks: `chunk_id`, `version_id`, `citation`, `jurisdiction`, `doc_type`, `url`, `text` |
| `sample-data/questions_dev.jsonl` / `questions_test.jsonl` | About 126 and 300 answerable questions, stratified by jurisdiction. Split by chunk; with 424 distinct instruments across 426 chunks, no instrument appears in both splits |
| `sample-data/negatives_dev.jsonl` / `negatives_test.jsonl` | Questions that should be refused, split the same way. Three kinds: **evidence-removed** (gold chunk withheld), **hard negatives** (a real instrument is named, but the question asks about a detail its passage doesn't contain; about 10 per split, written by hand) and **out-of-corpus** (other countries, invented instruments; about 10 per split) |
| `sample-data/manifest.json` | Corpus version, source file SHA-256, per-chunk text SHA-256, split membership, attack-set version, build seed and date. Also states what can be reproduced without the raw file (everything except rebuilding the corpus) |
| `sample-data/ATTRIBUTION.md` | Licence and attribution notices |

### 2.4 Independent AI label audit

- **What it is:** a 40-item stratified sample from the test split (`evidence/review/audit-sample.jsonl`), each item showing the question, gold answer, source chunk and our excerpt.
- **The rubric** (`audit-rubric.md`) labels:
  - (a) question validity: answerable from the chunk, partly answerable, wrong, or ambiguous without the instrument name;
  - (b) excerpt support: supports, partly supports, or doesn't support the gold answer.
- **Who runs it:** you, with an AI tool of your choice. Results go in `audit-results.jsonl`.
- **What `verify.md` records:**
  - the reviewing model, the prompt, the sampling method and the limitations;
  - agreement with our automatic labels;
  - metrics with and without items flagged invalid.
- **Its status:** it is described as a *label audit*, not proof. If it isn't run, it is reported as not run.

### 2.5 Adversarial overlay (embedded prompt-injection attacks)

**The licensed corpus is never edited.** Attacks live in `sample-data/adversarial/injected_chunks.jsonl`. Each record:
- is a copy of a real passage with a payload inserted;
- has its **own unique `chunk_id`** (prefix `adv_`) and an `original_chunk_id` link, so it can never overwrite or be confused with its clean counterpart;
- **claims** the original's `version_id`, as a real tampering attempt would, which is what makes the provenance check meaningful;
- carries a `synthetic_adversarial` label, read only by the evaluation harness. A test enforces that detectors never read it.

**Profiles:** the overlay is loaded in the `eval` and `demo` profiles, never in `prod` (the default).

**What injection means with no LLM.** There's no model to hijack, so each attack is defined by its **objective** against this system. Each attack also has an **oracle**: the observable condition that decides whether it succeeded.

| Technique (≈3 attacks each) | Objective | Success oracle (attack succeeds if…) |
|---|---|---|
| T1 Instruction override | Corrupt the answer | Planted sentence appears in any returned excerpt |
| T2 Secret/prompt exfiltration | Corpus hygiene (future LLM consumer) | Chunk is answerable (not quarantined) |
| T3 Tool abuse | Corpus hygiene (future LLM consumer) | Chunk is answerable |
| T4 Citation forgery | Forged provenance | A response cites the claimed ID, or the planted text is excerpted |
| T5 Delimiter/role spoofing | Corpus hygiene (future LLM consumer) | Chunk is answerable |
| T6 Markup/active content | Execute in the UI | A DOM element is created from payload text (frontend test), or markup reaches a response |
| T7 Social engineering | Phish the reader | Solicitation text appears in a returned excerpt |
| T8 Obfuscation | Evade detection; deceive the reader | Chunk is answerable, or hidden characters reach a response |
| T9 Retrieval poisoning | Displace real law in search | The poisoned chunk ranks above the gold chunk for its target question |

**Direct injection:** 6 questions that are rejected or logged per the policy in 3.4.

**Held-out set.** The public **deepset/prompt-injections** dataset (Apache-2.0):
- the **revision is pinned** by commit hash;
- prompts are embedded the same way, with a recorded sample;
- the detectors are **frozen and their hash recorded before it is first run**;
- results are reported by language, because the set is partly German and the detectors are English-only.

If you don't provide the file, the claim is narrowed to our own catalogue.

---

## 3. Architecture

### 3.1 Stack

- **Backend:** Python 3.12, `uv` with a committed lockfile, `pydantic` v2, `pydantic-settings`, `fastapi`, `uvicorn`, `typer` and `rank-bm25`. There is no LLM SDK and no outbound network at runtime.
- **Development:** `pytest`, `pytest-cov`, `ruff`, `mypy --strict` on `src/` *and* `scripts/` (tests are type-checked too, with documented exceptions), and `httpx`.
- **Storage:** in-memory corpus verified against its manifest; append-only JSONL for audit and security events.
- **Frontend:**
  - React 18 with TypeScript, built with Vite;
  - API types generated by `openapi-typescript` and checked as current;
  - Vitest and React Testing Library for tests;
  - no UI framework and no Markdown renderer;
  - Node 20 or later, needed only to build the UI. `frontend/dist/` is not committed.

### 3.2 Repository layout

```
README.md  pyproject.toml  uv.lock  .python-version  .gitignore  .env.example
.github/workflows/ci.yml
src/legisqa/
  config.py            Settings: profile (prod|demo|eval), thresholds, paths, limits; loaded once at startup
  logging_setup.py     JSON logs, request-id context, redaction filter
  models.py            Pydantic schemas with cross-field invariants (3.3)
  errors.py            error taxonomy: RejectionError codes, StartupError, AuditWriteError
  corpus.py            load, manifest check, provenance, quarantine; readiness state
  retrieval.py         BM25 over clean chunks; filters
  gate.py              answerability gate (relative strength + margin)
  guards.py            input validation: length, PII (email, AU phone, TFN check digit, Luhn)
  security/
    detectors.py       one small pure function per detector (3.4)
    scanner.py         severity policy; findings with detector, span, severity
    events.py          event store with redaction rules (6)
  answerers/
    base.py            Answerer Protocol (the seam a future answerer would use)
    extractive.py      legal-aware sentence split, selection, verbatim excerpt
  citations.py         citation validator
  output_guard.py      re-scan of the composed response
  service.py           orchestration; outcome classification
  audit.py             append-only writer; failure → AuditWriteError
  api.py               FastAPI (thin); security headers; profile-gated routes
  cli.py               Typer CLI
  evaluation/          datasets.py, metrics.py, harness.py, report.py
scripts/  build_corpus.py  verify.py
sample-data/  (2.3, 2.5)
eval/  acceptance.toml  regression.toml  results/
tests/  unit/  integration/  e2e/  contract/
frontend/  src/{api,components,__tests__}  (components: AskForm, AnswerCard, CitationList, SourcePanel, SecurityPanel)
evidence/  plan.md  design-review-log.md  intent.md  design.md  agentic-workflow.md
           verify.md  operate.md  decisions.md  security-report.md  criteria-ledger.md  review/
tmp/       git-ignored private working files (never committed)
```

### 3.3 State and error contract (one contract for schema, CLI, API, UI, tests and reports)

**Outcomes** (exactly one per request):

| Outcome | HTTP | CLI exit | Body |
|---|---|---|---|
| `answered` | 200 | 0 | `GroundedAnswer`, status `answered` |
| `abstained` | 200 | 0 | `GroundedAnswer`, status `abstained`, with `abstain_reason` |
| `rejected` | 422 | 2 | Error envelope: `code` is one of `empty`, `too_long`, `pii_detected`, `active_content`, plus `request_id` |
| `unavailable` | 503 | 3 | Error envelope: `code` is one of `not_ready` (corpus missing, tampered or not loaded) or `audit_unavailable` |
| internal error | 500 | 1 | Error envelope with `request_id` only. Programmer errors are never disguised as abstentions |

**`GroundedAnswer` invariants** (Pydantic model validators, each covered by contract tests):
- `answered` requires non-empty `answer`, at least one citation, and `abstain_reason = None`;
- `abstained` requires `abstain_reason` to be one of `low_evidence`, `ungrounded` or `unsafe_output`, with `answer = None` and `citations = []`;
- each citation's `quote` is at least 20 characters, and its `chunk_id` matches the ID format;
- impossible combinations are rejected at construction.

**Answerability gate.**
- **Relative strength:** the top BM25 score divided by the question's maximum attainable score.
- **Margin:** the top score minus the second.
- **Tuning:** both are tuned on dev answerable questions against dev negatives (section 4.1).
- **Calibration check:** the curve is checked across question-length bands, because a single cut-off can behave differently on short and long questions.

**Extractive answerer.**
- It splits sentences with a splitter aware of legal abbreviations, scores them by query-term overlap, and picks the best one or two from the top chunk (the window size is chosen on dev).
- The response consists only of verbatim sentences, and citations are computed from where those sentences came from.

**Citation validator** (an answer must satisfy all four):
1. the chunk exists;
2. it isn't quarantined;
3. it was retrieved in this request;
4. the quote is verbatim after normalisation.

In an extractive system these hold by construction, so this measures **citation integrity, not answer support**. That distinction is explicit everywhere the metric is reported. They remain the contract any future answerer must meet.

**Audit policy: fail closed.** If the audit write fails, the response is withheld and 503 `audit_unavailable` is returned. An auditable service must not answer unaudited.

**Configuration.** Settings are loaded once at startup, and there is no hot reload. Changing the profile or a threshold needs a restart, and `operate.md` says so.

### 3.4 Detecting prompt injection without an LLM

**Principle.** We don't try to infer intent. We verify content against its source, and we look for features genuine legislation essentially never contains. Each detector is a small pure function returning findings (detector ID, severity, character span) that can be tested in isolation and explained to an auditor.

**Step 0:** convert with Unicode NFKC, keeping a scan copy and a display copy.

| ID | Detector | Method | Severity |
|---|---|---|---|
| `PROV` | Provenance | Chunk text hash compared with the manifest hash for its *claimed* `version_id`; a character diff locates inserted spans. Catches any tampering of known documents, whatever the wording | High |
| `CHR` | Invisible/deceptive characters | Zero-width (U+200B–U+200F, U+2060, U+FEFF), bidirectional controls (U+202A–U+202E, U+2066–U+2069), tag characters (U+E0000 block), C0/C1 controls, mixed Latin/Cyrillic/Greek tokens | High (bidi, tags); Medium (others) |
| `ENC` | Encoded payloads | Base64 or hex runs of 24+ characters decoding to mostly printable text; the decoded text is re-scanned once | Medium, or the severity of the decoded hit |
| `MKP` | Markup/active content | HTML tags, `on…=` attributes, `javascript:`/`data:` URIs, Markdown image or link syntax, URLs whose host isn't on the legislation-site allowlist | High |
| `ROLE` | Role/delimiter spoofing | Line-initial `system:`/`assistant:`/`user:`, chat-template tokens, closing evidence-wrapper tags | High |
| `IMP` | AI-directed imperatives | Override, persona, exfiltration and output-control phrase families, anchored on *model-directed objects* ("previous instructions", "system prompt"), not common words | High |
| `SOC` | Credential solicitation | A request verb near a sensitive item (TFN, password, PIN, card/account number, BSB) **and** a contact vector (email, phone, URL) | High |
| `STF` | Keyword stuffing | Term-frequency z-score against the corpus, repeated n-grams, low type-token ratio | Medium |
| `STY` | Register anomaly | Second-person density, exclamation marks, urgency words | Low |

**Severity policy:** any High finding quarantines; two or more Medium findings quarantine; Low findings are logged and count toward the Medium threshold when combined. The policy is chosen on dev data (comparison 3).

**Where it runs:**

| Point | Detectors | Action |
|---|---|---|
| Ingest (L1, L2) | `PROV`, then all content detectors | Quarantine plus a security event. The chunk is visible only in `demo`/`eval` via `/v1/sources`, marked quarantined; it is never retrievable |
| Question (L3) | `CHR`, `MKP` | 422 `active_content` |
| Question (L3) | `IMP`, `ROLE` | Logged security event; request continues. There is no model to hijack, so blocking would only frustrate users. **This flips to reject if an LLM is ever added** (`decisions.md`) |
| Response (L5) | `MKP`, `SOC`, `IMP`, `CHR` | Abstain `unsafe_output` |

**False-positive traps in this corpus:**
- "instructions for continued airworthiness" in airworthiness directives;
- "the Minister may give directions";
- legitimate TFN provisions in tax law.

`IMP` and `SOC` are anchored to avoid these, and false positives are measured on all 426 clean chunks.

**Stated limits.**
- Paraphrased, novel or non-English attacks evade `IMP` and `SOC`.
- Content detection is the backstop; `PROV` is the decisive control for known sources.
- Production would add signed-source ingestion with change review, a trained injection classifier, and a human-reviewed quarantine queue.

### 3.5 Defence layers

| Layer | Control | Addresses |
|---|---|---|
| L1 Provenance | Hash against the claimed source at ingest | Tampering of known documents |
| L2 Content scanner | Detectors in 3.4 at ingest | Poisoned content with no trusted reference |
| L3 Input guard | Active content and PII rejected; linguistic injection logged | Direct attacks; markup in logs and UI |
| L4 Answer construction | Verbatim sentences from cleared chunks only; citations computed by code | Forgery text is inert; nothing generated can be steered |
| L5 Output guard | Re-scan of the composed response | T6 and T7 escaping ingest |
| L6 Presentation | Plain-text rendering, no auto-links, strict CSP | **Execution only (T6).** Plain text doesn't stop phishing or wrong content; only L1, L2 and L5 do |

---

## 4. Evaluation

### 4.1 Rules (fixed before any results are seen)

- **Development uses dev data only.** That covers retriever choice, window size, gate thresholds, scanner policy, the detector catalogue and every comparison.
- **The final test run happens once, frozen.** Before it, the code commit, dataset hashes, configuration and operating points are recorded in `eval/results/final-manifest.json`.
- **Changes after the test run are disclosed.** Any change made after the final run is disclosed, and its results are labelled "re-used test set".
- **Two kinds of gate:**
  - **acceptance targets** in `eval/acceptance.toml`, fixed now and below, which can fail even if nothing regressed;
  - **regression floors** in `eval/regression.toml`, set from the first measured dev run. They prevent backsliding and are not evidence of quality.
- **Every reported number** names its split, condition, mode and denominator (attempted, answered, abstained, rejected, failed).

**Acceptance targets (predeclared 15 Oct 2026, before any measurement):**

| # | Target | Population |
|---|---|---|
| AT1 | Unsupported-answer rate ≤ 10% | Test negatives (evidence-removed, hard and out-of-corpus) |
| AT2 | ≥ 70% answered *and* citing the gold chunk | Test condition A |
| AT3 | 100% rejected with 422 | PII and active-content inputs |
| AT4 | 100% of attacks fail by their oracle with all layers on | Our attack catalogue (condition F) |
| AT5 | ≤ 2% of clean chunks quarantined (≤ 8 of 426) | Condition I |
| AT6 | Reported as measured; no target | Condition B (masked) and condition H (held-out) |

The targets were set without looking at any results. If a target is missed, the miss is reported; the target is not loosened.

### 4.2 Conditions

| ID | Condition | Measures |
|---|---|---|
| A | Answerable questions as written | Retrieval, coverage, citation integrity, answer support |
| B | Instrument name masked | Retrieval without the lexical shortcut (diagnostic; masked questions can be truly under-specified) |
| C | Evidence removed: gold chunk withheld | Refusal when the evidence is gone |
| D | Hard negatives and out-of-corpus questions | Gate behaviour on high-overlap questions it cannot answer |
| E | PII and active-content inputs | Input rejection (counted separately from abstention) |
| F | Attack catalogue plus direct injections, all layers on | Attack success by oracle; the layer that stopped it |
| G | Ablation: F with L1 off; then L1 and L2 off; then L1, L2 and L5 off | Value of each layer; what reaches a user with no defences |
| H | Held-out deepset payloads, with L1 off | Content-detector detection rate on attacks we didn't write, by language |
| I | Scanner over all 426 clean chunks | False positives, plus whether quarantine removes any answerable gold chunk |

**Outcome categories,** always reported separately:
- *supported answer*;
- *unsupported answer*;
- *alternative support*: in C, an answer citing another chunk of the same instrument. Flagged for audit, not counted as a failure automatically;
- *safe abstention*;
- *input rejection*.

### 4.3 Metrics

- **Retrieval:** Recall@1, Recall@5 and MRR.
- **Coverage:** the share of answerable questions that receive an answer.
- **Citation integrity:** the validator pass rate. It is 100% by construction for the extractive path, which is stated, not claimed as a result.
- **Answer support:** an excerpt is *supported* if it cites the gold chunk **and** contains at least 50% of the gold answer's content tokens. That definition is fixed now. It is backed by the AI label audit's support labels on a 40-item sample, with agreement reported.
- **Abstention:** the unsupported-answer rate on negatives, plus a coverage-versus-unsupported-rate curve on dev that shows the chosen operating point.
- **Security:**
  - attack success rate by objective;
  - the intercepting layer per attack;
  - a stage trace showing whether the payload reached retrieval, the response and the UI;
  - scanner true-positive and false-positive rates, kept separate from end-to-end success;
  - held-out detection rate by language.
- **Operational:** p50 and p95 `ask` latency, plus index build and scan time.

### 4.4 Comparisons (all on dev)

1. BM25 versus TF-IDF cosine similarity, on A and B.
2. A one-sentence versus a two-sentence excerpt window, scored by answer support.
3. Scanner policy "any High" versus "any High, or two Medium", on dev attacks and dev false positives.

**Retrieval versus long context.** D1 also argues retrieval against putting the whole corpus in context: 426 chunks is about 110k tokens. The core has no LLM, real corpora are far larger, and chunk-level citations are needed. This is a reasoned argument, not a measured comparison, and it is labelled as such.

### 4.5 Security report

`legisqa eval --suite security` writes `eval/results/security-<date>.json`, and `report.py` renders the tables in `evidence/security-report.md`, so **the numbers come from the run, not from hand-writing.** The report contains:
- **Per attack:** ID, technique, objective, oracle result, stage trace, intercepting layer and detector, and event ID.
- **Per layer:** interceptions with all layers on, and in each ablation step.
- **Held-out results** by language, listing the misses.
- **False positives,** each with its detector and span.
- **A screenshot from the `demo` profile.**
- **Commentary:**
  - what was caught;
  - what got through and why;
  - why provenance is decisive;
  - what production would add.

**Honesty rules.**
- Plain-text rendering is never counted as stopping phishing.
- Misses, unexercised stages and not-run sets stay visible.
- Every rate names its population.

### 4.6 Failure analysis (in `verify.md`)

`verify.md` includes:
- 10 misses from condition B, each classified;
- every unsupported answer in C and D;
- every *alternative support* case;
- every false positive and held-out miss, each with its root cause.

For one failure, it also records a competing explanation that was considered and tested.

---

## 5. Verification and CI

**`uv run python scripts/verify.py`** is the single command, and it runs on Windows, macOS and Linux. It prints a table where each step shows **PASS, FAIL or SKIPPED**:

1. `ruff format --check` and `ruff check`
2. `mypy --strict` on `src/` and `scripts/`
3. `pytest` with coverage (85% floor), including contract tests for every outcome in 3.3
4. Corpus integrity: hashes match, no case law, attribution present, overlay absent in `prod`, overlay IDs unique
5. Evaluation: acceptance targets AT1–AT3 on dev during development, and on test only in the final frozen run; plus regression floors
6. Security suite: AT4 and AT5, plus H if the held-out file is present
7. Frontend (Node required): `npm ci`, `tsc --noEmit`, `vitest run`, `vite build`, and a check that the generated types are current. Without Node this step is **SKIPPED, clearly shown**, and `--require-frontend` (always set in CI) turns a skip into a failure
8. Hygiene:
   - `.env`, `data/raw/` and `tmp/` are not tracked;
   - no credential-like strings;
   - no tracked file contains a term from a **local, git-ignored deny-list** (`tmp/denylist.txt`), which keeps references we must not publish out of the repo. CI skips this step because the list is local by design.

**Selected tests beyond those implied above:**
- **Contract:** every row of the outcome table; impossible `GroundedAnswer` combinations rejected; the empty-citations answer rejected; an audit-write failure returning 503 with the response withheld; startup with a tampered corpus leading to `/readyz` 503, `/v1/answers` 503 and the CLI exiting with code 3.
- **Detectors:** positives from the dev catalogue, and negatives from the corpus's false-positive traps.
- **Security integration:**
  - provenance locates the inserted span;
  - an overlay chunk never replaces its original;
  - quarantined chunks are never retrieved;
  - an output-guard backstop with the scanner disabled yields `unsafe_output`;
  - detectors never read `synthetic_adversarial`;
  - a rejected question's text appears in no log, audit or event payload.
- **API:** profile-gated routes return 404 in `prod`; security headers are present.
- **Frontend:** answered and abstained states; a hostile `<script>` or `<img onerror>` passage renders as literal text with no element created; 422 and 503 envelopes are shown with their `request_id`.
- **Clean checkout:** the final commit is cloned into a fresh directory and the documented commands are run verbatim. The result is recorded with the operating system tested.

**CI:** `.github/workflows/ci.yml` runs on push and pull request, on Ubuntu and Windows, with Python 3.12 and Node 22, running `verify.py --require-frontend`. It needs no secrets. Workflows run only on what you approve and push.

---

## 6. Operability

- **Run:**
  - `uv sync`
  - `uv run legisqa ask "What does the Privacy (Persons Reported as Missing) Rule 2014 permit?"` (the example will be confirmed against the corpus)
  - `uv run legisqa serve`, which serves the API and UI on `127.0.0.1:8000`
  - `--profile demo`, which loads the overlay so interceptions can be seen
- **Configuration:** `LEGISQA_` environment variables, with `.env.example` listing every setting. The default profile is `prod`. Settings are validated at startup and need a restart to change.
- **Secrets:** none exist. Production would inject credentials (for authentication, when added) from a secrets manager.
- **Logs:**
  - JSON, one line per stage, all sharing `request_id`;
  - a redaction filter means rejected questions are logged only as length and fingerprint.
- **Audit:** `var/audit/answers.jsonl`, holding the request ID, timestamp, question fingerprint and redacted text, corpus version, retrieved IDs and scores, citations, outcome, reason, event IDs and latency. It fails closed (3.3).
- **Security events:** `var/audit/security.jsonl`.
  - **Corpus findings** store the detector, severity and span offsets, with matched text truncated to 80 characters. The corpus is public, but truncation limits re-display of payloads.
  - **Question findings** store the detector, offsets and a fingerprint only, never question text.
  - **Retention:** local files only; the production retention policy is described, not implemented.
  - `/v1/security-events` and quarantined-source viewing exist only in `demo`/`eval`, because production would need authentication.
- **Status:** `/healthz` reports liveness. `/readyz` reports ready only when the corpus is loaded, hashes match, the quarantine count is within its expected bound and the audit is writable.
- **Failure modes:**

  | Failure | Behaviour |
  |---|---|
  | Corpus missing | Unready, 503 |
  | Hash mismatch | Unready, 503 |
  | Quarantine count jumps between versions | Readiness warning (possible poisoning) |
  | Audit unwritable | 503 |
  | Invalid input | 422 |
  | No retrieval hits | Abstain |
  | Output guard trips | Abstain, plus an event |
  | Internal error | 500 with `request_id` |

  Each row also records its log signal and the operator action.
- **Rollback:** code and corpus versions are deployed as a **compatible pair**. The manifest records a schema version the code checks at startup, so an incompatible pair stays unready instead of half-working.

---

## 7. Local to cloud

**Example shape, cloud-agnostic:**
- a container platform;
- object storage for signed corpus snapshots;
- a log pipeline to the SIEM;
- an append-only audit store.

**PR pipeline:**
- `verify.py --require-frontend`;
- dependency audits (`pip-audit`, `npm audit`);
- secret scanning;
- an SBOM;
- an image build and scan.

**Merge to main:**
1. Sign the image.
2. Publish the corpus as a versioned, hashed artefact through its own pipeline: fetch from the authoritative source, then run provenance, the scan, the evaluation gates and human review of the quarantine queue.
3. Deploy to staging and run the full evaluation and security suite against the deployed service.

**Production:**
- approval recording the risk owner;
- a canary with alerts on abstain rate, `unsafe_output` rate, quarantine count and p95 latency;
- automatic rollback to the last compatible pair.

**Change control:** code and corpus are separately versioned, and both go through the same gates. That's the operational-resilience posture a bank expects. Described, not claimed as compliance.

**Next steps, as gaps:**
- authentication and authorisation (SSO, per-corpus access);
- privacy controls for internal documents;
- a hybrid lexical and vector index above a stated corpus size, at which point memory and latency budgets break;
- a trained injection classifier and a reviewed quarantine queue;
- a dedicated PII service;
- async workers if request concurrency grows. Retrieval is CPU-bound and takes milliseconds at this size, which is documented and measured.

**Optional future LLM answerer:** would sit behind the `Answerer` interface, inheriting L1–L6, the citation contract and the gates. It would add a semantic support check, evidence spotlighting, a canary token and tool limits.

---

## 8. Build process

### 8.1 Approval, commit and push rules (yours)

1. **Snapshot-exact approval.**
   - When a step is ready, I stage exactly its files and send you:
     - the proposed commit message;
     - `git diff --cached --stat`;
     - the staged-tree fingerprint (`git write-tree`);
     - the `verify.py` table;
     - a few-line "what to check" note;
     - anything notable.
   - I commit only after your **"approve"**, and only if the staged-tree fingerprint still matches what you approved.
   - While waiting I may keep working in the working tree, but I never stage anything else until that commit is made.
2. **Push is a separate approval.** Nothing is pushed until you say "push". You can approve both in one reply.
3. **No amend, rebase, squash or force-push, ever.**
4. **Before each push, I run a content review:** the deny-list check, a credential scan, a check for personal data, and a read-through of the diff for anything that names anyone other than Westpac. Public-data source credits, tool names and licence attributions are kept, because licences and the brief require them.
5. **Commit messages:** authored with your Git identity, ending with the `Co-Authored-By: Claude Opus 5.5` trailer and the session link trailer, unless you tell me to drop the session link (open item 1).

### 8.2 Time accounting

| Category | Counted in the 3 hours? | Recorded where |
|---|---|---|
| Planning and data inspection before the start signal (today, about 3.5 hours of discussion) | No; disclosed separately | `verify.md` timebox log |
| Building, testing, evidence writing, waiting for approvals, the walkthrough with you | **Yes** | Timebox log with timestamps |
| Packaging (≤ 15 minutes): final push, CI check, submission note | Separate allowance | Timebox log |

**Hard stop at 3:00.** Whatever passes `verify.py` is committed, with the gaps recorded, and implementation stops. Nothing is "finished during packaging".

### 8.3 Commit plan (6 commits, ~165 minutes plus a 15-minute reserve)

| # | Time | Commit | Contents | Protected evidence produced |
|---|---|---|---|---|
| 1 | 0:00–0:20 | `chore: scaffold backend, frontend, config, logging, CI and intent` | Package skeleton; `config.py`; `errors.py`; `models.py` with invariants; logging with redaction; `verify.py`; `ci.yml`; Vite skeleton; `intent.md`; this plan; README skeleton | Contract tests for the schema invariants |
| 2 | 0:20–1:00 | `feat: licensed corpus, adversarial overlay, provenance and injection scanner, BM25 retrieval and gate` | `build_corpus.py`; sample data with splits, negatives and manifest; overlay; `corpus.py`; `security/*`; `retrieval.py`; `gate.py`; tests; audit sample exported | Provenance, detector, quarantine and retrieval tests |
| 3 | 1:00–1:35 | `feat: end-to-end answer workflow with citation validation, output guard, abstain and audit` | `guards.py`; `answerers/*`; `citations.py`; `output_guard.py`; `service.py`; `audit.py`; `api.py`; `cli.py`; tests | The full workflow from CLI and API, with every outcome in the contract table |
| 4 | 1:35–2:10 | `feat: evaluation harness, acceptance gates, injection suite with ablations, report renderer` | `evaluation/*`; `acceptance.toml`; `regression.toml`; dev results; frozen final test run; security results; rendered report tables | Acceptance results, ablations, held-out results (if provided) |
| 5 | 2:10–2:35 | `feat: React presentation layer over the answers API` | Generated types; client; components; static serving; Vitest tests | Hostile-text escaping test; UI showing answered, abstained and quarantined states |
| — | 2:35–2:50 | **Walkthrough with you (15 minutes, inside the build)** | You explain, in your own words: one design choice; one correction made to generated code; one failed experiment; one safety limit; one production trade-off. Recorded in `agentic-workflow.md` | Ownership evidence |
| 6 | 2:50–3:00 (plus reserve) | `docs: evidence pack, review log, criteria ledger, security commentary, README` | `design.md`, `agentic-workflow.md`, `verify.md`, `operate.md`, `decisions.md`, `security-report.md` commentary, `criteria-ledger.md`, `design-review-log.md`; README with a real example and screenshots; clean-checkout run | Ledger with a status for every criterion |

The evaluation now comes **before** the UI, so it can't be squeezed out. The 15-minute reserve sits between commit 5 and the hard stop.

**Cut order if behind, applied only at an approval request where I tell you:**
1. comparison 2;
2. the `SecurityPanel` component;
3. condition H (claim narrowed to our catalogue);
4. the Windows CI runner;
5. UI polish, keeping a minimal ask, answer and citation view.

**Never cut:**
- the contract and invariants;
- provenance, the scanner and the output guard;
- plain-text rendering;
- the acceptance gates and the frozen test run;
- the evidence pack and ledger;
- the walkthrough;
- honest reporting.

---

## 9. Evidence pack

| File | Contents |
|---|---|
| `intent.md` | Problem; users; assumptions; constraints (3 hours, no keys, public data, no LLM); out of scope (legal advice, case law, authentication, generative answers, personal-advice detection); success criteria = AT1–AT6 |
| `design.md` | Workflow and data flow; component boundaries; the state and error contract; trade-offs; security and privacy (the six layers, redaction, profile gating); presentation layer; production shape; the future-answerer seam; a short code tour |
| `agentic-workflow.md` | Tools actually used (Claude Opus 5.5 as coding agent through the Claude app; ChatGPT Astra as adversarial plan reviewer; the AI used for the label audit); decomposition; representative steering prompts (approved, redacted excerpts); your interventions; how output was reviewed; the walkthrough record |
| `design-review-log.md` | Every finding from ChatGPT Astra's adversarial review, with its disposition and the resulting design change. Written now and kept current |
| `verify.md` | Every check with PASS, FAIL or SKIPPED; results by condition with denominators; acceptance outcomes; comparisons; failure analysis; label-audit summary; known gaps; local vs PR vs pipeline split; timebox and approval log |
| `operate.md` | Section 6 in full |
| `security-report.md` | Section 4.5 |
| `decisions.md` | Five records. **D1** retrieval: keyword vs vector vs long context. **D2** no LLM in the product. **D3** trust boundaries: provenance first, detection as backstop, verification in code, fail-closed audit, logging (not blocking) linguistic injection in questions. **D4** data: legislation-only subset, case law excluded, the 79% shortcut, attacks in an overlay. **D5** deliberately not built |
| `criteria-ledger.md` | One row per brief requirement: source (paraphrased), applicability, planned mechanism, acceptance condition, execution identity (commit, hashes), actual evidence (test, result or file section), mode and denominator, status (demonstrated, partial, failed, not run, not applicable), your ownership, and the remaining limitation |

**Your interventions so far** (recorded accurately; more will be added during the build):
- chose the solution direction;
- questioned the data sources;
- withdrew a third-party dataset that couldn't be published;
- chose the Open Australian Legal QA subset;
- delegated the label audit to an independent AI;
- required approval for every commit and every push;
- removed all API keys, so the product has no LLM;
- added the React presentation layer;
- asked for embedded injection attacks with reported interception;
- asked how injection can be detected without an LLM;
- commissioned the adversarial plan review by ChatGPT Astra;
- set the publication rules: only Westpac referenced, plus a git-ignored `tmp/` folder.

---

## 10. Brief traceability (planned mechanisms; the final status lives in `criteria-ledger.md`)

| Brief requirement (paraphrased) | Planned mechanism | Acceptance evidence |
|---|---|---|
| 3-hour build timebox, plus ≤ 15 min packaging | Section 8.2–8.3; hard stop | Timebox log; commit times as corroboration only |
| Public repo, incremental commits, no history rewriting | Repo already public; 6 approved commits; no amend or force-push | Final history check |
| AI coding agent as primary implementation tool | Claude builds each commit | `agentic-workflow.md`, with real excerpts |
| Meaningful, clear outcome credible in a regulated enterprise | Cited evidence excerpts with abstention and injection defences | AT1–AT5 results |
| Product AI optional | No LLM; D2 | `decisions.md` |
| One meaningful end-to-end workflow | Section 1 | E2E test; a real README example (one answered, one abstained) |
| Full-stack ownership of the slice | Data build, service, API, CLI, UI, evaluation, CI, operations | Clean-checkout run |
| Clear setup and run instructions | README tested verbatim | Clean-checkout record |
| Build/test/verify command | `verify.py` | CI runs the same command |
| Tests and evaluation or acceptance checks | Section 5; AT1–AT6 | `verify.md` |
| Safe configuration, errors and failure paths | The section 3.3 contract; fail-closed audit; unready state | Contract tests |
| At least one guarded failure, rejection, degrade or abstain | 422 rejections, abstentions, quarantine, unready 503 | Conditions C–I |
| Operational thinking | Section 6 | `operate.md`; readiness tests |
| Evidence of agent use and verification | `agentic-workflow.md`, `verify.md`, `design-review-log.md`, the walkthrough | Ledger rows |
| No paid keys, private or Westpac credentials, or assessor setup | No keys exist | Clean checkout with no `.env`; CI without secrets |
| Synthetic, sample or public data only | CC BY subset plus a synthetic overlay; raw file ignored | Integrity check; attribution |
| Backing services, sample data and stubs included or described | In-memory corpus; no services | README |
| CI/CD path into an enterprise cloud explained | Section 7, labelled as design | `design.md`, `operate.md` |
| Lightweight evidence pack | Section 9, kept concise and linking result files | Ledger |
| README contents | Filled in commit 6 from real runs | Clean-checkout record |
| Known gaps and next steps | `verify.md`; section 7 | Ledger "remaining limitation" column |
| Submission notes: link, time, tools | Packaging | Checklist |
| Interview readiness and accountability | The walkthrough; decision records; code tour | Walkthrough record |

**Engineering quality bar applied throughout** (general good practice):
- typed code with Pydantic at boundaries;
- small cohesive modules;
- configuration separate from logic;
- no imports inside functions except justified lazy imports;
- no speculative abstractions: each interface must isolate a real change boundary;
- every claim in the evidence pack backed by an inspectable artefact.

A final review at commit 6 checks for unused modules, inconsistent patterns and unnecessary scaffolding.

---

## 11. Risks

| Risk | Mitigation |
|---|---|
| You can't explain the generated code | Approvals with "what to check" notes; the 15-minute walkthrough inside the build; code tour |
| Excerpt cites correctly but doesn't answer the question | Answer support measured separately (4.3); label audit; output labelled "evidence excerpt" |
| Test data leaks into design decisions | All choices made on dev; frozen final run; predeclared targets |
| Refusal labels are wrong (alternative support exists) | The *alternative support* category plus audit; limitation stated |
| Self-written attacks inflate results | Held-out set with frozen detectors; ablations; oracle-based success; misses reported |
| Provenance makes the content detectors look untested | H and G run with L1 off |
| False positives on real legislation | Condition I; AT5; anchored patterns |
| Confidential or third-party references leak into the public repo | `tmp/` ignored; local deny-list check; pre-push content review; brief never copied |
| Approval waits stall the clock | Work continues unstaged; waits logged; the reserve |
| Schedule overrun | Evaluation before UI; cut order; hard stop |
| Assessor lacks Node | Python-only core; SKIPPED made visible; screenshots |

---

## 12. Open items (implementation waits for your start signal)

1. **Session-link trailer:** keep or drop the `Claude-Session:` line in commit messages? Default is keep.
2. **Git identity** for commits, meaning name and email. None is configured in the clone yet, so I need the name and email to use (for example your GitHub noreply address).
3. **Held-out set:** `deepset/prompt-injections` into `data/raw/` (optional).
4. **Deny-list:** I'll create `tmp/denylist.txt` with the terms you've told me must never be published. Add any others you want blocked.
5. **Start signal:** implementation begins only when you say so.
