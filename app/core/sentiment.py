import re
import unicodedata


THREAT_PHRASES = [
    "vou processar",
    "vou denunciar",
    "chamar advogado",
    "vou na policia",
    "vou expor",
    "vou no procon",
]
SEVERE_ACCUSATIONS = ["golpe", "estelionato", "roubo", "fraude"]
HEAVY_INSULTS = ["lixo", "idiota", "burro", "vagabundo", "palhaco", "merda"]
LIGHT_INSULTS = ["ridiculo", "que saco", "aff", "droga"]


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.lower()
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    return text


def _has_caps_intense(text: str) -> bool:
    letters = [ch for ch in text if ch.isalpha()]
    if len(letters) < 6:
        return False
    upper = [ch for ch in letters if ch.isupper()]
    return len(upper) / len(letters) >= 0.5


def detect_severe_flags(text: str) -> tuple[bool, str]:
    normalized = normalize_text(text)
    if any(phrase in normalized for phrase in THREAT_PHRASES):
        return True, "threat_detected"
    if any(word in normalized for word in SEVERE_ACCUSATIONS):
        return True, "fraud_accusation"
    if any(word in normalized for word in HEAVY_INSULTS):
        return True, "severe_insult"
    return False, ""


def compute_negativity_score(text: str) -> float:
    if not text:
        return 0.0
    normalized = normalize_text(text)
    score = 0.0
    if any(word in normalized for word in LIGHT_INSULTS):
        score += 0.4
    if any(word in normalized for word in HEAVY_INSULTS):
        score += 0.7
    if any(word in normalized for word in SEVERE_ACCUSATIONS):
        score += 0.6
    if any(phrase in normalized for phrase in THREAT_PHRASES):
        score += 1.0
    if normalized.count("!") >= 3 or _has_caps_intense(text):
        score += 0.2
    return min(1.0, score)


def analyze_sentiment_local(message: str) -> dict:
    severe, reason = detect_severe_flags(message)
    score = compute_negativity_score(message)

    if reason == "threat_detected":
        return {
            "sentiment_level": "threat",
            "sentiment_score": score,
            "needs_handoff": True,
            "handoff_reason": reason,
        }

    if reason in {"fraud_accusation", "severe_insult"}:
        return {
            "sentiment_level": "aggressive",
            "sentiment_score": score,
            "needs_handoff": True,
            "handoff_reason": reason,
        }

    if score >= 0.75:
        return {
            "sentiment_level": "aggressive",
            "sentiment_score": score,
            "needs_handoff": True,
            "handoff_reason": "high_negativity",
        }

    if score >= 0.40:
        return {
            "sentiment_level": "frustrated",
            "sentiment_score": score,
            "needs_handoff": False,
            "handoff_reason": "frustration_detected",
        }

    return {
        "sentiment_level": "calm",
        "sentiment_score": score,
        "needs_handoff": False,
        "handoff_reason": None,
    }
