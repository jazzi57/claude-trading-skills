"""Offline tests for the DFM official-data fetcher (pure logic only)."""

import datetime as dt

import pytest
from fetch_dfm_official import (
    add_day_to_series,
    build_form_body,
    iter_trading_days,
    parse_day_response,
    write_csvs,
)

SAMPLE = {
    "total_securities": 2,
    "sectors": [
        {
            "name": "Financials",
            "securities": [
                {
                    "symbol": "EMAAR",
                    "open": 13.04,
                    "high": 13.06,
                    "low": 12.78,
                    "close": 12.96,
                    "trade_count": 4484,
                },
                {
                    "symbol": "SALIK",
                    "open": 6.13,
                    "high": 6.14,
                    "low": 5.96,
                    "close": 5.96,
                    "trade_count": 1200,
                },
            ],
        },
        {
            "name": "Empty",
            "securities": [],
        },
        {
            "name": "Bad rows",
            "securities": [
                {"symbol": "SUSP", "open": None, "high": 1, "low": 1, "close": 1},  # bad open
                {
                    "symbol": "ZERO",
                    "open": 1,
                    "high": 1,
                    "low": 1,
                    "close": 0,
                },  # non-positive close
            ],
        },
    ],
}


# --------------------------------------------------------------------------- #
# iter_trading_days
# --------------------------------------------------------------------------- #
def test_iter_trading_days_excludes_weekend():
    # 2026-06-15 is a Monday; 2026-06-21 is a Sunday
    days = iter_trading_days(dt.date(2026, 6, 15), dt.date(2026, 6, 21))
    assert days == [
        dt.date(2026, 6, 15),
        dt.date(2026, 6, 16),
        dt.date(2026, 6, 17),
        dt.date(2026, 6, 18),
        dt.date(2026, 6, 19),
    ]  # Sat 20 + Sun 21 excluded


def test_iter_trading_days_single_day():
    assert iter_trading_days(dt.date(2026, 6, 17), dt.date(2026, 6, 17)) == [dt.date(2026, 6, 17)]


def test_iter_trading_days_bad_range():
    with pytest.raises(ValueError):
        iter_trading_days(dt.date(2026, 6, 19), dt.date(2026, 6, 1))


# --------------------------------------------------------------------------- #
# parse_day_response
# --------------------------------------------------------------------------- #
def test_parse_day_response_flattens_and_filters():
    rows = parse_day_response(SAMPLE)
    syms = [r["symbol"] for r in rows]
    assert syms == ["EMAAR", "SALIK"]  # bad/zero rows dropped
    assert rows[0]["open"] == 13.04 and rows[0]["close"] == 12.96
    assert rows[1]["trade_count"] == 1200


def test_parse_day_response_empty():
    assert parse_day_response({}) == []
    assert parse_day_response({"sectors": []}) == []


# --------------------------------------------------------------------------- #
# add_day_to_series
# --------------------------------------------------------------------------- #
def test_add_day_to_series_accumulates():
    series = {}
    rows = parse_day_response(SAMPLE)
    add_day_to_series(series, dt.date(2026, 6, 19), rows)
    add_day_to_series(series, dt.date(2026, 6, 18), rows)
    assert set(series) == {"EMAAR", "SALIK"}
    assert len(series["EMAAR"]) == 2
    assert series["EMAAR"][0]["date"] == "2026-06-19"
    assert series["EMAAR"][0]["volume"] == 4484


# --------------------------------------------------------------------------- #
# build_form_body
# --------------------------------------------------------------------------- #
def test_build_form_body_date_format():
    body = build_form_body(dt.date(2026, 6, 19)).decode()
    assert "Command=SearchCompanyPrices" in body
    assert "FromDate=19%2F06%2F2026" in body  # DD/MM/YYYY url-encoded
    assert "ToDate=19%2F06%2F2026" in body


# --------------------------------------------------------------------------- #
# write_csvs
# --------------------------------------------------------------------------- #
def test_write_csvs_roundtrip(tmp_path):
    series = {}
    add_day_to_series(series, dt.date(2026, 6, 18), parse_day_response(SAMPLE))
    add_day_to_series(series, dt.date(2026, 6, 19), parse_day_response(SAMPLE))
    paths = write_csvs(series, str(tmp_path))
    assert len(paths) == 2
    content = (tmp_path / "EMAAR.csv").read_text().strip().splitlines()
    assert content[0] == "Date,Open,High,Low,Close,Volume"
    assert len(content) == 3  # header + 2 days


def test_write_csvs_symbol_filter(tmp_path):
    series = {}
    add_day_to_series(series, dt.date(2026, 6, 19), parse_day_response(SAMPLE))
    paths = write_csvs(series, str(tmp_path), symbols=["SALIK"])
    assert len(paths) == 1
    assert paths[0].endswith("SALIK.csv")
