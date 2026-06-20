import json
import base64
import io
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from app import app
from backend.glossary_service import GlossaryService


ROOT = Path(__file__).parents[1]
client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_definition_exact_and_arabic_alias():
    response = client.get("/definition/MAWB")
    assert response.status_code == 200
    assert response.json()["source"] == "verified_glossary"
    response = client.get("/definition/رمز النظام المنسق")
    assert response.json()["term"] == "HS Code"


def test_fuzzy_ocr_match():
    service = GlossaryService(ROOT / "data/glossary.json", ROOT / "data/user_corrections.json", ROOT / "data/sme_approved_definitions.json")
    match = service.find_match("Commercia1 Invoice")
    assert match and match["canonical"] == "Commercial Invoice"


def test_invalid_image_rejected():
    response = client.post("/analyze-frame", json={"image_base64": "bad", "frame_width": 100, "frame_height": 100})
    assert response.status_code == 400


def test_vlm_disabled_is_graceful():
    response = client.post("/analyze-document-vlm", json={"user_requested": True})
    assert response.status_code == 200
    assert response.json()["status"] in {"unavailable", "configured"}


def test_feedback_and_sme_priority(tmp_path):
    glossary_path = tmp_path / "glossary.json"
    corrections_path = tmp_path / "corrections.json"
    approved_path = tmp_path / "approved.json"
    glossary_path.write_text(json.dumps({"MAWB": {"definition": "verified", "source": "verified_glossary"}}))
    corrections_path.write_text(json.dumps({"MAWB": {"corrected_definition": "user", "status": "pending_sme_review"}}))
    approved_path.write_text(json.dumps({"MAWB": {"definition": "approved"}}))
    service = GlossaryService(glossary_path, corrections_path, approved_path)
    result = service.definition("MAWB")
    assert result["definition"] == "approved"
    assert result["source"] == "sme_approved"


def test_docx_upload_returns_clickable_term_data():
    xml = '''<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>MAWB with Packing List</w:t></w:r></w:p></w:body></w:document>'''
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", xml)
    response = client.post("/analyze-document", json={
        "file_base64": base64.b64encode(buffer.getvalue()).decode(),
        "filename": "air-cargo.docx",
        "language_preference": "en",
    })
    assert response.status_code == 200
    terms = response.json()["detected_terms"]
    assert {item["term"] for item in terms} >= {"MAWB", "Packing List"}
    assert all(item["bbox"] and item["definition"] for item in terms)


def test_unsupported_legacy_word_is_clear():
    response = client.post("/analyze-document", json={
        "file_base64": base64.b64encode(b"legacy").decode(),
        "filename": "legacy.doc",
        "language_preference": "en",
    })
    assert response.status_code == 400
    assert "DOCX" in response.json()["detail"]


def test_selection_insight_has_summary_and_business_meaning():
    response = client.post("/explain-selection", json={
        "text": "Commercial Invoice with HS Code and Customs Duty",
        "language_preference": "en",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["summary"]
    assert data["business_meaning"]
    assert {item["term"] for item in data["recognized_terms"]} >= {
        "Commercial Invoice", "HS Code", "Customs Duty"
    }


def test_unknown_selection_is_clearly_unverified():
    response = client.post("/explain-selection", json={
        "text": "Internal reference XYZ-998",
        "language_preference": "en",
    })
    assert response.status_code == 200
    assert response.json()["source"] == "ai_generated_unverified"


def test_contextual_fallback_prevents_empty_dot_state():
    service = GlossaryService(ROOT / "data/glossary.json", ROOT / "data/user_corrections.json", ROOT / "data/sme_approved_definitions.json")
    terms = service.contextual_fallbacks([{
        "text": "Port Reference ZX-2048", "bbox": [20, 30, 280, 60],
        "confidence": 0.91, "language": "en",
    }])
    assert len(terms) == 1
    assert terms[0]["bbox"] == [20, 30, 280, 60]
    assert terms[0]["source"] == "ai_generated_unverified"


def test_scanner_serves_scroll_info_and_clean_status_controls():
    html = client.get("/").text
    assert 'id="documentScroller"' in html
    assert 'id="documentInfo"' in html
    assert 'id="stabilityMetric"' not in html
    assert 'id="lightMetric"' not in html
    assert 'id="ocrMetric"' not in html
