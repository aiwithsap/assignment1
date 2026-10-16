"""Build the committed sample data from the raw Open Australian Legal QA export.

The build is deterministic: the same raw file and seed always produce byte-identical
outputs. Only CC BY 4.0 legislation sources are kept; case law is excluded on licence
grounds. The adversarial overlay is written to separate files and never modifies the
clean corpus.
"""

import hashlib
import json
import random
import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from legisqa.models import Chunk, DocType, Jurisdiction

SEED = 20261015
DEV_FRACTION = 0.3
MANIFEST_SCHEMA_VERSION = 1
HARD_NEGATIVES_PER_SPLIT = 10

LICENSED_SOURCES = {
    "federal_register_of_legislation",
    "nsw_legislation",
    "queensland_legislation",
    "western_australian_legislation",
    "south_australian_legislation",
    "tasmanian_legislation",
}

TRANSFORMATIONS = [
    "kept only records whose source is a CC BY 4.0 legislation source; case law excluded",
    "Unicode NFC normalisation",
    "U+0092 (mis-encoded apostrophe) replaced with U+2019",
    "runs of spaces and tabs collapsed to one space; leading/trailing whitespace stripped",
    "one duplicate question dropped (first occurrence kept)",
    "chunk_id = 'c_' + first 12 hex chars of SHA-256(version_id)",
]

# Hard negatives name a real instrument but ask about a matter its passage does not cover.
HARD_NEGATIVE_TEMPLATES = [
    (
        "Under the {citation}, what penalty applies for failing to lodge a quarterly "
        "carbon emissions return?",
        ("carbon", "emission"),
    ),
    (
        "Under the {citation}, what is the maximum fine for operating an unlicensed "
        "cryptocurrency exchange?",
        ("crypto", "exchange"),
    ),
    (
        "Under the {citation}, what is the minimum age for flying a commercial drone at night?",
        ("drone", "age"),
    ),
    (
        "Under the {citation}, how many days' notice must a landlord give before evicting a "
        "tenant?",
        ("landlord", "tenant", "evict"),
    ),
]

STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "does",
        "for",
        "from",
        "has",
        "how",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "under",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "with",
    ]
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFC", text).replace("\u0092", "\u2019")
    return re.sub(r"[ \t]+", " ", text).strip()


def chunk_id_for(version_id: str) -> str:
    return "c_" + sha256_text(version_id)[:12]


def adversarial_id_for(attack_id: str) -> str:
    return "adv_" + sha256_text(attack_id)[:12]


@dataclass(frozen=True)
class Question:
    question_id: str
    question: str
    gold_answer: str
    gold_chunk_id: str
    jurisdiction: str
    citation: str

    def to_json(self) -> dict[str, str]:
        return dict(vars(self))


def _jsonl(records: Iterable[dict[str, Any]]) -> str:
    return "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in records)


def _write(path: Path, content: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = content.encode("utf-8")
    path.write_bytes(data)
    return sha256_bytes(data)


def load_licensed(raw_path: Path) -> tuple[list[Chunk], list[Question], dict[str, int]]:
    """Read the raw export, keep licensed legislation, and return chunks and questions."""
    chunks: dict[str, Chunk] = {}
    questions: list[Question] = []
    seen_questions: set[str] = set()
    stats = {"records_total": 0, "excluded_case_law": 0, "duplicate_questions": 0}
    with raw_path.open(encoding="utf-8") as handle:
        for line in handle:
            stats["records_total"] += 1
            record = json.loads(line)
            source = record["source"]
            if source["source"] not in LICENSED_SOURCES:
                stats["excluded_case_law"] += 1
                continue
            chunk = Chunk(
                chunk_id=chunk_id_for(source["version_id"]),
                version_id=source["version_id"],
                citation=normalise(source["citation"]),
                jurisdiction=Jurisdiction(source["jurisdiction"]),
                doc_type=DocType(source["type"]),
                url=source["url"].replace("http://", "https://", 1),
                text=normalise(source["text"]),
            )
            chunks[chunk.chunk_id] = chunk
            question_text = normalise(record["question"])
            if question_text in seen_questions:
                stats["duplicate_questions"] += 1
                continue
            seen_questions.add(question_text)
            questions.append(
                Question(
                    question_id="q_" + sha256_text(chunk.version_id + question_text)[:10],
                    question=question_text,
                    gold_answer=normalise(record["answer"]),
                    gold_chunk_id=chunk.chunk_id,
                    jurisdiction=chunk.jurisdiction.value,
                    citation=chunk.citation,
                )
            )
    return sorted(chunks.values(), key=lambda c: c.chunk_id), questions, stats


def split_questions(
    questions: list[Question], seed: int = SEED
) -> tuple[list[Question], list[Question]]:
    """Stratified by jurisdiction. Each chunk has one question, so no chunk spans both splits."""
    by_jurisdiction: dict[str, list[Question]] = defaultdict(list)
    for q in sorted(questions, key=lambda q: q.question_id):
        by_jurisdiction[q.jurisdiction].append(q)
    rng = random.Random(seed)  # noqa: S311 - deterministic sampling, not cryptography
    dev: list[Question] = []
    test: list[Question] = []
    for jurisdiction in sorted(by_jurisdiction):
        group = by_jurisdiction[jurisdiction]
        rng.shuffle(group)
        n_dev = round(len(group) * DEV_FRACTION)
        dev.extend(group[:n_dev])
        test.extend(group[n_dev:])
    return dev, test


def hard_negatives(questions: list[Question], chunks: dict[str, Chunk]) -> list[dict[str, str]]:
    """Template questions naming a real instrument about a matter its passage lacks."""
    out: list[dict[str, str]] = []
    for q in sorted(questions, key=lambda q: q.question_id):
        if len(out) >= HARD_NEGATIVES_PER_SPLIT:
            break
        template, keywords = HARD_NEGATIVE_TEMPLATES[len(out) % len(HARD_NEGATIVE_TEMPLATES)]
        text = chunks[q.gold_chunk_id].text.lower()
        if any(k in text for k in keywords):
            continue
        out.append(
            {
                "negative_id": "n_" + sha256_text("hard" + q.question_id)[:10],
                "kind": "hard_negative",
                "question": template.format(citation=q.citation),
                "related_chunk_id": q.gold_chunk_id,
            }
        )
    return out


def out_of_corpus(sources_dir: Path) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    data = json.loads((sources_dir / "out_of_corpus.json").read_text("utf-8"))
    items = [
        {
            "negative_id": "n_" + sha256_text("ooc" + text)[:10],
            "kind": "out_of_corpus",
            "question": text,
            "related_chunk_id": "",
        }
        for text in data["questions"]
    ]
    return items[0::2], items[1::2]


def content_words(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOPWORDS]


def build_overlay(
    sources_dir: Path, dev: list[Question], chunks: dict[str, Chunk]
) -> tuple[list[Chunk], list[dict[str, Any]], list[dict[str, str]]]:
    """Insert each catalogue attack into a copy of a distinct dev passage."""
    catalogue = json.loads((sources_dir / "attack_catalogue.json").read_text("utf-8"))
    targets = sorted(dev, key=lambda q: q.question_id)
    poisoned: list[Chunk] = []
    labels: list[dict[str, Any]] = []
    attack_questions: list[dict[str, str]] = []
    for attack, target in zip(catalogue["attacks"], targets, strict=False):
        original = chunks[target.gold_chunk_id]
        payload: str = attack["payload"]
        if "{stuffing}" in payload:
            stuffing = " ".join(content_words(target.question) * 6)
            payload = payload.replace("{stuffing}", stuffing)
        payload = payload.replace("{echo}", target.question)
        text = original.text
        if attack["position"] == "start":
            new_text, start = f"{payload} {text}", 0
        elif attack["position"] == "end":
            new_text, start = f"{text} {payload}", len(text) + 1
        else:
            cut = text.find(". ", len(text) // 2)
            cut = len(text) // 2 if cut == -1 else cut + 2
            new_text, start = f"{text[:cut]}{payload} {text[cut:]}", cut
        chunk = original.model_copy(
            update={"chunk_id": adversarial_id_for(attack["attack_id"]), "text": new_text}
        )
        poisoned.append(chunk)
        labels.append(
            {
                "chunk_id": chunk.chunk_id,
                "attack_id": attack["attack_id"],
                "technique": attack["technique"],
                "objective": attack["objective"],
                "original_chunk_id": original.chunk_id,
                "payload_span": [start, start + len(payload)],
                "target_question_id": target.question_id,
            }
        )
        attack_questions.append(
            {
                "attack_id": attack["attack_id"],
                "question": target.question,
                "gold_chunk_id": original.chunk_id,
                "poisoned_chunk_id": chunk.chunk_id,
            }
        )
    return poisoned, labels, attack_questions


def build(raw_path: Path, out_dir: Path, seed: int = SEED) -> dict[str, Any]:
    """Write all sample-data outputs and return the manifest."""
    sources_dir = out_dir / "sources"
    chunk_list, questions, stats = load_licensed(raw_path)
    chunks = {c.chunk_id: c for c in chunk_list}
    dev, test = split_questions(questions, seed)
    ooc_dev, ooc_test = out_of_corpus(sources_dir)
    negatives = {
        "dev": hard_negatives(dev, chunks) + ooc_dev,
        "test": hard_negatives(test, chunks) + ooc_test,
    }
    poisoned, labels, attack_questions = build_overlay(sources_dir, dev, chunks)

    files: dict[str, str] = {}

    def emit(rel: str, content: str) -> None:
        files[rel] = _write(out_dir / rel, content)

    emit("corpus.jsonl", _jsonl(c.model_dump(mode="json") for c in chunk_list))
    emit("questions_dev.jsonl", _jsonl(q.to_json() for q in dev))
    emit("questions_test.jsonl", _jsonl(q.to_json() for q in test))
    emit("negatives_dev.jsonl", _jsonl(negatives["dev"]))
    emit("negatives_test.jsonl", _jsonl(negatives["test"]))
    emit("adversarial/injected_chunks.jsonl", _jsonl(c.model_dump(mode="json") for c in poisoned))
    emit("adversarial/labels.jsonl", _jsonl(labels))
    emit("adversarial/questions.jsonl", _jsonl(attack_questions))
    for name in ("attack_catalogue.json", "direct_injections.json", "out_of_corpus.json"):
        files[f"sources/{name}"] = sha256_bytes((sources_dir / name).read_bytes())

    manifest: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "corpus_version": "c-" + files["corpus.jsonl"][:12],
        "seed": seed,
        "source": {
            "dataset": "Open Australian Legal QA (umarbutler/open-australian-legal-qa)",
            "file_sha256": sha256_bytes(raw_path.read_bytes()),
            **stats,
            "legislation_chunks": len(chunk_list),
            "questions": len(questions),
        },
        "transformations": TRANSFORMATIONS,
        "splits": {
            "dev": [q.question_id for q in dev],
            "test": [q.question_id for q in test],
        },
        "attack_set": {
            "attacks": len(poisoned),
            "catalogue_sha256": files["sources/attack_catalogue.json"],
        },
        "chunk_text_sha256": {c.version_id: sha256_text(c.text) for c in chunk_list},
        "files": dict(sorted(files.items())),
        "reproducible_without_raw_file": (
            "Everything except rebuilding sample-data from source. The committed files and "
            "this manifest are sufficient to run, test and evaluate."
        ),
    }
    _write(out_dir / "manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest
