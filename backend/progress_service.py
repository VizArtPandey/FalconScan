import json
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock


class ProgressService:
    def __init__(self, path: Path):
        self.path = path
        self.lock = RLock()
        self._cache = None
        self._mtime = 0.0

    def get(self) -> dict:
        try:
            mtime = self.path.stat().st_mtime
        except FileNotFoundError:
            mtime = 0.0
        if self._cache is None or mtime > self._mtime:
            with self.lock:
                try:
                    self._cache = json.loads(self.path.read_text(encoding="utf-8"))
                except FileNotFoundError:
                    self._cache = {}
                self._mtime = mtime
        return self._cache

    def update(self, **changes) -> dict:
        with self.lock:
            data = dict(self.get())
            data.update(changes)
            data["last_updated"] = datetime.now(timezone.utc).isoformat()
            self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            self._cache = data
            try:
                self._mtime = self.path.stat().st_mtime
            except FileNotFoundError:
                self._mtime = 0.0
            return data
