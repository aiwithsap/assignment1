"""Rebuild sample-data/ from the raw export (git-ignored, under data/raw/).

Usage:
    uv run python scripts/build_corpus.py [--raw data/raw/qa.jsonl] [--out sample-data]
"""

import argparse
import sys
from pathlib import Path

from legisqa.corpus_build import build


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=Path("data/raw/qa.jsonl"))
    parser.add_argument("--out", type=Path, default=Path("sample-data"))
    args = parser.parse_args(argv)
    if not args.raw.is_file():
        print(f"raw file not found: {args.raw}", file=sys.stderr)
        return 2
    manifest = build(args.raw, args.out)
    src = manifest["source"]
    print(
        f"corpus {manifest['corpus_version']}: {src['legislation_chunks']} chunks, "
        f"{src['questions']} questions ({len(manifest['splits']['dev'])} dev / "
        f"{len(manifest['splits']['test'])} test), {manifest['attack_set']['attacks']} attacks; "
        f"excluded {src['excluded_case_law']} case-law records"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
