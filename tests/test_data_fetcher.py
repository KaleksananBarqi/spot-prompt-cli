"""Unit test untuk data fetcher (Network-Free dengan Mock Session)."""

import json
import os
from unittest.mock import MagicMock
import pytest
import requests

from spot_prompt.data_fetcher import (
    FALLBACK_REASON_BLOCKED,
    FALLBACK_REASON_NOT_FOUND,
    FALLBACK_REASON_SHORT_CIRCUIT,
    DataFetchError,
    ProviderConnectionError,
    SymbolNotFoundError,
    _find_next_reachable_provider,
    fetch_binance_futures_klines,
    fetch_binance_klines,
    fetch_binance_spot_klines,
    fetch_btc_performance,
    fetch_fear_and_greed,
    fetch_gateio_klines,
    fetch_market_klines_with_fallback,
    fetch_mexc_klines,
    fetch_relative_performance_vs_btc,
    get_default_session,
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
    assert reason == "blocked"


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


def test_fetch_btc_performance_fallback_to_mexc_on_binance_error():
    """fetch_btc_performance berhasil mengembalikan performa 30d dan 90d
    meskipun Binance Spot mengalami ProviderConnectionError dan data diambil dari MEXC Spot."""
    called_urls = []
    with open(os.path.join(FIXTURES_DIR, "mock_klines_daily.json")) as f:
        daily_json = json.load(f)

    def fake_get(url, params=None, timeout=None):
        called_urls.append(url)
        mock_resp = MagicMock(spec=requests.Response)
        if "api.binance.com" in url:
            mock_resp.status_code = 403
            return mock_resp
        if "api.mexc.com" in url:
            mock_resp.status_code = 200
            mock_resp.json.return_value = daily_json
            mock_resp.raise_for_status.return_value = None
            return mock_resp
        mock_resp.status_code = 404
        return mock_resp

    mock_sess = MagicMock(spec=requests.Session)
    mock_sess.get.side_effect = fake_get

    perf_30d, perf_90d = fetch_btc_performance(session=mock_sess)

    assert perf_30d is not None
    assert perf_90d is not None
    assert isinstance(perf_30d, float)
    assert isinstance(perf_90d, float)
    assert any("api.mexc.com" in u for u in called_urls)


def test_fetch_relative_performance_vs_btc_fallback_to_mexc_on_binance_error(mock_session):
    """fetch_relative_performance_vs_btc berhasil menghitung performa relatif
    meskipun Binance Spot mengalami ProviderConnectionError dan BTC diambil dari MEXC Spot."""
    called_urls = []
    with open(os.path.join(FIXTURES_DIR, "mock_klines_daily.json")) as f:
        daily_json = json.load(f)

    # Buat dummy DataFrame untuk koin simbol (misal SOL)
    df_symbol = fetch_binance_klines("SOLUSDT", interval="1d", session=mock_session)

    def fake_get(url, params=None, timeout=None):
        called_urls.append(url)
        mock_resp = MagicMock(spec=requests.Response)
        # Binance Spot diblokir
        if "api.binance.com" in url:
            mock_resp.status_code = 403
            return mock_resp
        # MEXC Spot melayani BTCUSDT
        if "api.mexc.com" in url:
            mock_resp.status_code = 200
            mock_resp.json.return_value = daily_json
            mock_resp.raise_for_status.return_value = None
            return mock_resp
        mock_resp.status_code = 404
        return mock_resp

    mock_sess = MagicMock(spec=requests.Session)
    mock_sess.get.side_effect = fake_get

    rel_perf = fetch_relative_performance_vs_btc("SOLUSDT", df_symbol, session=mock_sess)

    assert rel_perf is not None
    assert isinstance(rel_perf, float)
    assert any("api.mexc.com" in u for u in called_urls)


def test_btc_benchmark_skips_binance_when_domain_unreachable():
    """Jika unreachable_domains berisi 'binance.com', Binance langsung dilewati
    dan data BTC diambil dari MEXC Spot tanpa ada panggilan HTTP ke binance.com."""
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

    # 1. Test fetch_btc_performance
    perf_30d, perf_90d = fetch_btc_performance(session=mock_sess, unreachable_domains=unreachable)
    assert perf_30d is not None
    assert perf_90d is not None
    assert not any("binance.com" in u for u in called_urls)

    # 2. Test fetch_relative_performance_vs_btc
    # Gunakan klines daily yang sama sebagai df_symbol
    from spot_prompt.data_fetcher import parse_binance_like_klines
    df_symbol = parse_binance_like_klines(daily_json)

    called_urls.clear()
    rel_perf = fetch_relative_performance_vs_btc(
        "SOLUSDT",
        df_symbol,
        session=mock_sess,
        unreachable_domains=unreachable,
    )
    assert rel_perf is not None
    assert not any("binance.com" in u for u in called_urls)
    assert any("api.mexc.com" in u for u in called_urls)


def test_btc_benchmark_graceful_degradation_on_all_exchanges_failure():
    """Jika seluruh bursa gagal untuk BTC, kedua fungsi mengembalikan (None, None)
    dan None secara aman tanpa unhandled crash."""
    def fake_get(url, params=None, timeout=None):
        mock_resp = MagicMock(spec=requests.Response)
        mock_resp.status_code = 500
        mock_resp.raise_for_status.side_effect = requests.HTTPError("Server Error 500")
        return mock_resp

    mock_sess = MagicMock(spec=requests.Session)
    mock_sess.get.side_effect = fake_get

    with open(os.path.join(FIXTURES_DIR, "mock_klines_daily.json")) as f:
        daily_json = json.load(f)
    from spot_prompt.data_fetcher import parse_binance_like_klines
    df_symbol = parse_binance_like_klines(daily_json)

    # 1. fetch_btc_performance aman mengembalikan (None, None)
    perf_30d, perf_90d = fetch_btc_performance(session=mock_sess)
    assert perf_30d is None
    assert perf_90d is None

    # 2. fetch_relative_performance_vs_btc aman mengembalikan None
    rel_perf = fetch_relative_performance_vs_btc("SOLUSDT", df_symbol, session=mock_sess)
    assert rel_perf is None


def test_get_default_session_with_proxy():
    """get_default_session mengisi proxies http dan https sesuai argumen proxy."""
    session = get_default_session(proxy="http://127.0.0.1:8080")
    assert session.proxies.get("http") == "http://127.0.0.1:8080"
    assert session.proxies.get("https") == "http://127.0.0.1:8080"


def test_get_default_session_without_proxy():
    """get_default_session tanpa argumen proxy tidak mengisi proxies default."""
    session = get_default_session()
    assert session.proxies.get("http") is None
    assert session.proxies.get("https") is None


def test_fallback_all_fail_all_connection_error_diagnoses_network():
    """Jika seluruh bursa gagal karena ProviderConnectionError, diagnosis harus
    menyatakan kegagalan jaringan/koneksi dan merekomendasikan flag --proxy."""
    def fake_get(url, params=None, timeout=None):
        mock_resp = MagicMock(spec=requests.Response)
        mock_resp.status_code = 403
        return mock_resp

    mock_sess = MagicMock(spec=requests.Session)
    mock_sess.get.side_effect = fake_get

    with pytest.raises(DataFetchError) as exc_info:
        fetch_market_klines_with_fallback("SOLUSDT", session=mock_sess)

    msg = str(exc_info.value)
    assert "Gagal terhubung ke seluruh bursa" in msg
    assert "Periksa koneksi internet Anda atau gunakan flag --proxy" in msg


def test_fallback_all_fail_all_symbol_not_found_diagnoses_unlisted():
    """Jika seluruh bursa gagal karena SymbolNotFoundError, diagnosis harus
    menyatakan simbol tidak terdaftar di seluruh bursa yang didukung."""
    def fake_get(url, params=None, timeout=None):
        mock_resp = MagicMock(spec=requests.Response)
        mock_resp.status_code = 404
        return mock_resp

    mock_sess = MagicMock(spec=requests.Session)
    mock_sess.get.side_effect = fake_get

    with pytest.raises(DataFetchError) as exc_info:
        fetch_market_klines_with_fallback("UNKNOWNCOIN", session=mock_sess)

    msg = str(exc_info.value)
    assert "Simbol 'UNKNOWNCOIN' tidak terdaftar" in msg
    assert "seluruh bursa yang didukung" in msg


def test_fallback_all_fail_mixed_diagnoses_partial_issues():
    """Jika kegagalan adalah campuran antara kendala koneksi dan simbol tidak ditemukan,
    diagnosis harus mencatat adanya kendala campuran."""
    def fake_get(url, params=None, timeout=None):
        mock_resp = MagicMock(spec=requests.Response)
        if "binance.com" in url:
            mock_resp.status_code = 403  # ProviderConnectionError
        else:
            mock_resp.status_code = 404  # SymbolNotFoundError
        return mock_resp

    mock_sess = MagicMock(spec=requests.Session)
    mock_sess.get.side_effect = fake_get

    with pytest.raises(DataFetchError) as exc_info:
        fetch_market_klines_with_fallback("MIXEDCOIN", session=mock_sess)

    msg = str(exc_info.value)
    assert "kendala koneksi" in msg.lower() or "pemblokiran" in msg.lower()
    assert "tidak ditemukan" in msg.lower()


def test_fallback_reasons_passed_to_callback_blocked_not_found_short_circuit():
    """Memverifikasi bahwa alasan fallback 'blocked', 'not_found', dan 'short_circuit'
    diteruskan dengan benar ke callback on_fallback."""
    with open(os.path.join(FIXTURES_DIR, "mock_klines_daily.json")) as f:
        daily_json = json.load(f)

    gateio_json = [
        ["1700000000", "50000", "100.5", "102.0", "99.0", "100.0", "500.0", "true"],
        ["1700086400", "60000", "101.5", "103.0", "100.0", "100.5", "600.0", "true"],
    ]

    # Skenario: unreachable_domains sudah berisi binance.com (short-circuit di provider pertama)
    def fake_get_short_circuit(url, params=None, timeout=None):
        mock_resp = MagicMock(spec=requests.Response)
        if "api.mexc.com" in url:
            mock_resp.status_code = 200
            mock_resp.json.return_value = daily_json
            mock_resp.raise_for_status.return_value = None
            return mock_resp
        mock_resp.status_code = 404
        return mock_resp

    mock_sess = MagicMock(spec=requests.Session)
    mock_sess.get.side_effect = fake_get_short_circuit

    events = []
    fetch_market_klines_with_fallback(
        "SOLUSDT",
        session=mock_sess,
        unreachable_domains={"binance.com"},
        on_fallback=lambda prev, nxt, reason=None: events.append((prev, nxt, reason)),
    )

    assert len(events) >= 1
    assert events[0][0] == "Binance Spot"
    assert events[0][1] == "MEXC Spot"
    assert events[0][2] == "short_circuit"


def test_get_default_session_all_proxy_env(monkeypatch):
    """get_default_session membaca variabel lingkungan ALL_PROXY jika parameter proxy None."""
    monkeypatch.setenv("ALL_PROXY", "socks5://127.0.0.1:1080")
    monkeypatch.delenv("all_proxy", raising=False)
    session = get_default_session()
    assert session.proxies.get("http") == "socks5://127.0.0.1:1080"
    assert session.proxies.get("https") == "socks5://127.0.0.1:1080"


def test_get_default_session_all_proxy_lowercase_env(monkeypatch):
    """get_default_session membaca variabel lingkungan all_proxy jika ALL_PROXY tidak disetel."""
    monkeypatch.delenv("ALL_PROXY", raising=False)
    monkeypatch.setenv("all_proxy", "http://127.0.0.1:7890")
    session = get_default_session()
    assert session.proxies.get("http") == "http://127.0.0.1:7890"
    assert session.proxies.get("https") == "http://127.0.0.1:7890"


def test_get_default_session_explicit_proxy_overrides_env(monkeypatch):
    """Parameter proxy eksplisit memiliki prioritas lebih tinggi daripada ALL_PROXY."""
    monkeypatch.setenv("ALL_PROXY", "socks5://127.0.0.1:1080")
    session = get_default_session(proxy="http://127.0.0.1:8888")
    assert session.proxies.get("http") == "http://127.0.0.1:8888"
    assert session.proxies.get("https") == "http://127.0.0.1:8888"


def test_find_next_reachable_provider_helper():
    """_find_next_reachable_provider mencari provider berikutnya yang belum unreachable."""
    dummy_providers = [
        ("Prov1", "domain1.com", None),
        ("Prov2", "domain2.com", None),
        ("Prov3", "domain1.com", None),
        ("Prov4", "domain3.com", None),
    ]

    # Mulai dari index 1, tanpa unreachable
    name, idx = _find_next_reachable_provider(dummy_providers, 1, set())
    assert name == "Prov2"
    assert idx == 1

    # Jika domain2.com dan domain1.com unreachable, dari index 1 harus melompat ke Prov4
    name, idx = _find_next_reachable_provider(dummy_providers, 1, {"domain1.com", "domain2.com"})
    assert name == "Prov4"
    assert idx == 3

    # Jika semua unreachable
    name, idx = _find_next_reachable_provider(dummy_providers, 1, {"domain1.com", "domain2.com", "domain3.com"})
    assert name is None
    assert idx is None


def test_fallback_chain_empty_data_does_not_mark_domain_unreachable():
    """Jika bursa mengembalikan data klines kosong (DataFetchError non-connection),
    domain bursa tersebut TIDAK dimasukkan ke unreachable_domains dan bursa berikutnya dalam domain yang sama
    (misal Binance Futures) tetap dapat dicoba."""
    called_urls = []
    with open(os.path.join(FIXTURES_DIR, "mock_klines_daily.json")) as f:
        daily_json = json.load(f)

    def fake_get(url, params=None, timeout=None):
        called_urls.append(url)
        mock_resp = MagicMock(spec=requests.Response)

        # 1. Binance Futures: sukses (periksa fapi terlebih dahulu sebelum api.binance.com)
        if "fapi.binance.com" in url:
            mock_resp.status_code = 200
            mock_resp.json.return_value = daily_json
            mock_resp.raise_for_status.return_value = None
            return mock_resp

        # 2. Binance Spot mengembalikan array kosong -> DataFetchError("Data klines kosong.")
        if "api.binance.com" in url:
            mock_resp.status_code = 200
            mock_resp.json.return_value = []
            mock_resp.raise_for_status.return_value = None
            return mock_resp

        # 3. MEXC Spot: simbol tidak ditemukan (HTTP 404)
        if "api.mexc.com" in url:
            mock_resp.status_code = 404
            return mock_resp

        mock_resp.status_code = 404
        return mock_resp

    mock_sess = MagicMock(spec=requests.Session)
    mock_sess.get.side_effect = fake_get

    unreachable = set()
    df_d, df_w, prov = fetch_market_klines_with_fallback(
        "FUTURESCOINUSDT",
        session=mock_sess,
        unreachable_domains=unreachable,
    )

    # Memverifikasi Binance Futures berhasil melayani data
    assert prov == "Binance Futures"
    assert len(df_d) == 300
    # Domain binance.com tidak boleh ada di unreachable_domains
    assert "binance.com" not in unreachable
    # fapi.binance.com terbukti dipanggil
    assert any("fapi.binance.com" in u for u in called_urls)


def test_fallback_reasons_comprehensive_sequence():
    """Memverifikasi urutan transisi fallback meneruskan alasan canonical string
    (blocked, not_found, short_circuit) secara tepat."""
    with open(os.path.join(FIXTURES_DIR, "mock_klines_daily.json")) as f:
        daily_json = json.load(f)
    gateio_json = [
        ["1700000000", "50000", "100.5", "102.0", "99.0", "100.0", "500.0", "true"],
        ["1700086400", "60000", "101.5", "103.0", "100.0", "100.5", "600.0", "true"],
    ]

    # Binance Spot: 403 (blocked)
    # MEXC Spot: 404 (not_found)
    # Binance Futures: dilewati (short_circuit karena binance.com unreachable)
    # Gate.io Spot: 200 (sukses)
    def fake_get(url, params=None, timeout=None):
        mock_resp = MagicMock(spec=requests.Response)
        if "api.binance.com" in url:
            mock_resp.status_code = 403
            return mock_resp
        if "api.mexc.com" in url:
            mock_resp.status_code = 404
            return mock_resp
        if "gateio.ws" in url or "api.gateio.ws" in url:
            mock_resp.status_code = 200
            mock_resp.json.return_value = gateio_json
            mock_resp.raise_for_status.return_value = None
            return mock_resp
        mock_resp.status_code = 404
        return mock_resp

    mock_sess = MagicMock(spec=requests.Session)
    mock_sess.get.side_effect = fake_get

    events = []
    unreachable = set()
    df_d, df_w, prov = fetch_market_klines_with_fallback(
        "TESTCOINUSDT",
        session=mock_sess,
        unreachable_domains=unreachable,
        on_fallback=lambda prev, nxt, reason=None: events.append((prev, nxt, reason)),
    )

    assert prov == "Gate.io Spot"
    assert len(events) == 2
    # Transisi 1: Binance Spot -> MEXC Spot (alasan: blocked)
    assert events[0] == ("Binance Spot", "MEXC Spot", FALLBACK_REASON_BLOCKED)
    # Transisi 2: MEXC Spot -> Gate.io Spot (alasan: not_found, melompati Binance Futures)
    assert events[1] == ("MEXC Spot", "Gate.io Spot", FALLBACK_REASON_NOT_FOUND)






