"""Unit test untuk Jinja2 template rendering."""

from spot_prompt.models import (
    BollingerBands,
    ExecutionConfig,
    IndicatorFacts,
    MiniCandle,
    PriceRange30D,
    VolumePOC,
)
from spot_prompt.template_renderer import render_spot_prompt


def test_render_spot_prompt_conservative():
    facts = IndicatorFacts(
        symbol="SOLUSDT",
        current_price=145.20,
        price_range_30d=PriceRange30D(low=128.0, high=162.5, percentile=49.8),
        sma_200w=105.0,
        sma_200w_dev_pct=38.28,
        sma_200w_available=True,
        sma_200d=138.0,
        sma_200d_dev_pct=5.21,
        ema_50d=151.0,
        ema_50d_dev_pct=-3.84,
        poc_90d=VolumePOC(poc_price=137.5, poc_range_low=135.0, poc_range_high=140.0, total_volume=500000),
        rsi_14_daily=41.5,
        rsi_14_weekly=48.2,
        bollinger=BollingerBands(upper=160.0, middle=150.0, lower=140.0, percent_b=0.26),
        atr_14_daily=6.80,
        atr_14_pct_of_price=4.68,
        fear_greed_score=32,
        fear_greed_text="Fear",
        perf_vs_btc_30d_pct=-4.5,
        recent_candles=[
            MiniCandle(date_str="2026-10-25", close=142.0, change_pct=-1.2, volume_ratio=0.9),
            MiniCandle(date_str="2026-10-26", close=144.5, change_pct=1.76, volume_ratio=1.1),
        ],
    )
    config = ExecutionConfig(
        symbol="SOLUSDT",
        budget=500.0,
        currency="USDT",
        mode="conservative",
    )

    prompt = render_spot_prompt(facts, config)

    assert "SOLUSDT" in prompt
    assert "500.00 USDT" in prompt
    assert "CONSERVATIVE" in prompt
    assert "145.2000" in prompt
    assert "200-Week SMA" in prompt
    assert "105.0000" in prompt
    assert "+38.28%" in prompt
    assert "Point of Control (POC)" in prompt
    assert "Crypto Fear & Greed Index: 32 (Fear)" in prompt
    assert "Performa Relatif vs Bitcoin (30 Hari): -4.50%" in prompt
    assert "Underperforming Bitcoin" in prompt
    assert "INSTRUKSI OUTPUT" in prompt


def test_render_spot_prompt_young_coin_na():
    facts = IndicatorFacts(
        symbol="SUIUSDT",
        current_price=2.15,
        price_range_30d=PriceRange30D(low=1.80, high=2.30, percentile=70.0),
        sma_200w=None,
        sma_200w_dev_pct=None,
        sma_200w_available=False,
        sma_200d=1.95,
        sma_200d_dev_pct=10.25,
        ema_50d=2.05,
        ema_50d_dev_pct=4.87,
        poc_90d=VolumePOC(poc_price=1.90, poc_range_low=1.85, poc_range_high=1.95, total_volume=20000),
        rsi_14_daily=55.0,
        rsi_14_weekly=None,
        bollinger=BollingerBands(upper=2.40, middle=2.10, lower=1.80, percent_b=0.58),
        atr_14_daily=0.12,
        atr_14_pct_of_price=5.58,
        fear_greed_score=60,
        fear_greed_text="Greed",
        perf_vs_btc_30d_pct=12.5,
    )
    config = ExecutionConfig(
        symbol="SUIUSDT",
        budget=None,
        currency="USDT",
        mode="aggressive",
    )

    prompt = render_spot_prompt(facts, config)

    assert "SUIUSDT" in prompt
    assert "AGGRESSIVE" in prompt
    assert "N/A (Riwayat perdagangan koin di bursa belum mencapai 200 minggu)" in prompt
    assert "Outperforming Bitcoin" in prompt
