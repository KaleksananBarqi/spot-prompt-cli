"""Unit test untuk data fetcher (Network-Free dengan Mock Session)."""

import json
import os
from unittest.mock import MagicMock
import pytest
import requests

from spot_prompt.data_fetcher import (
    DataFetchError,
    ProviderConnectionError,
    SymbolNotFoundError,
    fetch_binance_futures_klines,
    fetch_binance_klines,
    fetch_binance_spot_klines,
    fetch_btc_performance,
    fetch_fear_and_greed,
    fetch_gateio_klines,
    fetch_market_klines_with_fallback,
    fetch_mexc_klines,
    fetch_relative_performance_vs_btc,
)

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.fixture
def mock_session():
    with open(os.path.join(FIXTURES_DIR, "mock_klines_daily.json")) as f:
        daily_json = json.load(f)
    with open(os.path.join(FIXTURES_DIR, "mock_fng.json")) as f:
        fng_json = json.load(f)

    # Gate.io mock rows: [sec, quote_volume, close, high, low, open, base_volume, ...]
    gateio_json = [
        ["1700000000", "50000", "100.5", "102.0", "99.0", "100.0", "500.0", "true"],
        ["1700086400", "60000", "101.5", "103.0", "100.0", "100.5", "600.0", "true"],
    ]

    session = MagicMock(spec=requests.Session)

    def fake_get(url, params=None, timeout=None):
        mock_resp = MagicMock(spec=requests.Response)
        mock_resp.status_code = 200

        # Handle gate.io candlesticks
        if "candlesticks" in url:
            pair = (params or {}).get("currency_pair", "")
            if "INVALID" in pair:
                mock_resp.status_code = 400
                mock_resp.json.return_value = {"label": "INVALID_CURRENCY_PAIR"}
                return mock_resp
            mock_resp.json.return_value = gateio_json
            mock_resp.raise_for_status.return_value = None
            return mock_resp

        # Handle Binance Spot / Futures / MEXC klines
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
    with pytest.raises(SymbolNotFoundError):
        fetch_binance_klines("INVALIDUSDT", interval="1d", session=mock_session)


def test_fetch_mexc_klines_success(mock_session):
    df = fetch_mexc_klines("FARTCOINUSDT", interval="1w", session=mock_session)
    assert len(df) == 300
    assert "close" in df.columns


def test_fetch_binance_futures_klines_success(mock_session):
    df = fetch_binance_futures_klines("FARTCOINUSDT", interval="1d", session=mock_session)
    assert len(df) == 300
    assert "close" in df.columns


def test_fetch_gateio_klines_success(mock_session):
    df = fetch_gateio_klines("SOLUSDT", interval="1d", session=mock_session)
    assert len(df) == 2
    assert "close" in df.columns
    assert "volume" in df.columns


def test_fetch_gateio_klines_invalid(mock_session):
    with pytest.raises(SymbolNotFoundError):
        fetch_gateio_klines("INVALIDUSDT", interval="1d", session=mock_session)


def test_fetch_market_klines_fallback_to_mexc(mock_session):
    """Skenario koin seperti FARTCOIN: tidak ada di Binance Spot, ada di MEXC Spot."""
    def fake_get_fallback(url, params=None, timeout=None):
        mock_resp = MagicMock(spec=requests.Response)
        symbol = (params or {}).get("symbol", "")

        # Binance Spot gagal
        if "api.binance.com" in url:
            mock_resp.status_code = 400
            return mock_resp

        # MEXC Spot sukses
        if "api.mexc.com" in url:
            with open(os.path.join(FIXTURES_DIR, "mock_klines_daily.json")) as f:
                daily_json = json.load(f)
            mock_resp.status_code = 200
            mock_resp.json.return_value = daily_json
            mock_resp.raise_for_status.return_value = None
            return mock_resp

        mock_resp.status_code = 400
        return mock_resp

    mock_sess = MagicMock(spec=requests.Session)
    mock_sess.get.side_effect = fake_get_fallback

    fallbacks = []
    df_d, df_w, prov = fetch_market_klines_with_fallback(
        "FARTCOINUSDT",
        session=mock_sess,
        on_fallback=lambda prev, nxt: fallbacks.append((prev, nxt)),
    )

    assert prov == "MEXC Spot"
    assert len(df_d) == 300
    assert len(df_w) == 300
    assert ("Binance Spot", "MEXC Spot") in fallbacks


def test_fetch_market_klines_fallback_all_fail():
    """Skenario semua provider gagal."""
    mock_sess = MagicMock(spec=requests.Session)
    mock_resp = MagicMock(spec=requests.Response)
    mock_resp.status_code = 400
    mock_sess.get.return_value = mock_resp

    with pytest.raises(DataFetchError) as exc_info:
        fetch_market_klines_with_fallback("UNKNOWNCOIN", session=mock_sess)

    assert "tidak ditemukan di seluruh bursa yang didukung" in str(exc_info.value)


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


def test_provider_connection_error_subclass():
    assert issubclass(ProviderConnectionError, DataFetchError)
    assert not issubclass(ProviderConnectionError, SymbolNotFoundError)


@pytest.mark.parametrize(
    "fetch_fn",
    [
        fetch_binance_spot_klines,
        fetch_mexc_klines,
        fetch_binance_futures_klines,
        fetch_gateio_klines,
    ],
)
@pytest.mark.parametrize("status_code", [403, 451, 500, 502, 503, 504])
def test_provider_connection_error_on_blocked_or_server_error(fetch_fn, status_code):
    mock_sess = MagicMock(spec=requests.Session)
    mock_resp = MagicMock(spec=requests.Response)
    mock_resp.status_code = status_code
    mock_sess.get.return_value = mock_resp

    with pytest.raises(ProviderConnectionError):
        fetch_fn("SOLUSDT", interval="1d", session=mock_sess)


@pytest.mark.parametrize(
    "fetch_fn",
    [
        fetch_binance_spot_klines,
        fetch_mexc_klines,
        fetch_binance_futures_klines,
        fetch_gateio_klines,
    ],
)
@pytest.mark.parametrize(
    "network_exception",
    [
        requests.exceptions.ConnectionError("Connection refused"),
        requests.exceptions.ConnectTimeout("Connection timed out"),
        requests.exceptions.ReadTimeout("Read timed out"),
        requests.exceptions.Timeout("Request timed out"),
    ],
)
def test_provider_connection_error_on_transport_exceptions(fetch_fn, network_exception):
    mock_sess = MagicMock(spec=requests.Session)
    mock_sess.get.side_effect = network_exception

    with pytest.raises(ProviderConnectionError):
        fetch_fn("SOLUSDT", interval="1d", session=mock_sess)


@pytest.mark.parametrize(
    "fetch_fn",
    [
        fetch_binance_spot_klines,
        fetch_mexc_klines,
        fetch_binance_futures_klines,
        fetch_gateio_klines,
    ],
)
@pytest.mark.parametrize("status_code", [400, 404])
def test_symbol_not_found_on_400_and_404(fetch_fn, status_code):
    mock_sess = MagicMock(spec=requests.Session)
    mock_resp = MagicMock(spec=requests.Response)
    mock_resp.status_code = status_code
    mock_sess.get.return_value = mock_resp

    with pytest.raises(SymbolNotFoundError):
        fetch_fn("NONEXISTENTUSDT", interval="1d", session=mock_sess)


def test_fallback_chain_short_circuits_binance_futures_on_connection_error():
    """Jika Binance Spot gagal karena ProviderConnectionError (misal 403/451/timeout),
    domain binance.com dicatat sebagai unreachable dan Binance Futures (Tier 3)
    dilewati (short-circuited) langsung ke Gate.io Spot tanpa panggilan HTTP ke Futures."""
    called_urls = []
    with open(os.path.join(FIXTURES_DIR, "mock_klines_daily.json")) as f:
        daily_json = json.load(f)

    gateio_json = [
        ["1700000000", "50000", "100.5", "102.0", "99.0", "100.0", "500.0", "true"],
        ["1700086400", "60000", "101.5", "103.0", "100.0", "100.5", "600.0", "true"],
    ]

    def fake_get(url, params=None, timeout=None):
        called_urls.append(url)
        mock_resp = MagicMock(spec=requests.Response)

        # 1. Binance Futures tidak boleh dipanggil, tapi jika dipanggil mock response:
        if "fapi.binance.com" in url:
            mock_resp.status_code = 200
            mock_resp.json.return_value = daily_json
            mock_resp.raise_for_status.return_value = None
            return mock_resp

        # 2. Binance Spot diblokir / connection error (HTTP 403)
        if "api.binance.com" in url:
            mock_resp.status_code = 403
            return mock_resp

        # 4. Gate.io Spot sukses
        if "gateio.ws" in url or "api.gateio.ws" in url:
            mock_resp.status_code = 200
            mock_resp.json.return_value = gateio_json
            mock_resp.raise_for_status.return_value = None
            return mock_resp

        mock_resp.status_code = 404
        return mock_resp

    mock_sess = MagicMock(spec=requests.Session)
    mock_sess.get.side_effect = fake_get

    unreachable = set()
    transitions = []

    df_d, df_w, prov = fetch_market_klines_with_fallback(
        "NEWCOINUSDT",
        session=mock_sess,
        unreachable_domains=unreachable,
        on_fallback=lambda prev, nxt: transitions.append((prev, nxt)),
    )

    # 1. Gate.io Spot yang berhasil melayani data
    assert prov == "Gate.io Spot"
    assert len(df_d) == 2
    assert len(df_w) == 2

    # 2. Domain binance.com dicatat sebagai unreachable
    assert "binance.com" in unreachable

    # 3. Binance Futures (Tier 3) TIDAK PERNAH dipanggil (short-circuit)
    futures_calls = [u for u in called_urls if "fapi.binance.com" in u]
    assert len(futures_calls) == 0, f"Binance Futures seharusnya tidak dipanggil, tapi dipanggil: {futures_calls}"

    # 4. Callback fallback melompati Binance Futures: Binance Spot -> MEXC Spot, lalu MEXC Spot -> Gate.io Spot
    assert transitions == [
        ("Binance Spot", "MEXC Spot"),
        ("MEXC Spot", "Gate.io Spot"),
    ]


def test_fallback_chain_tries_binance_futures_on_symbol_not_found():
    """Jika Binance Spot gagal karena SymbolNotFoundError (bukan masalah koneksi),
    domain binance.com TIDAK dimasukkan ke unreachable domains, sehingga Binance Futures tetap dicoba."""
    called_urls = []
    with open(os.path.join(FIXTURES_DIR, "mock_klines_daily.json")) as f:
        daily_json = json.load(f)

    def fake_get(url, params=None, timeout=None):
        called_urls.append(url)
        mock_resp = MagicMock(spec=requests.Response)

        # 1. Binance Futures: koin ada di futures (HTTP 200)
        if "fapi.binance.com" in url:
            mock_resp.status_code = 200
            mock_resp.json.return_value = daily_json
            mock_resp.raise_for_status.return_value = None
            return mock_resp

        # 2. Binance Spot: simbol tidak ada (HTTP 400 SymbolNotFoundError)
        if "api.binance.com" in url:
            mock_resp.status_code = 400
            return mock_resp

        # 3. MEXC Spot: simbol tidak ada (HTTP 400 SymbolNotFoundError)
        if "api.mexc.com" in url:
            mock_resp.status_code = 400
            return mock_resp

        mock_resp.status_code = 404
        return mock_resp

    mock_sess = MagicMock(spec=requests.Session)
    mock_sess.get.side_effect = fake_get

    unreachable = set()
    transitions = []

    df_d, df_w, prov = fetch_market_klines_with_fallback(
        "PERPCOINUSDT",
        session=mock_sess,
        unreachable_domains=unreachable,
        on_fallback=lambda prev, nxt: transitions.append((prev, nxt)),
    )

    # 1. Binance Futures berhasil melayani data
    assert prov == "Binance Futures"
    assert len(df_d) == 300

    # 2. binance.com TIDAK dimasukkan ke unreachable
    assert "binance.com" not in unreachable

    # 3. Binance Futures terbukti dipanggil
    futures_calls = [u for u in called_urls if "fapi.binance.com" in u]
    assert len(futures_calls) > 0

    # 4. Transisi normal melalui MEXC Spot lalu ke Binance Futures
    assert transitions == [
        ("Binance Spot", "MEXC Spot"),
        ("MEXC Spot", "Binance Futures"),
    ]


def test_on_fallback_supports_three_arguments_with_reason():
    """on_fallback callback mendukung signature 3 argumen (prev, next, reason)."""
    def fake_get(url, params=None, timeout=None):
        mock_resp = MagicMock(spec=requests.Response)
        if "api.binance.com" in url:
            mock_resp.status_code = 403
            return mock_resp
        if "api.mexc.com" in url:
            with open(os.path.join(FIXTURES_DIR, "mock_klines_daily.json")) as f:
                daily_json = json.load(f)
            mock_resp.status_code = 200
            mock_resp.json.return_value = daily_json
            mock_resp.raise_for_status.return_value = None
            return mock_resp
        mock_resp.status_code = 404
        return mock_resp

    mock_sess = MagicMock(spec=requests.Session)
    mock_sess.get.side_effect = fake_get

    events = []

    def cb_with_reason(prev, nxt, reason):
        events.append((prev, nxt, reason))

    df_d, df_w, prov = fetch_market_klines_with_fallback(
        "SOLUSDT",
        session=mock_sess,
        on_fallback=cb_with_reason,
    )

    assert prov == "MEXC Spot"
    assert len(events) == 1
    prev, nxt, reason = events[0]
    assert prev == "Binance Spot"
    assert nxt == "MEXC Spot"
    assert isinstance(reason, ProviderConnectionError) or "403" in str(reason)


def test_fallback_chain_skips_preseeded_unreachable_domains():
    """Jika unreachable_domains sudah berisi binance.com sebelum pemanggilan,
    Binance Spot dan Binance Futures langsung dilewati tanpa panggilan HTTP."""
    called_urls = []
    with open(os.path.join(FIXTURES_DIR, "mock_klines_daily.json")) as f:
        daily_json = json.load(f)

    def fake_get(url, params=None, timeout=None):
        called_urls.append(url)
        mock_resp = MagicMock(spec=requests.Response)
        if "api.mexc.com" in url:
            mock_resp.status_code = 200
            mock_resp.json.return_value = daily_json
            mock_resp.raise_for_status.return_value = None
            return mock_resp
        mock_resp.status_code = 404
        return mock_resp

    mock_sess = MagicMock(spec=requests.Session)
    mock_sess.get.side_effect = fake_get

    unreachable = {"binance.com"}
    df_d, df_w, prov = fetch_market_klines_with_fallback(
        "SOLUSDT",
        session=mock_sess,
        unreachable_domains=unreachable,
    )

    assert prov == "MEXC Spot"
    assert len(df_d) == 300
    # Pastikan tidak ada satupun pemanggilan HTTP ke binance.com
    assert not any("binance.com" in u for u in called_urls)


def test_fallback_chain_short_circuit_on_transport_timeout():
    """Jika Binance Spot gagal karena requests.exceptions.Timeout,
    domain binance.com dicatat sebagai unreachable dan Binance Futures dilewati."""
    called_urls = []
    with open(os.path.join(FIXTURES_DIR, "mock_klines_daily.json")) as f:
        daily_json = json.load(f)

    def fake_get(url, params=None, timeout=None):
        called_urls.append(url)
        if "api.binance.com" in url:
            raise requests.exceptions.ConnectTimeout("WAF Dropped packet")
        if "api.mexc.com" in url:
            mock_resp = MagicMock(spec=requests.Response)
            mock_resp.status_code = 200
            mock_resp.json.return_value = daily_json
            mock_resp.raise_for_status.return_value = None
            return mock_resp
        raise requests.exceptions.ConnectionError("Unhandled")

    mock_sess = MagicMock(spec=requests.Session)
    mock_sess.get.side_effect = fake_get

    unreachable = set()
    df_d, df_w, prov = fetch_market_klines_with_fallback(
        "SOLUSDT",
        session=mock_sess,
        unreachable_domains=unreachable,
    )

    assert prov == "MEXC Spot"
    assert "binance.com" in unreachable
    assert not any("fapi.binance.com" in u for u in called_urls)



