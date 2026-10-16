"""The build is deterministic, excludes case law and isolates the attack overlay."""

import json
import shutil
from pathlib import Path

from legisqa.corpus import load_corpus
from legisqa.corpus_build import build, chunk_id_for, normalise

REPO = Path(__file__).resolve().parents[2]


def raw_record(i: int, source: str, jurisdiction: str = "commonwealth") -> dict[str, object]:
    return {
        "question": f"Under the Example Act {i}, what must a licensee do about item {i}?",
        "answer": f"The licensee must lodge return {i}.",
        "source": {
            "version_id": f"src:{i}",
            "type": "decision" if source.endswith("caselaw") else "primary_legislation",
            "jurisdiction": jurisdiction,
            "source": source,
            "citation": f"Example Act {i} (Cth)",
            "url": f"http://www.legislation.gov.au/{i}",
            "text": f"Section {i}.  A licensee must lodge   return {i} each year.\u0092s note. "
            + " ".join(f"Clause {i}.{n} applies to category {n}." for n in range(5)),
        },
    }


def make_fixture(tmp_path: Path) -> tuple[Path, Path]:
    raw = tmp_path / "raw.jsonl"
    records = [raw_record(i, "federal_register_of_legislation") for i in range(40)]
    records.append(raw_record(99, "nsw_caselaw", "new_south_wales"))
    raw.write_text("".join(json.dumps(r) + "\n" for r in records), "utf-8")
    out = tmp_path / "out"
    shutil.copytree(REPO / "sample-data/sources", out / "sources")
    return raw, out


def test_build_is_deterministic_and_excludes_case_law(tmp_path: Path) -> None:
    raw, out = make_fixture(tmp_path)
    first = build(raw, out)
    first_bytes = (out / "manifest.json").read_bytes()
    second = build(raw, out)
    assert (out / "manifest.json").read_bytes() == first_bytes
    assert first == second
    assert first["source"]["excluded_case_law"] == 1
    assert first["source"]["legislation_chunks"] == 40
    assert len(first["splits"]["dev"]) == 12


def test_build_output_loads_and_overlay_is_isolated(tmp_path: Path) -> None:
    raw, out = make_fixture(tmp_path)
    build(raw, out)
    clean = load_corpus(out, include_overlay=False)
    full = load_corpus(out, include_overlay=True)
    assert len(clean.clean) == 40
    assert set(full.clean) == set(clean.clean)
    assert all(c.startswith("adv_") for c in full.quarantined)


def test_normalisation() -> None:
    assert normalise("  a\u0092s   b\t c ") == "a\u2019s b c"
    assert chunk_id_for("x").startswith("c_") and len(chunk_id_for("x")) == 14
