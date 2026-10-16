# Design review log

This log records every finding from independent reviews of the design and how the design changed in response. It is part of the evidence of how AI output was challenged and verified before implementation began.

## Review 1: adversarial plan review by ChatGPT Astra

- **Date:** 15 October 2026 (AEDT)
- **Reviewer:** ChatGPT Astra, an AI model from a different provider than the coding agent, prompted to review the plan adversarially
- **Object reviewed:** plan revision 2 (`evidence/plan.md`), SHA-256 `3f08eeafeb7da01c1c30dee6ad7e0bb9920adda28ce10bc8705e23e8cfffd7b3`
- **Review verdict:** "Revise before implementation." The review found 12 findings: 7 rated High and 5 rated Medium.
- **Response:** plan revision 4. Revision 3, which removed the LLM, was written before the review arrived and already superseded three findings.
- **Process:** the coding agent (Claude) triaged each finding as accepted, partly accepted, superseded or declined, with reasons. The candidate approved the approach and directed that the triage and resulting changes be recorded here.
- **Review text:** the full review is kept privately and not published, because it quotes confidential exercise material.

### Summary

| Disposition | Count | Findings |
|---|---|---|
| Accepted | 8 | F02, F03, F05, F06, F07, F10, F11, F12 |
| Partly accepted | 1 | F04 |
| Superseded by revision 3 (no LLM in the product) | 3 | F01, F08, F09 |
| Declined | 0 | — |

Three individual recommendations within accepted findings were adjusted rather than adopted as written. They are noted under "Adjusted" below.

### Findings and dispositions

| ID | Severity | Finding (summary) | Disposition | Design change | Plan section |
|---|---|---|---|---|---|
| F01 | High | Claims about model behaviour (tool use, structured output, prompt effect) can't be supported by scripted test doubles; real-model evidence was optional and could be skipped | **Superseded** | Revision 3 removed the LLM and all API keys. No model-behaviour claims are made; the evidence pack states which LLM-related signals are not demonstrated, as the review recommended for this case | 1, 9 (D2) |
| F02 | High | The citation validator proves provenance, not that the answer is supported; "groundedness" overstated it; an answered response with an empty citation list could pass | **Accepted** | Metric renamed to *citation integrity*. Output reframed as *evidence excerpts*. A separate *answer support* measure is defined in advance (gold chunk cited plus at least 50% gold-answer content overlap), backed by an AI label audit. Schema invariants make an answer with no citations, or an abstention with an answer, impossible to construct | 1, 3.3, 4.3, 2.4 |
| F03 | High | Test data influenced design (retriever and model selection on test); regression floors from the first run could lock in a weak baseline; there was no negative development set | **Accepted** | Every choice is made on dev. Dev negatives were added. The final test run happens once, frozen, with a recorded manifest. Acceptance targets AT1–AT6 are fixed before measurement and kept separate from regression floors. The split is documented as by chunk, with 424 distinct instruments, so there is no instrument overlap | 2.3, 4.1 |
| F04 | High | Removing the gold chunk doesn't prove no other evidence exists; input rejection was mixed with semantic abstention; refusal promises (personal advice, future dates) had no implementation | **Partly accepted** | Separate outcome categories: supported, unsupported, *alternative support* (audited, not auto-failed), safe abstention, input rejection. About 10 hand-written hard negatives per split. The unimplemented refusal promises were **removed** rather than built | 2.3, 4.2, 9 |
| F05 | High | "Intercepted" mixed different outcomes; plain-text rendering prevents code execution but not phishing; held-out attack data needs pinning and frozen detectors | **Accepted** | Every attack has an objective and a success oracle. Stage traces show how far each payload travelled. Plain-text rendering is credited only against execution attacks. Scanner accuracy is reported apart from end-to-end success. The held-out dataset revision is pinned, and detectors are frozen and hashed before it is run | 2.5, 3.5, 4.5 |
| F06 | High | The schedule had no reserve; optional breadth outranked required evidence; candidate review was outside the build time; time accounting was ambiguous | **Accepted (adjusted)** | Evaluation moved ahead of the UI. A 15-minute reserve and a hard-stop rule were added. A 15-minute candidate walkthrough happens inside the build. Planning time is disclosed separately from build and packaging | 8.2, 8.3 |
| F07 | High | Contract contradictions: the abstention reasons didn't match the output guard; rejection and abstention were conflated; "refuse to start" conflicted with a readiness 503; no audit-failure policy | **Accepted** | One state and error contract (answered, abstained, rejected, unavailable, internal error), each with an HTTP code and a CLI exit code. Rejection codes are separate from abstention reasons. The process starts *unready* on corpus failure. The audit fails closed. Settings load at startup only. Code and corpus roll back as a compatible pair | 3.3, 6 |
| F08 | Medium | Prompt versioning was planned, but there was no prompt-iteration experiment | **Superseded** | There are no prompts in the product after revision 3 | — |
| F09 | Medium | Tool-call contracts (call IDs, multiple calls, invalid arguments, budgets) were underspecified; a live-run cost estimate was miscounted | **Superseded** | There are no tools or provider calls in the product after revision 3 | — |
| F10 | Medium | The repository was to be made public only at packaging; edits continuing during a pending approval could alter the approved snapshot; attribution claims must be verified; the confidential brief must not be published | **Accepted** | The repository is public from the start. Approval is snapshot-exact (a staged-tree fingerprint must match at commit time). Pushing requires its own approval. The brief is paraphrased, never copied. Private material goes in a git-ignored `tmp/`, checked by a local deny-list and a pre-push content review. Interventions are recorded as they actually happen | 8.1, 9, 10 |
| F11 | Medium | Adversarial copies reused the original chunk ID; security-event payloads could re-disclose sensitive text; endpoint exposure by profile was unspecified; skipped UI checks could read as a pass | **Accepted** | Overlay chunks have unique IDs, link to their original and *claim* its source ID. Security events redact question text, storing only a fingerprint and offsets. Security endpoints exist only in demo and eval. `verify.py` shows SKIPPED explicitly, and CI fails on a skip. The manifest records split membership and the attack-set version | 2.3, 2.5, 5, 6 |
| F12 | Medium | Traceability tables claimed demonstration from plans and file existence; candidate ownership was weakly evidenced | **Accepted** | Plan tables now list *planned mechanisms* only. A `criteria-ledger.md` is produced from actual results, in the reviewer's suggested format, with a status per criterion. Ownership is evidenced by the walkthrough and by the approval notes | 9, 10 |

### Adjusted recommendations

1. **F06: "treat the UI as optional ahead of evidence".** The candidate explicitly requested the UI, and the reviewer itself cautioned against dropping requested scope without asking. Instead of cutting it, the UI was moved after evaluation so it can't crowd evaluation out. UI breadth (the security panel, polish) sits in the cut order.
2. **F04: "validate answerability against all available evidence".** Full validation of every negative isn't feasible within the timebox. The proportionate version is used instead: same-instrument detection, the *alternative support* category and an AI label audit. The limitation is stated in `verify.md`.
3. **F02: "valid quote with contradictory answer" counterexamples.** In a purely extractive design the answer *is* the quoted text, so a contradiction between the two can't occur. The empty-citation and invariant tests were adopted, and the contradiction test is recorded as not applicable, with this reasoning.

### Changes beyond the review, made at the same time

- Detection without an LLM was specified as a provenance-first, deterministic detector set with stated limits (plan 3.4). This came from the candidate's question, not from the review.
- Publication controls were added at the candidate's direction: only Westpac is referenced in published material, `tmp/` is git-ignored, and a local deny-list check runs before every push.
