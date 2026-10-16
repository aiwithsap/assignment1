# Verification

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
