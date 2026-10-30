"""Unit test untuk kalkulasi indikator teknikal (Pandas/NumPy)."""

import json
import os
import pandas as pd
import pytest

from spot_prompt.indicators import (
    calculate_atr,
    calculate_bollinger_bands,
    calculate_ema,
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


def test_calculate_volume_poc(daily_df):
    poc = calculate_volume_poc(daily_df, days=90, num_bins=100)
    assert poc is not None
    assert poc.poc_range_low <= poc.poc_price <= poc.poc_range_high
    assert poc.total_volume > 0


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
    assert facts.rsi_14_daily is not None
    assert facts.rsi_14_weekly is not None
    assert facts.bollinger is not None
    assert facts.fear_greed_score == 35
    assert facts.fear_greed_text == "Fear"
    assert facts.perf_vs_btc_30d_pct == 5.2
    assert len(facts.recent_candles) == 5


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
