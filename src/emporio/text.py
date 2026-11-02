import unicodedata


def normalize(text: str) -> str:
    """Lowercase and strip accents so 'Violão' matches 'violao'."""
    decomposed = unicodedata.normalize("NFKD", text)
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(without_accents.lower().split())


def digits_only(text: str) -> str:
    return "".join(ch for ch in text if ch.isdigit())
