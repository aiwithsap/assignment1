# Criteria ledger

One row per requirement of the exercise brief (paraphrased). **Status** is one of: demonstrated, partial,
not run, not applicable. Execution identity for all results: code fingerprint `46422f6e1b70832e`, corpus
`c-968bf594e635`, final results `eval/results/final.json`, clean-checkout run of `89de1cf`.

| # | Requirement (paraphrased) | Mechanism | Evidence | Status | Remaining limitation |
|---|---|---|---|---|---|
| 1 | Build within about 3 hours, plus up to 15 minutes packaging | Six commits, hard stop rule | `verify.md` timebox log | Demonstrated | Planning time before the clock is disclosed, not counted |
| 2 | Public repository with regular incremental commits; no history rewriting | Six build commits plus a packaging fix, never amended or squashed | `git log` on github.com/aiwithsap/assignment1 (public) | Demonstrated | Pushed after the build, with commit times preserved |
| 3 | AI coding agent as primary implementation tool | Claude (Opus 5.5) wrote and ran everything | `agentic-workflow.md` | Demonstrated | |
| 4 | Meaningful solution, clear outcome, credible in a regulated enterprise | Cited evidence excerpts, abstain, injection defences, audit | `design.md`; AT1 to AT5 pass | Demonstrated | Excerpts are evidence, not tailored answers |
| 5 | Product AI optional | No LLM in the product | `decisions.md` D2 | Demonstrated | |
| 6 | One meaningful end-to-end workflow | Question to audited answer via CLI, API and UI | `tests/integration/test_service.py`, `test_api.py`; README example; screenshots | Demonstrated | |
| 7 | Full-stack ownership of the slice | Data build, service, API, CLI, UI, evaluation, CI, operations | Repository; clean-checkout run | Demonstrated | |
| 8 | Clear setup and run instructions | README | Clean-checkout run (Linux), commands run verbatim; CI green on Ubuntu and Windows | Demonstrated | |
| 9 | A simple build/test/verify command | `scripts/verify.py` | Same command in `.github/workflows/ci.yml` | Demonstrated | |
| 10 | Tests, evaluation or acceptance checks | 177 Python and 13 UI tests; acceptance targets AT1 to AT6 | `verify.md` | Demonstrated | Held-out attack set not run |
| 11 | Safe handling of configuration | Typed immutable settings, fail-fast validation, safe `prod` default | `tests/unit/test_config.py` | Demonstrated | No hot reload (restart required, documented) |
| 12 | Safe handling of errors and failure paths | One outcome contract: 422, 503, 500 envelopes; unready start; fail-closed audit | `tests/contract/`, `tests/integration/test_api.py` | Demonstrated | |
| 13 | At least one guarded failure, rejection, degrade or abstain | 422 rejections, three abstain reasons, quarantine, unready 503 | AT1, AT3, AT4 | Demonstrated | |
| 14 | Basic operational thinking | JSON logs, audit trail, security events, `/healthz`, `/readyz`, failure-mode table | `operate.md` | Demonstrated | |
| 15 | Evidence of agent use and of verifying its output | Steering record, review mechanisms, adversarial review, disclosed failure | `agentic-workflow.md`, `design-review-log.md`, `verify.md` | Demonstrated | Label audit pending |
| 16 | Core path needs no paid keys, private or Westpac credentials, or assessor-specific setup | No keys exist; no network at runtime | Clean-checkout run with no `.env` | Demonstrated | |
| 17 | Only synthetic, sample or public data | CC BY legislation subset; synthetic labelled overlay; raw file git-ignored | `sample-data/ATTRIBUTION.md`, `manifest.json`, hygiene check | Demonstrated | |
| 18 | Backing services, sample data, mocks and stubs included or described | In-memory corpus committed; no services needed | README; `operate.md` | Demonstrated | |
| 19 | Explain the CI/CD path into a cloud enterprise environment | Pipeline and promotion design | `operate.md`, `design.md` | Demonstrated (as design) | Not deployed (not required) |
| 20 | Lightweight evidence pack with intent, design, agentic workflow, verification, operations, 3 to 5 decisions | All files present, plus security report, review log, ledger | `evidence/` | Demonstrated | |
| 21 | README covers what, prerequisites, setup, run, test, an example, limitations, evidence location | README | README | Demonstrated | |
| 22 | Known gaps and next steps stated | Known-gaps list; production additions | `verify.md`, `security-report.md`, `design.md` | Demonstrated | |
| 23 | Submission notes: link, setup notes, time spent, tools | To be written at packaging | n/a | Not run | Packaging step |
| 24 | Candidate accountable for all code and decisions | Approvals of commits 1 and 2; code tour; ownership checklist | `agentic-workflow.md` | Partial | The planned walkthrough with the candidate was not held during the build |
