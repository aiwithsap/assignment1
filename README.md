# Legislation Q&A with verified citations

A thin, locally runnable slice of a research assistant for compliance and legal analysts. You ask a
question about Australian legislation. The service returns **verbatim evidence excerpts whose citations
are machine-verified** against a pinned, licensed corpus, or it **abstains and says why**. Passages that
try to manipulate the system or its readers are detected at load time, quarantined and reported, and a
backstop re-checks every answer before it leaves the service.

There is no LLM in the product and no API key anywhere. The solution was built with an AI coding agent
and reviewed by a second AI; see the [evidence pack](#evidence-pack).

**Results on the held-back test split** (targets fixed before measurement; details in
[`evidence/verify.md`](evidence/verify.md)):

| | Result | Target |
|---|---|---|
| Questions answered from the correct passage | 92.9% of 297 | at least 70% |
| Questions that must be refused but were answered | 5.0% of 120 | at most 10% |
| PII and markup inputs rejected | 13 of 13 | all |
| Planted attacks that succeeded, all defences on | 0 of 31 | none |
| Genuine passages wrongly quarantined | 0 of 426 | at most 8 |

## Prerequisites

- [uv](https://docs.astral.sh/uv/getting-started/installation/), which installs Python 3.12 automatically
- Node.js 20 or later, only to build or test the browser UI
- No accounts, keys or network services

## Setup

```bash
git clone https://github.com/aiwithsap/assignment1.git
cd assignment1
uv sync
```

## Run

```bash
uv run legisqa ask "What are the assay limits for the content of active ingredients or components in tablets and capsules?"
uv run legisqa serve                 # API and UI on http://127.0.0.1:8000 (OpenAPI docs at /docs)
uv run legisqa serve --profile demo  # also loads the attack overlay, to watch interceptions
uv run legisqa verify-corpus         # manifest hashes, overlay isolation, quarantine counts
```

`ask` prints the JSON response. Exit codes follow the outcome contract: 0 answered or abstained, 2 rejected
input, 3 service unavailable, 1 internal error.

### Example

```text
$ uv run legisqa ask "What are the assay limits for the content of active ingredients or components in tablets and capsules?"
{
  "outcome": "answered",
  "corpus_version": "c-968bf594e635",
  "result": {
    "status": "answered",
    "answer": "Schedule 2¾Tablets and capsules: assay limits for content of active ingredient or component in a tablet or capsule Note: See section 14. Column 2 Column 3 Column 4 Active ingredient Not less than ...",
    "citations": [{ "chunk_id": "c_2aa4572e79ef", "quote": "Schedule 2¾Tablets and capsules: ..." }]
  },
  "retrieved": [{ "chunk_id": "c_2aa4572e79ef", "top_terms": ["capsules", "active", "tablets", "content", "assay"], ... }],
  "notice": "Evidence excerpts from public legislation, provided for research. Not legal advice."
}

$ uv run legisqa ask "Under the Queensland Weather Control Act 2036, who may authorise cloud seeding?"
  -> "outcome": "abstained", "abstain_reason": "low_evidence"   (exit 0)

$ uv run legisqa ask "My TFN is 123 456 782, what applies?"
  -> "outcome": "rejected", "code": "pii_detected"              (exit 2)
```

The "¾" in the first excerpt is an encoding artefact in the source data, quoted verbatim (see Known
limitations).

## Browser UI

```bash
cd frontend && npm ci && npm run build && cd ..
uv run legisqa serve --profile demo   # open http://127.0.0.1:8000
```

The UI is a thin client of the API. Its TypeScript types are generated from the API's OpenAPI schema
(`uv run python scripts/export_openapi.py`, then `npm run gen:types`), and every string is rendered as plain
text. In the `demo` profile it also lists the content intercepted at load time.

![Answer with a verified citation in the margin](evidence/screenshots/answer.png)

## Verify

One command runs every check CI runs and prints a PASS / FAIL / SKIPPED table:

```bash
uv run python scripts/verify.py
```

It runs format, lint and strict type checks, 177 Python tests (coverage floor 85%), corpus integrity, the
evaluation and security gates, the UI checks (13 tests, type check, build, generated-types freshness) and
repository hygiene. CI (`.github/workflows/ci.yml`, Ubuntu and Windows) runs it with `--require-frontend`,
which turns a skipped UI check into a failure.

## Evaluate

```bash
uv run legisqa eval dev     # tune on the dev split only; writes eval/results/dev.json
uv run legisqa eval final   # frozen test run with the dev-chosen settings; renders evidence tables
uv run legisqa eval check   # CI gate: dev floors, security targets, frozen-run integrity
```

## Data

`sample-data/` holds 426 passages of Commonwealth and state legislation (CC BY 4.0, see
[`sample-data/ATTRIBUTION.md`](sample-data/ATTRIBUTION.md)), a dev/test question split, refusal cases, and a
separate, labelled overlay of 31 attack passages used only in the `demo` and `eval` profiles. Everything
needed to run and test is committed. Rebuilding from the raw export (not committed) is deterministic:

```bash
uv run python scripts/build_corpus.py --raw data/raw/qa.jsonl
```

## Known limitations

- **Excerpts, not tailored answers.** 92.9% of test questions are answered from the right passage, but only
  51.2% of excerpts meet the strict, predeclared support measure.
- **Keyword retrieval.** With instrument names removed from questions, only 60.3% are answered from the
  right passage. Paraphrase and synonyms are the weak spot.
- **Detectors are English and pattern-based.** They were tested on our own attack catalogue only, because
  the planned held-out set was unavailable. Provenance checking is the decisive control.
- **The gate measures evidence strength, not topic match.** Its strength measure can saturate on short
  passages (`evidence/verify.md`, failure analysis).
- **Source encoding artefacts** are quoted verbatim, to keep provenance hashes faithful.
- **Single user, localhost, no authentication.** Not legal advice.

## Evidence pack

| File | Purpose |
|---|---|
| [`evidence/intent.md`](evidence/intent.md) | Problem, users, assumptions, constraints, scope, acceptance targets |
| [`evidence/design.md`](evidence/design.md) | Architecture, data flow, boundaries, trade-offs, security, production shape, code tour |
| [`evidence/agentic-workflow.md`](evidence/agentic-workflow.md) | Tools, decomposition, steering, how AI output was reviewed |
| [`evidence/verify.md`](evidence/verify.md) | Checks, results, disclosures, failure analysis, known gaps, timebox log |
| [`evidence/operate.md`](evidence/operate.md) | Running, configuration, logs and audit, failure modes, rollback, local to cloud |
| [`evidence/decisions.md`](evidence/decisions.md) | Five decision records |
| [`evidence/security-report.md`](evidence/security-report.md) | Prompt-injection and poisoned-content interception report |
| [`evidence/design-review-log.md`](evidence/design-review-log.md) | Independent adversarial review (ChatGPT Astra) and the design changes it caused |
| [`evidence/criteria-ledger.md`](evidence/criteria-ledger.md) | Status of every requirement, with evidence and limitations |
| [`evidence/plan.md`](evidence/plan.md) | The build plan as approved before implementation |
