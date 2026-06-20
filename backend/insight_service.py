from backend.glossary_service import GlossaryService


CATEGORY_MEANING = {
    "Air Cargo": "This affects how air cargo is documented, consolidated, tracked, and released.",
    "Customs Classification": "This can affect duty rates, permits, restrictions, reporting, and customs clearance.",
    "Customs Charges": "This can affect the landed cost and payment required before goods are released.",
    "Shipping Documents": "This is part of the evidence customs and carriers use to identify and release a shipment.",
    "Trade Documents": "This supports customs valuation, verification, and consistency checks across the shipment file.",
    "Incoterms": "This defines which party carries transport cost, operational responsibility, and risk at each stage.",
    "Shipment Parties": "This identifies who sends, receives, or takes responsibility for the shipment.",
    "Cargo Release": "This can determine whether a carrier or terminal is authorized to release the cargo.",
    "Customs Clearance": "This is used to trace the declaration and progress the shipment through customs controls.",
}


class InsightService:
    def __init__(self, glossary: GlossaryService):
        self.glossary = glossary

    def explain(self, text: str, language: str = "en") -> dict:
        clean = " ".join(text.split())[:5000]
        if not clean:
            raise ValueError("Select a word, phrase, or paragraph first")
        terms = self.glossary.match_regions([{
            "text": clean, "bbox": [0, 0, 1, 1], "confidence": 1.0, "language": language,
        }])
        unique = []
        seen = set()
        for term in terms:
            if term["term"] not in seen:
                seen.add(term["term"])
                unique.append(term)
        if unique:
            names = ", ".join(item["term"] for item in unique[:4])
            definitions = " ".join(item["definition"] for item in unique[:3])
            summary = f"This selection contains {len(unique)} recognized trade concept{'s' if len(unique) != 1 else ''}: {names}. {definitions}"
            meanings = []
            for item in unique:
                meaning = CATEGORY_MEANING.get(item.get("category"))
                if meaning and meaning not in meanings:
                    meanings.append(meaning)
            business_meaning = " ".join(meanings[:3]) or "Use these terms to cross-check the shipment documents and confirm the responsible parties before clearance."
            confidence = round(sum(item["confidence"] for item in unique) / len(unique), 3)
            source = "verified_glossary"
            source_label = "Verified Customs Glossary"
        else:
            excerpt = clean if len(clean) <= 220 else clean[:217] + "…"
            summary = f"Selected document text: {excerpt}"
            business_meaning = "No governed customs term was found in this selection. Review it in the surrounding document context or request customs-expert verification before acting on it."
            confidence = 0.35
            source = "ai_generated_unverified"
            source_label = "Context summary · needs expert verification"
        return {
            "selected_text": clean,
            "summary": summary,
            "business_meaning": business_meaning,
            "recognized_terms": unique,
            "source": source,
            "source_label": source_label,
            "confidence": confidence,
        }
