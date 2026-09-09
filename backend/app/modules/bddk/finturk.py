from .common import parse_tr_number


def flatten_json(obj, prefix=""):
    rows = []

    if isinstance(obj, dict):
        for key, value in obj.items():
            new_prefix = (
                f"{prefix}.{key}"
                if prefix
                else str(key)
            )

            rows.extend(
                flatten_json(
                    value,
                    new_prefix,
                )
            )

    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            new_prefix = (
                f"{prefix}[{index}]"
                if prefix
                else f"[{index}]"
            )

            rows.extend(
                flatten_json(
                    value,
                    new_prefix,
                )
            )

    else:
        rows.append(
            {
                "field": prefix,
                "value_raw": obj,
                "value_numeric": (
                    parse_tr_number(obj)
                    if isinstance(
                        obj,
                        (str, int, float),
                    )
                    else None
                ),
            }
        )

    return rows
