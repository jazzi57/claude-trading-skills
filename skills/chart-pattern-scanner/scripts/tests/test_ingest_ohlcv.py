"""Offline tests for the OHLCV ingester (pure parsing logic)."""

import pytest
from ingest_ohlcv import (
    build_series,
    detect_columns,
    normalize_header,
    parse_date,
    parse_rows,
)


def test_normalize_header_aliases():
    assert normalize_header("Open") == "open"
    assert normalize_header(" CLOSE ") == "close"
    assert normalize_header("Ticker") == "symbol"
    assert normalize_header("Vol") == "volume"
    assert normalize_header("nonsense") is None


def test_detect_columns():
    cols = detect_columns(["Date", "Open", "High", "Low", "Close", "Volume", "Symbol"])
    assert cols == {"date": 0, "open": 1, "high": 2, "low": 3, "close": 4, "volume": 5, "symbol": 6}


@pytest.mark.parametrize(
    "raw,iso",
    [
        ("2026-06-19", "2026-06-19"),
        ("19/06/2026", "2026-06-19"),
        ("06/19/2026", "2026-06-19"),  # falls through to US format
        ("19-06-2026", "2026-06-19"),
        ("2026-06-19T15:00:00", "2026-06-19"),
    ],
)
def test_parse_date_formats(raw, iso):
    assert parse_date(raw) == iso


def test_parse_date_bad():
    with pytest.raises(ValueError):
        parse_date("not-a-date")


def test_parse_rows_single_symbol_from_default():
    headers = ["Date", "Open", "High", "Low", "Close", "Volume"]
    rows = [["19/06/2026", "13.04", "13.06", "12.78", "12.96", "4484"]]
    recs = parse_rows(headers, rows, default_symbol="EMAAR")
    assert recs == [
        (
            "EMAAR",
            {
                "date": "2026-06-19",
                "open": 13.04,
                "high": 13.06,
                "low": 12.78,
                "close": 12.96,
                "volume": 4484.0,
            },
        )
    ]


def test_parse_rows_multi_symbol_column():
    headers = ["Symbol", "Date", "Open", "High", "Low", "Close"]
    rows = [
        ["emaar", "2026-06-18", "12.84", "13.10", "12.74", "13.02"],
        ["SALIK", "2026-06-18", "5.95", "6.10", "5.94", "6.10"],
    ]
    recs = parse_rows(headers, rows)
    assert {r[0] for r in recs} == {"EMAAR", "SALIK"}


def test_parse_rows_missing_columns():
    with pytest.raises(ValueError, match="missing required columns"):
        parse_rows(["Date", "Open", "Close"], [["2026-06-19", "1", "2"]], default_symbol="X")


def test_parse_rows_skips_blank_and_nonpositive_close():
    headers = ["Date", "Open", "High", "Low", "Close"]
    rows = [
        ["", "", "", "", ""],  # blank
        ["2026-06-19", "1", "1", "1", "0"],  # close=0 dropped
        ["2026-06-19", "1", "2", "0.5", "1.5"],  # ok
    ]
    recs = parse_rows(headers, rows, default_symbol="X")
    assert len(recs) == 1
    assert recs[0][1]["close"] == 1.5


def test_normalize_header_bulletin_aliases():
    # DFM bulletin export column names
    assert normalize_header("report_date") == "date"
    assert normalize_header("current_close") == "close"
    assert normalize_header("last_price") == "close"
    assert normalize_header("trade_volume") == "volume"
    # 52-week high/low must NOT be mistaken for the daily high/low
    assert normalize_header("52week_high") is None
    assert normalize_header("52week_low") is None


def test_detect_columns_prefers_earlier_alias_for_duplicates():
    # bulletin carries both current_close and last_price (both -> close);
    # the more-preferred alias (current_close, the daily settlement) wins.
    headers = ["report_date", "open", "high", "low", "current_close", "last_price", "trade_volume"]
    cols = detect_columns(headers)
    assert cols["close"] == 4  # current_close, not last_price
    assert cols["date"] == 0
    assert cols["volume"] == 6


def test_detect_columns_alias_rank_beats_physical_position():
    # Even when last_price physically precedes current_close, the preferred
    # alias (current_close) still wins — selection is by alias rank, not order.
    headers = ["date", "open", "high", "low", "last_price", "current_close", "volume"]
    assert detect_columns(headers)["close"] == 5  # current_close at index 5
    # bare 'c' is a real close alias and must beat a last-traded-price column
    headers2 = ["date", "o", "h", "l", "c", "ltp", "volume"]
    assert detect_columns(headers2)["close"] == 4  # 'c', not 'ltp'


def test_parse_rows_coerces_nonstring_cells():
    # pre-typed rows (numeric/None) must parse like stringified reader output
    headers = ["Symbol", "Date", "Open", "High", "Low", "Close", "Volume"]
    rows = [["EMAAR", "2026-06-19", 13.04, 13.06, 12.78, 12.96, 4484]]
    recs = parse_rows(headers, rows)
    assert recs[0][1]["volume"] == 4484.0
    assert recs[0][1]["close"] == 12.96


def test_parse_rows_bulletin_shape():
    headers = ["symbol", "report_date", "open", "high", "low", "current_close", "trade_volume"]
    rows = [["EMAAR", "2026-06-26 00:00:00", "12.84", "13.10", "12.74", "13.02", "1500000"]]
    recs = parse_rows(headers, rows)
    assert recs == [
        (
            "EMAAR",
            {
                "date": "2026-06-26",
                "open": 12.84,
                "high": 13.10,
                "low": 12.74,
                "close": 13.02,
                "volume": 1500000.0,
            },
        )
    ]


def test_parse_rows_skips_untraded_zero_ohl():
    # bulletin untraded days carry O=H=L=0 (and sometimes a carried close) — drop them
    headers = ["Date", "Open", "High", "Low", "Close"]
    rows = [
        ["2026-06-19", "0", "0", "0", "12.5"],  # untraded: O=H=L=0, carried close
        ["2026-06-20", "0", "0", "0", "0"],  # fully empty
        ["2026-06-21", "1", "2", "0.5", "1.5"],  # ok
    ]
    recs = parse_rows(headers, rows, default_symbol="X")
    assert len(recs) == 1
    assert recs[0][1]["date"] == "2026-06-21"


def test_build_series_sorts_and_dedupes():
    recs = [
        ("EMAAR", {"date": "2026-06-19", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 0}),
        ("EMAAR", {"date": "2026-06-17", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 0}),
        (
            "EMAAR",
            {"date": "2026-06-19", "open": 9, "high": 9, "low": 9, "close": 9, "volume": 0},
        ),  # dup date
    ]
    s = build_series(recs)
    assert [b["date"] for b in s["EMAAR"]] == ["2026-06-17", "2026-06-19"]
    assert s["EMAAR"][1]["close"] == 1  # first occurrence kept
