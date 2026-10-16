# Decision records

## D1. Keyword retrieval (BM25) over a pinned corpus

- **Context.** Questions must be answered with verifiable citations, offline, with no paid keys.
- **Options.** (a) BM25 keyword search; (b) TF-IDF cosine; (c) vector embeddings; (d) put the whole corpus
  in a model's context.
- **Decision.** BM25, chosen on the dev split: Recall@1 100% vs 96.9% (TF-IDF) as written, 80.5% vs 71.1%
  with instrument names masked.
- **Why not (c) or (d).** Embeddings need a model download or a hosted (paid) service; legislation leans on
  exact names and section numbers where keywords do well. Long context (426 passages is roughly 110k
  tokens) needs an LLM, would not scale to a real corpus, and gives looser citations. This part is reasoned,
  not measured.
- **Consequence.** Paraphrased questions are the weak spot: with names masked only 60.3% of test questions
  are answered from the right passage. A hybrid index is the next step.

## D2. No LLM in the product

- **Context.** No API keys may be required; the candidate removed even an optional key. The brief allows a
  non-AI solution.
- **Decision.** A deterministic extractive answerer: the response is a verbatim sentence window from the
  best passage, with citations computed by code.
- **Gains.** Runs anywhere offline; every word shown is checkable; nothing generated can be steered by
  poisoned text.
- **Costs.** Excerpts are not tailored answers. Against the strict, predeclared support measure (gold
  passage cited and at least half the gold answer's content words present) only 51.2% of test excerpts
  qualify, although 92.9% cite the right passage. AI engineering is shown in how the system was built,
  reviewed and evaluated rather than in the product.

## D3. Trust boundaries: provenance first, detection as backstop, verification in code

- **Decision.**
  - L1 provenance (hash against the manifest for the claimed source) is the decisive control for known
    documents.
  - L2 deterministic detectors cover content without a trusted reference.
  - The citation validator and the L5 output guard run on every answer; the UI renders text only.
  - Abstain rather than guess; fail closed when the corpus or audit log is unusable.
  - Linguistic injection in *questions* is logged, not blocked, because there is no model to hijack;
    this flips to blocking if an LLM is added.
- **Evidence.** With all layers on, 0 of 31 catalogue attacks succeeded; with provenance off, the
  detectors alone still caught 31 of 31; with all ingest defences off, 16 succeeded and L5 stopped the two
  adaptive attacks it is designed for (`evidence/security-report.md`).
- **Limit.** Detectors are English, pattern-based and were developed against our own catalogue. The
  held-out set could not be run.

## D4. Data: licensed legislation subset; attacks in a separate overlay

- **Decision.** Use only the 426 legislation records of Open Australian Legal QA whose sources are CC BY 4.0;
  exclude 1,698 case-law records because of the courts' terms. Keep attack text in a labelled overlay of
  modified copies with their own identifiers, loaded only in `demo` and `eval`.
- **Handled shortcut.** 79% of questions name their instrument, which flatters keyword search. Every
  retrieval result is reported with names masked as well.
- **Known data defect.** Some passages carry encoding artefacts from the source (for example a "3/4"
  character where a dash belongs). Not repaired, to keep provenance hashes faithful to the source.

## D5. Deliberately not built

Authentication and authorisation; multi-user operation; a vector index; an LLM answerer; a trained
injection classifier; Markdown or link rendering in the UI; case law; legal advice or personal-advice
detection; cloud deployment (described in `design.md` and `operate.md`).
