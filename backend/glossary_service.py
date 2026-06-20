from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from threading import RLock


SOURCE_LABELS = {
    "user_corrected": "User correction (pending SME review)",
    "sme_approved": "SME-approved definition",
    "verified_glossary": "Verified Customs Glossary",
    "rag_retrieved": "Knowledge Base",
    "ai_generated_unverified": "AI-generated · unverified",
}


def normalize(value: str) -> str:
    return re.sub(r"[^\w\u0600-\u06ff]+", " ", value.casefold()).strip()


class GlossaryService:
    def __init__(self, glossary_path: Path, corrections_path: Path, approved_path: Path):
        self.glossary_path = glossary_path
        self.corrections_path = corrections_path
        self.approved_path = approved_path
        self.lock = RLock()

    @staticmethod
    def _read(path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def _index(self) -> tuple[dict, dict]:
        glossary = self._read(self.glossary_path)
        aliases: dict[str, str] = {}
        for canonical, entry in glossary.items():
            for alias in [canonical, *entry.get("aliases", [])]:
                aliases[normalize(alias)] = canonical
        return glossary, aliases

    def find_match(self, text: str, threshold: float = 0.78) -> dict | None:
        glossary, aliases = self._index()
        target = normalize(text)
        if not target:
            return None
        # Prefer longest contained phrases, then fuzzy matching for OCR errors.
        contained = [(alias, canonical) for alias, canonical in aliases.items()
                     if alias and re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", target)]
        match_type, score = "exact", 1.0
        if contained:
            alias, canonical = max(contained, key=lambda item: len(item[0]))
            match_type = "exact" if alias == target else "phrase"
        else:
            alias, canonical, score = "", "", 0.0
            for candidate, name in aliases.items():
                candidate_score = SequenceMatcher(None, target, candidate).ratio()
                if candidate_score > score:
                    alias, canonical, score = candidate, name, candidate_score
            if score < threshold:
                return None
            match_type = "fuzzy"
        return {"canonical": canonical, "entry": glossary[canonical],
                "match_type": match_type, "match_confidence": round(score, 3)}

    def definition(self, term: str) -> dict | None:
        with self.lock:
            matched = self.find_match(term)
            canonical = matched["canonical"] if matched else term
            norm = normalize(canonical)
            approved = self._read(self.approved_path)
            corrections = self._read(self.corrections_path)
            # SME approval is official and intentionally overrides pending user correction.
            selected = next((v for k, v in approved.items() if normalize(k) == norm), None)
            if selected:
                return self._response(canonical, selected, "sme_approved", 1.0, matched)
            selected = next((v for k, v in corrections.items()
                             if normalize(k) == norm and v.get("status") == "pending_sme_review"), None)
            if selected:
                item = dict(selected)
                item["definition"] = item.get("corrected_definition", item.get("definition", ""))
                return self._response(canonical, item, "user_corrected", 0.9, matched)
            if matched:
                return self._response(canonical, matched["entry"],
                                      matched["entry"].get("source", "verified_glossary"),
                                      matched["match_confidence"], matched)
            return None

    @staticmethod
    def _response(term: str, entry: dict, source: str, confidence: float, matched: dict | None) -> dict:
        return {
            "term": term,
            "full_form": entry.get("full_form"),
            "definition": entry.get("definition", ""),
            "definition_ar": entry.get("definition_ar"),
            "source": source,
            "source_label": SOURCE_LABELS.get(source, source),
            "confidence": round(float(confidence), 3),
            "category": entry.get("category"),
            "related_terms": entry.get("related_terms", []),
            "document_types": entry.get("document_types", []),
            "match_type": matched.get("match_type") if matched else "direct",
        }

    def match_ocr(self, detections: list[dict]) -> tuple[list[dict], list[dict]]:
        found, unknown = [], []
        for item in detections:
            definition = self.definition(item["text"])
            if definition:
                definition.update({"bbox": item["bbox"], "ocr_text": item["text"],
                                   "ocr_confidence": item["confidence"], "language": item["language"]})
                definition["confidence"] = round(definition["confidence"] * item["confidence"], 3)
                found.append(definition)
            elif len(item["text"]) >= 3:
                unknown.append(item)
        return found, unknown

    def match_regions(self, regions: list[dict]) -> list[dict]:
        """Find every known canonical term inside positioned text regions."""
        _, aliases = self._index()
        found: list[dict] = []
        seen: set[tuple[str, tuple[int, ...]]] = set()
        for region in regions:
            normalized_text = normalize(region.get("text", ""))
            if not normalized_text:
                continue
            matches: dict[str, str] = {}
            for alias, canonical in aliases.items():
                if alias and re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", normalized_text):
                    previous = matches.get(canonical, "")
                    if len(alias) > len(previous):
                        matches[canonical] = alias
            for canonical in matches:
                bbox = [round(value) for value in region["bbox"]]
                key = (canonical, tuple(bbox))
                if key in seen:
                    continue
                seen.add(key)
                definition = self.definition(canonical)
                if definition:
                    definition.update({
                        "bbox": bbox,
                        "ocr_text": region.get("text", canonical),
                        "ocr_confidence": region.get("confidence", 1.0),
                        "language": region.get("language", "en"),
                    })
                    knowledge_confidence = float(definition["confidence"])
                    recognition_confidence = float(region.get("confidence", 1.0))
                    # Calibrate two independent signals instead of multiplying them into an
                    # artificially low score. OCR remains the dominant factor.
                    definition["confidence"] = round(
                        0.72 * recognition_confidence + 0.28 * knowledge_confidence, 3
                    )
                    found.append(definition)
        return found

    def contextual_fallbacks(self, regions: list[dict], limit: int = 6,
                             existing: list[dict] | None = None) -> list[dict]:
        """Return clearly unverified markers when OCR succeeds but the governed glossary has no match."""
        candidates = []
        occupied = {tuple(item.get("bbox", [])) for item in (existing or [])}
        seen = set()
        for region in sorted(regions, key=lambda item: float(item.get("confidence", 0)), reverse=True):
            text = " ".join(str(region.get("text", "")).split())
            region_box = tuple(round(value) for value in region.get("bbox", []))
            if region_box in occupied:
                continue
            if not 2 <= len(text) <= 120 or float(region.get("confidence", 1)) < 0.55:
                continue
            label = text if len(text) <= 58 else text[:55].rstrip() + "…"
            key = normalize(label)
            if not key or key in seen:
                continue
            seen.add(key)
            confidence = round(min(0.62, float(region.get("confidence", 1)) * 0.62), 3)
            candidates.append({
                "term": label,
                "full_form": None,
                "definition": "This document phrase is not yet in the verified customs glossary. Select or highlight it for a contextual summary and business meaning.",
                "definition_ar": None,
                "source": "ai_generated_unverified",
                "source_label": "Contextual marker · needs verification",
                "confidence": confidence,
                "category": "Document Context",
                "related_terms": [],
                "document_types": [],
                "match_type": "contextual_fallback",
                "bbox": list(region_box),
                "ocr_text": text,
                "ocr_confidence": region.get("confidence", 1.0),
                "language": region.get("language", "en"),
            })
            if len(candidates) >= limit:
                break
        return candidates
