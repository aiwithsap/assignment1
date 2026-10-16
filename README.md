# Legislation Q&A with verified citations

A thin, locally runnable slice of a research assistant for compliance and legal analysts. You ask a
question about Australian legislation. The service returns **verbatim evidence excerpts whose
citations are machine-verified** against a pinned, licensed corpus, or it **abstains and says why**.
Content that tries to manipulate the system or its readers is detected, quarantined and reported.

There is no LLM in the product and no API key anywhere. The solution was built with an AI coding
agent; see [the evidence pack](#evidence-pack).

> **Status:** under construction, committed in stages. This README is completed in the final
> commit with a real example, known limitations and results. The build plan is in
> [`evidence/plan.md`](evidence/plan.md).

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (installs Python 3.12 automatically)
- Node.js 20 or later, only to build or test the browser UI

## Setup

```bash
uv sync
```

## Run

```bash
uv run legisqa --version
uv run legisqa show-config
```

The `ask`, `serve` and `eval` commands arrive with their features.

## Verify

One command runs every check CI runs and prints a PASS / FAIL / SKIPPED table:

```bash
uv run python scripts/verify.py
```

CI runs the same command with `--require-frontend`, which turns a skipped UI check into a failure.

## Evidence pack

| File | Purpose |
|---|---|
| [`evidence/plan.md`](evidence/plan.md) | Build plan and requirement traceability |
| [`evidence/intent.md`](evidence/intent.md) | Problem, users, assumptions, constraints, scope, success criteria |
| [`evidence/design-review-log.md`](evidence/design-review-log.md) | Independent adversarial review findings and how the design changed |

Further evidence files (design, agentic workflow, verification, operations, decisions, security
report, criteria ledger) are added as the corresponding work lands.
