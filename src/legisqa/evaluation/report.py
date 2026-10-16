"""Render evaluation results into the evidence pack. Generated sections sit between markers;
hand-written commentary outside the markers is preserved."""

from pathlib import Path
from typing import Any

BEGIN = "<!-- BEGIN GENERATED: {name} -->"
END = "<!-- END GENERATED: {name} -->"


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _yes(flag: bool) -> str:
    return "yes" if flag else "no"


def replace_section(path: Path, name: str, body: str) -> None:
    begin, end = BEGIN.format(name=name), END.format(name=name)
    block = f"{begin}\n{body.rstrip()}\n{end}"
    text = path.read_text("utf-8") if path.exists() else ""
    if begin in text and end in text:
        head, rest = text.split(begin, 1)
        _, tail = rest.split(end, 1)
        text = head + block + tail
    else:
        text = (text.rstrip() + "\n\n" if text else "") + block + "\n"
    path.write_text(text, "utf-8")


def acceptance_table(final: dict[str, Any]) -> str:
    rows = ["| Target | Description | Threshold | Measured | Result |", "|---|---|---|---|---|"]
    for t in final["acceptance"]:
        sign = "<=" if t["kind"] == "max" else ">="
        value = t["value"]
        shown = f"{value:g}" if t["metric"].endswith("quarantined") else _pct(value)
        threshold = (
            f"{t['threshold']:g}" if t["metric"].endswith("quarantined") else _pct(t["threshold"])
        )
        result = "not run" if t["passed"] is None else ("**PASS**" if t["passed"] else "**FAIL**")
        rows.append(f"| {t['id']} | {t['description']} | {sign} {threshold} | {shown} | {result} |")
    rows.append(
        "| AT6 | Instrument-name-masked questions; held-out attacks | reported only | "
        f"masked: {_pct(final['B_masked']['answered_and_cites_gold'])} answered and citing gold; "
        "held-out: not run | n/a |"
    )
    return "\n".join(rows)


def answerable_table(sections: dict[str, dict[str, Any]]) -> str:
    rows = [
        "| Condition | n | Coverage | Answered & cites gold | Supported | Recall@1 | Recall@5 | MRR |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for label, s in sections.items():
        rows.append(
            f"| {label} | {s['n']} | {_pct(s['coverage'])} | {_pct(s['answered_and_cites_gold'])} | "
            f"{_pct(s['supported'])} | {_pct(s['recall_at_1'])} | {_pct(s['recall_at_5'])} | {s['mrr']} |"
        )
    return "\n".join(rows)


def negatives_table(neg: dict[str, Any]) -> str:
    rows = [
        "| Kind | n | Safe abstention | Unsupported answer | Alternative support (audit) |",
        "|---|---|---|---|---|",
    ]
    for kind, c in neg["by_kind"].items():
        rows.append(
            f"| {kind} | {c['n']} | {c.get('safe_abstention', 0)} | {c.get('unsupported_answer', 0)} | "
            f"{c.get('alternative_support', 0)} |"
        )
    rows.append(
        f"| **all** | {neg['n']} | | **{neg['unsupported_answers']}** ({_pct(neg['unsupported_answer_rate'])}) | |"
    )
    return "\n".join(rows)


def results_markdown(dev: dict[str, Any], final: dict[str, Any]) -> str:
    op = final["operating_point"]
    retrieval = dev["comparison_retrieval"]
    window = dev["comparison_window"]
    lat = final["latency_ms"]
    return "\n".join(
        [
            f"Final frozen test run. Code fingerprint `{final['code_fingerprint']}`, corpus "
            f"`{final['corpus_version']}`. Operating point (chosen on dev): gate min strength "
            f"{op['gate_min_strength']}, min margin {op['gate_min_margin']}, excerpt window "
            f"{op['max_excerpt_sentences']} sentence(s). Source: `eval/results/final.json`.",
            "",
            "#### Acceptance targets (fixed before measurement)",
            "",
            acceptance_table(final),
            "",
            "#### Answerable questions (test)",
            "",
            answerable_table(
                {
                    "A: as written": final["A"],
                    "A, subset naming its instrument": final["A_names_instrument"],
                    "B: instrument name masked": final["B_masked"],
                }
            ),
            "",
            "#### Questions that must be refused (test)",
            "",
            negatives_table(final["negatives"]),
            "",
            "#### Development-time comparisons (dev split only)",
            "",
            "| Comparison | Option | Result | Chosen |",
            "|---|---|---|---|",
            f"| Retrieval, as written | BM25 / TF-IDF | Recall@1 {_pct(retrieval['A_as_written']['bm25']['recall_at_1'])} / "
            f"{_pct(retrieval['A_as_written']['tfidf']['recall_at_1'])} | BM25 |",
            f"| Retrieval, masked | BM25 / TF-IDF | Recall@1 {_pct(retrieval['B_masked']['bm25']['recall_at_1'])} / "
            f"{_pct(retrieval['B_masked']['tfidf']['recall_at_1'])} | BM25 |",
            f"| Excerpt window | 1 / 2 sentences | supported {_pct(window['1']['A']['supported'])} / "
            f"{_pct(window['2']['A']['supported'])} | {op['max_excerpt_sentences']} |",
            "",
            f"Latency (offline, {lat['n']} test questions): p50 {lat['p50']} ms, p95 {lat['p95']} ms.",
        ]
    )


LAYER_NAMES = {
    "L1_provenance": "L1 provenance",
    "L2_content": "L2 content scan",
    "L5_output_guard": "L5 output guard",
    "none_needed": "not reached (excerpt did not select payload)",
    "none": "none",
}


def security_markdown(final: dict[str, Any]) -> str:
    sec = final["security"]
    ab = sec["ablations"]
    lines = [
        f"Generated from `eval/results/final.json` (code `{final['code_fingerprint']}`). "
        f"Population: our catalogue of {sec['attacks']} attacks, embedded in copies of dev passages.",
        "",
        "#### Attack success by defence configuration (ablation)",
        "",
        "| Configuration | Attacks that succeeded (by their oracle) |",
        "|---|---|",
    ]
    names = {
        "all_layers": "All layers on",
        "no_L1": "L1 provenance off",
        "no_L1_L2": "L1 + L2 off (no ingest defences)",
        "no_L1_L2_L5": "L1 + L2 + L5 off (no defences except answer construction)",
    }
    for key, label in names.items():
        lines.append(f"| {label} | {sec['succeeded_by_ablation'][key]} of {sec['attacks']} |")
    lines += [
        "",
        "#### Per attack",
        "",
        "| Attack | Objective | All layers: stopped by | L1 off: stopped by | L1+L2 off: stopped by | "
        "L1+L2 off: succeeded | L1+L2+L5 off: succeeded |",
        "|---|---|---|---|---|---|---|",
    ]
    for i, row in enumerate(ab["all_layers"]):
        l1 = ab["no_L1"][i]
        l12 = ab["no_L1_L2"][i]
        l125 = ab["no_L1_L2_L5"][i]
        lines.append(
            f"| {row['attack_id']} | {row['objective']} | {LAYER_NAMES[row['intercepted_by']]} | "
            f"{LAYER_NAMES[l1['intercepted_by']]} ({', '.join(l1['detectors']) or '-'}) | "
            f"{LAYER_NAMES[l12['intercepted_by']]} | {_yes(l12['attack_succeeded'])} | "
            f"{_yes(l125['attack_succeeded'])} |"
        )
    policy = sec["scanner_policy_comparison"]
    ba = sec["benign_availability"]
    direct = sec["direct_injections"]
    lines += [
        "",
        "#### Scanner accuracy (kept separate from end-to-end attack success)",
        "",
        "| Measure | Result |",
        "|---|---|",
        f"| Catalogue attacks caught by content scan alone (L1 off) | "
        f"{sec['content_scan_without_provenance']['caught']} of {sec['content_scan_without_provenance']['of']} |",
        f"| Clean passages quarantined (false positives, of 426) | {len(sec['false_positives'])} |",
        f"| Policy 'any High or two Medium' vs 'any High only' (attacks caught / clean quarantined) | "
        f"{policy['any_high_or_two_medium']['attacks_caught']}/{policy['any_high_or_two_medium']['clean_quarantined']} vs "
        f"{policy['any_high_only']['attacks_caught']}/{policy['any_high_only']['clean_quarantined']} |",
        f"| Attack target questions still answered from the genuine passage, overlay loaded | "
        f"{ba['answered_with_gold_with_overlay']} of {ba['n']} (without overlay: {ba['answered_with_gold_without_overlay']}) |",
        f"| Held-out attacks (deepset/prompt-injections) | {sec['held_out']['status'].replace('_', ' ')}: {sec['held_out']['reason']} |",
        "",
        "#### Direct injection and personal information in questions",
        "",
        "| Input | Expected | Observed |",
        "|---|---|---|",
    ]
    lines += [f"| {d['id']} | {d['expected']} | {d['observed']} |" for d in direct]
    rejected = sum(p["rejected"] for p in sec["pii"])
    lines.append(
        f"| 10 questions with synthetic PII | rejected (pii_detected) | {rejected} of {len(sec['pii'])} rejected |"
    )
    return "\n".join(lines)


def render(dev: dict[str, Any], final: dict[str, Any], evidence: Path) -> None:
    replace_section(evidence / "verify.md", "results", results_markdown(dev, final))
    replace_section(evidence / "security-report.md", "security", security_markdown(final))
