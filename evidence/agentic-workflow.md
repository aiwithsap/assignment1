# Agentic workflow

## Tools

| Role | Tool |
|---|---|
| Coding agent (primary implementation) | **Claude (Opus 5.5)** in the Claude app, working directly in the repository through a shell on the candidate's computer. It wrote all code, tests, data builds and documents, and ran every check |
| Adversarial plan reviewer | **ChatGPT Astra**, a model from a different provider, asked to attack the plan before implementation (`design-review-log.md`) |
| Label audit (pending) | An independent AI model chosen by the candidate, using `review/audit-rubric.md` |
| Checks the agent could not override | `ruff`, `mypy --strict`, `pytest` with a coverage floor, `tsc`, Vitest, the corpus manifest, the evaluation gates and the frozen-run fingerprint, all run through `scripts/verify.py` |

## How the work was decomposed

1. **Planning before the clock.** The agent read the brief, interviewed the candidate, inspected the data
   (2,124 records, of which 426 were licensed legislation, and 79% of questions naming their instrument) and
   wrote `plan.md`. The plan went through four revisions, each in response to the candidate or the reviewer.
2. **Build in six approved commits:** scaffold and contracts; corpus, provenance and detectors; the
   end-to-end workflow; evaluation and security suite; UI; evidence. The candidate approved commits 1 and 2
   individually, seeing the staged snapshot fingerprint, then told the agent to continue to the end without
   further approvals. Pushing remains a separate approval.

## Where the candidate steered (paraphrased)

| Instruction from the candidate | Effect on the design |
|---|---|
| "Interview me, plan it out, analysis only" | Requirements gathered and a plan written before any code |
| Questioned where sample data would come from; proposed and then withdrew a third-party dataset that could not be published | Switched to public, licensed data with attribution and a provenance manifest |
| Chose a public legal QA dataset, "option (1) only" | Single dataset; case law excluded on licence grounds |
| Considered running live model tests on a subscription, then: no API key at all | The LLM was removed from the product; detection made deterministic (D2) |
| "Without an LLM, how will we detect these attacks?" | Provenance-first design: hash check before pattern detectors (D3) |
| Asked for a React presentation layer | UI added as a thin typed client; evaluation was scheduled before it so it could not crowd out evidence |
| Asked for prompt-injection attacks embedded in the data, with interception reported | Attack overlay, per-attack success tests, ablations, generated report |
| Approval before every commit; no push without approval; publish only Westpac references; keep private files in a git-ignored `tmp/` | Snapshot-fingerprint approvals, local deny-list check in `verify.py`, `tmp/` ignored |
| Commissioned an adversarial review of the plan | 12 findings: 8 accepted, 1 partly accepted, 3 superseded (`design-review-log.md`) |

## Representative steering prompts given to the agent by itself

The agent kept these rules in its working plan and applied them in every step:

- "All choices on dev; the test split runs once, frozen; acceptance targets fixed before measurement."
- "Never claim a check that was not run; SKIPPED is not PASS; report misses with their cause."
- "Rendering as plain text does not count as stopping phishing."
- "Before every commit: run `verify.py`; nothing from `tmp/` or `data/raw/` may be committable."

## How generated output was reviewed

| Mechanism | What it caught |
|---|---|
| Static and type checks | Unsafe type-ignore uses, untyped Literal mismatches in the outcome models, non-ASCII characters that the shell transport had turned into real invisible characters (all Python files were re-escaped to ASCII) |
| Tests written against the contract | A degenerate scoring case in tiny corpora (idf of 0) in the extractive answerer; a test still assuming the old gate threshold |
| Evaluation on dev data | A keyword-stuffing detector that fired on 38% of genuine dev passages; a phone pattern that missed 1900 numbers; an untested output guard (led to the adaptive attacks) |
| The frozen-run guard | The first final run used placeholder thresholds because a scripted edit had silently failed; disclosed in `verify.md`, and a guard now prevents it |
| Independent adversarial review (ChatGPT Astra) | Citation integrity mislabelled as groundedness; test data used for selection; contract contradictions; schedule risks; publication boundaries |
| Candidate approvals | Commits 1 and 2 reviewed at snapshot level |

## Ownership

- The candidate is accountable for every line. The planned 15-minute walkthrough was not held during the
  build because the candidate asked the agent to continue without stopping.
- Before the interview the candidate should be able to explain, in their own words:
  - **a design choice:** provenance before detection;
  - **a correction to generated code:** the stuffing detector, from 49 false positives to 0;
  - **a failed experiment:** the misconfigured first final run;
  - **a safety limit:** English, pattern-based detectors with no held-out evidence;
  - **a production trade-off:** fail-closed audit versus availability.
- The code tour in `design.md` is the starting point.
