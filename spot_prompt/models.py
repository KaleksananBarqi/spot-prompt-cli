"""Model data dan struktur kontainer fakta pasar untuk spot-prompt."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


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
    """Point of Control (POC) berdasarkan volume distribution 90 hari."""
    poc_price: float
    poc_range_low: float
    poc_range_high: float
    total_volume: float


@dataclass
class MiniCandle:
    """Snapshot ringkas candle harian terkini."""
    date_str: str
    close: float
    change_pct: float
    volume_ratio: float  # volume / rata-rata volume


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

    # Volume Profile
    poc_90d: Optional[VolumePOC] = None

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


@dataclass
class ExecutionConfig:
    """Konfigurasi eksekusi DCA yang diinputkan pengguna."""
    symbol: str
    budget: Optional[float] = None
    currency: str = "USDT"
    mode: str = "moderate"  # 'conservative', 'moderate', 'aggressive'
