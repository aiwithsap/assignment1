"""Append-only audit log. A failed write raises ``AuditWriteError``: no audit, no answer."""

import json
from pathlib import Path
from threading import Lock
from typing import Any

from legisqa.errors import AuditWriteError


class AuditLog:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = Lock()

    @property
    def path(self) -> Path:
        return self._path

    def writable(self) -> bool:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8"):
                pass
        except OSError:
            return False
        return True

    def write(self, record: dict[str, Any]) -> None:
        line = json.dumps(record, ensure_ascii=False, sort_keys=True, default=str)
        try:
            with self._lock:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                with self._path.open("a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
        except OSError as exc:
            raise AuditWriteError(f"audit log not writable: {exc.strerror}") from exc
