"""Cevaptaki sayıların tool çıktılarına dayanıp dayanmadığını ölçer.

Yalnızca ölçer ve raporlar; cevabı ASLA değiştirmez veya reddetmez.

Not: inline_series.py'deki sütun seviyesi sezgiselden farklı bir amaç güder.
Orada veri analiz edileceği için tek bir doğru yorum seçilmek zorundadır; burada
ise yalnızca eşleşme aranır ve yanlış pozitifi azaltmak için tüm olası yorumlar
kabul edilir. İki modül bilerek birbirine bağlanmaz.
"""
from __future__ import annotations

import re
from bisect import bisect_left, bisect_right

# İlk kol yalnızca en az bir binlik grubu olan sayıları yakalar ("1.234", "1.234,56");
# aksi halde "1234" gibi düz tam sayılar "123" + "4" diye bölünürdü.
NUM_RE = re.compile(r"-?\d{1,3}(?:[.,]\d{3})+(?!\d)(?:[.,]\d+)?|-?\d+(?:[.,]\d+)?")

REL_TOLERANCE = 0.01
ABS_TOLERANCE = 0.01

_THOUSANDS_GROUPS = re.compile(r"^\d{1,3}(?:[.,]\d{3})+$")
_TABLE_ALIGNMENT_LINE = re.compile(r"^\s*\|?[\s:\-|]+\|?\s*$")
# Tarihler sayı sayılmaz: 2024-03-31, 2024-03, 31.03.2024, 31/03/2024
_DATE_RE = re.compile(r"\b\d{4}-\d{1,2}(?:-\d{1,2})?\b|\b\d{1,2}[./]\d{1,2}[./]\d{4}\b")


def _empty() -> dict:
    return {"checked": 0, "grounded": 0, "ungrounded": [], "ratio": 1.0, "sources": {"tool": 0, "document": 0}}


def _candidates(raw: str) -> list[float]:
    """Bir sayı dizgisinin olası yorumlarını döndürür.

    Türkçe/İngilizce format belirsizliği nedeniyle tek bir yorum yeterli
    değil: "1.234" Türkçe'de 1234, İngilizce'de 1.234 demektir. Her iki
    yorumu da üretip eşleşme ararız — amaç yanlış pozitifi azaltmak.
    """
    text = raw.strip().lstrip("-")
    if not text:
        return []
    values: list[float] = []

    def add(candidate: str) -> None:
        try:
            values.append(float(candidate))
        except ValueError:
            pass

    has_dot, has_comma = "." in text, "," in text
    if has_dot and has_comma:
        decimal_sep = "." if text.rfind(".") > text.rfind(",") else ","
        thousands_sep = "," if decimal_sep == "." else "."
        add(text.replace(thousands_sep, "").replace(decimal_sep, "."))
    elif has_comma:
        if text.count(",") == 1:
            add(text.replace(",", "."))  # ondalık: "42,1" -> 42.1
        if _THOUSANDS_GROUPS.match(text):
            add(text.replace(",", ""))  # binlik: "1,234" -> 1234
    elif has_dot:
        if text.count(".") == 1:
            add(text)  # ondalık: "1.234" -> 1.234
        if _THOUSANDS_GROUPS.match(text):
            add(text.replace(".", ""))  # binlik: "1.234" -> 1234
    else:
        add(text)
    return values


def _is_skipped_integer(raw: str) -> bool:
    """Yıllar (1900-2100) ve küçük tam sayılar (0-12: madde/ay/adım numarası) kontrol edilmez."""
    if not re.fullmatch(r"-?\d+", raw):
        return False
    n = abs(int(raw))
    return n <= 12 or 1900 <= n <= 2100


def _strip_layout(text: str) -> str:
    lines = [line for line in text.splitlines() if not _TABLE_ALIGNMENT_LINE.match(line)]
    return _DATE_RE.sub(" ", "\n".join(lines))


def _extract_answer_numbers(answer: str) -> list[str]:
    """Cevaptaki kontrol edilecek sayı dizgilerini (tekilleştirilmiş, sıralı) döndürür."""
    text = _strip_layout(answer)
    found: list[str] = []
    for match in NUM_RE.finditer(text):
        raw = match.group(0)
        before = text[match.start() - 1] if match.start() > 0 else ""
        after = text[match.end()] if match.end() < len(text) else ""
        # Tanımlayıcı/ürün adı içindeki rakamlar (Qwen3-27B, KTR100, TP.AB.B1) sayı değildir.
        if before.isalpha() or before == "_" or after.isalpha() or after == "_":
            continue
        # "10-20" gibi aralıklarda tire eksi işareti değildir.
        if raw.startswith("-") and before.isdigit():
            raw = raw[1:]
        if _is_skipped_integer(raw):
            continue
        if raw not in found:
            found.append(raw)
    return found


def _build_pool(tool_outputs: list[str]) -> list[float]:
    pool: set[float] = set()
    for output in tool_outputs:
        if not isinstance(output, str):
            continue
        for match in NUM_RE.finditer(output):
            pool.update(_candidates(match.group(0)))
    return sorted(pool)


def _matches(value: float, pool: list[float]) -> bool:
    """value, havuzdaki herhangi bir değere %1 göreli (mutlak min. 0.01) toleransla eşleşiyor mu."""
    window = max(ABS_TOLERANCE, REL_TOLERANCE * abs(value)) * 1.05
    lo = bisect_left(pool, value - window)
    hi = bisect_right(pool, value + window)
    return any(
        abs(value - candidate) <= max(ABS_TOLERANCE, REL_TOLERANCE * abs(candidate))
        for candidate in pool[lo:hi]
    )


def check_grounding(
    answer: str,
    tool_outputs: list[str],
    extra_sources: list[str] | None = None,
) -> dict:
    """Cevaptaki sayıları tool çıktılarındaki (ve varsa yüklenen belgedeki) sayılarla karşılaştırır.

    Bir sayı hem tool çıktısında hem belgede varsa "tool" sayılır.
    """
    try:
        if not isinstance(answer, str) or not isinstance(tool_outputs, list):
            return _empty()
        numbers = _extract_answer_numbers(answer)
        if not numbers:
            return _empty()
        tool_pool = _build_pool(tool_outputs)  # işaret duyarsız karşılaştırma için mutlak değer havuzu
        document_pool = _build_pool(extra_sources) if isinstance(extra_sources, list) else []
        ungrounded: list[str] = []
        from_tool = from_document = 0
        for raw in numbers:
            candidates = _candidates(raw)
            if any(_matches(candidate, tool_pool) for candidate in candidates):
                from_tool += 1
            elif any(_matches(candidate, document_pool) for candidate in candidates):
                from_document += 1
            else:
                ungrounded.append(raw)
        checked = len(numbers)
        grounded = from_tool + from_document
        return {
            "checked": checked,
            "grounded": grounded,
            "ungrounded": ungrounded,
            "ratio": grounded / checked if checked else 1.0,
            "sources": {"tool": from_tool, "document": from_document},
        }
    except Exception:
        return _empty()
