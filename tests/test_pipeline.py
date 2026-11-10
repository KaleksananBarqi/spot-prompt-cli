"""Unit test untuk PromptPipeline, MarketDataClient, dan RawFactsAnalyzer."""

import json
import os
from datetime import datetime, timedelta, timezone
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


def test_prompt_pipeline_embeds_deterministic_snapshot_timestamp(tmp_path, mock_market_context):
    """Memastikan PromptPipeline menyematkan stempel waktu snapshot UTC dan WIB deterministik."""
    mock_client = MagicMock(spec=MarketDataClient)
    mock_client.fetch_context.return_value = mock_market_context

    pipeline = PromptPipeline(data_client=mock_client)
    config = ExecutionConfig(symbol="SOLUSDT", budget=300.0, mode="moderate")
    fixed_utc = datetime(2026, 11, 10, 14, 30, 5, tzinfo=timezone.utc)
    options = PipelineOptions(
        output_dir=str(tmp_path),
        save_to_disk=True,
        copy_clipboard=False,
        snapshot_time=fixed_utc,
    )

    result = pipeline.execute(config, options=options)

    assert result.facts is not None
    assert result.facts.snapshot_timestamp_utc == "2026-11-10 14:30:05 UTC"
    assert result.facts.snapshot_timestamp_wib == "2026-11-10 21:30:05 WIB (UTC+7)"
    assert (
        "- Data Snapshot Timestamp: 2026-11-10 14:30:05 UTC | 2026-11-10 21:30:05 WIB (UTC+7)"
        in result.rendered_prompt
    )
    assert result.saved_filepath is not None
    assert "2026-11-10-14-30-05-UTC" in os.path.basename(result.saved_filepath)


def test_prompt_pipeline_normalizes_non_utc_and_naive_snapshot_time(tmp_path, mock_market_context):
    """Memastikan sumber waktu aware non-UTC maupun naive dikonversi secara deterministik ke UTC dan WIB."""
    mock_client = MagicMock(spec=MarketDataClient)
    mock_client.fetch_context.return_value = mock_market_context

    pipeline = PromptPipeline(data_client=mock_client)
    config = ExecutionConfig(symbol="SOLUSDT", budget=300.0, mode="moderate")

    # Aware WIB (UTC+7): 2026-11-10 21:30:05+07:00 == 2026-11-10 14:30:05 UTC
    wib_input = datetime(2026, 11, 10, 21, 30, 5, tzinfo=timezone(timedelta(hours=7)))
    res_wib = pipeline.execute(
        config,
        options=PipelineOptions(save_to_disk=False, copy_clipboard=False, snapshot_time=wib_input),
    )
    assert res_wib.facts.snapshot_timestamp_utc == "2026-11-10 14:30:05 UTC"
    assert res_wib.facts.snapshot_timestamp_wib == "2026-11-10 21:30:05 WIB (UTC+7)"

    # Naive datetime diperlakukan sebagai UTC
    naive_input = datetime(2026, 11, 10, 14, 30, 5)
    res_naive = pipeline.execute(
        config,
        options=PipelineOptions(save_to_disk=False, copy_clipboard=False, snapshot_time=naive_input),
    )
    assert res_naive.facts.snapshot_timestamp_utc == "2026-11-10 14:30:05 UTC"
    assert res_naive.facts.snapshot_timestamp_wib == "2026-11-10 21:30:05 WIB (UTC+7)"


def _make_constant_atr_context(
    symbol: str = "HYPEUSDT",
    current_price: float = 100.0,
    daily_tr: float = 10.0,
) -> MarketContext:
    """Membuat MarketContext sintetis dengan True Range harian konstan agar ATR-14 terprediksi eksak."""
    half_tr = daily_tr / 2.0
    base_ts = int(datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc).timestamp() * 1000)
    day_ms = 86_400_000
    week_ms = 7 * day_ms

    daily_rows = [
        {
            "timestamp": base_ts + i * day_ms,
            "open": current_price,
            "high": current_price + half_tr,
            "low": current_price - half_tr,
            "close": current_price,
            "volume": 1000.0,
        }
        for i in range(35)
    ]
    weekly_rows = [
        {
            "timestamp": base_ts + i * week_ms,
            "open": current_price,
            "high": current_price + half_tr,
            "low": current_price - half_tr,
            "close": current_price,
            "volume": 7000.0,
        }
        for i in range(20)
    ]

    return MarketContext(
        symbol=symbol,
        df_daily=pd.DataFrame(daily_rows),
        df_weekly=pd.DataFrame(weekly_rows),
        source_exchange="Binance Spot",
        fear_greed_score=45,
        fear_greed_text="Fear",
        perf_vs_btc_30d=-3.2,
    )


def test_prompt_pipeline_includes_pre_execution_staleness_check():
    """Memastikan prompt menyertakan Pre-Execution Staleness Check terhadap batas 0.5x ATR-14 dan Level 1."""
    mock_client = MagicMock(spec=MarketDataClient)
    mock_client.fetch_context.return_value = _make_constant_atr_context(
        symbol="HYPEUSDT",
        current_price=100.0,
        daily_tr=10.0,
    )

    pipeline = PromptPipeline(data_client=mock_client)
    config = ExecutionConfig(symbol="HYPE", budget=300.0, mode="aggressive")
    fixed_utc = datetime(2026, 11, 10, 14, 30, 0, tzinfo=timezone.utc)
    result = pipeline.execute(
        config,
        options=PipelineOptions(save_to_disk=False, copy_clipboard=False, snapshot_time=fixed_utc),
    )

    prompt = result.rendered_prompt
    assert "Pre-Execution Staleness Check" in prompt
    assert "2026-11-10 14:30:00 UTC" in prompt
    assert "2026-11-10 21:30:00 WIB (UTC+7)" in prompt
    assert "5.0000 USDT" in prompt
    assert "Level 1" in prompt
    assert "generate ulang" in prompt.lower()


def test_prompt_pipeline_enforces_l1_anti_overlap_distance_usdt():
    """Memastikan aturan kuantitatif dan Self-Check menegakkan jarak Harga Terkini - Level 1 >= 0.5x ATR-14 dalam USDT."""
    mock_client = MagicMock(spec=MarketDataClient)
    mock_client.fetch_context.return_value = _make_constant_atr_context(
        symbol="HYPEUSDT",
        current_price=100.0,
        daily_tr=10.0,
    )

    pipeline = PromptPipeline(data_client=mock_client)
    config = ExecutionConfig(symbol="HYPE", budget=300.0, mode="aggressive")
    fixed_utc = datetime(2026, 11, 10, 14, 30, 0, tzinfo=timezone.utc)
    result = pipeline.execute(
        config,
        options=PipelineOptions(save_to_disk=False, copy_clipboard=False, snapshot_time=fixed_utc),
    )

    prompt = result.rendered_prompt
    quant_section, self_check_section = prompt.split("Self-Check Validasi Kuantitatif", maxsplit=1)

    assert "Harga Terkini - Level 1 >= 5.0000 USDT" in quant_section
    assert "0.5x ATR-14" in quant_section
    assert "95.0000" in quant_section

    assert "Harga Terkini - Level 1 >= 5.0000 USDT" in self_check_section
    assert "0.5x ATR-14" in self_check_section


def test_prompt_pipeline_enforces_l1_anti_overlap_and_staleness_dual_currency_idr():
    """Memastikan guardrail timeline sync dan anti-overlap L1 terformat Dual-Currency Display untuk mode IDR."""
    mock_client = MagicMock(spec=MarketDataClient)
    mock_client.fetch_context.return_value = _make_constant_atr_context(
        symbol="HYPEUSDT",
        current_price=100.0,
        daily_tr=10.0,
    )
    mock_client.fetch_usdt_idr_rate.return_value = 18000.0

    pipeline = PromptPipeline(data_client=mock_client)
    config = ExecutionConfig(symbol="HYPEIDR", budget=1500000.0, mode="aggressive")
    fixed_utc = datetime(2026, 11, 10, 14, 30, 0, tzinfo=timezone.utc)
    result = pipeline.execute(
        config,
        options=PipelineOptions(save_to_disk=False, copy_clipboard=False, snapshot_time=fixed_utc),
    )

    prompt = result.rendered_prompt
    assert (
        "- Data Snapshot Timestamp: 2026-11-10 14:30:00 UTC | 2026-11-10 21:30:00 WIB (UTC+7)"
        in prompt
    )
    assert "Pre-Execution Staleness Check" in prompt

    quant_section, self_check_section = prompt.split("Self-Check Validasi Kuantitatif", maxsplit=1)
    assert "Harga Terkini - Level 1 >= Rp 90.000 (~$5.0000 USDT)" in quant_section
    assert "Rp 1.710.000 (~$95.0000 USDT)" in quant_section
    assert "Harga Terkini - Level 1 >= Rp 90.000 (~$5.0000 USDT)" in self_check_section
    mock_client.fetch_context.assert_called_once_with("HYPEUSDT")


def test_prompt_pipeline_populates_default_snapshot_timestamp_when_omitted(mock_market_context):
    """Memastikan stempel waktu UTC dan WIB tetap terisi otomatis saat snapshot_time tidak disetel."""
    mock_client = MagicMock(spec=MarketDataClient)
    mock_client.fetch_context.return_value = mock_market_context

    pipeline = PromptPipeline(data_client=mock_client)
    config = ExecutionConfig(symbol="SOLUSDT", budget=300.0, mode="moderate")
    result = pipeline.execute(
        config,
        options=PipelineOptions(save_to_disk=False, copy_clipboard=False),
    )

    assert result.facts is not None
    assert result.facts.snapshot_timestamp_utc is not None
    assert result.facts.snapshot_timestamp_utc.endswith(" UTC")
    assert result.facts.snapshot_timestamp_wib is not None
    assert result.facts.snapshot_timestamp_wib.endswith(" WIB (UTC+7)")
    assert "- Data Snapshot Timestamp: N/A" not in result.rendered_prompt
    assert f"- Data Snapshot Timestamp: {result.facts.snapshot_timestamp_utc} | {result.facts.snapshot_timestamp_wib}" in result.rendered_prompt
