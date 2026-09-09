from app.modules.bddk.finturk import (
    flatten_json,
)


def test_flatten_json_nested_object():
    data = {
        "ADANA": {
            "Toplam Nakdi Krediler": "65.046.605",
            "Nakdi Krediler": "61.583.376",
            "Takipteki Alacaklar": "3.463.229",
        }
    }

    rows = flatten_json(data)

    fields = {
        row["field"]: row
        for row in rows
    }

    assert (
        fields[
            "ADANA.Toplam Nakdi Krediler"
        ]["value_numeric"]
        == 65046605.0
    )

    assert (
        fields[
            "ADANA.Nakdi Krediler"
        ]["value_numeric"]
        == 61583376.0
    )

    assert (
        fields[
            "ADANA.Takipteki Alacaklar"
        ]["value_numeric"]
        == 3463229.0
    )


def test_flatten_json_list():
    data = {
        "iller": [
            {"ad": "ADANA"},
            {"ad": "ANKARA"},
        ]
    }

    rows = flatten_json(data)

    fields = [
        row["field"]
        for row in rows
    ]

    assert "iller[0].ad" in fields
    assert "iller[1].ad" in fields


def test_flatten_json_empty_dict():
    assert flatten_json({}) == []
