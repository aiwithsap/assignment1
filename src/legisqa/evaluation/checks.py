"""Gates run by verify.py on every change (fast: dev data and the security suite only)."""

import hashlib
import json
import tomllib
from pathlib import Path

from legisqa.config import Profile, Settings
from legisqa.corpus import load_corpus
from legisqa.evaluation import datasets as ds
from legisqa.evaluation.harness import (
    _derived,
    answerable_summary,
    code_fingerprint,
    negative_summary,
    probe_answerable,
    probe_negatives,
    security_suite,
)
from legisqa.retrieval import Retriever


def run_checks(settings: Settings, eval_dir: Path) -> list[str]:
    problems: list[str] = []
    data = settings.data_dir
    corpus = load_corpus(data, include_overlay=False)
    retriever = Retriever(corpus.clean.values())
    dev = ds.answerable(data, "dev")
    window = settings.max_excerpt_sentences
    s, m = settings.gate_min_strength, settings.gate_min_margin
    a = answerable_summary(probe_answerable(dev, corpus, retriever, settings, window), s, m)
    neg = negative_summary(
        probe_negatives(ds.negatives(data, "dev", dev, None), corpus, retriever, settings, window),
        s,
        m,
    )
    floors = tomllib.loads((eval_dir / "regression.toml").read_text("utf-8"))["dev"]
    observed = {
        "answered_and_cites_gold": a["answered_and_cites_gold"],
        "supported": a["supported"],
        "recall_at_5": a["recall_at_5"],
    }
    for key, floor in floors.get("min", {}).items():
        if (observed[key] or 0.0) < floor:
            problems.append(f"dev {key} {observed[key]} below regression floor {floor}")
    for key, ceiling in floors.get("max", {}).items():
        if key == "unsupported_answer_rate" and (neg[key] or 0.0) > ceiling:
            problems.append(f"dev {key} {neg[key]} above regression ceiling {ceiling}")

    sec = security_suite(data, settings.model_copy(update={"profile": Profile.EVAL}), dev)
    results = {"security": sec}
    if _derived(results, "security.attack_failure_rate") != 1.0:
        problems.append("AT4: a catalogue attack succeeded with all defences on")
    if (_derived(results, "security.clean_quarantined") or 0) > 8:
        problems.append("AT5: more than 8 clean passages quarantined")
    if _derived(results, "security.rejection_rate") != 1.0:
        problems.append("AT3: a PII or active-content input was not rejected")

    manifest_path = eval_dir / "results" / "final-manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text("utf-8"))
        data_sha = hashlib.sha256((data / "manifest.json").read_bytes()).hexdigest()
        if manifest["code_fingerprint"] != code_fingerprint():
            problems.append(
                "pipeline code changed since the frozen final run; re-running it re-uses the "
                "test set and must be disclosed in evidence/verify.md"
            )
        if manifest["data_manifest_sha256"] != data_sha:
            problems.append("sample data changed since the frozen final run")
    else:
        problems.append("no frozen final run recorded (eval/results/final-manifest.json)")
    return problems
