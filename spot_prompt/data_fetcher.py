"""Pengambil data pasar publik gratis (Multi-Exchange Fallback Chain & Alternative.me)."""

import inspect
import os
from typing import Any, Callable, Optional, Set, Tuple
import pandas as pd
import requests

from spot_prompt.config import (
    ALTERNATIVE_ME_FNG_URL,
    BINANCE_API_BASE,
    BINANCE_FUTURES_API_BASE,
    BINANCE_FUTURES_KLINES_PATH,
    BINANCE_KLINES_PATH,
    DEFAULT_TIMEOUT_SECONDS,
    GATEIO_API_BASE,
    GATEIO_CANDLESTICKS_PATH,
    MEXC_API_BASE,
    MEXC_KLINES_PATH,
    USER_AGENT,
)
from spot_prompt.normalizer import (
    extract_base_asset,
    is_btc_symbol,
    to_gateio_currency_pair,
)


class DataFetchError(Exception):
    """Kesalahan umum saat mengambil data dari API publik."""
    pass


class SymbolNotFoundError(DataFetchError):
    """Simbol tidak terdaftar atau tidak ditemukan di bursa tertentu."""
    pass


class ProviderConnectionError(DataFetchError):
    """Koneksi ke bursa gagal akibat pemblokiran jaringan, sensor, timeout, atau gangguan server."""
    pass


# Konstanta alasan transisi fallback kanonikal
FALLBACK_REASON_BLOCKED = "blocked"
FALLBACK_REASON_NOT_FOUND = "not_found"
FALLBACK_REASON_SHORT_CIRCUIT = "short_circuit"


def get_default_session(proxy: Optional[str] = None) -> requests.Session:
    """Membuat session requests dengan User-Agent default dan konfigurasi proxy opsional.

    Mendukung proxy eksplisit serta fallback otomatis ke variabel lingkungan ALL_PROXY / all_proxy.
    """
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    proxy_target = proxy or os.environ.get("ALL_PROXY") or os.environ.get("all_proxy")
    if proxy_target:
        session.proxies.update({
            "http": proxy_target,
            "https": proxy_target,
        })
    return session


def parse_binance_like_klines(raw_data: list) -> pd.DataFrame:
    """Mengubah format array candlestick standar (Binance Spot, Binance Futures, MEXC) ke DataFrame."""
    if not isinstance(raw_data, list) or len(raw_data) == 0:
        raise DataFetchError("Data klines kosong.")

    # Kolom minimum yang dibutuhkan: [timestamp, open, high, low, close, volume]
    cols_count = len(raw_data[0]) if raw_data else 12
    standard_columns = [
        "timestamp", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades", "taker_base", "taker_quote", "ignore",
    ]
    df = pd.DataFrame(raw_data, columns=standard_columns[:cols_count])

    df = df[["timestamp", "open", "high", "low", "close", "volume"]].copy()
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce")

    return df.dropna().sort_values("timestamp").reset_index(drop=True)


def parse_gateio_candlesticks(raw_data: list) -> pd.DataFrame:
    """Mengubah format array candlestick Gate.io ke DataFrame standar.

    Format Gate.io: [timestamp_sec, quote_volume, close, high, low, open, base_volume, ...]
    """
    if not isinstance(raw_data, list) or len(raw_data) == 0:
        raise DataFetchError("Data klines kosong dari Gate.io.")

    rows = []
    for item in raw_data:
        try:
            rows.append(
                {
                    "timestamp": int(item[0]) * 1000,
                    "open": float(item[5]),
                    "high": float(item[3]),
                    "low": float(item[4]),
                    "close": float(item[2]),
                    "volume": float(item[6]),
                }
            )
        except (IndexError, ValueError):
            continue

    if not rows:
        raise DataFetchError("Gagal mem-parsing candlestick dari Gate.io.")

    df = pd.DataFrame(rows)
    return df.dropna().sort_values("timestamp").reset_index(drop=True)


def _handle_response_status(resp: requests.Response, provider_name: str, symbol: str) -> None:
    """Memeriksa kode status HTTP response dan melempar exception domain yang sesuai."""
    if resp.status_code in (400, 404):
        raise SymbolNotFoundError(f"Simbol '{symbol}' tidak valid atau tidak ditemukan di {provider_name}.")
    if resp.status_code in (403, 451) or 500 <= resp.status_code < 600:
        raise ProviderConnectionError(
            f"Koneksi ke {provider_name} gagal/diblokir (HTTP {resp.status_code}) untuk simbol '{symbol}'."
        )
    resp.raise_for_status()


def _handle_request_exception(exc: requests.RequestException, provider_name: str, symbol: str) -> None:
    """Menangani requests.RequestException dan memetakan ke error domain yang sesuai."""
    status = getattr(exc.response, "status_code", None)
    if status in (400, 404):
        raise SymbolNotFoundError(f"Simbol '{symbol}' tidak valid atau tidak ditemukan di {provider_name}.") from exc
    if status in (403, 451) or (status and 500 <= status < 600):
        raise ProviderConnectionError(
            f"Koneksi ke {provider_name} gagal/diblokir (HTTP {status}) untuk simbol '{symbol}': {exc}"
        ) from exc
    raise ProviderConnectionError(
        f"Koneksi jaringan ke {provider_name} gagal untuk {symbol}: {exc}"
    ) from exc


def fetch_binance_spot_klines(
    symbol: str,
    interval: str,
    limit: int = 500,
    session: Optional[requests.Session] = None,
) -> pd.DataFrame:
    """Mengambil data candlestick dari Binance Spot Public REST API."""
    sess = session or get_default_session()
    url = f"{BINANCE_API_BASE}{BINANCE_KLINES_PATH}"
    params = {
        "symbol": symbol.upper(),
        "interval": interval,
        "limit": limit,
    }

    try:
        resp = sess.get(url, params=params, timeout=DEFAULT_TIMEOUT_SECONDS)
        _handle_response_status(resp, "Binance Spot", symbol)
        raw_data = resp.json()
    except (SymbolNotFoundError, ProviderConnectionError):
        raise
    except requests.RequestException as exc:
        _handle_request_exception(exc, "Binance Spot", symbol)

    return parse_binance_like_klines(raw_data)


# Alias kompatibel untuk fungsi lama
fetch_binance_klines = fetch_binance_spot_klines


def fetch_mexc_klines(
    symbol: str,
    interval: str,
    limit: int = 500,
    session: Optional[requests.Session] = None,
) -> pd.DataFrame:
    """Mengambil data candlestick dari MEXC Spot Public REST API (Fallback Tier 1)."""
    sess = session or get_default_session()
    url = f"{MEXC_API_BASE}{MEXC_KLINES_PATH}"

    # MEXC menggunakan '1W' (huruf besar) untuk interval mingguan
    mexc_interval = "1W" if interval.lower() == "1w" else interval

    params = {
        "symbol": symbol.upper(),
        "interval": mexc_interval,
        "limit": limit,
    }

    try:
        resp = sess.get(url, params=params, timeout=DEFAULT_TIMEOUT_SECONDS)
        _handle_response_status(resp, "MEXC Spot", symbol)
        raw_data = resp.json()
    except (SymbolNotFoundError, ProviderConnectionError):
        raise
    except requests.RequestException as exc:
        _handle_request_exception(exc, "MEXC Spot", symbol)

    return parse_binance_like_klines(raw_data)


def fetch_binance_futures_klines(
    symbol: str,
    interval: str,
    limit: int = 500,
    session: Optional[requests.Session] = None,
) -> pd.DataFrame:
    """Mengambil data candlestick dari Binance USDⓈ-M Futures REST API (Fallback Tier 2)."""
    sess = session or get_default_session()
    url = f"{BINANCE_FUTURES_API_BASE}{BINANCE_FUTURES_KLINES_PATH}"
    params = {
        "symbol": symbol.upper(),
        "interval": interval,
        "limit": limit,
    }

    try:
        resp = sess.get(url, params=params, timeout=DEFAULT_TIMEOUT_SECONDS)
        _handle_response_status(resp, "Binance Futures", symbol)
        raw_data = resp.json()
    except (SymbolNotFoundError, ProviderConnectionError):
        raise
    except requests.RequestException as exc:
        _handle_request_exception(exc, "Binance Futures", symbol)

    return parse_binance_like_klines(raw_data)


def fetch_gateio_klines(
    symbol: str,
    interval: str,
    limit: int = 500,
    session: Optional[requests.Session] = None,
) -> pd.DataFrame:
    """Mengambil data candlestick dari Gate.io Spot REST API (Fallback Tier 3)."""
    sess = session or get_default_session()
    url = f"{GATEIO_API_BASE}{GATEIO_CANDLESTICKS_PATH}"

    # Gate.io menggunakan format pair dengan garis bawah (SOL_USDT) dan interval '7d' untuk mingguan
    pair = to_gateio_currency_pair(symbol)
    gate_interval = "7d" if interval.lower() in ("1w", "7d") else interval

    params = {
        "currency_pair": pair,
        "interval": gate_interval,
        "limit": limit,
    }

    try:
        resp = sess.get(url, params=params, timeout=DEFAULT_TIMEOUT_SECONDS)
        _handle_response_status(resp, "Gate.io Spot", pair)
        raw_data = resp.json()
    except (SymbolNotFoundError, ProviderConnectionError):
        raise
    except requests.RequestException as exc:
        _handle_request_exception(exc, "Gate.io Spot", pair)

    return parse_gateio_candlesticks(raw_data)


def _find_next_reachable_provider(
    providers: list,
    start_index: int,
    unreachable_domains: Set[str],
) -> Tuple[Optional[str], Optional[int]]:
    """Mencari nama provider dan indeks berikutnya dalam rantai yang domainnya belum ditandai unreachable."""
    for idx, (next_name, next_domain, _) in enumerate(providers[start_index:], start=start_index):
        if next_domain not in unreachable_domains:
            return next_name, idx
    return None, None


def _notify_fallback(
    callback: Optional[Callable],
    prev_prov: str,
    next_prov: str,
    reason: Optional[Any] = None,
) -> None:
    """Memanggil callback on_fallback dengan fleksibilitas 2 atau 3 parameter tanpa merusak pemanggil lama."""
    if callback is None:
        return

    try:
        sig = inspect.signature(callback)
        pos_params = [
            p for p in sig.parameters.values()
            if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        ]
        has_varargs = any(p.kind == inspect.Parameter.VAR_POSITIONAL for p in sig.parameters.values())
        if has_varargs or len(pos_params) >= 3:
            callback(prev_prov, next_prov, reason)
        else:
            callback(prev_prov, next_prov)
    except (ValueError, TypeError):
        try:
            callback(prev_prov, next_prov, reason)
        except TypeError:
            callback(prev_prov, next_prov)


def fetch_market_klines_with_fallback(
    symbol: str,
    daily_limit: int = 500,
    weekly_limit: int = 300,
    session: Optional[requests.Session] = None,
    on_fallback: Optional[Callable[..., None]] = None,
    unreachable_domains: Optional[Set[str]] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame, str]:
    """Mengambil data klines harian (1d) dan mingguan (1w) dengan rantai fallback otomatis.

    Mencoba bursa sesuai prioritas:
    1. Binance Spot (domain: binance.com)
    2. MEXC Spot (domain: mexc.com, pasar spot utama untuk koin baru / meme coin)
    3. Binance Futures (domain: binance.com, USDⓈ-M perp dengan likuiditas tinggi)
    4. Gate.io Spot (domain: gate.io, bursa spot cadangan)

    Jika suatu bursa mengalami ProviderConnectionError, domain bursa tersebut dimasukkan ke
    unreachable_domains sehingga bursa berikutnya dalam domain yang sama akan dilewati (short-circuit).

    Returns:
        Tuple (df_daily, df_weekly, source_exchange_name)
    """
    if unreachable_domains is None:
        unreachable_domains = set()

    providers = [
        (
            "Binance Spot",
            "binance.com",
            lambda s, sess: (
                fetch_binance_spot_klines(s, interval="1d", limit=daily_limit, session=sess),
                fetch_binance_spot_klines(s, interval="1w", limit=weekly_limit, session=sess),
            ),
        ),
        (
            "MEXC Spot",
            "mexc.com",
            lambda s, sess: (
                fetch_mexc_klines(s, interval="1d", limit=daily_limit, session=sess),
                fetch_mexc_klines(s, interval="1w", limit=weekly_limit, session=sess),
            ),
        ),
        (
            "Binance Futures",
            "binance.com",
            lambda s, sess: (
                fetch_binance_futures_klines(s, interval="1d", limit=daily_limit, session=sess),
                fetch_binance_futures_klines(s, interval="1w", limit=weekly_limit, session=sess),
            ),
        ),
        (
            "Gate.io Spot",
            "gate.io",
            lambda s, sess: (
                fetch_gateio_klines(s, interval="1d", limit=daily_limit, session=sess),
                fetch_gateio_klines(s, interval="1w", limit=weekly_limit, session=sess),
            ),
        ),
    ]

    sess = session or get_default_session()
    errors_log = []
    connection_errors_count = 0
    symbol_not_found_count = 0
    other_errors_count = 0
    last_target_index: Optional[int] = None

    for i, (prov_name, domain, fetch_func) in enumerate(providers):
        # Lewati provider jika domain induk telah ditandai unreachable (in-memory short-circuit)
        if domain in unreachable_domains:
            errors_log.append(f"{prov_name}: Dilewati karena domain '{domain}' tidak dapat dijangkau (short-circuit).")
            connection_errors_count += 1

            next_prov_name, next_idx = _find_next_reachable_provider(providers, i + 1, unreachable_domains)

            # Jika provider ini belum dilompati oleh transisi fallback sebelumnya
            if next_prov_name and on_fallback and (last_target_index is None or i >= last_target_index):
                _notify_fallback(
                    on_fallback,
                    prov_name,
                    next_prov_name,
                    FALLBACK_REASON_SHORT_CIRCUIT,
                )
                last_target_index = next_idx
            continue

        try:
            df_daily, df_weekly = fetch_func(symbol, sess)
            if len(df_daily) > 0 and len(df_weekly) > 0:
                return df_daily, df_weekly, prov_name
            raise DataFetchError(f"Data klines kosong di {prov_name}.")
        except Exception as exc:
            errors_log.append(f"{prov_name}: {exc}")

            # Klasifikasikan alasan fallback
            if isinstance(exc, ProviderConnectionError):
                unreachable_domains.add(domain)
                connection_errors_count += 1
                reason = FALLBACK_REASON_BLOCKED
            elif isinstance(exc, SymbolNotFoundError):
                symbol_not_found_count += 1
                reason = FALLBACK_REASON_NOT_FOUND
            else:
                # Kesalahan parsing atau data kosong bukan masalah koneksi bursa
                other_errors_count += 1
                reason = FALLBACK_REASON_NOT_FOUND

            next_prov_name, next_idx = _find_next_reachable_provider(providers, i + 1, unreachable_domains)

            # Picu callback transisi fallback jika masih ada provider berikutnya
            if next_prov_name and on_fallback:
                _notify_fallback(on_fallback, prov_name, next_prov_name, reason)
                last_target_index = next_idx

    # Evaluasi diagnosis kegagalan akhir secara cerdas
    if symbol_not_found_count == 0 and other_errors_count == 0 and connection_errors_count > 0:
        raise ProviderConnectionError(
            f"Gagal terhubung ke seluruh bursa (Binance Spot, MEXC Spot, Binance Futures, Gate.io Spot) "
            f"akibat kendala jaringan atau pemblokiran akses. "
            f"Periksa koneksi internet Anda atau gunakan flag --proxy.\n"
            f"Detail kegagalan:\n - " + "\n - ".join(errors_log)
        )
    elif connection_errors_count == 0 and other_errors_count == 0 and symbol_not_found_count > 0:
        raise SymbolNotFoundError(
            f"Simbol '{symbol}' tidak terdaftar atau tidak ditemukan di seluruh bursa yang didukung "
            f"(Binance Spot, MEXC Spot, Binance Futures, Gate.io Spot).\n"
            f"Detail kegagalan:\n - " + "\n - ".join(errors_log)
        )
    elif other_errors_count > 0 and connection_errors_count == 0 and symbol_not_found_count == 0:
        raise DataFetchError(
            f"Gagal mengambil data untuk simbol '{symbol}' karena data tidak lengkap atau gagal diparsing di seluruh bursa.\n"
            f"Detail kegagalan:\n - " + "\n - ".join(errors_log)
        )
    else:
        raise DataFetchError(
            f"Gagal mengambil data untuk simbol '{symbol}'. "
            f"Terdapat kendala koneksi atau pemblokiran pada beberapa bursa dan simbol tidak ditemukan pada bursa lainnya.\n"
            f"Detail kegagalan:\n - " + "\n - ".join(errors_log)
        )


def fetch_fear_and_greed(session: Optional[requests.Session] = None) -> Tuple[Optional[int], Optional[str]]:
    """Mengambil indeks Fear & Greed terkini dari alternative.me."""
    sess = session or get_default_session()
    try:
        resp = sess.get(ALTERNATIVE_ME_FNG_URL, timeout=DEFAULT_TIMEOUT_SECONDS)
        resp.raise_for_status()
        data = resp.json()
        item = data.get("data", [])[0]
        score = int(item["value"])
        label = item["value_classification"]
        return score, label
    except Exception:
        # Fallback graceful jika API alternatif sedang down / timeout
        return None, None


def fetch_btc_performance(
    session: Optional[requests.Session] = None,
    unreachable_domains: Optional[Set[str]] = None,
    on_fallback: Optional[Callable[..., None]] = None,
) -> Tuple[Optional[float], Optional[float]]:
    """Mengambil kinerja persentase harga Bitcoin dalam 30 dan 90 hari terakhir menggunakan rantai fallback."""
    try:
        df_btc, _, _ = fetch_market_klines_with_fallback(
            "BTCUSDT",
            daily_limit=95,
            weekly_limit=10,
            session=session,
            on_fallback=on_fallback,
            unreachable_domains=unreachable_domains,
        )
        if len(df_btc) < 30:
            return None, None

        current_close = df_btc["close"].iloc[-1]
        close_30d_ago = df_btc["close"].iloc[-30]
        perf_30d = ((current_close - close_30d_ago) / close_30d_ago) * 100.0

        perf_90d = None
        if len(df_btc) >= 90:
            close_90d_ago = df_btc["close"].iloc[-90]
            perf_90d = ((current_close - close_90d_ago) / close_90d_ago) * 100.0

        return float(perf_30d), float(perf_90d) if perf_90d is not None else None
    except Exception:
        return None, None


def fetch_relative_performance_vs_btc(
    symbol: str,
    df_symbol_daily: pd.DataFrame,
    session: Optional[requests.Session] = None,
    unreachable_domains: Optional[Set[str]] = None,
    on_fallback: Optional[Callable[..., None]] = None,
) -> Optional[float]:
    """Menghitung performa relatif koin terhadap BTC selama 30 hari terakhir.

    Mencoba pair langsung <COIN>BTC terlebih dahulu melalui rantai fallback; jika tidak tersedia,
    menggunakan rasio sintetis terhadap BTCUSDT melalui rantai fallback.
    """
    if is_btc_symbol(symbol):
        return None

    base_asset = extract_base_asset(symbol)
    direct_btc_pair = f"{base_asset}BTC"

    sess = session or get_default_session()

    # Opsi 1: Cek pair langsung <COIN>BTC dengan fallback
    try:
        df_pair, _, _ = fetch_market_klines_with_fallback(
            direct_btc_pair,
            daily_limit=35,
            weekly_limit=10,
            session=sess,
            on_fallback=on_fallback,
            unreachable_domains=unreachable_domains,
        )
        if len(df_pair) >= 30:
            curr_val = df_pair["close"].iloc[-1]
            old_val = df_pair["close"].iloc[-30]
            if old_val > 0:
                return float(((curr_val - old_val) / old_val) * 100.0)
    except Exception:
        pass

    # Opsi 2: Rasio sintetis terhadap BTCUSDT dengan fallback
    try:
        df_btc, _, _ = fetch_market_klines_with_fallback(
            "BTCUSDT",
            daily_limit=35,
            weekly_limit=10,
            session=sess,
            on_fallback=on_fallback,
            unreachable_domains=unreachable_domains,
        )
        if len(df_btc) >= 30 and len(df_symbol_daily) >= 30:
            coin_now = df_symbol_daily["close"].iloc[-1]
            coin_30d = df_symbol_daily["close"].iloc[-30]
            btc_now = df_btc["close"].iloc[-1]
            btc_30d = df_btc["close"].iloc[-30]

            ratio_now = coin_now / btc_now if btc_now > 0 else 0
            ratio_30d = coin_30d / btc_30d if btc_30d > 0 else 0

            if ratio_30d > 0:
                return float(((ratio_now - ratio_30d) / ratio_30d) * 100.0)
    except Exception:
        pass

    return None
