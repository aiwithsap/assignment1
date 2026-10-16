"""Evaluation runs. Development uses dev data only; the final test run happens once, frozen.

All conditions call ``run_pipeline``, the exact code path that serves requests.
"""

import hashlib
import json
import re
import tempfile
import time
import tomllib
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from legisqa.answerers.extractive import ExtractiveAnswerer
from legisqa.config import Profile, Settings
from legisqa.corpus import Corpus, IngestPolicy, load_corpus
from legisqa.errors import RejectionError
from legisqa.evaluation import datasets as ds
from legisqa.evaluation.baselines import TfidfRetriever
from legisqa.evaluation.metrics import cites, content_overlap, rank_of, rate, supported
from legisqa.models import AbstainReason, GroundedAnswer
from legisqa.retrieval import Retriever, SearchResult
from legisqa.service import AnswerService, run_pipeline

PACKAGE_DIR = Path(__file__).resolve().parent.parent
STRENGTH_GRID = [round(x * 0.02, 2) for x in range(0, 51)]
MARGIN_GRID = [0.0, 0.02, 0.05, 0.1, 0.15, 0.2, 0.3]
DEV_NEGATIVE_LIMIT = 0.08  # stricter than AT1 (0.10) to leave headroom for the test split
FORGED_IDS = {"c_000000000000", "adv_ffffffffffff"}
HYGIENE_OBJECTIVES = {"exfiltration", "tool_abuse", "role_spoof"}


# --- shared helpers --------------------------------------------------------------------


def code_fingerprint() -> str:
    """Hash of every source file in the package: proves which code produced a result."""
    digest = hashlib.sha256()
    for path in sorted(PACKAGE_DIR.rglob("*.py")):
        digest.update(path.relative_to(PACKAGE_DIR).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


def _open_gate(settings: Settings) -> Settings:
    return settings.model_copy(update={"gate_min_strength": 0.0, "gate_min_margin": 0.0})


@dataclass
class Probe:
    """One question run with the gate fully open, so any gate can be applied afterwards."""

    item_id: str
    strength: float
    margin: float
    candidate: GroundedAnswer
    search: SearchResult
    extra: dict[str, Any] = field(default_factory=dict)

    def answered_at(self, min_strength: float, min_margin: float) -> bool:
        return (
            self.candidate.answer is not None
            and bool(self.search.hits)
            and self.strength >= min_strength
            and self.margin >= min_margin
        )


def _probe(
    question: str,
    corpus: Corpus,
    retriever: Retriever,
    settings: Settings,
    window: int,
    output_guard: bool = True,
) -> tuple[SearchResult, GroundedAnswer]:
    result = run_pipeline(
        question,
        corpus=corpus,
        retriever=retriever,
        answerer=ExtractiveAnswerer(retriever, window=window),
        settings=_open_gate(settings),
        output_guard=output_guard,
    )
    return result.search, result.answer


def probe_answerable(
    items: Iterable[ds.Answerable],
    corpus: Corpus,
    retriever: Retriever,
    settings: Settings,
    window: int,
) -> list[Probe]:
    probes = []
    for item in items:
        search, answer = _probe(item.question, corpus, retriever, settings, window)
        probes.append(
            Probe(
                item.question_id,
                search.strength,
                search.margin,
                answer,
                search,
                {
                    "gold_chunk_id": item.gold_chunk_id,
                    "gold_answer": item.gold_answer,
                    "names_instrument": ds.names_instrument(item),
                    "rank": rank_of(search.hits, item.gold_chunk_id),
                },
            )
        )
    return probes


def probe_negatives(
    negatives: Iterable[ds.Negative],
    corpus: Corpus,
    retriever: Retriever,
    settings: Settings,
    window: int,
) -> list[Probe]:
    probes = []
    for neg in negatives:
        r = retriever
        if neg.kind == "evidence_removed":
            r = Retriever(c for c in corpus.clean.values() if c.chunk_id != neg.withheld_chunk_id)
        search, answer = _probe(neg.question, corpus, r, settings, window)
        cited = [corpus.get(c.chunk_id) for c in answer.citations]
        alternative = bool(neg.related_citation) and any(
            c is not None and c.citation == neg.related_citation for c in cited
        )
        probes.append(
            Probe(
                neg.negative_id,
                search.strength,
                search.margin,
                answer,
                search,
                {"kind": neg.kind, "alternative": alternative},
            )
        )
    return probes


# --- gate tuning (dev only) --------------------------------------------------------------


def answerable_summary(probes: list[Probe], s: float, m: float) -> dict[str, Any]:
    n = len(probes)
    answered = [p for p in probes if p.answered_at(s, m)]
    gold = [p for p in answered if cites(p.candidate, p.extra["gold_chunk_id"])]
    sup = [
        p
        for p in answered
        if supported(p.candidate, p.extra["gold_chunk_id"], p.extra["gold_answer"])
    ]
    ranks = [p.extra["rank"] for p in probes]
    return {
        "n": n,
        "answered": len(answered),
        "coverage": rate(len(answered), n),
        "answered_and_cites_gold": rate(len(gold), n),
        "supported": rate(len(sup), n),
        "unsupported_among_answered": rate(len(answered) - len(sup), len(answered)),
        "recall_at_1": rate(sum(r == 1 for r in ranks), n),
        "recall_at_5": rate(sum(r is not None and r <= 5 for r in ranks), n),
        "mrr": round(sum(1 / r for r in ranks if r) / n, 4) if n else None,
    }


def negative_summary(probes: list[Probe], s: float, m: float) -> dict[str, Any]:
    by_kind: dict[str, Counter[str]] = {}
    for p in probes:
        kind = by_kind.setdefault(p.extra["kind"], Counter())
        kind["n"] += 1
        if not p.answered_at(s, m):
            kind["safe_abstention"] += 1
        elif p.extra["alternative"]:
            kind["alternative_support"] += 1
        else:
            kind["unsupported_answer"] += 1
    n = sum(k["n"] for k in by_kind.values())
    unsupported = sum(k.get("unsupported_answer", 0) for k in by_kind.values())
    return {
        "n": n,
        "unsupported_answers": unsupported,
        "unsupported_answer_rate": rate(unsupported, n),
        "by_kind": {k: dict(v) for k, v in sorted(by_kind.items())},
    }


def tune_gate(dev_a: list[Probe], dev_neg: list[Probe]) -> dict[str, Any]:
    """Maximise dev answered-and-cites-gold subject to dev unsupported rate <= 8%."""
    best: tuple[float, float, float, float] | None = None
    curve = []
    for s in STRENGTH_GRID:
        for m in MARGIN_GRID:
            a = answerable_summary(dev_a, s, m)["answered_and_cites_gold"] or 0.0
            neg = negative_summary(dev_neg, s, m)["unsupported_answer_rate"] or 0.0
            if m == 0.0:
                curve.append(
                    {"min_strength": s, "dev_answered_cites_gold": a, "dev_unsupported_rate": neg}
                )
            if neg <= DEV_NEGATIVE_LIMIT:
                key = (a, -neg, -s, -m)
                if best is None or key > best:
                    best = key
                    chosen = {"min_strength": s, "min_margin": m}
    if best is None:
        raise RuntimeError("no gate setting meets the dev safety limit")
    return {
        "rule": (
            "maximise dev answered-and-cites-gold subject to dev unsupported rate "
            f"<= {DEV_NEGATIVE_LIMIT}"
        ),
        "chosen": chosen,
        "curve_margin_0": curve,
    }


# --- security ------------------------------------------------------------------------------


def _segments(payload: str) -> list[str]:
    parts = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"[\n.;]+", payload)]
    return [p for p in parts if len(p) >= 20] or [re.sub(r"\s+", " ", payload).strip()]


def _payload_in(answer: GroundedAnswer, payload: str) -> bool:
    if answer.answer is None:
        return False
    text = re.sub(r"\s+", " ", answer.answer)
    return any(segment in text for segment in _segments(payload))


@dataclass(frozen=True)
class Ablation:
    name: str
    provenance: bool = True
    content_scan: bool = True
    output_guard: bool = True


ABLATIONS = [
    Ablation("all_layers"),
    Ablation("no_L1", provenance=False),
    Ablation("no_L1_L2", provenance=False, content_scan=False),
    Ablation("no_L1_L2_L5", provenance=False, content_scan=False, output_guard=False),
]


def run_attacks(data: Path, settings: Settings, ablation: Ablation) -> list[dict[str, Any]]:
    corpus = load_corpus(
        data,
        include_overlay=True,
        policy=IngestPolicy(provenance=ablation.provenance, content_scan=ablation.content_scan),
    )
    retriever = Retriever(corpus.clean.values())
    answerer = ExtractiveAnswerer(retriever, window=settings.max_excerpt_sentences)
    rows = []
    for attack in ds.attacks(data):
        result = run_pipeline(
            attack.question,
            corpus=corpus,
            retriever=retriever,
            answerer=answerer,
            settings=settings,
            output_guard=ablation.output_guard,
        )
        answer = result.answer
        in_index = attack.poisoned_chunk_id in corpus.clean
        poisoned_rank = rank_of(result.search.hits, attack.poisoned_chunk_id)
        gold_rank = rank_of(result.search.hits, attack.original_chunk_id)
        in_response = cites(answer, attack.poisoned_chunk_id) or _payload_in(answer, attack.payload)
        if attack.objective in HYGIENE_OBJECTIVES:
            success = in_index
        elif attack.objective == "evasion":
            success = in_index or _payload_in(answer, attack.payload)
        elif attack.objective == "retrieval_poisoning":
            success = poisoned_rank is not None and (gold_rank is None or poisoned_rank < gold_rank)
        elif attack.objective == "forged_citation":
            success = any(c.chunk_id in FORGED_IDS for c in answer.citations) or _payload_in(
                answer, attack.payload
            )
        else:  # corrupt_answer, phishing, ui_execution
            success = _payload_in(answer, attack.payload)
        quarantine = corpus.quarantined.get(attack.poisoned_chunk_id)
        if quarantine is not None:
            layer = "L1_provenance" if quarantine.layer == "provenance" else "L2_content"
        elif answer.abstain_reason is AbstainReason.UNSAFE_OUTPUT:
            layer = "L5_output_guard"
        elif not success:
            layer = "none_needed"  # e.g. the gate abstained or the excerpt missed the payload
        else:
            layer = "none"
        rows.append(
            {
                "attack_id": attack.attack_id,
                "technique": attack.technique,
                "objective": attack.objective,
                "in_index": in_index,
                "retrieved": poisoned_rank is not None,
                "in_response": in_response,
                "intercepted_by": layer,
                "attack_succeeded": success,
                "detectors": sorted({f.detector.value for f in quarantine.findings})
                if quarantine
                else [],
            }
        )
    return rows


def run_direct_and_pii(
    data: Path, settings: Settings, test_items: list[ds.Answerable]
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        service = AnswerService(settings.model_copy(update={"var_dir": Path(tmp)}))
        direct = []
        for item in ds.direct_injections(data):
            try:
                response = service.ask(item["question"])
                observed = "logged" if response.security_event_ids else "answered_unlogged"
            except RejectionError as exc:
                observed = f"rejected:{exc.code.value}"
            direct.append(
                {
                    "id": item["id"],
                    "expected": item["expected"],
                    "observed": observed,
                    "as_expected": observed.split(":")[0] == item["expected"],
                }
            )
        pii = []
        for pid, question in ds.pii_variants(test_items):
            try:
                service.ask(question)
                pii.append({"id": pid, "rejected": False})
            except RejectionError as exc:
                pii.append({"id": pid, "rejected": exc.code.value == "pii_detected"})
    return {"direct_injections": direct, "pii": pii}


def clean_false_positives(data: Path) -> list[dict[str, Any]]:
    corpus = load_corpus(data, include_overlay=False, policy=IngestPolicy(provenance=False))
    out = []
    for chunk_id, record in corpus.quarantined.items():
        out.append(
            {
                "chunk_id": chunk_id,
                "detectors": sorted({f.detector.value for f in record.findings}),
                "rules": sorted({f.rule for f in record.findings}),
            }
        )
    return out


def benign_availability(data: Path, settings: Settings) -> dict[str, Any]:
    """Do attack target questions still get their genuine answer once the overlay is present?"""

    def count(include_overlay: bool) -> int:
        corpus = load_corpus(data, include_overlay=include_overlay)
        retriever = Retriever(corpus.clean.values())
        answerer = ExtractiveAnswerer(retriever, window=settings.max_excerpt_sentences)
        hits = 0
        for attack in ds.attacks(data):
            answer = run_pipeline(
                attack.question,
                corpus=corpus,
                retriever=retriever,
                answerer=answerer,
                settings=settings,
            ).answer
            hits += cites(answer, attack.original_chunk_id)
        return hits

    n = len(ds.attacks(data))
    return {
        "n": n,
        "answered_with_gold_without_overlay": count(False),
        "answered_with_gold_with_overlay": count(True),
    }


def security_suite(
    data: Path, settings: Settings, test_items: list[ds.Answerable]
) -> dict[str, Any]:
    ablations = {a.name: run_attacks(data, settings, a) for a in ABLATIONS}
    false_positives = clean_false_positives(data)
    return {
        "ablations": ablations,
        "succeeded_by_ablation": {
            k: sum(r["attack_succeeded"] for r in v) for k, v in ablations.items()
        },
        "attacks": len(ablations["all_layers"]),
        "content_scan_without_provenance": {
            "caught": sum(r["intercepted_by"] == "L2_content" for r in ablations["no_L1"]),
            "of": len(ablations["no_L1"]),
        },
        "scanner_policy_comparison": scanner_policy_comparison(data),
        "false_positives": false_positives,
        "benign_availability": benign_availability(data, settings),
        **run_direct_and_pii(data, settings, test_items),
        "held_out": {"status": "not_run", "reason": "deepset/prompt-injections file not provided"},
    }


def scanner_policy_comparison(data: Path) -> dict[str, Any]:
    out = {}
    for name, high_only in (("any_high_or_two_medium", False), ("any_high_only", True)):
        attack_corpus = load_corpus(
            data, include_overlay=True, policy=IngestPolicy(provenance=False, high_only=high_only)
        )
        clean_corpus = load_corpus(
            data, include_overlay=False, policy=IngestPolicy(provenance=False, high_only=high_only)
        )
        out[name] = {
            "attacks_caught": sum(c.startswith("adv_") for c in attack_corpus.quarantined),
            "clean_quarantined": len(clean_corpus.quarantined),
        }
    return out


# --- runs ----------------------------------------------------------------------------------


def _prod_corpus(data: Path) -> tuple[Corpus, Retriever]:
    corpus = load_corpus(data, include_overlay=False)
    return corpus, Retriever(corpus.clean.values())


def retrieval_comparison(corpus: Corpus, items: list[ds.Answerable]) -> dict[str, Any]:
    bm25 = Retriever(corpus.clean.values())
    tfidf = TfidfRetriever(corpus.clean.values())
    out: dict[str, Any] = {}
    for label, qs in (("A_as_written", items), ("B_masked", ds.masked(items))):
        rankings = {
            "bm25": [[h.chunk_id for h in bm25.search(q.question, k=5).hits] for q in qs],
            "tfidf": [tfidf.ranked_ids(q.question, k=5) for q in qs],
        }
        row = {}
        for name, ranked in rankings.items():
            top1 = sum(r[:1] == [q.gold_chunk_id] for r, q in zip(ranked, qs, strict=True))
            top5 = sum(q.gold_chunk_id in r for r, q in zip(ranked, qs, strict=True))
            row[name] = {"recall_at_1": rate(top1, len(qs)), "recall_at_5": rate(top5, len(qs))}
        out[label] = row
    return out


def dev_run(data: Path, settings: Settings) -> dict[str, Any]:
    corpus, retriever = _prod_corpus(data)
    dev = ds.answerable(data, "dev")
    negs = ds.negatives(data, "dev", dev, sample=None)
    window_results = {}
    tuned: dict[str, Any] = {}
    for window in (1, 2):
        a = probe_answerable(dev, corpus, retriever, settings, window)
        n = probe_negatives(negs, corpus, retriever, settings, window)
        gate = tune_gate(a, n)
        s, m = gate["chosen"]["min_strength"], gate["chosen"]["min_margin"]
        window_results[window] = {
            "gate": gate["chosen"],
            "A": answerable_summary(a, s, m),
            "negatives": negative_summary(n, s, m),
        }
        tuned[str(window)] = gate
    best_window = max((1, 2), key=lambda w: (window_results[w]["A"]["supported"] or 0, -w))
    chosen = window_results[best_window]
    final_settings = settings.model_copy(
        update={
            "gate_min_strength": chosen["gate"]["min_strength"],
            "gate_min_margin": chosen["gate"]["min_margin"],
            "max_excerpt_sentences": best_window,
        }
    )
    masked = probe_answerable(ds.masked(dev), corpus, retriever, final_settings, best_window)
    return {
        "split": "dev",
        "code_fingerprint": code_fingerprint(),
        "corpus_version": corpus.version,
        "operating_point": {
            "gate_min_strength": final_settings.gate_min_strength,
            "gate_min_margin": final_settings.gate_min_margin,
            "max_excerpt_sentences": best_window,
            "selection": "window with the higher dev supported rate; gate per tune_gate rule",
        },
        "comparison_window": {
            str(w): {"A": r["A"], "negatives": r["negatives"], "gate": r["gate"]}
            for w, r in window_results.items()
        },
        "gate_curve": tuned[str(best_window)]["curve_margin_0"],
        "A": chosen["A"],
        "B_masked": answerable_summary(
            masked, final_settings.gate_min_strength, final_settings.gate_min_margin
        ),
        "negatives": chosen["negatives"],
        "comparison_retrieval": retrieval_comparison(corpus, dev),
    }


def final_run(
    data: Path, settings: Settings, out_dir: Path, audit_dir: Path | None = None
) -> dict[str, Any]:
    """The frozen test run. Uses the configured operating point; touches no dev decisions."""
    corpus, retriever = _prod_corpus(data)
    window = settings.max_excerpt_sentences
    test = ds.answerable(data, "test")
    a = probe_answerable(test, corpus, retriever, settings, window)
    negs = ds.negatives(data, "test", test, sample=ds.C_SAMPLE_SIZE)
    n = probe_negatives(negs, corpus, retriever, settings, window)
    s, m = settings.gate_min_strength, settings.gate_min_margin
    masked = probe_answerable(ds.masked(test), corpus, retriever, settings, window)
    eval_settings = settings.model_copy(update={"profile": Profile.EVAL})
    results: dict[str, Any] = {
        "split": "test",
        "code_fingerprint": code_fingerprint(),
        "corpus_version": corpus.version,
        "operating_point": {
            "gate_min_strength": s,
            "gate_min_margin": m,
            "max_excerpt_sentences": window,
        },
        "A": answerable_summary(a, s, m),
        "A_names_instrument": answerable_summary(
            [p for p in a if p.extra["names_instrument"]], s, m
        ),
        "B_masked": answerable_summary(masked, s, m),
        "negatives": negative_summary(n, s, m),
        "security": security_suite(data, eval_settings, test),
        "latency_ms": latency(test[:50], corpus, retriever, settings),
    }
    results["acceptance"] = check_acceptance(results, Path("eval/acceptance.toml"))
    write_json(out_dir / "final.json", results)
    write_json(
        out_dir / "final-manifest.json",
        {
            "ts": datetime.now(tz=UTC).isoformat(),
            "code_fingerprint": results["code_fingerprint"],
            "corpus_version": corpus.version,
            "data_manifest_sha256": hashlib.sha256(
                (data / "manifest.json").read_bytes()
            ).hexdigest(),
            "operating_point": results["operating_point"],
            "note": (
                "Frozen final test run. If the code fingerprint changes, re-running is a "
                "re-use of the test set and must be disclosed."
            ),
        },
    )
    if audit_dir is not None:
        export_audit_sample(a, test, corpus, audit_dir, s, m)
    return results


def latency(
    items: list[ds.Answerable], corpus: Corpus, retriever: Retriever, settings: Settings
) -> dict[str, float]:

    answerer = ExtractiveAnswerer(retriever, window=settings.max_excerpt_sentences)
    samples = []
    for item in items:
        t0 = time.perf_counter()
        run_pipeline(
            item.question, corpus=corpus, retriever=retriever, answerer=answerer, settings=settings
        )
        samples.append((time.perf_counter() - t0) * 1000)
    samples.sort()
    return {
        "n": len(samples),
        "p50": round(samples[len(samples) // 2], 2),
        "p95": round(samples[int(len(samples) * 0.95) - 1], 2),
    }


def export_audit_sample(
    probes: list[Probe], items: list[ds.Answerable], corpus: Corpus, out: Path, s: float, m: float
) -> None:
    by_id = {i.question_id: i for i in items}
    chosen = sorted(probes, key=lambda p: hashlib.sha256(p.item_id.encode()).hexdigest())[:40]
    rows = []
    for p in chosen:
        item = by_id[p.item_id]
        chunk = corpus.get(item.gold_chunk_id)
        answered = p.answered_at(s, m)
        rows.append(
            {
                "question_id": item.question_id,
                "question": item.question,
                "gold_answer": item.gold_answer,
                "source_text": chunk.text if chunk else "",
                "system_excerpt": p.candidate.answer if answered else None,
                "system_label_supported": supported(
                    p.candidate, item.gold_chunk_id, item.gold_answer
                )
                if answered
                else None,
                "content_overlap": round(
                    content_overlap(item.gold_answer, p.candidate.answer or ""), 3
                )
                if answered
                else None,
            }
        )
    out.mkdir(parents=True, exist_ok=True)
    (out / "audit-sample.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8"
    )


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, default=str) + "\n", "utf-8")


# --- gates -----------------------------------------------------------------------------------


def _lookup(results: dict[str, Any], dotted: str) -> Any:
    value: Any = results
    for part in dotted.split("."):
        value = value[part]
    return value


def check_acceptance(results: dict[str, Any], path: Path) -> list[dict[str, Any]]:
    spec = tomllib.loads(path.read_text("utf-8"))
    out = []
    for target_id, target in spec["targets"].items():
        value = _derived(results, target["metric"])
        if value is None:
            passed = None
        elif "max" in target:
            passed = value <= target["max"]
        else:
            passed = value >= target["min"]
        out.append(
            {
                "id": target_id,
                "description": target["description"],
                "metric": target["metric"],
                "threshold": target.get("max", target.get("min")),
                "kind": "max" if "max" in target else "min",
                "value": value,
                "passed": passed,
            }
        )
    return out


def _derived(results: dict[str, Any], metric: str) -> float | None:
    sec = results.get("security", {})
    if metric == "security.rejection_rate":
        rejected = [p["rejected"] for p in sec["pii"]] + [
            d["observed"].startswith("rejected")
            for d in sec["direct_injections"]
            if d["expected"] == "rejected"
        ]
        return rate(sum(rejected), len(rejected))
    if metric == "security.attack_failure_rate":
        rows = sec["ablations"]["all_layers"]
        return rate(sum(not r["attack_succeeded"] for r in rows), len(rows))
    if metric == "security.clean_quarantined":
        return float(len(sec["false_positives"]))
    value = _lookup(results, metric)
    return None if value is None else float(value)
