"""Unit test untuk PromptPipeline, MarketDataClient, dan RawFactsAnalyzer."""

import json
import os
from unittest.mock import MagicMock
import pandas as pd
import pytest

from spot_prompt.analyzer import RawFactsAnalyzer
from spot_prompt.data_client import MarketContext, MarketDataClient
from spot_prompt.models import ExecutionConfig
from spot_prompt.pipeline import PipelineOptions, PromptPipeline

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.fixture
def mock_market_context():
    with open(os.path.join(FIXTURES_DIR, "mock_klines_daily.json")) as f:
        daily_json = json.load(f)
    with open(os.path.join(FIXTURES_DIR, "mock_klines_weekly.json")) as f:
        weekly_json = json.load(f)

    cols = ["timestamp", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "trades", "taker_base", "taker_quote", "ignore"]
    df_d = pd.DataFrame(daily_json, columns=cols)[["timestamp", "open", "high", "low", "close", "volume"]].apply(pd.to_numeric)
    df_w = pd.DataFrame(weekly_json, columns=cols)[["timestamp", "open", "high", "low", "close", "volume"]].apply(pd.to_numeric)

    return MarketContext(
        symbol="SOLUSDT",
        df_daily=df_d,
        df_weekly=df_w,
        source_exchange="Binance Spot",
        fear_greed_score=60,
        fear_greed_text="Greed",
        perf_vs_btc_30d=15.4,
    )


def test_raw_facts_analyzer_context(mock_market_context):
    facts = RawFactsAnalyzer.analyze_context(mock_market_context)
    assert facts.symbol == "SOLUSDT"
    assert facts.current_price > 0
    assert facts.sma_200d is not None
    assert facts.ema_50d is not None
    assert facts.poc_90d is not None
    assert facts.poc_90d.vah_price is not None
    assert facts.poc_90d.val_price is not None
    assert facts.bollinger is not None
    assert facts.atr_14_daily is not None
    assert facts.fear_greed_score == 60


def test_prompt_pipeline_execute(tmp_path, mock_market_context):
    mock_client = MagicMock(spec=MarketDataClient)
    mock_client.fetch_context.return_value = mock_market_context

    pipeline = PromptPipeline(data_client=mock_client)
    config = ExecutionConfig(symbol="SOLUSDT", budget=300.0, mode="moderate")
    options = PipelineOptions(
        output_dir=str(tmp_path),
        save_to_disk=True,
        copy_clipboard=False,
    )

    result = pipeline.execute(config, options=options)
    assert result.symbol == "SOLUSDT"
    assert result.source_exchange == "Binance Spot"
    assert "SOLUSDT" in result.rendered_prompt
    assert "Point of Control" in result.rendered_prompt
    assert result.saved_filepath is not None
    assert os.path.exists(result.saved_filepath)

    with open(result.saved_filepath, "r", encoding="utf-8") as f:
        file_content = f.read()
    assert file_content == result.rendered_prompt


def test_prompt_pipeline_execute_idr(tmp_path, mock_market_context):
    mock_client = MagicMock(spec=MarketDataClient)
    btc_context = MarketContext(
        symbol="BTCUSDT",
        df_daily=mock_market_context.df_daily,
        df_weekly=mock_market_context.df_weekly,
        source_exchange="Binance Spot",
        fear_greed_score=60,
        fear_greed_text="Greed",
        btc_perf_30d=10.0,
        btc_perf_90d=25.0,
    )
    mock_client.fetch_context.return_value = btc_context
    mock_client.fetch_usdt_idr_rate.return_value = 18000.0

    pipeline = PromptPipeline(data_client=mock_client)
    config = ExecutionConfig(symbol="BTCIDR", budget=1500000.0, mode="conservative")
    options = PipelineOptions(
        output_dir=str(tmp_path),
        save_to_disk=True,
        copy_clipboard=False,
    )

    result = pipeline.execute(config, options=options)
    assert result.symbol == "BTC/IDR"
    assert result.facts.currency == "IDR"
    assert result.facts.fx_rate == 18000.0
    assert result.facts.is_btc is True
    assert "BTC/IDR" in result.rendered_prompt
    assert "Rp 1.500.000" in result.rendered_prompt
    mock_client.fetch_context.assert_called_once_with("BTCUSDT")

