import pytest
from bs4 import BeautifulSoup

from app.modules.bddk.weekly import (
    find_token,
    parse_report_date,
    parse_table,
)


def test_find_token():
    soup = BeautifulSoup(
        """
        <input
            name="__RequestVerificationToken"
            value="abc123"
        />
        """,
        "html.parser",
    )

    assert find_token(soup) == "abc123"


def test_find_token_missing():
    soup = BeautifulSoup(
        "<html></html>",
        "html.parser",
    )

    with pytest.raises(RuntimeError):
        find_token(soup)


def test_parse_report_date():
    soup = BeautifulSoup(
        """
        <table id="TabloExcel">
          <tr>
            <th>
              Sektör / Krediler
              (8 Ocak 2021 Cuma)
              (Milyon TL)
            </th>
          </tr>
        </table>
        """,
        "html.parser",
    )

    table = soup.find("table")

    assert (
        parse_report_date(table)
        == "2021-01-08"
    )


def test_parse_table():
    soup = BeautifulSoup(
        """
        <table id="TabloExcel">
          <tr>
            <th>No</th>
            <th>Krediler (26 Haziran 2026 Cuma)</th>
            <th>TP</th>
            <th>YP</th>
            <th>Toplam</th>
          </tr>
          <tr>
            <td>1</td>
            <td>Toplam Krediler</td>
            <td>16.955.526,22</td>
            <td>9.581.766,01</td>
            <td>26.537.292,23</td>
          </tr>
        </table>
        """,
        "html.parser",
    )

    category = {
        "id": "289",
        "name": "Krediler",
    }

    period = {
        "year": 2026,
        "month": 6,
        "day": 26,
        "dropdown_date": "2026-06-26",
        "donem_id": "652",
        "period_text": "Haziran/26",
    }

    rows, report_date = parse_table(
        soup,
        category,
        period,
    )

    assert report_date == "2026-06-26"
    assert len(rows) == 3
    assert rows[0]["variable"] == "TP"
    assert rows[0]["value"] == 16955526.22
    assert rows[1]["value"] == 9581766.01
    assert rows[2]["value"] == 26537292.23
    assert rows[0]["date_mismatch"] is False
