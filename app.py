from __future__ import annotations

import json
import logging
from threading import Thread
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel, Field

from backend.ai_definition_service import AIDefinitionService
from backend.document_service import DocumentService
from backend.feedback_service import FeedbackService
from backend.glossary_service import GlossaryService
from backend.image_utils import decode_data_url, image_fingerprint, image_quality
from backend.insight_service import InsightService
from backend.ocr_service import OCRService
from backend.progress_service import ProgressService
from backend.vlm_service import VLMService

ROOT = Path(__file__).parent
DATA = ROOT / "data"
logging.basicConfig(level=logging.INFO)


class CacheControlledStaticFiles(StaticFiles):
    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "public, max-age=86400"
        return response


app = FastAPI(title="FalconScan", version="1.0.0", description="CPU-first customs terminology camera assistant")
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.mount("/static", CacheControlledStaticFiles(directory=ROOT / "frontend"), name="static")

ocr = OCRService()
Thread(target=ocr.warmup, daemon=True, name="falconscan-ocr-warmup").start()
glossary = GlossaryService(DATA / "glossary.json", DATA / "user_corrections.json", DATA / "sme_approved_definitions.json")
feedback = FeedbackService(DATA / "user_corrections.json", DATA / "feedback_history.json", DATA / "sme_approved_definitions.json")
ai = AIDefinitionService()
vlm = VLMService()
progress = ProgressService(DATA / "project_progress.json")
documents = DocumentService(ocr, glossary)
insights = InsightService(glossary)


class FrameRequest(BaseModel):
    image_base64: str
    frame_width: int = Field(gt=0, le=10000)
    frame_height: int = Field(gt=0, le=10000)
    language_preference: str = Field(default="en", pattern="^(en|ar)$")


class FeedbackRequest(BaseModel):
    term: str = Field(min_length=1, max_length=200)
    old_definition: str = Field(default="", max_length=2000)
    corrected_definition: Optional[str] = Field(default=None, max_length=2000)
    feedback_type: str = Field(pattern="^(thumbs_up|thumbs_down)$")
    suggested_by: str = Field(default="anonymous", max_length=100)


class ReviewRequest(BaseModel):
    term: str
    action: str = Field(pattern="^(approve|reject)$")
    reviewer: str = "SME"


class VLMRequest(BaseModel):
    image_base64: Optional[str] = None
    user_requested: bool = True


class DocumentRequest(BaseModel):
    file_base64: str
    filename: str = Field(min_length=1, max_length=255)
    language_preference: str = Field(default="en", pattern="^(en|ar)$")


class SelectionRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    language_preference: str = Field(default="en", pattern="^(en|ar)$")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(ROOT / "frontend" / "index.html")


@app.get("/health")
def health():
    return {"status": "ok", "ocr": ocr.status(), "ai_enabled": ai.enabled,
            "vlm_enabled": vlm.enabled, "storage": "local_json"}


@app.post("/analyze-frame")
def analyze_frame(request: FrameRequest):
    try:
        image = decode_data_url(request.image_base64)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    fingerprint = image_fingerprint(image)
    cache_path = DATA / "ocr_cache.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    cached = cache.get(fingerprint)
    if cached:
        return {**cached, "cached": True}
    quality = image_quality(image)
    try:
        detections = ocr.extract(image, request.language_preference)
    except RuntimeError as exc:
        # Honest degraded mode: camera works and reports setup rather than fabricating OCR.
        return {"detected_terms": [], "unknown_terms": [], "ocr_items": [], "cached": False,
                "quality": quality, "ocr_available": False, "message": str(exc),
                "suggest_vlm": False, "vlm_reasons": []}
    terms = glossary.match_regions(detections)
    if len(terms) < 3:
        terms.extend(glossary.contextual_fallbacks(detections, 3 - len(terms), terms))
    _, unknown = glossary.match_ocr(detections)
    mean_confidence = sum(x["confidence"] for x in detections) / len(detections) if detections else 0.0
    suggest_vlm, reasons = vlm.should_suggest(mean_confidence, len(unknown))
    result = {"detected_terms": terms, "unknown_terms": unknown[:10], "ocr_items": detections,
              "cached": False, "ocr_available": True, "quality": quality,
              "mean_ocr_confidence": round(mean_confidence, 3), "suggest_vlm": suggest_vlm,
              "vlm_reasons": reasons}
    cache[fingerprint] = result
    # Bounded local cache: images are never persisted.
    if len(cache) > 100:
        cache.pop(next(iter(cache)))
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


@app.post("/analyze-document")
def analyze_document(request: DocumentRequest):
    try:
        return documents.analyze(request.file_base64, request.filename, request.language_preference)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/explain-selection")
def explain_selection(request: SelectionRequest):
    try:
        return insights.explain(request.text, request.language_preference)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/definition/{term:path}")
def get_definition(term: str, language: str = "en"):
    result = glossary.definition(term)
    return result or ai.define(term, language=language)


@app.post("/submit-feedback")
def submit_feedback(request: FeedbackRequest):
    if request.feedback_type == "thumbs_down" and not request.corrected_definition:
        raise HTTPException(status_code=400, detail="A corrected definition is required for thumbs down")
    return feedback.submit(**request.model_dump())


@app.get("/admin/corrections")
def pending_corrections():
    return {"items": feedback.pending()}


@app.post("/admin/review")
def review_correction(request: ReviewRequest):
    try:
        return feedback.review(request.term, request.action, request.reviewer)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Correction not found") from exc


@app.post("/analyze-document-vlm")
def analyze_document_vlm(request: VLMRequest):
    return vlm.analyze(request.user_requested)


@app.get("/progress")
def project_progress():
    return progress.get()
