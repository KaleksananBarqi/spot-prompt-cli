"""Klien data pasar publik terpadu (Multi-Exchange Fallback Chain & Sentimen)."""

import os
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
import pandas as pd
import requests

from spot_prompt.config import (
    ALTERNATIVE_ME_FNG_URL,
    BINANCE_API_BASE,
    BINANCE_FUTURES_API_BASE,
    BINANCE_FUTURES_KLINES_PATH,
    BINANCE_KLINES_PATH,
    COINGECKO_SIMPLE_PRICE_USDTIDR_URL,
    DEFAULT_TIMEOUT_SECONDS,
    GATEIO_API_BASE,
    GATEIO_CANDLESTICKS_PATH,
    INDODAX_TICKER_USDTIDR_URL,
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


def _find_next_reachable_provider(
    providers: list,
    start_index: int,
    unreachable_domains: Set[str],
) -> Tuple[Optional[str], Optional[int]]:
    """Mencari penyedia berikutnya yang domainnya tidak termasuk dalam unreachable_domains."""
    for idx, (next_name, next_domain, _) in enumerate(providers[start_index:], start=start_index):
        if next_domain not in unreachable_domains:
            return next_name, idx
    return None, None


@dataclass(frozen=True)
class MarketContext:
    """Kontrak data pasar mentah lengkap untuk analisis teknikal dan sentimen."""
    symbol: str
    df_daily: pd.DataFrame
    df_weekly: pd.DataFrame
    source_exchange: str
    fear_greed_score: Optional[int]
    fear_greed_text: Optional[str]
    perf_vs_btc_30d: Optional[float] = None
    btc_perf_30d: Optional[float] = None
    btc_perf_90d: Optional[float] = None


def create_default_session(proxy: Optional[str] = None) -> requests.Session:
    """Membuat session requests dengan User-Agent default dan konfigurasi proxy."""
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
    """Mengubah format array candlestick Gate.io ke DataFrame standar."""
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


class MarketDataClient:
    """Modul mendalam pengambil data pasar dengan proteksi ketahanan jaringan."""

    def __init__(
        self,
        session: Optional[requests.Session] = None,
        proxy: Optional[str] = None,
        on_fallback: Optional[Callable[[str, str, Optional[Any]], None]] = None,
    ) -> None:
        self.session = session or create_default_session(proxy=proxy)
        self.on_fallback = on_fallback
        self.unreachable_domains: Set[str] = set()
        # Pelacak internal domain unreachable yang sudah dilaporkan agar log short-circuit tidak berulang
        self._notified_unreachable_domains: Set[str] = set()

    def _handle_response_status(self, resp: requests.Response, provider_name: str, symbol: str) -> None:
        """Memeriksa kode status HTTP response dan melempar exception domain."""
        if resp.status_code in (400, 404):
            raise SymbolNotFoundError(f"Simbol '{symbol}' tidak valid atau tidak ditemukan di {provider_name}.")
        if resp.status_code in (403, 451) or 500 <= resp.status_code < 600:
            raise ProviderConnectionError(
                f"Koneksi ke {provider_name} gagal/diblokir (HTTP {resp.status_code}) untuk simbol '{symbol}'."
            )
        resp.raise_for_status()

    def _handle_request_exception(self, exc: requests.RequestException, provider_name: str, symbol: str) -> None:
        """Menangani requests.RequestException dan memetakan ke error domain."""
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

    def _fetch_binance_spot(self, symbol: str, interval: str, limit: int) -> pd.DataFrame:
        url = f"{BINANCE_API_BASE}{BINANCE_KLINES_PATH}"
        params = {"symbol": symbol.upper(), "interval": interval, "limit": limit}
        try:
            resp = self.session.get(url, params=params, timeout=DEFAULT_TIMEOUT_SECONDS)
            self._handle_response_status(resp, "Binance Spot", symbol)
            return parse_binance_like_klines(resp.json())
        except (SymbolNotFoundError, ProviderConnectionError):
            raise
        except requests.RequestException as exc:
            self._handle_request_exception(exc, "Binance Spot", symbol)

    def _fetch_mexc_spot(self, symbol: str, interval: str, limit: int) -> pd.DataFrame:
        url = f"{MEXC_API_BASE}{MEXC_KLINES_PATH}"
        mexc_interval = "1W" if interval.lower() == "1w" else interval
        params = {"symbol": symbol.upper(), "interval": mexc_interval, "limit": limit}
        try:
            resp = self.session.get(url, params=params, timeout=DEFAULT_TIMEOUT_SECONDS)
            self._handle_response_status(resp, "MEXC Spot", symbol)
            return parse_binance_like_klines(resp.json())
        except (SymbolNotFoundError, ProviderConnectionError):
            raise
        except requests.RequestException as exc:
            self._handle_request_exception(exc, "MEXC Spot", symbol)

    def _fetch_binance_futures(self, symbol: str, interval: str, limit: int) -> pd.DataFrame:
        url = f"{BINANCE_FUTURES_API_BASE}{BINANCE_FUTURES_KLINES_PATH}"
        params = {"symbol": symbol.upper(), "interval": interval, "limit": limit}
        try:
            resp = self.session.get(url, params=params, timeout=DEFAULT_TIMEOUT_SECONDS)
            self._handle_response_status(resp, "Binance Futures", symbol)
            return parse_binance_like_klines(resp.json())
        except (SymbolNotFoundError, ProviderConnectionError):
            raise
        except requests.RequestException as exc:
            self._handle_request_exception(exc, "Binance Futures", symbol)

    def _fetch_gateio_spot(self, symbol: str, interval: str, limit: int) -> pd.DataFrame:
        url = f"{GATEIO_API_BASE}{GATEIO_CANDLESTICKS_PATH}"
        pair = to_gateio_currency_pair(symbol)
        gate_interval = "7d" if interval.lower() in ("1w", "7d") else interval
        params = {"currency_pair": pair, "interval": gate_interval, "limit": limit}
        try:
            resp = self.session.get(url, params=params, timeout=DEFAULT_TIMEOUT_SECONDS)
            self._handle_response_status(resp, "Gate.io Spot", pair)
            return parse_gateio_candlesticks(resp.json())
        except (SymbolNotFoundError, ProviderConnectionError):
            raise
        except requests.RequestException as exc:
            self._handle_request_exception(exc, "Gate.io Spot", pair)

    def _notify_fallback(self, prev_prov: str, next_prov: str, reason: Optional[Any] = None) -> None:
        if not self.on_fallback:
            return
        try:
            self.on_fallback(prev_prov, next_prov, reason)
        except TypeError:
            try:
                self.on_fallback(prev_prov, next_prov)
            except Exception:
                pass

    def fetch_market_klines(
        self,
        symbol: str,
        daily_limit: int = 500,
        weekly_limit: int = 300,
        notify_fallback: bool = True,
    ) -> Tuple[pd.DataFrame, pd.DataFrame, str]:
        """Mengambil klines 1d & 1w dengan fallback chain otomatis dan domain short-circuit."""
        providers = [
            (
                "Binance Spot",
                "binance.com",
                lambda s: (
                    self._fetch_binance_spot(s, "1d", daily_limit),
                    self._fetch_binance_spot(s, "1w", weekly_limit),
                ),
            ),
            (
                "MEXC Spot",
                "mexc.com",
                lambda s: (
                    self._fetch_mexc_spot(s, "1d", daily_limit),
                    self._fetch_mexc_spot(s, "1w", weekly_limit),
                ),
            ),
            (
                "Binance Futures",
                "binance.com",
                lambda s: (
                    self._fetch_binance_futures(s, "1d", daily_limit),
                    self._fetch_binance_futures(s, "1w", weekly_limit),
                ),
            ),
            (
                "Gate.io Spot",
                "gate.io",
                lambda s: (
                    self._fetch_gateio_spot(s, "1d", daily_limit),
                    self._fetch_gateio_spot(s, "1w", weekly_limit),
                ),
            ),
        ]

        errors_log: List[str] = []
        connection_errors_count = 0
        symbol_not_found_count = 0
        other_errors_count = 0
        last_target_index: Optional[int] = None

        for i, (prov_name, domain, fetch_func) in enumerate(providers):
            if domain in self.unreachable_domains:
                errors_log.append(f"{prov_name}: Dilewati karena domain '{domain}' tidak dapat dijangkau (short-circuit).")
                connection_errors_count += 1

                # Cari provider berikutnya yang belum unreachable
                next_prov_name, next_idx = _find_next_reachable_provider(
                    providers, i + 1, self.unreachable_domains
                )

                if (
                    notify_fallback
                    and next_prov_name
                    and self.on_fallback
                    and domain not in self._notified_unreachable_domains
                    and (last_target_index is None or i >= last_target_index)
                ):
                    self._notify_fallback(prov_name, next_prov_name, FALLBACK_REASON_SHORT_CIRCUIT)
                    self._notified_unreachable_domains.add(domain)
                    last_target_index = next_idx
                elif notify_fallback and last_target_index is not None and i < last_target_index:
                    # Tandai domain yang otomatis terlewati dalam lompatan fallback agar tidak dilaporkan ulang
                    self._notified_unreachable_domains.add(domain)
                continue

            try:
                df_daily, df_weekly = fetch_func(symbol)
                if len(df_daily) > 0 and len(df_weekly) > 0:
                    return df_daily, df_weekly, prov_name
                raise DataFetchError(f"Data klines kosong di {prov_name}.")
            except Exception as exc:
                errors_log.append(f"{prov_name}: {exc}")

                if isinstance(exc, ProviderConnectionError):
                    self.unreachable_domains.add(domain)
                    connection_errors_count += 1
                    reason = FALLBACK_REASON_BLOCKED
                elif isinstance(exc, SymbolNotFoundError):
                    symbol_not_found_count += 1
                    reason = FALLBACK_REASON_NOT_FOUND
                else:
                    other_errors_count += 1
                    reason = FALLBACK_REASON_NOT_FOUND

                next_prov_name, next_idx = _find_next_reachable_provider(
                    providers, i + 1, self.unreachable_domains
                )

                if notify_fallback and next_prov_name and self.on_fallback:
                    self._notify_fallback(prov_name, next_prov_name, reason)
                    if isinstance(exc, ProviderConnectionError):
                        self._notified_unreachable_domains.add(domain)
                    last_target_index = next_idx

        # Evaluasi diagnosis kegagalan akhir
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

    def fetch_fear_and_greed(self) -> Tuple[Optional[int], Optional[str]]:
        """Mengambil indeks Fear & Greed terkini dari alternative.me."""
        try:
            resp = self.session.get(ALTERNATIVE_ME_FNG_URL, timeout=DEFAULT_TIMEOUT_SECONDS)
            resp.raise_for_status()
            data = resp.json()
            item = data.get("data", [])[0]
            return int(item["value"]), item["value_classification"]
        except Exception:
            return None, None

    def fetch_btc_performance(self, notify_fallback: bool = True) -> Tuple[Optional[float], Optional[float]]:
        """Mengambil kinerja persentase harga Bitcoin dalam 30 dan 90 hari terakhir."""
        try:
            df_btc, _, _ = self.fetch_market_klines(
                "BTCUSDT",
                daily_limit=95,
                weekly_limit=10,
                notify_fallback=notify_fallback,
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
        self,
        symbol: str,
        df_symbol_daily: pd.DataFrame,
    ) -> Optional[float]:
        """Menghitung performa relatif koin terhadap BTC selama 30 hari terakhir."""
        if is_btc_symbol(symbol):
            return None

        base_asset = extract_base_asset(symbol)
        direct_btc_pair = f"{base_asset}BTC"

        # Opsi 1: Cek pair langsung <COIN>BTC tanpa memicu log fallback simbol utama
        try:
            df_pair, _, _ = self.fetch_market_klines(
                direct_btc_pair,
                daily_limit=35,
                weekly_limit=10,
                notify_fallback=False,
            )
            if len(df_pair) >= 30:
                curr_val = df_pair["close"].iloc[-1]
                old_val = df_pair["close"].iloc[-30]
                if old_val > 0:
                    return float(((curr_val - old_val) / old_val) * 100.0)
        except Exception:
            pass

        # Opsi 2: Rasio sintetis terhadap BTCUSDT (tekan log fallback sekunder agar tidak membingungkan user)
        try:
            df_btc, _, _ = self.fetch_market_klines(
                "BTCUSDT",
                daily_limit=35,
                weekly_limit=10,
                notify_fallback=False,
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

    def fetch_usdt_idr_rate(self) -> float:
        """Mengambil kurs spot USDT/IDR dari Indodax dengan fallback otomatis ke CoinGecko."""
        # 1. Coba Indodax Ticker (Penyedia Primer)
        try:
            resp = self.session.get(INDODAX_TICKER_USDTIDR_URL, timeout=DEFAULT_TIMEOUT_SECONDS)
            resp.raise_for_status()
            data = resp.json()
            ticker = data.get("ticker", {})
            rate_val = ticker.get("last") or ticker.get("buy")
            if rate_val:
                rate = float(rate_val)
                if rate > 0:
                    return rate
            if self.on_fallback:
                self._notify_fallback("Indodax Ticker", "CoinGecko Simple Price", "Harga kurs Indodax tidak valid atau 0")
        except Exception as exc:
            if self.on_fallback:
                self._notify_fallback("Indodax Ticker", "CoinGecko Simple Price", exc)

        # 2. Coba CoinGecko Simple Price (Penyedia Sekunder)
        try:
            resp = self.session.get(COINGECKO_SIMPLE_PRICE_USDTIDR_URL, timeout=DEFAULT_TIMEOUT_SECONDS)
            resp.raise_for_status()
            data = resp.json()
            rate = float(data.get("tether", {}).get("idr", 0.0))
            if rate > 0:
                return rate
        except Exception:
            pass

        raise ProviderConnectionError(
            "Gagal mengambil kurs USDT/IDR dari seluruh bursa penyedia (Indodax & CoinGecko). "
            "Periksa koneksi internet Anda atau gunakan opsi --fx-rate untuk memasukkan kurs secara manual."
        )

    def fetch_context(self, symbol: str) -> MarketContext:
        """Mengambil seluruh data pasar dan sentimen dalam satu panggilan tunggal."""
        df_daily, df_weekly, source_exchange = self.fetch_market_klines(symbol)
        fg_score, fg_text = self.fetch_fear_and_greed()

        perf_vs_btc = None
        btc_30d, btc_90d = None, None

        if is_btc_symbol(symbol):
            # Penarikan BTC utama baru saja berjalan sehingga fallback tidak perlu dilaporkan ulang
            btc_30d, btc_90d = self.fetch_btc_performance(notify_fallback=False)
        else:
            perf_vs_btc = self.fetch_relative_performance_vs_btc(symbol, df_daily)

        return MarketContext(
            symbol=symbol,
            df_daily=df_daily,
            df_weekly=df_weekly,
            source_exchange=source_exchange,
            fear_greed_score=fg_score,
            fear_greed_text=fg_text,
            perf_vs_btc_30d=perf_vs_btc,
            btc_perf_30d=btc_30d,
            btc_perf_90d=btc_90d,
        )

