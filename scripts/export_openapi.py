"""Write the API's OpenAPI schema to frontend/openapi.json (the source of the UI's types).

Usage:
    uv run python scripts/export_openapi.py [--out frontend/openapi.json]
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path

from legisqa.api import create_app
from legisqa.config import Profile, Settings


def schema_json() -> str:
    with tempfile.TemporaryDirectory() as tmp:
        # demo profile so the schema includes the profile-gated security endpoint
        settings = Settings(
            profile=Profile.DEMO, var_dir=Path(tmp), frontend_dist=Path(tmp) / "none"
        )
        app = create_app(settings)
        return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("frontend/openapi.json"))
    args = parser.parse_args(argv)
    args.out.write_text(schema_json(), "utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
