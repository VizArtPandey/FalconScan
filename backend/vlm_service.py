from __future__ import annotations

import os


class VLMService:
    """Phase 3 gate. Never loads a VLM in the CPU process."""

    def __init__(self):
        self.endpoint = os.getenv("FALCONSCAN_VLM_ENDPOINT", "")
        self.token = os.getenv("HF_TOKEN", "")

    @property
    def enabled(self) -> bool:
        return bool(self.endpoint and self.token)

    def should_suggest(self, ocr_confidence: float, unknown_count: int,
                       user_requested: bool = False, complex_layout: bool = False) -> tuple[bool, list[str]]:
        reasons = []
        if ocr_confidence < 0.7:
            reasons.append("low_ocr_confidence")
        if unknown_count:
            reasons.append("unknown_terms")
        if user_requested:
            reasons.append("user_requested")
        if complex_layout:
            reasons.append("complex_layout")
        return bool(reasons), reasons

    def analyze(self, user_requested: bool) -> dict:
        if not user_requested:
            return {"status": "not_run", "message": "VLM analysis requires an explicit trigger."}
        if not self.enabled:
            return {"status": "unavailable", "message": "Optional VLM endpoint is not configured. Glossary-first OCR remains available."}
        return {"status": "configured", "message": "VLM endpoint is configured; provider adapter can be enabled for the selected model."}
