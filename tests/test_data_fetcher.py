"""Unit test untuk data fetcher (Network-Free dengan Mock Session)."""

import json
import os
from unittest.mock import MagicMock
import pytest
import requests

from spot_prompt.data_fetcher import (
    DataFetchError,
    fetch_binance_klines,
    fetch_btc_performance,
    fetch_fear_and_greed,
    fetch_relative_performance_vs_btc,
)

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.fixture
def mock_session():
    with open(os.path.join(FIXTURES_DIR, "mock_klines_daily.json")) as f:
        daily_json = json.load(f)
    with open(os.path.join(FIXTURES_DIR, "mock_fng.json")) as f:
        fng_json = json.load(f)

    session = MagicMock(spec=requests.Session)

    def fake_get(url, params=None, timeout=None):
        mock_resp = MagicMock(spec=requests.Response)
        mock_resp.status_code = 200

        if "klines" in url:
            symbol = (params or {}).get("symbol", "")
            if symbol == "INVALIDUSDT":
                mock_resp.status_code = 400
                mock_resp.raise_for_status.side_effect = requests.HTTPError("Bad Request")
                return mock_resp
            mock_resp.json.return_value = daily_json
            mock_resp.raise_for_status.return_value = None
            return mock_resp

        if "fng" in url:
            mock_resp.json.return_value = fng_json
            mock_resp.raise_for_status.return_value = None
            return mock_resp

        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {}
        return mock_resp

    session.get.side_effect = fake_get
    return session


def test_fetch_binance_klines_success(mock_session):
    df = fetch_binance_klines("SOLUSDT", interval="1d", session=mock_session)
    assert len(df) == 300
    assert "close" in df.columns
    assert "volume" in df.columns


def test_fetch_binance_klines_invalid_symbol(mock_session):
    with pytest.raises(DataFetchError):
        fetch_binance_klines("INVALIDUSDT", interval="1d", session=mock_session)


def test_fetch_fear_and_greed(mock_session):
    score, label = fetch_fear_and_greed(session=mock_session)
    assert score == 35
    assert label == "Fear"


def test_fetch_btc_performance(mock_session):
    perf_30d, perf_90d = fetch_btc_performance(session=mock_session)
    assert perf_30d is not None
    assert perf_90d is not None


def test_fetch_relative_performance_vs_btc(mock_session):
    df = fetch_binance_klines("SOLUSDT", interval="1d", session=mock_session)
    rel_perf = fetch_relative_performance_vs_btc("SOLUSDT", df, session=mock_session)
    assert rel_perf is not None
