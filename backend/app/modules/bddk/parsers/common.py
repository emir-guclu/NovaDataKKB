"""Shared parsing utilities for BDDK Silver transformations."""

import re
from typing import Any, Optional


_NULL_TOKENS = {
    "",
    "-",
    "—",
    "–",
    "n.a.",
    "n/a",
    "na",
    "null",
    "none",
    "nan",
}


def parse_tr_number(raw: Any) -> Optional[float]:
    """
    Parse Turkish-formatted numeric values into float.

    Examples
    --------
    "1.234.567,89" -> 1234567.89
    "334.521,04"   -> 334521.04
    "12,5%"        -> 12.5
    "-"            -> None
    None           -> None

    Rules
    -----
    - Dot is treated as thousands separator when comma is present.
    - Comma is treated as decimal separator.
    - Percent sign is removed but the numeric magnitude is preserved.
      Example: "12,5%" -> 12.5, not 0.125.
    - Existing numeric Python values are preserved as float.
    """
    if raw is None:
        return None

    if isinstance(raw, bool):
        return None

    if isinstance(raw, (int, float)):
        try:
            if raw != raw:  # NaN
                return None
        except TypeError:
            pass
        return float(raw)

    text = str(raw).strip()

    if text.lower() in _NULL_TOKENS:
        return None

    text = text.replace("\u00a0", " ")
    text = text.replace("%", "").strip()
    text = text.replace(" ", "")

    if not text:
        return None

    # Turkish format:
    # 1.234.567,89 -> 1234567.89
    if "," in text:
        text = text.replace(".", "")
        text = text.replace(",", ".")
    else:
        # No comma:
        # If multiple dots exist, they are almost certainly thousands separators.
        if text.count(".") > 1:
            text = text.replace(".", "")

    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def extract_unit_hint(header_text: Any) -> Optional[str]:
    """
    Extract unit information from BDDK header/category text.

    Examples
    --------
    "Bilanço (milyon TL), Dönem:2021/1" -> "milyon TL"
    "Krediler (Bin TL)"                 -> "bin TL"
    "Oranlar (%)"                       -> "%"
    "Şubeler (Adet)"                    -> "adet"

    Returns None when no supported unit hint is found.
    """
    if header_text is None:
        return None

    text = str(header_text).strip()

    if not text:
        return None

    parenthetical_parts = re.findall(r"\(([^()]*)\)", text)

    for part in parenthetical_parts:
        normalized = re.sub(r"\s+", " ", part).strip()

        lower = normalized.lower()

        if lower in {"%", "yüzde", "oran"}:
            return "%"

        if "milyon" in lower and "tl" in lower:
            return "milyon TL"

        if ("bin" in lower or "bin." in lower) and "tl" in lower:
            return "bin TL"

        if lower == "tl" or "türk lirası" in lower or "turk lirasi" in lower:
            return "TL"

        if "adet" in lower:
            return "adet"

    # Some category names may contain unit-like text outside parentheses.
    lower_text = text.lower()

    if "milyon tl" in lower_text:
        return "milyon TL"

    if "bin tl" in lower_text:
        return "bin TL"

    return None
