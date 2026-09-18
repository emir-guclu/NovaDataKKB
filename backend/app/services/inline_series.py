"""Satır içi (inline) zaman serisi ayrıştırıcısı.

Lakehouse dışından gelen veriyi (yüklenen Excel/PDF, web URL ile okunan tablo)
analiz araçlarına `observations` parametresi olarak vermek için kullanılır.
"""
from __future__ import annotations

import calendar
import math
import re
from datetime import date, datetime

SUPPORTED_INLINE_METRICS = ("value", "mom_pct_change")
MIN_OBSERVATIONS = 3
MIN_PARSE_RATIO = 0.5
MAX_ROW_WARNINGS = 5
DOT_THOUSANDS_RATIO = 0.7

SERIES_ID_DESCRIPTION = "Lakehouse'taki seri ID'si. observations verilmişse boş bırakılır."
OBSERVATIONS_DESCRIPTION = (
    "Satır içi zaman serisi: [{'date': 'YYYY-MM-DD', 'value': 123.4}, ...]. "
    "Lakehouse dışı kaynaklardan (yüklenen Excel/PDF/görsel, web URL ile "
    "okunan sayfa) gelen veriyi analiz etmek için kullanılır. En az 3 "
    "gözlem gerekir. series_id ile birlikte KULLANILMAZ."
)
EXACTLY_ONE_SOURCE_ERROR = (
    "series_id veya observations parametrelerinden tam olarak biri "
    "verilmelidir. Lakehouse verisi için series_id, dışarıdan gelen "
    "veri için observations kullanın."
)
DIMENSION_IGNORED_WARNING = "Satır içi seride dimension kullanılmaz, yok sayıldı."

class SeriesLoadError(Exception):
    """Araç verisi yüklenemedi; mesaj olduğu gibi araç çıktısına `error` olarak yazılır."""

    def __init__(self, message: str, data_source: str | None = None) -> None:
        super().__init__(message)
        self.data_source = data_source


_DATE_KEYS = ("date", "tarih")
_VALUE_KEYS = ("value", "deger", "değer", "close", "kapanis", "kapanış")
_DATE_FORMATS = ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y")
_YEAR_MONTH = re.compile(r"^(\d{4})-(\d{1,2})$")


def _pick(row: dict, aliases: tuple[str, ...]):
    """Anahtar adını büyük/küçük harf duyarsız eşleyerek ilk bulunan değeri döndürür."""
    folded = {str(k).strip().casefold(): v for k, v in row.items()}
    for alias in aliases:
        if alias in folded:
            return folded[alias]
    return None


def _parse_date(raw) -> date | None:
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    if not isinstance(raw, str):
        return None
    text = raw.strip().split("T")[0].split(" ")[0]
    match = _YEAR_MONTH.match(text)
    if match:
        year, month = int(match.group(1)), int(match.group(2))
        if 1 <= month <= 12:
            # Lakehouse aylık serileri dönem sonu tarihiyle tutar; aynısını kullan.
            return date(year, month, calendar.monthrange(year, month)[1])
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _clean_numeric_text(raw: str) -> str:
    return re.sub(r"[\s\u00a0%]", "", raw)


def _detect_dot_role(raw_values: list[str]) -> str:
    """Tek noktalı sayılarda noktanın rolünü sütun geneline bakarak belirler.

    Döndürür: "thousands" | "decimal"
    """
    candidates = []
    for raw in raw_values:
        text = _clean_numeric_text(raw)
        if text.count(".") == 1 and "," not in text:
            candidates.append(text.split(".")[1])
    if not candidates:
        return "decimal"
    three_digit = sum(1 for tail in candidates if len(tail) == 3 and tail.isdigit())
    return "thousands" if three_digit / len(candidates) >= DOT_THOUSANDS_RATIO else "decimal"


def _parse_value(raw, dot_role: str = "decimal") -> float | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        number = float(raw)
    elif isinstance(raw, str):
        text = re.sub(r"[\s %]", "", raw)
        if not text:
            return None
        if "," in text:
            # Türkçe format: "1.234,56" -> 1234.56
            text = text.replace(".", "").replace(",", ".")
        elif text.count(".") > 1:
            # "1.234.567" -> binlik ayraç. Tek nokta ondalık kabul edilir.
            text = text.replace(".", "")
        elif dot_role == "thousands" and text.count(".") == 1:
            # Sütun genelinde binlik ayraç algılandı; yalnızca tam 3 haneli kuyruk binlik olabilir.
            tail = text.split(".")[1]
            if len(tail) == 3 and tail.isdigit():
                text = text.replace(".", "")
        try:
            number = float(text)
        except ValueError:
            return None
    else:
        return None
    return number if math.isfinite(number) else None


def parse_inline_observations(
    observations: list[dict],
    metric: str = "value",
    start_date: str | None = None,
    end_date: str | None = None,
) -> tuple[list[tuple[str, float]], list[str]]:
    """Satır içi gözlemleri (date, value) çiftlerine çevirir.

    Döndürür: (veri, uyarılar)
    Hata durumunda ValueError fırlatır — mesaj LLM'e geri beslenecek,
    bu yüzden düzeltici ve açık olmalı.
    """
    if metric not in SUPPORTED_INLINE_METRICS:
        raise ValueError("Satır içi seride yalnızca 'value' ve 'mom_pct_change' metrikleri desteklenir.")
    if not observations:
        raise ValueError(f"Satır içi seri için en az {MIN_OBSERVATIONS} gözlem gerekir; liste boş.")

    warnings: list[str] = []
    raw_strings = [
        raw for row in observations
        if isinstance(row, dict) and isinstance(raw := _pick(row, _VALUE_KEYS), str)
    ]
    dot_role = _detect_dot_role(raw_strings)
    if dot_role == "thousands":
        warnings.append(
            "Sütun formatı algılandı: tek nokta binlik ayraç olarak yorumlandı (örn. 1.234 → 1234)."
        )
    skipped = 0
    parsed: dict[date, float] = {}
    duplicates = 0

    for index, row in enumerate(observations, start=1):
        reason = None
        row_date = row_value = None
        if not isinstance(row, dict):
            reason = "öğe bir nesne ({'date':..., 'value':...}) değil"
        else:
            row_date = _parse_date(_pick(row, _DATE_KEYS))
            row_value = _parse_value(_pick(row, _VALUE_KEYS), dot_role)
            if row_date is None:
                reason = "tarih ayrıştırılamadı (YYYY-MM-DD, YYYY-MM, DD.MM.YYYY, DD/MM/YYYY beklenir)"
            elif row_value is None:
                reason = "değer sayıya çevrilemedi"
        if reason:
            skipped += 1
            if skipped <= MAX_ROW_WARNINGS:
                warnings.append(f"Satır {index} atlandı: {reason}.")
            continue
        if row_date in parsed:
            duplicates += 1
        parsed[row_date] = row_value  # aynı tarihte sonuncusu kazanır

    if skipped > MAX_ROW_WARNINGS:
        warnings.append(f"... ve {skipped - MAX_ROW_WARNINGS} satır daha atlandı (toplam {skipped}).")
    if duplicates:
        warnings.append(f"{duplicates} tekrarlanan tarih bulundu; her tarih için son gözlem kullanıldı.")

    ratio = len(parsed) / len(observations)
    if ratio < MIN_PARSE_RATIO:
        raise ValueError(
            f"Verilen satırların yalnızca %{round(ratio * 100)}'i ayrıştırılabildi. "
            "'date' ve 'value' alanlarını kontrol edin."
        )
    if len(parsed) < MIN_OBSERVATIONS:
        raise ValueError(
            f"Satır içi seri için en az {MIN_OBSERVATIONS} geçerli gözlem gerekir "
            f"(ayrıştırılabilen: {len(parsed)})."
        )

    series = sorted(parsed.items())

    if start_date or end_date:
        lower = _parse_date(start_date) if start_date else None
        upper = _parse_date(end_date) if end_date else None
        if (start_date and lower is None) or (end_date and upper is None):
            raise ValueError("start_date ve end_date YYYY-MM-DD biçiminde olmalıdır.")
        series = [
            (d, v) for d, v in series
            if (lower is None or d >= lower) and (upper is None or d <= upper)
        ]
        if len(series) < MIN_OBSERVATIONS:
            raise ValueError(
                f"Belirtilen tarih aralığında yalnızca {len(series)} gözlem var; "
                f"en az {MIN_OBSERVATIONS} gerekir."
            )

    if metric == "mom_pct_change":
        changes: list[tuple[date, float]] = []
        zero_base = 0
        for (_, previous), (current_date, current) in zip(series, series[1:]):
            if previous == 0:
                zero_base += 1
                continue
            changes.append((current_date, (current - previous) / previous * 100))
        if zero_base:
            warnings.append(f"{zero_base} gözlemde önceki değer 0 olduğu için değişim hesaplanamadı.")
        warnings.append(
            "mom_pct_change ardışık gözlemler arasındaki yüzde değişimdir; "
            "gözlemler aylık değilse dönemsel değişim olarak yorumlayın."
        )
        series = changes

    return [(d.isoformat(), v) for d, v in series], warnings
