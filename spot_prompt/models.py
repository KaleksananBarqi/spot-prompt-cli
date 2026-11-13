"""Model data dan struktur kontainer fakta pasar untuk spot-prompt."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


def _format_rupiah_int(amount: float) -> str:
    """Helper privat untuk memformat nominal integer Rupiah dengan pemisah titik."""
    return f"Rp {int(round(amount)):,}".replace(",", ".")


def format_idr_amount(amount: float) -> str:
    """Memformat nominal Rupiah (budget atau notional) dengan pemisah ribuan titik."""
    if amount >= 100:
        return _format_rupiah_int(amount)
    return f"Rp {amount:.2f}".replace(".", ",")


def format_adaptive_price(price: float, currency: str = "USDT") -> str:
    """Memformat harga secara adaptif berdasarkan mata uang dan nilai tick.

    Untuk IDR:
    - price >= 100: bilangan bulat dengan pemisah titik (misal 'Rp 1.050.234.000')
    - 1 <= price < 100: 2 digit desimal (misal 'Rp 12,50')
    - 0.01 <= price < 1: 4 digit desimal (misal 'Rp 0,2850')
    - price < 0.01: 6 digit desimal presisi untuk koin mikro (misal 'Rp 0,004512')

    Untuk USDT:
    - price >= 0.01: format 4 desimal standar ('145.2000' atau '1.2345')
    - price < 0.01: format 6 desimal presisi ('0.000015')
    """
    if currency.upper() == "IDR":
        if price >= 100:
            return _format_rupiah_int(price)
        elif price >= 1:
            return f"Rp {price:.2f}".replace(".", ",")
        elif price >= 0.01:
            return f"Rp {price:.4f}".replace(".", ",")
        else:
            return f"Rp {price:.6f}".replace(".", ",")
    else:
        if price >= 0.01:
            return f"{price:,.4f}"
        return f"{price:,.6f}"


def format_currency_amount(amount: float, currency: str = "USDT", is_unit_price: bool = False) -> str:
    """Antarmuka kanonikal untuk memformat angka mata uang (harga satuan atau total budget)."""
    if is_unit_price:
        return format_adaptive_price(amount, currency)
    if currency.upper() == "IDR":
        return format_idr_amount(amount)
    return f"{amount:,.2f} {currency.upper()}"


def format_dual_currency_price(
    price_usdt: float,
    fx_rate: Optional[float] = None,
    currency: str = "USDT",
    include_unit: bool = False,
) -> str:
    """Menghasilkan format harga Dual-Currency jika currency == IDR, atau format standar untuk USDT."""
    norm_currency = (currency or "USDT").upper()
    if norm_currency == "IDR" and fx_rate and fx_rate > 0:
        idr_price = price_usdt * fx_rate
        idr_str = format_adaptive_price(idr_price, "IDR")
        if price_usdt >= 100:
            usdt_str = f"${price_usdt:,.2f}"
        elif price_usdt >= 0.01:
            usdt_str = f"${price_usdt:,.4f}"
        else:
            usdt_str = f"${price_usdt:,.6f}"
        return f"{idr_str} (~{usdt_str} USDT)"
    base_str = format_adaptive_price(price_usdt, "USDT")
    if include_unit:
        unit = norm_currency if norm_currency != "IDR" else "USDT"
        return f"{base_str} {unit}"
    return base_str


def format_price_with_unit(
    price_usdt: float,
    fx_rate: Optional[float] = None,
    currency: str = "USDT",
) -> str:
    """Memformat harga lengkap dengan label unit mata uang (untuk filter Jinja2 price_with_unit)."""
    return format_dual_currency_price(
        price_usdt,
        fx_rate=fx_rate,
        currency=currency,
        include_unit=True,
    )


@dataclass
class Candle:
    """Representasi satu candlestick OHLCV."""
    timestamp: int  # epoch milliseconds
    open: float
    high: float
    low: float
    close: float
    volume: float

    @property
    def datetime_utc(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp / 1000.0)


@dataclass
class PriceRange30D:
    """Rentang harga 30 hari dan posisi persentil harga saat ini."""
    low: float
    high: float
    percentile: float  # 0.0 - 100.0


@dataclass
class BollingerBands:
    """Nilai Bollinger Bands (20, 2) dan metrik %B."""
    upper: float
    middle: float
    lower: float
    percent_b: float


@dataclass
class VolumePOC:
    """Point of Control (POC) dan Value Area (70% VAH/VAL) berdasarkan distribusi volume 90 hari."""
    poc_price: float
    poc_range_low: float
    poc_range_high: float
    total_volume: float
    vah_price: Optional[float] = None
    val_price: Optional[float] = None


@dataclass
class MiniCandle:
    """Snapshot ringkas candle harian terkini."""
    date_str: str
    close: float
    change_pct: float
    volume_ratio: float  # volume / rata-rata volume 20H closed
    is_closed: bool = True


@dataclass
class VWAPFacts:
    """Fakta jangkar valuasi VWAP berbasis Closed-Candle Baseline (Q-VWAP dan 365D R-VWAP)."""
    q_vwap: Optional[float] = None
    q_vwap_upper_1: Optional[float] = None
    q_vwap_lower_1: Optional[float] = None
    q_vwap_upper_2: Optional[float] = None
    q_vwap_lower_2: Optional[float] = None
    q_vwap_dev_pct: Optional[float] = None
    quarter_label: Optional[str] = None
    quarter_start_date: Optional[str] = None
    quarter_candles_count: int = 0
    r_vwap_365d: Optional[float] = None
    r_vwap_365d_dev_pct: Optional[float] = None
    r_vwap_365d_available: bool = False
    available_closed_days: int = 0


@dataclass
class ExecutionGuardrails:
    """Nilai batas guardrail kuantitatif siap-pakai hasil kalkulasi Python untuk rendering template."""
    half_atr: float = 0.0
    max_l1_price: Optional[float] = None
    crash_3x_price: Optional[float] = None
    crash_5x_price: Optional[float] = None
    q_vwap_lower_2_target: Optional[float] = None
    r_vwap_365d_target: Optional[float] = None
    sma_200w_target: Optional[float] = None
    consolidation_threshold: float = 20.0


@dataclass
class IndicatorFacts:
    """Fakta objektif indikator teknikal dan konteks pasar makro."""
    symbol: str
    current_price: float
    price_range_30d: PriceRange30D

    # Valuasi Makro (Moving Averages)
    sma_200w: Optional[float] = None
    sma_200w_dev_pct: Optional[float] = None
    sma_200w_available: bool = True
    sma_200d: Optional[float] = None
    sma_200d_dev_pct: Optional[float] = None
    ema_50d: Optional[float] = None
    ema_50d_dev_pct: Optional[float] = None

    # Volume Profile & Jangkar VWAP
    poc_90d: Optional[VolumePOC] = None
    vwap: Optional[VWAPFacts] = None

    # Momentum & Volatilitas
    rsi_14_daily: Optional[float] = None
    rsi_14_weekly: Optional[float] = None
    bollinger: Optional[BollingerBands] = None
    atr_14_daily: Optional[float] = None
    atr_14_pct_of_price: Optional[float] = None

    # Sentimen & Makro
    fear_greed_score: Optional[int] = None
    fear_greed_text: Optional[str] = None
    perf_vs_btc_30d_pct: Optional[float] = None
    btc_perf_30d_pct: Optional[float] = None
    btc_perf_90d_pct: Optional[float] = None
    is_btc: bool = False

    # Sumber Data
    source_exchange: str = "Binance Spot"

    # Snapshot mikro
    recent_candles: List[MiniCandle] = field(default_factory=list)

    # Konteks Mata Uang & Valuasi Lokal
    currency: str = "USDT"
    fx_rate: Optional[float] = None
    min_notional: float = 10.0
    display_symbol: Optional[str] = None

    # Stempel Waktu Snapshot Data (UTC & WIB)
    snapshot_timestamp_utc: Optional[str] = None
    snapshot_timestamp_wib: Optional[str] = None

    # Guardrail Kuantitatif Terkomputasi
    guardrails: Optional[ExecutionGuardrails] = None


@dataclass
class ExecutionConfig:
    """Konfigurasi eksekusi DCA yang diinputkan pengguna."""
    symbol: str
    budget: Optional[float] = None
    currency: str = "USDT"
    mode: str = "moderate"  # 'conservative', 'moderate', 'aggressive'
    fx_rate: Optional[float] = None
    display_symbol: Optional[str] = None
