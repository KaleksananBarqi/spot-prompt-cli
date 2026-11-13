"""Factory dan helper mock session HTTP network-free untuk suite pengujian."""

import json
import os
from typing import List, Optional, Tuple
from unittest.mock import MagicMock
import requests

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_fixture_json(filename: str):
    """Memuat berkas JSON fixture statis dari direktori tests/fixtures."""
    with open(os.path.join(FIXTURES_DIR, filename), encoding="utf-8") as f:
        return json.load(f)


def make_blocked_binance_session(
    *,
    mexc_symbols: Tuple[str, ...] = ("HYPEUSDT", "BTCUSDT"),
    mexc_missing_status: int = 404,
    gateio_rows: Optional[list] = None,
    gateio_missing_status: int = 404,
    block_all_binance: bool = False,
    called_urls: Optional[List[str]] = None,
    use_weekly_fixture: bool = False,
) -> MagicMock:
    """Membuat mock requests.Session untuk skenario domain binance.com terblokir atau short-circuit."""
    daily_json = _load_fixture_json("mock_klines_daily.json")
    weekly_json = _load_fixture_json("mock_klines_weekly.json") if use_weekly_fixture else daily_json
    fng_json = _load_fixture_json("mock_fng.json")

    def fake_get(url, params=None, timeout=None):
        if called_urls is not None:
            called_urls.append(url)

        mock_resp = MagicMock(spec=requests.Response)
        symbol = (params or {}).get("symbol", "")
        interval = (params or {}).get("interval", "")

        if block_all_binance and "binance.com" in url:
            raise AssertionError("Domain binance.com seharusnya dilewati (short-circuit)!")

        if "api.binance.com" in url:
            mock_resp.status_code = 403
            return mock_resp

        if "fapi.binance.com" in url:
            raise AssertionError("Binance Futures seharusnya dilewati (short-circuit)!")

        if "api.mexc.com" in url:
            if symbol in mexc_symbols:
                mock_resp.status_code = 200
                mock_resp.json.return_value = weekly_json if interval.lower() == "1w" else daily_json
                mock_resp.raise_for_status.return_value = None
                return mock_resp
            mock_resp.status_code = mexc_missing_status
            return mock_resp

        if "gateio.ws" in url or "api.gateio.ws" in url:
            if gateio_rows is not None:
                mock_resp.status_code = 200
                mock_resp.json.return_value = gateio_rows
                mock_resp.raise_for_status.return_value = None
                return mock_resp
            mock_resp.status_code = gateio_missing_status
            return mock_resp

        if "fng" in url:
            mock_resp.status_code = 200
            mock_resp.json.return_value = fng_json
            mock_resp.raise_for_status.return_value = None
            return mock_resp

        mock_resp.status_code = 404
        return mock_resp

    mock_sess = MagicMock(spec=requests.Session)
    mock_sess.get.side_effect = fake_get
    return mock_sess
