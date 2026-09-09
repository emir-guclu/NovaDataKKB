import re
import unicodedata


def slugify(text: str) -> str:
    replacements = {
        "ı": "i",
        "İ": "I",
        "ş": "s",
        "Ş": "S",
        "ğ": "g",
        "Ğ": "G",
        "ü": "u",
        "Ü": "U",
        "ö": "o",
        "Ö": "O",
        "ç": "c",
        "Ç": "C",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)

    return text.strip("_")


def parse_tr_number(value):
    if value is None:
        return None

    value = str(value).strip()

    if value in {"", "-", "—", "–"}:
        return None

    cleaned = (
        value
        .replace(" ", "")
        .replace("%", "")
        .replace(".", "")
        .replace(",", ".")
    )

    try:
        return float(cleaned)
    except ValueError:
        return None
