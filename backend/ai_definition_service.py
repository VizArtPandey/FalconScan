import os


class AIDefinitionService:
    """Conservative optional text-model fallback; disabled unless explicitly configured."""

    def __init__(self):
        self.endpoint = os.getenv("FALCONSCAN_AI_ENDPOINT", "")
        self.token = os.getenv("HF_TOKEN", "")

    @property
    def enabled(self) -> bool:
        return bool(self.endpoint and self.token)

    def define(self, term: str, nearby_text: str = "", language: str = "en") -> dict:
        # A remote call is deliberately not implicit on free Spaces. Integrators may place a
        # compatible inference endpoint behind this interface without changing API behavior.
        if not self.enabled:
            message = ("هذا المصطلح يحتاج إلى تحقق من خبير جمركي."
                       if language == "ar" else "This term needs customs expert verification.")
            return {"term": term, "definition": message, "source": "ai_generated_unverified",
                    "source_label": "AI-generated · unverified", "confidence": 0.2,
                    "ai_available": False}
        # Keep a safe placeholder rather than guessing if an endpoint contract is unknown.
        return {"term": term, "definition": "This term needs customs expert verification.",
                "source": "ai_generated_unverified", "source_label": "AI-generated · unverified",
                "confidence": 0.2, "ai_available": True}
