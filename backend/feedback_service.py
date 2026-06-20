from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from uuid import uuid4


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class FeedbackService:
    def __init__(self, corrections_path: Path, history_path: Path, approved_path: Path):
        self.corrections_path = corrections_path
        self.history_path = history_path
        self.approved_path = approved_path
        self.lock = RLock()

    @staticmethod
    def _read(path: Path):
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write(path: Path, value):
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")

    def submit(self, term: str, old_definition: str, corrected_definition: str | None,
               feedback_type: str, suggested_by: str = "anonymous") -> dict:
        with self.lock:
            event_id = str(uuid4())
            event = {"id": event_id, "term": term, "old_definition": old_definition,
                     "corrected_definition": corrected_definition, "feedback_type": feedback_type,
                     "suggested_by": suggested_by, "status": "pending_sme_review" if corrected_definition else "recorded",
                     "created_at": now()}
            history = self._read(self.history_path)
            history.append(event)
            self._write(self.history_path, history)
            if corrected_definition:
                corrections = self._read(self.corrections_path)
                corrections[term] = {**event, "source": "user_corrected",
                                     "previous_definition": old_definition}
                self._write(self.corrections_path, corrections)
            return {"status": "saved", "message": "Correction saved and will be used next time." if corrected_definition else "Feedback recorded.",
                    "source": "user_corrected" if corrected_definition else "feedback", "id": event_id}

    def pending(self) -> list[dict]:
        corrections = self._read(self.corrections_path)
        return [value for value in corrections.values() if value.get("status") == "pending_sme_review"]

    def review(self, term: str, action: str, reviewer: str = "SME") -> dict:
        with self.lock:
            corrections = self._read(self.corrections_path)
            if term not in corrections:
                raise KeyError(term)
            correction = corrections[term]
            correction.update({"status": "approved" if action == "approve" else "rejected",
                               "reviewed_by": reviewer, "reviewed_at": now()})
            corrections[term] = correction
            self._write(self.corrections_path, corrections)
            if action == "approve":
                approved = self._read(self.approved_path)
                approved[term] = {
                    "term": term, "definition": correction["corrected_definition"],
                    "previous_definition": correction.get("previous_definition"),
                    "source": "sme_approved", "approved_by": reviewer,
                    "approved_at": correction["reviewed_at"],
                }
                self._write(self.approved_path, approved)
            return {"status": correction["status"], "term": term}
