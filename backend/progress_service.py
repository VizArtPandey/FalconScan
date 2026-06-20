import json
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock


class ProgressService:
    def __init__(self, path: Path):
        self.path = path
        self.lock = RLock()

    def get(self) -> dict:
        with self.lock:
            return json.loads(self.path.read_text(encoding="utf-8"))

    def update(self, **changes) -> dict:
        with self.lock:
            data = self.get()
            data.update(changes)
            data["last_updated"] = datetime.now(timezone.utc).isoformat()
            self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return data
