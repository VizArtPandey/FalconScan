import base64
import hashlib
import io
import textwrap
import zipfile
from collections import OrderedDict
from pathlib import Path
from xml.etree import ElementTree

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from backend.glossary_service import GlossaryService
from backend.ocr_service import OCRService


class DocumentService:
    MAX_BYTES = 15 * 1024 * 1024
    MAX_PDF_PAGES = 12

    def __init__(self, ocr: OCRService, glossary: GlossaryService):
        self.ocr = ocr
        self.glossary = glossary
        self._cache: OrderedDict[str, dict] = OrderedDict()

    def analyze(self, encoded: str, filename: str, language: str) -> dict:
        try:
            raw = base64.b64decode(encoded, validate=True)
        except Exception as exc:
            raise ValueError("Invalid uploaded document") from exc
        if not raw or len(raw) > self.MAX_BYTES:
            raise ValueError("Document must be between 1 byte and 15 MB")
        cache_key = hashlib.sha256(raw + filename.lower().encode() + language.encode()).hexdigest()
        if cache_key in self._cache:
            self._cache.move_to_end(cache_key)
            return {**self._cache[cache_key], "cached": True}
        extension = Path(filename).suffix.lower()
        if extension in {".jpg", ".jpeg", ".png", ".webp"}:
            result = self._image(raw, language)
        elif extension == ".pdf":
            result = self._pdf(raw)
        elif extension == ".docx":
            result = self._docx(raw)
        else:
            raise ValueError("Supported formats are JPG, PNG, WebP, PDF, and DOCX")
        self._cache[cache_key] = result
        while len(self._cache) > 16:
            self._cache.popitem(last=False)
        return {**result, "cached": False}

    def _image(self, raw: bytes, language: str) -> dict:
        try:
            image = Image.open(io.BytesIO(raw)).convert("RGB")
            image.load()
        except Exception as exc:
            raise ValueError("The uploaded image could not be opened") from exc
        image.thumbnail((1000, 1000), Image.Resampling.BICUBIC)
        prepared = ImageOps.autocontrast(image.convert("L")).filter(ImageFilter.SHARPEN).convert("RGB")
        detections = self.ocr.extract(prepared, language)
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
            page_count = min(document.page_count, self.MAX_PDF_PAGES)
            rendered = []
            canvas_width = 0
            for index in range(page_count):
                page = document[index]
                zoom = min(1.2, 800 / max(1, page.rect.width))
                pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
                page_image = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
                rendered.append((page, page_image, zoom))
                canvas_width = max(canvas_width, page_image.width)
            gap = 18
            total_height = sum(item[1].height for item in rendered) + gap * max(0, page_count - 1)
            image = Image.new("RGB", (canvas_width, total_height), "#dfe3df")
            regions = []
            y_offset = 0
            for page, page_image, zoom in rendered:
                x_offset = (canvas_width - page_image.width) // 2
                image.paste(page_image, (x_offset, y_offset))
                page_regions = []
                for block in page.get_text("blocks"):
                    x1, y1, x2, y2, text = block[:5]
                    if text.strip():
                        page_regions.append({
                            "text": text,
                            "bbox": [x_offset + x1 * zoom, y_offset + y1 * zoom,
                                     x_offset + x2 * zoom, y_offset + y2 * zoom],
                            "confidence": 1.0,
                            "language": self._language(text),
                        })
                if page_regions:
                    regions.extend(page_regions)
                else:
                    page_detections = self.ocr.extract(page_image, "en")
                    for item in page_detections:
                        item["bbox"] = [item["bbox"][0] + x_offset, item["bbox"][1] + y_offset,
                                        item["bbox"][2] + x_offset, item["bbox"][3] + y_offset]
                    regions.extend(page_detections)
                y_offset += page_image.height + gap
            terms = self.glossary.match_regions(regions)
            if len(terms) < 3:
                terms.extend(self.glossary.contextual_fallbacks(regions, 3 - len(terms), terms))
            result = self._result(image, terms, regions, [], "pdf_multpage")
            result.update({"page_count": document.page_count, "pages_analyzed": page_count,
                           "truncated": document.page_count > page_count})
            return result
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
        width, margin, line_height = 1000, 80, 36
        wrapped = []
        for paragraph in paragraphs:
            wrapped.extend(textwrap.wrap(paragraph, width=65, break_long_words=False) or [""])
            wrapped.append("")
        height = max(900, margin * 2 + len(wrapped) * line_height)
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
        image.save(output, format="JPEG", quality=70, optimize=True)
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
