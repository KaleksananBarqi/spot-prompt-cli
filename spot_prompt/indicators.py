"""Kalkulasi indikator teknikal murni menggunakan vektorisasi Pandas dan NumPy."""

from typing import List, Optional, Tuple
import numpy as np
import pandas as pd

from spot_prompt.config import (
    ATR_WINDOW,
    BOLLINGER_STD_DEV,
    BOLLINGER_WINDOW,
    EMA_50D_WINDOW,
    POC_BINS,
    POC_DAYS,
    RSI_WINDOW,
    SMA_200D_WINDOW,
    SMA_200W_WINDOW,
)
from spot_prompt.models import (
    BollingerBands,
    IndicatorFacts,
    MiniCandle,
    PriceRange30D,
    VolumePOC,
)
from spot_prompt.normalizer import is_btc_symbol


def calculate_sma(series: pd.Series, window: int) -> pd.Series:
    """Menghitung Simple Moving Average (SMA)."""
    return series.rolling(window=window).mean()


def calculate_ema(series: pd.Series, window: int) -> pd.Series:
    """Menghitung Exponential Moving Average (EMA)."""
    return series.ewm(span=window, adjust=False).mean()


def calculate_rsi(series: pd.Series, window: int = RSI_WINDOW) -> pd.Series:
    """Menghitung Relative Strength Index (RSI) dengan metode penghalusan Wilder."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    # Wilder's smoothing menggunakan alpha = 1 / window
    avg_gain = gain.ewm(alpha=1.0 / window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / window, adjust=False).mean()

    # Hindari pembagian dengan nol
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    # Jika avg_loss nol, RSI = 100
    rsi = rsi.fillna(100.0)
    return rsi


def calculate_bollinger_bands(
    series: pd.Series,
    window: int = BOLLINGER_WINDOW,
    num_std: float = BOLLINGER_STD_DEV,
) -> Tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    """Menghitung Upper Band, Middle Band, Lower Band, dan metrik %B."""
    middle = series.rolling(window=window).mean()
    std = series.rolling(window=window).std()
    upper = middle + (num_std * std)
    lower = middle - (num_std * std)

    bandwidth = upper - lower
    pct_b = (series - lower) / bandwidth.replace(0, np.nan)
    return upper, middle, lower, pct_b


def calculate_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    window: int = ATR_WINDOW,
) -> pd.Series:
    """Menghitung Average True Range (ATR) dengan Wilder's smoothing."""
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.ewm(alpha=1.0 / window, adjust=False).mean()
    return atr


def calculate_volume_poc(
    df_daily: pd.DataFrame,
    days: int = POC_DAYS,
    num_bins: int = POC_BINS,
) -> Optional[VolumePOC]:
    """Menghitung Point of Control (POC) akumulasi volume selama 90 hari terakhir."""
    if len(df_daily) == 0:
        return None

    df_window = df_daily.tail(days).copy()
    if len(df_window) == 0:
        return None

    min_price = float(df_window["low"].min())
    max_price = float(df_window["high"].max())

    if min_price >= max_price:
        return VolumePOC(
            poc_price=min_price,
            poc_range_low=min_price,
            poc_range_high=max_price,
            total_volume=float(df_window["volume"].sum()),
        )

    bin_edges = np.linspace(min_price, max_price, num_bins + 1)
    bin_volumes = np.zeros(num_bins)

    # Distribusikan volume setiap candle ke dalam bucket yang terlewati rentang low-high
    for _, row in df_window.iterrows():
        c_low = row["low"]
        c_high = row["high"]
        c_vol = row["volume"]

        if c_high <= c_low or c_vol <= 0:
            # Jika doji sempurna atau tidak ada volume, letakkan pada bin terdekat
            idx = int(np.clip(np.searchsorted(bin_edges, c_low) - 1, 0, num_bins - 1))
            bin_volumes[idx] += c_vol
            continue

        # Temukan bin index yang bersinggungan
        start_idx = int(np.clip(np.searchsorted(bin_edges, c_low) - 1, 0, num_bins - 1))
        end_idx = int(np.clip(np.searchsorted(bin_edges, c_high) - 1, 0, num_bins - 1))

        covered_bins = max(1, end_idx - start_idx + 1)
        distributed_vol = c_vol / covered_bins
        bin_volumes[start_idx : end_idx + 1] += distributed_vol

    max_idx = int(np.argmax(bin_volumes))
    poc_low = float(bin_edges[max_idx])
    poc_high = float(bin_edges[max_idx + 1])
    poc_price = (poc_low + poc_high) / 2.0

    return VolumePOC(
        poc_price=poc_price,
        poc_range_low=poc_low,
        poc_range_high=poc_high,
        total_volume=float(df_window["volume"].sum()),
    )


def calculate_price_range_30d(df_daily: pd.DataFrame) -> PriceRange30D:
    """Menghitung rentang harga 30 hari dan posisi persentil harga terkini."""
    df_30 = df_daily.tail(30)
    low_30 = float(df_30["low"].min())
    high_30 = float(df_30["high"].max())
    current_price = float(df_daily["close"].iloc[-1])

    if high_30 <= low_30:
        percentile = 50.0
    else:
        percentile = ((current_price - low_30) / (high_30 - low_30)) * 100.0
        percentile = float(np.clip(percentile, 0.0, 100.0))

    return PriceRange30D(low=low_30, high=high_30, percentile=percentile)


def calculate_mini_candles(df_daily: pd.DataFrame, count: int = 5) -> List[MiniCandle]:
    """Menyiapkan ringkasan 5 candle harian terakhir."""
    subset = df_daily.tail(count + 20).copy()  # Tambah margin untuk kalkulasi rata-rata volume
    vol_mean_20 = subset["volume"].rolling(20).mean()
    subset["vol_ratio"] = subset["volume"] / vol_mean_20.replace(0, np.nan)

    result: List[MiniCandle] = []
    for _, row in subset.tail(count).iterrows():
        ts = row["timestamp"]
        dt = pd.to_datetime(ts, unit="ms", utc=True)
        date_str = dt.strftime("%Y-%m-%d")

        open_val = float(row["open"])
        close_val = float(row["close"])
        change_pct = ((close_val - open_val) / open_val) * 100.0 if open_val > 0 else 0.0

        v_ratio = float(row["vol_ratio"]) if not np.isnan(row["vol_ratio"]) else 1.0

        result.append(
            MiniCandle(
                date_str=date_str,
                close=close_val,
                change_pct=change_pct,
                volume_ratio=v_ratio,
            )
        )
    return result


def extract_indicator_facts(
    symbol: str,
    df_daily: pd.DataFrame,
    df_weekly: pd.DataFrame,
    fear_greed: Tuple[Optional[int], Optional[str]],
    perf_vs_btc_30d: Optional[float] = None,
    btc_perf_30d: Optional[float] = None,
    btc_perf_90d: Optional[float] = None,
) -> IndicatorFacts:
    """Mengagregasikan seluruh fakta indikator teknikal dari data daily dan weekly."""
    current_price = float(df_daily["close"].iloc[-1])
    price_range_30 = calculate_price_range_30d(df_daily)

    # 1. Moving Averages Harian
    sma_200d_series = calculate_sma(df_daily["close"], SMA_200D_WINDOW)
    sma_200d = float(sma_200d_series.iloc[-1]) if not np.isnan(sma_200d_series.iloc[-1]) else None
    sma_200d_dev = (((current_price - sma_200d) / sma_200d) * 100.0) if sma_200d else None

    ema_50d_series = calculate_ema(df_daily["close"], EMA_50D_WINDOW)
    ema_50d = float(ema_50d_series.iloc[-1]) if not np.isnan(ema_50d_series.iloc[-1]) else None
    ema_50d_dev = (((current_price - ema_50d) / ema_50d) * 100.0) if ema_50d else None

    # 2. 200-Week SMA (Penanganan Graceful jika riwayat < 200 minggu)
    sma_200w = None
    sma_200w_dev = None
    sma_200w_avail = False
    if len(df_weekly) >= SMA_200W_WINDOW:
        sma_200w_series = calculate_sma(df_weekly["close"], SMA_200W_WINDOW)
        val = sma_200w_series.iloc[-1]
        if not np.isnan(val):
            sma_200w = float(val)
            sma_200w_dev = ((current_price - sma_200w) / sma_200w) * 100.0
            sma_200w_avail = True

    # 3. Volume Profile POC 90-Hari
    poc = calculate_volume_poc(df_daily, days=POC_DAYS, num_bins=POC_BINS)

    # 4. Momentum: RSI Daily & Weekly
    rsi_daily_series = calculate_rsi(df_daily["close"], RSI_WINDOW)
    rsi_daily = float(rsi_daily_series.iloc[-1]) if not np.isnan(rsi_daily_series.iloc[-1]) else None

    rsi_weekly = None
    if len(df_weekly) >= RSI_WINDOW:
        rsi_weekly_series = calculate_rsi(df_weekly["close"], RSI_WINDOW)
        val = rsi_weekly_series.iloc[-1]
        if not np.isnan(val):
            rsi_weekly = float(val)

    # 5. Volatilitas: Bollinger Bands (20, 2) Daily & %B
    bb_u, bb_m, bb_l, bb_pct = calculate_bollinger_bands(df_daily["close"], BOLLINGER_WINDOW, BOLLINGER_STD_DEV)
    bollinger = BollingerBands(
        upper=float(bb_u.iloc[-1]),
        middle=float(bb_m.iloc[-1]),
        lower=float(bb_l.iloc[-1]),
        percent_b=float(bb_pct.iloc[-1]),
    )

    # 6. Volatilitas: ATR-14 Daily
    atr_series = calculate_atr(df_daily["high"], df_daily["low"], df_daily["close"], ATR_WINDOW)
    atr_val = float(atr_series.iloc[-1]) if not np.isnan(atr_series.iloc[-1]) else 0.0
    atr_pct = (atr_val / current_price) * 100.0 if current_price > 0 else 0.0

    # 7. Snapshot 5 Candle Harian Terakhir
    mini_candles = calculate_mini_candles(df_daily, count=5)

    fg_score, fg_text = fear_greed
    is_btc = is_btc_symbol(symbol)

    return IndicatorFacts(
        symbol=symbol,
        current_price=current_price,
        price_range_30d=price_range_30,
        sma_200w=sma_200w,
        sma_200w_dev_pct=sma_200w_dev,
        sma_200w_available=sma_200w_avail,
        sma_200d=sma_200d,
        sma_200d_dev_pct=sma_200d_dev,
        ema_50d=ema_50d,
        ema_50d_dev_pct=ema_50d_dev,
        poc_90d=poc,
        rsi_14_daily=rsi_daily,
        rsi_14_weekly=rsi_weekly,
        bollinger=bollinger,
        atr_14_daily=atr_val,
        atr_14_pct_of_price=atr_pct,
        fear_greed_score=fg_score,
        fear_greed_text=fg_text,
        perf_vs_btc_30d_pct=perf_vs_btc_30d,
        btc_perf_30d_pct=btc_perf_30d,
        btc_perf_90d_pct=btc_perf_90d,
        is_btc=is_btc,
        recent_candles=mini_candles,
    )
