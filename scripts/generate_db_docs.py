"""Veritabanı tanımlarını koddan otomatik Markdown'a döker.

Kaynaklar:
  - backend/app/models/lakehouse_models.py  (SQLAlchemy metadata: Gold + katalog)
  - backend/app/models/silver_canonical.py  (Pydantic: Canonical Silver şeması)

Çalıştırma (repo kökünden):
    PYTHONPATH=backend python scripts/generate_db_docs.py
Çıktı: docs/database_schema.md
"""
from __future__ import annotations

import sys
import types
import typing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pydantic.fields import FieldInfo  # noqa: E402

from backend.app.models import silver_canonical  # noqa: E402
from backend.app.models.lakehouse_models import lakehouse_metadata  # noqa: E402

OUTPUT = ROOT / "docs" / "database_schema.md"


def _cell(value: object) -> str:
    """Markdown tablo hücresi için güvenli metin."""
    return str(value).replace("|", "\\|").replace("\n", " ")


def _type_name(annotation: object) -> str:
    if isinstance(annotation, types.UnionType) or typing.get_origin(annotation) is typing.Union:
        return " \\| ".join(_type_name(a) for a in typing.get_args(annotation))
    origin = typing.get_origin(annotation)
    if origin is not None:
        args = ", ".join(_type_name(a) for a in typing.get_args(annotation))
        return f"{getattr(origin, '__name__', str(origin))}[{args}]"
    if annotation is type(None):
        return "None"
    return getattr(annotation, "__name__", str(annotation))


def _default(field: FieldInfo) -> str:
    if field.is_required():
        return "—"
    if field.default_factory is not None:
        return f"`{field.default_factory.__name__}()`"
    return f"`{field.default!r}`"


def _lakehouse_section(lines: list[str]) -> None:
    lines.append("## Lakehouse Tabloları (Gold ve Katalog)\n")
    for table in lakehouse_metadata.sorted_tables:
        lines.append(f"\n### `{table.name}`\n")
        if table.comment:
            lines.append(f"{table.comment}\n")
        lines.append("\n| Kolon | Tip | Açıklama |\n|---|---|---|")
        for col in table.columns:
            pk = " 🔑" if col.primary_key else ""
            lines.append(f"| `{col.name}`{pk} | {col.type} | {_cell(col.comment or '')} |")


def _model_table(model: type, lines: list[str]) -> None:
    lines.append(f"\n### `{model.__name__}`\n")
    if model.__doc__:
        lines.append(f"{model.__doc__.strip()}\n")
    lines.append("\n| Alan | Tip | Zorunlu | Varsayılan |\n|---|---|---|---|")
    for name, field in model.model_fields.items():
        required = "evet" if field.is_required() else "hayır"
        lines.append(f"| `{name}` | `{_type_name(field.annotation)}` | {required} | {_default(field)} |")


def _canonical_section(lines: list[str]) -> None:
    lines.append("\n## Canonical Silver Şeması\n")
    lines.append(
        "Kaynaktan bağımsız ortak sözleşme (`backend/app/models/silver_canonical.py`). "
        "Doğrulama kuralları Pydantic validator'larıyla uygulanır.\n"
    )
    _model_table(silver_canonical.CanonicalObservation, lines)
    _model_table(silver_canonical.CanonicalSeriesMetadata, lines)

    lines.append("\n### İzin Verilen Değerler\n")
    lines.append("| Sabit | Değerler |\n|---|---|")
    for const in ("VALID_FREQS", "VALID_ACCUMULATIONS", "VALID_NATURES", "VALID_ALIGNMENT_OVERRIDES"):
        values = ", ".join(f"`{v}`" for v in sorted(getattr(silver_canonical, const)))
        lines.append(f"| `{const}` | {values} |")


def main() -> None:
    lines = [
        "# Veritabanı Tanımları\n",
        "> Bu dosya `scripts/generate_db_docs.py` ile koddan otomatik üretilir.",
        "> Elle düzenlemeyin; şema değişince script'i tekrar çalıştırın.\n",
    ]
    _lakehouse_section(lines)
    _canonical_section(lines)
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Yazıldı: {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
