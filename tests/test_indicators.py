"""Unit test untuk kalkulasi indikator teknikal (Pandas/NumPy)."""

import json
import os
import pandas as pd
import pytest

from spot_prompt.indicators import (
    calculate_atr,
    calculate_bollinger_bands,
    calculate_ema,
    calculate_mini_candles,
    calculate_price_range_30d,
    calculate_rsi,
    calculate_sma,
    calculate_volume_poc,
    extract_indicator_facts,
)

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.fixture
def daily_df():
    with open(os.path.join(FIXTURES_DIR, "mock_klines_daily.json")) as f:
        raw = json.load(f)
    df = pd.DataFrame(
        raw,
        columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades", "taker_base", "taker_quote", "ignore",
        ],
    )
    df = df[["timestamp", "open", "high", "low", "close", "volume"]].copy()
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col])
    df["timestamp"] = pd.to_numeric(df["timestamp"])
    return df


@pytest.fixture
def weekly_df():
    with open(os.path.join(FIXTURES_DIR, "mock_klines_weekly.json")) as f:
        raw = json.load(f)
    df = pd.DataFrame(
        raw,
        columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades", "taker_base", "taker_quote", "ignore",
        ],
    )
    df = df[["timestamp", "open", "high", "low", "close", "volume"]].copy()
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col])
    df["timestamp"] = pd.to_numeric(df["timestamp"])
    return df


def test_calculate_sma(daily_df):
    sma = calculate_sma(daily_df["close"], window=200)
    assert len(sma) == len(daily_df)
    assert pd.isna(sma.iloc[198])
    assert not pd.isna(sma.iloc[199])
    assert sma.iloc[-1] > 0


def test_calculate_ema(daily_df):
    ema = calculate_ema(daily_df["close"], window=50)
    assert len(ema) == len(daily_df)
    assert not pd.isna(ema.iloc[-1])
    assert ema.iloc[-1] > 0


def test_calculate_rsi(daily_df):
    rsi = calculate_rsi(daily_df["close"], window=14)
    assert len(rsi) == len(daily_df)
    last_rsi = rsi.iloc[-1]
    assert 0.0 <= last_rsi <= 100.0


def test_calculate_bollinger_bands(daily_df):
    upper, middle, lower, pct_b = calculate_bollinger_bands(daily_df["close"], window=20, num_std=2.0)
    assert len(upper) == len(daily_df)
    u_val = upper.iloc[-1]
    m_val = middle.iloc[-1]
    l_val = lower.iloc[-1]
    b_val = pct_b.iloc[-1]

    assert u_val > m_val > l_val
    assert isinstance(b_val, float)


def test_calculate_atr(daily_df):
    atr = calculate_atr(daily_df["high"], daily_df["low"], daily_df["close"], window=14)
    assert len(atr) == len(daily_df)
    assert atr.iloc[-1] > 0


def test_calculate_volume_poc_and_value_area(daily_df):
    poc = calculate_volume_poc(daily_df, days=90, num_bins=100)
    assert poc is not None
    assert poc.poc_range_low <= poc.poc_price <= poc.poc_range_high
    assert poc.val_price is not None
    assert poc.vah_price is not None
    assert poc.val_price <= poc.poc_price <= poc.vah_price
    assert poc.total_volume > 0


def test_calculate_mini_candles_closed_and_running_status(daily_df):
    candles = calculate_mini_candles(daily_df, count=5)
    assert len(candles) == 5
    assert [c.is_closed for c in candles] == [True, True, True, True, False]

    # Pastikan perubahan volume ekstrem di candle terakhir (running) tidak mendilusi vol_ratio 4 candle closed
    mutated_df = daily_df.copy()
    mutated_df.loc[mutated_df.index[-1], "volume"] = 0.0001
    mutated_candles = calculate_mini_candles(mutated_df, count=5)
    for i in range(4):
        assert candles[i].volume_ratio == pytest.approx(mutated_candles[i].volume_ratio)
    assert mutated_candles[4].volume_ratio < 0.01


def test_calculate_price_range_30d(daily_df):
    pr = calculate_price_range_30d(daily_df)
    assert pr.low <= pr.high
    assert 0.0 <= pr.percentile <= 100.0


def test_extract_indicator_facts_full(daily_df, weekly_df):
    facts = extract_indicator_facts(
        symbol="SOLUSDT",
        df_daily=daily_df,
        df_weekly=weekly_df,
        fear_greed=(35, "Fear"),
        perf_vs_btc_30d=5.2,
    )
    assert facts.symbol == "SOLUSDT"
    assert facts.current_price > 0
    assert facts.sma_200w_available is True
    assert facts.sma_200w is not None
    assert facts.sma_200d is not None
    assert facts.ema_50d is not None
    assert facts.poc_90d is not None
    assert facts.poc_90d.val_price <= facts.poc_90d.poc_price <= facts.poc_90d.vah_price
    assert facts.rsi_14_daily is not None
    assert facts.rsi_14_weekly is not None
    assert facts.bollinger is not None
    assert facts.fear_greed_score == 35
    assert facts.fear_greed_text == "Fear"
    assert facts.perf_vs_btc_30d_pct == 5.2
    assert len(facts.recent_candles) == 5
    assert facts.recent_candles[-1].is_closed is False
    assert all(c.is_closed for c in facts.recent_candles[:-1])


def test_extract_indicator_facts_closed_candle_isolation(daily_df, weekly_df):
    """Memastikan fluktuasi candle berjalan (iloc[-1]) tidak mengubah baseline indikator closed,
    tetapi memperbarui current_price, deviasi MA, dan posisi %B."""
    base_facts = extract_indicator_facts(
        symbol="BTCUSDT",
        df_daily=daily_df,
        df_weekly=weekly_df,
        fear_greed=(50, "Neutral"),
    )

    live_mutated_daily = daily_df.copy()
    live_mutated_weekly = weekly_df.copy()
    # Ubah harga close, rentang high-low, dan volume pada baris terakhir (running candle)
    new_live_price = float(daily_df["close"].iloc[-1]) * 1.15
    live_mutated_daily.loc[live_mutated_daily.index[-1], "close"] = new_live_price
    live_mutated_daily.loc[live_mutated_daily.index[-1], "high"] = new_live_price * 1.20
    live_mutated_daily.loc[live_mutated_daily.index[-1], "low"] = new_live_price * 0.50
    live_mutated_daily.loc[live_mutated_daily.index[-1], "volume"] = 999999999.0
    live_mutated_weekly.loc[live_mutated_weekly.index[-1], "close"] = new_live_price

    mutated_facts = extract_indicator_facts(
        symbol="BTCUSDT",
        df_daily=live_mutated_daily,
        df_weekly=live_mutated_weekly,
        fear_greed=(50, "Neutral"),
    )

    # Baseline indikator closed wajib identik (bebas intraday repainting)
    assert mutated_facts.sma_200d == pytest.approx(base_facts.sma_200d)
    assert mutated_facts.ema_50d == pytest.approx(base_facts.ema_50d)
    assert mutated_facts.sma_200w == pytest.approx(base_facts.sma_200w)
    assert mutated_facts.rsi_14_daily == pytest.approx(base_facts.rsi_14_daily)
    assert mutated_facts.rsi_14_weekly == pytest.approx(base_facts.rsi_14_weekly)
    assert mutated_facts.atr_14_daily == pytest.approx(base_facts.atr_14_daily)
    assert mutated_facts.bollinger.upper == pytest.approx(base_facts.bollinger.upper)
    assert mutated_facts.bollinger.middle == pytest.approx(base_facts.bollinger.middle)
    assert mutated_facts.bollinger.lower == pytest.approx(base_facts.bollinger.lower)
    assert mutated_facts.poc_90d.poc_price == pytest.approx(base_facts.poc_90d.poc_price)
    assert mutated_facts.poc_90d.val_price == pytest.approx(base_facts.poc_90d.val_price)
    assert mutated_facts.poc_90d.vah_price == pytest.approx(base_facts.poc_90d.vah_price)

    # Namun current_price, deviasi %, dan %B live wajib berubah mengikuti harga terkini
    assert mutated_facts.current_price == pytest.approx(new_live_price)
    assert mutated_facts.sma_200d_dev_pct > base_facts.sma_200d_dev_pct
    assert mutated_facts.bollinger.percent_b > base_facts.bollinger.percent_b


def test_extract_indicator_facts_short_history_graceful(daily_df, weekly_df):
    # Simulasi koin baru dengan hanya 50 candle mingguan (< 200)
    short_weekly = weekly_df.tail(50).copy()
    facts = extract_indicator_facts(
        symbol="SUIUSDT",
        df_daily=daily_df,
        df_weekly=short_weekly,
        fear_greed=(28, "Extreme Fear"),
        perf_vs_btc_30d=-2.1,
    )
    assert facts.sma_200w_available is False
    assert facts.sma_200w is None
    assert facts.sma_200w_dev_pct is None
    # 200D SMA tetap ada karena daily_df cukup
    assert facts.sma_200d is not None
