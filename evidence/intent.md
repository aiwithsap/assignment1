# Intent

## Problem

Analysts in a bank's risk, compliance and legal teams spend time locating the exact legislative
text that answers a question. Generic search returns documents, not evidence; generative tools can
produce fluent answers whose support cannot be checked. In a regulated setting, an answer that
cannot show its evidence, or that repeats manipulated content, is worse than no answer.

This slice answers questions over a pinned corpus of Australian legislation with **verbatim
excerpts and machine-verified citations**, and **abstains** when the evidence is insufficient.
It treats the corpus itself as an attack surface: tampered or manipulative passages are detected
and quarantined before they can reach a reader.

## Intended users

- **Compliance analyst:** needs the governing text quickly, with a citation they can check.
- **Legal researcher:** needs to know when the corpus does *not* answer a question.
- **Policy or control owner:** needs evidence that answers are auditable and that poisoned content
  cannot reach users.

## Assumptions

- Public CC BY 4.0 legislation (a 426-passage subset of the Open Australian Legal QA dataset) is a
  realistic proxy for an internal policy corpus. Moving to internal documents would change the
  corpus *and* add access-control and privacy requirements (see `plan.md`, section 7).
- Questions are short English text. The detectors for manipulative content are English-only.
- A single user on localhost. No authentication in this slice.

## Constraints

- About three hours of build time, with commits made incrementally and approved by the candidate.
- The core path must run locally from a clean checkout with no paid API keys or private credentials.
- Only synthetic, sample or public data; case law is excluded for licensing reasons.
- No LLM in the product. AI is used to build and to review the solution.

## Out of scope

- Legal advice, and any judgement about how the law applies to a person's situation.
- Generative (written) answers; outputs are evidence excerpts.
- Detecting requests for personal advice or questions about future law (not implemented, so not
  claimed).
- Case law; authentication and authorisation; multi-user or multi-tenant operation.
- Cloud deployment (described, not built).

## Success criteria

Acceptance targets were fixed on 15 October 2026, before any measurement. A target that is missed
is reported as missed; it is not loosened.

| # | Target | Population |
|---|---|---|
| AT1 | Unsupported-answer rate ≤ 10% | Test negatives: evidence removed, hard negatives, out-of-corpus |
| AT2 | ≥ 70% answered *and* citing the gold passage | Test questions as written |
| AT3 | 100% rejected with HTTP 422 | PII-bearing and active-content inputs |
| AT4 | 100% of attacks fail by their success oracle, all defences on | Our attack catalogue |
| AT5 | ≤ 2% of clean passages quarantined (≤ 8 of 426) | Clean corpus |
| AT6 | Reported as measured, no target | Instrument-name-masked questions; held-out attacks |

In addition: one end-to-end workflow works from a clean checkout; a single verification command
runs every CI check; and every claim in the evidence pack points to an inspectable artefact.
