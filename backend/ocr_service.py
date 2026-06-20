import logging
import os
import re
import shutil
from typing import Any

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


class OCRService:
    """Lazy PaddleOCR adapter. Models load only on the first real scan."""

    def __init__(self):
        self.enabled = os.getenv("FALCONSCAN_OCR_ENABLED", "true").lower() == "true"
        self.engine_mode = os.getenv("FALCONSCAN_OCR_ENGINE", "fast").lower()
        self._engines: dict[str, Any] = {}
        self._rapid = None
        self.warming = False
        self.ready = False

    def _engine(self, language: str):
        key = "ar" if language == "ar" else "en"
        if key not in self._engines:
            if not self.enabled:
                raise RuntimeError("OCR is disabled")
            try:
                from paddleocr import PaddleOCR
            except ImportError as exc:
                raise RuntimeError("PaddleOCR is not installed") from exc
            # PaddleOCR uses Arabic model code 'ar'. Angle classification helps camera captures.
            self._engines[key] = PaddleOCR(use_angle_cls=True, lang=key, show_log=False)
        return self._engines[key]

    @staticmethod
    def _box(points: list) -> list[int]:
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        return [round(min(xs)), round(min(ys)), round(max(xs)), round(max(ys))]

    @staticmethod
    def _language(text: str) -> str:
        return "ar" if re.search(r"[\u0600-\u06ff]", text) else "en"

    def extract(self, image: Image.Image, language_preference: str = "en") -> list[dict]:
        if not self.enabled:
            raise RuntimeError("OCR is disabled")
        if self.engine_mode != "paddle":
            if language_preference == "ar" and shutil.which("tesseract"):
                return self._extract_tesseract(image)
            return self._extract_rapid(image)
        try:
            import paddleocr  # noqa: F401
            paddle_available = True
        except ImportError:
            paddle_available = False
        if not paddle_available:
            return self._extract_rapid(image)

        languages = ["ar", "en"] if language_preference == "ar" else ["en", "ar"]
        detections: list[dict] = []
        seen: set[tuple[str, tuple[int, ...]]] = set()
        for language in languages:
            try:
                result = self._engine(language).ocr(np.asarray(image), cls=True) or []
            except RuntimeError:
                raise
            except Exception as exc:
                logger.warning("%s OCR failed: %s", language, exc)
                continue
            for page in result:
                for line in page or []:
                    points, value = line
                    text, confidence = value
                    box = self._box(points)
                    key = (text.strip().casefold(), tuple(box))
                    if text.strip() and key not in seen:
                        seen.add(key)
                        detections.append({
                            "text": text.strip(), "bbox": box,
                            "confidence": round(float(confidence), 4),
                            "language": self._language(text),
                        })
        return detections

    def _extract_tesseract(self, image: Image.Image) -> list[dict]:
        """Fast preinstalled bilingual OCR path for CPU Spaces."""
        try:
            import pytesseract
            from pytesseract import Output
        except ImportError as exc:
            raise RuntimeError("Arabic OCR support is not installed") from exc
        data = pytesseract.image_to_data(image, lang="ara+eng", output_type=Output.DICT,
                                         config="--oem 1 --psm 6")
        detections = []
        for index, value in enumerate(data.get("text", [])):
            text = str(value).strip()
            confidence = float(data["conf"][index]) if str(data["conf"][index]) != "-1" else -1
            if not text or confidence < 35:
                continue
            left, top = int(data["left"][index]), int(data["top"][index])
            width, height = int(data["width"][index]), int(data["height"][index])
            detections.append({
                "text": text,
                "bbox": [left, top, left + width, top + height],
                "confidence": round(confidence / 100, 4),
                "language": self._language(text),
            })
        self.ready = True
        return detections

    def _extract_rapid(self, image: Image.Image) -> list[dict]:
        """Portable CPU fallback for environments where Paddle wheels are unavailable."""
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError as exc:
            raise RuntimeError("Neither PaddleOCR nor the CPU fallback is installed") from exc
        if self._rapid is None:
            self._rapid = RapidOCR()
        result, _ = self._rapid(np.asarray(image))
        self.ready = True
        detections = []
        for line in result or []:
            points, text, confidence = line
            if text and text.strip():
                detections.append({
                    "text": text.strip(),
                    "bbox": self._box(points),
                    "confidence": round(float(confidence), 4),
                    "language": self._language(text),
                })
        return detections

    def warmup(self) -> None:
        """Load the portable OCR sessions before the user's first scan."""
        if not self.enabled or self.ready or self.warming:
            return
        self.warming = True
        try:
            from rapidocr_onnxruntime import RapidOCR
            if self._rapid is None:
                self._rapid = RapidOCR()
            self.ready = True
        except Exception as exc:
            logger.warning("OCR warm-up failed: %s", exc)
        finally:
            self.warming = False

    def status(self) -> dict:
        try:
            import paddleocr  # noqa: F401
            installed = True
        except ImportError:
            installed = False
        try:
            import rapidocr_onnxruntime  # noqa: F401
            fallback_installed = True
        except ImportError:
            fallback_installed = False
        return {"enabled": self.enabled, "installed": installed,
                "fallback_installed": fallback_installed,
                "loaded_languages": list(self._engines),
                "warming": self.warming, "ready": self.ready,
                "engine_mode": self.engine_mode,
                "arabic_tesseract": bool(shutil.which("tesseract"))}
