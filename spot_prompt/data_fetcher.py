"""Pengambil data pasar publik (Binance Spot REST API & Alternative.me)."""

from typing import Optional, Tuple
import pandas as pd
import requests

from spot_prompt.config import (
    ALTERNATIVE_ME_FNG_URL,
    BINANCE_API_BASE,
    BINANCE_KLINES_PATH,
    DEFAULT_TIMEOUT_SECONDS,
    USER_AGENT,
)
from spot_prompt.normalizer import extract_base_asset, is_btc_symbol


class DataFetchError(Exception):
    """Kesalahan saat mengambil data dari API publik."""
    pass


def get_default_session() -> requests.Session:
    """Membuat session requests dengan User-Agent default."""
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def fetch_binance_klines(
    symbol: str,
    interval: str,
    limit: int = 500,
    session: Optional[requests.Session] = None,
) -> pd.DataFrame:
    """Mengambil data candlestick OHLCV dari Binance Spot Public REST API."""
    sess = session or get_default_session()
    url = f"{BINANCE_API_BASE}{BINANCE_KLINES_PATH}"
    params = {
        "symbol": symbol.upper(),
        "interval": interval,
        "limit": limit,
    }

    try:
        resp = sess.get(url, params=params, timeout=DEFAULT_TIMEOUT_SECONDS)
        if resp.status_code == 400:
            raise DataFetchError(f"Simbol '{symbol}' tidak valid atau tidak ditemukan di Binance Spot.")
        resp.raise_for_status()
        raw_data = resp.json()
    except requests.RequestException as exc:
        raise DataFetchError(f"Gagal mengambil klines {interval} untuk {symbol}: {exc}") from exc

    if not isinstance(raw_data, list) or len(raw_data) == 0:
        raise DataFetchError(f"Data klines kosong untuk {symbol} ({interval}).")

    # Format Binance: [0: open_time, 1: open, 2: high, 3: low, 4: close, 5: volume, ...]
    df = pd.DataFrame(
        raw_data,
        columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades", "taker_base", "taker_quote", "ignore",
        ],
    )
    # Konversi tipe data numerik
    df = df[["timestamp", "open", "high", "low", "close", "volume"]].copy()
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce")

    df = df.dropna().sort_values("timestamp").reset_index(drop=True)
    return df


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


def fetch_btc_performance(session: Optional[requests.Session] = None) -> Tuple[Optional[float], Optional[float]]:
    """Mengambil kinerja persentase harga Bitcoin dalam 30 dan 90 hari terakhir."""
    try:
        df_btc = fetch_binance_klines("BTCUSDT", interval="1d", limit=95, session=session)
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
) -> Optional[float]:
    """Menghitung performa relatif koin terhadap BTC selama 30 hari terakhir.

    Mencoba pair langsung <COIN>BTC terlebih dahulu; jika tidak tersedia,
    menggunakan rasio sintetis terhadap BTCUSDT.
    """
    if is_btc_symbol(symbol):
        return None

    base_asset = extract_base_asset(symbol)
    direct_btc_pair = f"{base_asset}BTC"

    sess = session or get_default_session()

    # Opsi 1: Cek pair langsung <COIN>BTC di Binance
    try:
        df_pair = fetch_binance_klines(direct_btc_pair, interval="1d", limit=35, session=sess)
        if len(df_pair) >= 30:
            curr_val = df_pair["close"].iloc[-1]
            old_val = df_pair["close"].iloc[-30]
            if old_val > 0:
                return float(((curr_val - old_val) / old_val) * 100.0)
    except Exception:
        pass

    # Opsi 2: Rasio sintetis terhadap BTCUSDT
    try:
        df_btc = fetch_binance_klines("BTCUSDT", interval="1d", limit=35, session=sess)
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
