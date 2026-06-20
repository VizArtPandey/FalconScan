import base64
import io
import textwrap
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from PIL import Image, ImageDraw, ImageFont

from backend.glossary_service import GlossaryService
from backend.ocr_service import OCRService


class DocumentService:
    MAX_BYTES = 15 * 1024 * 1024

    def __init__(self, ocr: OCRService, glossary: GlossaryService):
        self.ocr = ocr
        self.glossary = glossary

    def analyze(self, encoded: str, filename: str, language: str) -> dict:
        try:
            raw = base64.b64decode(encoded, validate=True)
        except Exception as exc:
            raise ValueError("Invalid uploaded document") from exc
        if not raw or len(raw) > self.MAX_BYTES:
            raise ValueError("Document must be between 1 byte and 15 MB")
        extension = Path(filename).suffix.lower()
        if extension in {".jpg", ".jpeg", ".png", ".webp"}:
            return self._image(raw, language)
        if extension == ".pdf":
            return self._pdf(raw)
        if extension == ".docx":
            return self._docx(raw)
        raise ValueError("Supported formats are JPG, PNG, WebP, PDF, and DOCX")

    def _image(self, raw: bytes, language: str) -> dict:
        try:
            image = Image.open(io.BytesIO(raw)).convert("RGB")
            image.load()
        except Exception as exc:
            raise ValueError("The uploaded image could not be opened") from exc
        detections = self.ocr.extract(image, language)
        terms = self.glossary.match_regions(detections)
        if len(terms) < 3:
            terms.extend(self.glossary.contextual_fallbacks(detections, 3 - len(terms), terms))
        _, unknown = self.glossary.match_ocr(detections)
        return self._result(image, terms, detections, unknown, "image_ocr")

    def _pdf(self, raw: bytes) -> dict:
        try:
            import fitz
        except ImportError as exc:
            raise RuntimeError("PDF support is not installed") from exc
        try:
            document = fitz.open(stream=raw, filetype="pdf")
            if document.page_count < 1:
                raise ValueError("The PDF has no pages")
            page = document[0]
            zoom = min(2.0, 1800 / max(page.rect.width, page.rect.height))
            matrix = fitz.Matrix(zoom, zoom)
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            image = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
            regions = []
            for block in page.get_text("blocks"):
                x1, y1, x2, y2, text = block[:5]
                if text.strip():
                    regions.append({"text": text, "bbox": [x1 * zoom, y1 * zoom, x2 * zoom, y2 * zoom],
                                    "confidence": 1.0, "language": self._language(text)})
            terms = self.glossary.match_regions(regions)
            if len(terms) < 3:
                terms.extend(self.glossary.contextual_fallbacks(regions, 3 - len(terms), terms))
            if not regions:
                detections = self.ocr.extract(image, "en")
                terms = self.glossary.match_regions(detections)
                if len(terms) < 3:
                    terms.extend(self.glossary.contextual_fallbacks(detections, 3 - len(terms), terms))
                _, unknown = self.glossary.match_ocr(detections)
                return self._result(image, terms, detections, unknown, "scanned_pdf_ocr")
            return self._result(image, terms, regions, [], "pdf_text")
        except (ValueError, RuntimeError):
            raise
        except Exception as exc:
            raise ValueError("The PDF could not be processed") from exc

    def _docx(self, raw: bytes) -> dict:
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                xml = archive.read("word/document.xml")
        except Exception as exc:
            raise ValueError("The Word document could not be opened") from exc
        root = ElementTree.fromstring(xml)
        paragraphs = []
        for paragraph in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
            text = "".join(node.text or "" for node in paragraph.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"))
            if text.strip():
                paragraphs.append(text.strip())
        if not paragraphs:
            raise ValueError("The Word document contains no readable text")
        return self._render_text(paragraphs)

    def _render_text(self, paragraphs: list[str]) -> dict:
        width, margin, line_height = 1400, 100, 42
        wrapped = []
        for paragraph in paragraphs:
            wrapped.extend(textwrap.wrap(paragraph, width=85, break_long_words=False) or [""])
            wrapped.append("")
        height = min(2200, max(900, margin * 2 + len(wrapped) * line_height))
        image = Image.new("RGB", (width, height), "#ffffff")
        draw = ImageDraw.Draw(image)
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
        except OSError:
            font = ImageFont.load_default()
        regions = []
        y = margin
        for line in wrapped:
            if y + line_height > height - margin:
                break
            if line:
                draw.text((margin, y), line, fill="#17211e", font=font)
                regions.append({"text": line, "bbox": [margin, y, width - margin, y + line_height],
                                "confidence": 1.0, "language": self._language(line)})
            y += line_height
        terms = self.glossary.match_regions(regions)
        if len(terms) < 3:
            terms.extend(self.glossary.contextual_fallbacks(regions, 3 - len(terms), terms))
        return self._result(image, terms, regions, [], "docx_text")

    @staticmethod
    def _language(text: str) -> str:
        return "ar" if any("\u0600" <= character <= "\u06ff" for character in text) else "en"

    @staticmethod
    def _result(image: Image.Image, terms: list, detections: list, unknown: list, method: str) -> dict:
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=88, optimize=True)
        return {
            "detected_terms": terms,
            "ocr_items": detections,
            "unknown_terms": unknown[:10],
            "frame_width": image.width,
            "frame_height": image.height,
            "preview_base64": "data:image/jpeg;base64," + base64.b64encode(output.getvalue()).decode(),
            "ocr_available": True,
            "analysis_method": method,
            "mean_ocr_confidence": round(sum(float(item.get("confidence", 1)) for item in detections) / len(detections), 3) if detections else 0,
        }
