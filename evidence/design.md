# Design

## What the slice does

A compliance or legal analyst asks a question about Australian legislation. The service either returns
**verbatim evidence excerpts whose citations are machine-verified** against a pinned, licensed corpus, or
it **abstains** and says why. Passages that try to manipulate the system or its readers are detected at
load time and quarantined; a backstop re-checks every answer before it leaves the service.

There is **no LLM in the product** (decision D2). AI was used to build and to review the solution.

## Architecture and data flow

```
INGEST (startup)
sample-data/corpus.jsonl (426 CC BY passages) + adversarial overlay (demo/eval profiles only)
   |-- manifest check: every file hash must match sample-data/manifest.json, else UNREADY (503)
   |-- L1 provenance: passage text hash vs the manifest hash of the source it claims -> quarantine
   |-- L2 content scan: 9 deterministic detectors -> quarantine
   v
clean passages -> BM25 index           quarantined passages -> security events (never answerable)

REQUEST (React UI, CLI or HTTP API)
question -> L3 input guard --(empty / too long / PII / markup or hidden characters)--> 422 rejected
               | linguistic injection ("ignore your rules") -> security event, request continues
               v
            BM25 retrieval -> answerability gate --(weak or ambiguous evidence)--> abstain: low_evidence
               v
            L4 extractive answerer: verbatim sentence window from the top passage, citation computed by code
               v
            citation validator --(unknown / quarantined / not retrieved / not verbatim)--> abstain: ungrounded
               v
            L5 output guard --(markup, external link, credential request, AI-directed text)--> abstain: unsafe_output
               v
            audit write (fails closed: no audit, no answer -> 503) + JSON logs + security events
               v
            L6 presentation: React renders plain text only, no links, strict Content-Security-Policy
```

## Component boundaries

| Module (`src/legisqa/`) | Responsibility | Depends on |
|---|---|---|
| `config.py` | Typed, immutable settings; profiles `prod` (default), `demo`, `eval` | - |
| `errors.py` | The outcome contract (HTTP status and CLI exit code per outcome) and exceptions | - |
| `models.py` | Pydantic schemas with cross-field invariants (an answer always has citations; an abstention never has text) | `errors` |
| `corpus_build.py` | Deterministic build of `sample-data/` from the raw export | `models` |
| `corpus.py` | Load, verify against manifest, provenance check, quarantine | `security` |
| `security/` | Detectors (pure functions), severity policy, redacted security events | - |
| `retrieval.py`, `gate.py` | BM25 over clean passages; relative strength and margin; the gate decision | - |
| `guards.py` | Input validation and PII detection (TFN check digit, Luhn, AU phone, email) | `security` |
| `answerers/` | `Answerer` protocol (the seam for any future answerer) and the extractive implementation | `retrieval` |
| `citations.py`, `output_guard.py` | Citation integrity and the output backstop | `corpus`, `security` |
| `service.py` | `run_pipeline` (pure, shared with evaluation) and `AnswerService` (I/O, audit, events, readiness) | all of the above |
| `api.py`, `cli.py` | Thin adapters over the service | `service` |
| `evaluation/` | Datasets, metric definitions, dev tuning, frozen final run, security suite, report renderer, CI checks | `service` |

`run_pipeline` is the single code path used by both the service and the evaluation harness, so the
evaluation measures exactly what serves requests.

## Key trade-offs

- **Keyword retrieval (BM25) rather than vectors or long context.** Offline, deterministic, explainable
  (top matching terms are returned with every hit) and strong on exact legal names. Measured on dev: BM25
  beat TF-IDF (Recall@1 80.5% vs 71.1% with instrument names masked). Weakness: synonyms and paraphrase,
  visible in the masked-name results. See D1.
- **Extractive answers rather than generated prose.** Nothing generated can be steered by poisoned text,
  and every word shown is a verbatim quote. The cost is readability and answer completeness: only 51.2%
  of test excerpts meet the strict support definition (D2).
- **Provenance first, pattern detection second.** For documents with a trusted reference, a hash check
  catches any alteration regardless of wording. Pattern detectors are the backstop for content without a
  reference and are explicitly evadable (D3).
- **Fail closed.** A missing or tampered corpus leaves the service unready; an unwritable audit log blocks
  answers. Availability is traded for auditability.
- **Linguistic injection in questions is logged, not blocked**, because there is no model to hijack;
  markup and hidden characters in questions are rejected because they would flow into logs and the UI.

## Security and privacy

- **No secrets exist** in the product. No outbound network calls at runtime.
- **Question text is never logged or audited**; logs and the audit trail hold a length and a SHA-256
  fingerprint. PII-bearing questions are rejected before retrieval.
- **Security events** about corpus content keep at most 80 characters of matched text; events about
  questions or answers keep only offsets and a fingerprint.
- **Profile gating:** `/v1/security-events` and viewing quarantined passages exist only in `demo` and
  `eval`, because in production they would need authentication.
- **Browser:** plain-text rendering, no Markdown, no auto-links; CSP `default-src 'self'`,
  `frame-ancestors 'none'`, `object-src 'none'`; `X-Content-Type-Options: nosniff`; no external fonts or
  scripts.
- **Data:** only CC BY 4.0 legislation; case law excluded; attack text is synthetic and labelled; the raw
  export is git-ignored.

## Presentation layer

The React UI is a thin, typed client: its TypeScript types are generated from the API's OpenAPI schema,
and `verify.py` fails if either the schema or the types are stale. The excerpt is set like a statute page,
with the citation and "quote verified against source" as a margin note. In the `demo` profile a security
panel lists everything intercepted at load. Screenshots: `evidence/screenshots/`.

## Production and cloud shape (design, not built)

- **Runtime:** a container on the bank's container platform behind the internal gateway with SSO; the
  corpus as a signed, versioned artefact in object storage; logs and security events to the SIEM; audit
  records to an append-only store.
- **Corpus pipeline:** fetch from the authoritative source (for legislation, the official registers),
  rebuild, provenance and content scan, evaluation gates, human review of anything quarantined, then
  publish the signed snapshot. A jump in quarantine count blocks promotion.
- **Scaling:** retrieval is CPU-bound and sub-millisecond at 426 passages (p50 0.88 ms offline). When the
  corpus no longer fits comfortably in one process's memory, or latency budgets are missed under load
  tests, move to a hybrid lexical and vector index served separately. That threshold should be measured,
  not assumed.
- **Future LLM answerer:** would implement `Answerer`, inherit L1, L2, L5, L6, the citation contract and the
  evaluation gates, and add a semantic support check, evidence spotlighting, a canary token and tool limits.
  Linguistic injection in questions would then be rejected rather than logged.

## Code tour (where to look first)

1. `service.py: run_pipeline` - the whole request path in one function.
2. `models.py: GroundedAnswer._check_invariants` - the evidence contract.
3. `corpus.py: load_corpus` - provenance and quarantine.
4. `security/detectors.py` - each detector is a small, separately tested function.
5. `evaluation/harness.py: tune_gate`, `final_run`, `run_attacks` - how numbers are produced.
6. `scripts/verify.py` - what CI runs.
