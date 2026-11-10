"""Unit test untuk PromptPipeline, MarketDataClient, dan RawFactsAnalyzer."""

from datetime import datetime, timedelta, timezone
import json
import os
from unittest.mock import MagicMock
import pandas as pd
import pytest
import requests

from spot_prompt.analyzer import RawFactsAnalyzer, resolve_execution_guardrails
from spot_prompt.data_client import MarketContext, MarketDataClient
from spot_prompt.models import ExecutionConfig, IndicatorFacts, PriceRange30D, VWAPFacts
from spot_prompt.pipeline import PipelineOptions, PromptPipeline

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _make_binance_kline_row(
    dt_utc: datetime,
    open_p: float,
    high_p: float,
    low_p: float,
    close_p: float,
    vol: float,
) -> list:
    """Membuat satu baris array kline berformat Binance REST API."""
    ts_ms = int(dt_utc.timestamp() * 1000)
    close_ms = ts_ms + 86_400_000 - 1
    return [
        ts_ms,
        f"{open_p}",
        f"{high_p}",
        f"{low_p}",
        f"{close_p}",
        f"{vol}",
        close_ms,
        f"{close_p * vol}",
        100,
        f"{vol / 2}",
        f"{close_p * vol / 2}",
        "0",
    ]


def _make_mock_http_session(
    daily_rows: list,
    weekly_rows: list,
    fx_rate_idr: float = 18000.0,
) -> MagicMock:
    """Membuat mock requests.Session untuk menguji seam PromptPipeline.execute tanpa jaringan."""
    session = MagicMock(spec=requests.Session)
    with open(os.path.join(FIXTURES_DIR, "mock_fng.json")) as f:
        fng_json = json.load(f)

    def fake_get(url, params=None, timeout=None):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = 200
        resp.raise_for_status.return_value = None

        if "klines" in url:
            interval = (params or {}).get("interval", "1d")
            resp.json.return_value = weekly_rows if interval == "1w" else daily_rows
            return resp
        if "fng" in url:
            resp.json.return_value = fng_json
            return resp
        if "indodax.com" in url:
            resp.json.return_value = {"ticker": {"last": str(fx_rate_idr)}}
            return resp

        resp.json.return_value = {}
        return resp

    session.get.side_effect = fake_get
    return session


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


def test_pipeline_q_vwap_deterministic_usdt_and_zero_extra_http_calls():
    """Slice 1: Q-VWAP (±1σ/±2σ) dihitung deterministik per kuartal UTC tanpa request HTTP tambahan."""
    # 30 candle tertutup pada Q3 2024 (2024-09-01..2024-09-30) harus terpisah dari Q4
    q3_start = datetime(2024, 9, 1, 0, 0, tzinfo=timezone.utc)
    daily_rows = [
        _make_binance_kline_row(q3_start + timedelta(days=i), 50.0, 55.0, 45.0, 50.0, 1000.0)
        for i in range(30)
    ]
    # 2 candle tertutup Q4 2024: TP=100 (vol=100) & TP=120 (vol=300) -> mean=115.0, std=sqrt(75)=8.660254...
    daily_rows.append(
        _make_binance_kline_row(datetime(2024, 10, 1, 0, 0, tzinfo=timezone.utc), 100.0, 110.0, 90.0, 100.0, 100.0)
    )
    daily_rows.append(
        _make_binance_kline_row(datetime(2024, 10, 2, 0, 0, tzinfo=timezone.utc), 115.0, 125.0, 115.0, 120.0, 300.0)
    )
    # Candle running (belum tutup) pada 2024-10-03 (current_price = 118.0)
    daily_rows.append(
        _make_binance_kline_row(datetime(2024, 10, 3, 0, 0, tzinfo=timezone.utc), 118.0, 119.0, 116.0, 118.0, 5000.0)
    )

    weekly_start = datetime(2024, 5, 20, 0, 0, tzinfo=timezone.utc)
    weekly_rows = [
        _make_binance_kline_row(weekly_start + timedelta(weeks=i), 50.0, 55.0, 45.0, 50.0, 5000.0)
        for i in range(20)
    ]

    mock_session = _make_mock_http_session(daily_rows=daily_rows, weekly_rows=weekly_rows)
    client = MarketDataClient(session=mock_session)
    pipeline = PromptPipeline(data_client=client)

    result = pipeline.execute(
        ExecutionConfig(symbol="SOLUSDT", budget=300.0, mode="moderate"),
        options=PipelineOptions(save_to_disk=False, copy_clipboard=False),
    )

    # Pastikan tidak ada request HTTP tambahan untuk VWAP (hanya 5 panggilan standar: 1d, 1w, fng, 1d BTC pair, 1w BTC pair)
    assert mock_session.get.call_count == 5
    intervals = [call.kwargs.get("params", {}).get("interval") for call in mock_session.get.call_args_list if "klines" in call.args[0]]
    assert set(intervals) == {"1d", "1w"}

    vwap = result.facts.vwap
    assert vwap is not None
    assert vwap.quarter_label == "2024-Q4"
    assert vwap.quarter_start_date == "2024-10-01"
    assert vwap.quarter_candles_count == 2
    assert vwap.q_vwap == pytest.approx(115.0)
    assert vwap.q_vwap_upper_1 == pytest.approx(123.660254, abs=1e-5)
    assert vwap.q_vwap_lower_1 == pytest.approx(106.339746, abs=1e-5)
    assert vwap.q_vwap_upper_2 == pytest.approx(132.320508, abs=1e-5)
    assert vwap.q_vwap_lower_2 == pytest.approx(97.679492, abs=1e-5)

    prompt = result.rendered_prompt
    assert "Q-VWAP +2σ: 132.3205 [>= HARGA TERKINI -> RESISTANCE / DILARANG JADI LIMIT BUY]" in prompt
    assert "Q-VWAP +1σ: 123.6603 [>= HARGA TERKINI -> RESISTANCE / DILARANG JADI LIMIT BUY]" in prompt
    assert "Q-VWAP Mean: 115.0000" in prompt
    assert "[DI BAWAH HARGA -> KANDIDAT SUPPORT]" in prompt
    assert "Q-VWAP -1σ: 106.3397 [DI BAWAH HARGA -> KANDIDAT SUPPORT]" in prompt
    assert "Q-VWAP -2σ: 97.6795 [DI BAWAH HARGA -> KANDIDAT SUPPORT]" in prompt
    assert "Sejak 2024-10-01 (2 candle harian tertutup)" in prompt


def test_pipeline_365d_r_vwap_and_running_candle_isolation():
    """Slice 2: 365D R-VWAP menghitung 365 candle tertutup terakhir dan kebal mutasi Running Candle."""
    start_dt = datetime(2024, 9, 23, 0, 0, tzinfo=timezone.utc)
    daily_rows = []
    # 10 hari di luar jendela 365 hari tertutup terakhir (harga 1000, volume raksasa harus diabaikan)
    for i in range(10):
        daily_rows.append(
            _make_binance_kline_row(start_dt + timedelta(days=i), 1000.0, 1000.0, 1000.0, 1000.0, 10000.0)
        )
    # 363 hari pertama dalam jendela 365D: TP=100, vol=100 (total vol=36300, tp*vol=3630000)
    for i in range(10, 373):
        daily_rows.append(
            _make_binance_kline_row(start_dt + timedelta(days=i), 100.0, 110.0, 90.0, 100.0, 100.0)
        )
    # 2 hari terakhir (2025-10-01 & 2025-10-02, sekaligus Q4 2025): TP=200, vol=1850 each -> total vol=40000, R-VWAP=109.25
    for i in range(373, 375):
        daily_rows.append(
            _make_binance_kline_row(start_dt + timedelta(days=i), 200.0, 210.0, 190.0, 200.0, 1850.0)
        )
    # Running candle (2025-10-03), current_price=150.0
    running_dt = start_dt + timedelta(days=375)
    daily_rows.append(_make_binance_kline_row(running_dt, 150.0, 155.0, 145.0, 150.0, 100.0))

    weekly_start = datetime(2024, 5, 20, 0, 0, tzinfo=timezone.utc)
    weekly_rows = [
        _make_binance_kline_row(weekly_start + timedelta(weeks=i), 100.0, 110.0, 90.0, 100.0, 5000.0)
        for i in range(60)
    ]

    session_base = _make_mock_http_session(daily_rows=daily_rows, weekly_rows=weekly_rows)
    pipeline_base = PromptPipeline(data_client=MarketDataClient(session=session_base))
    res_base = pipeline_base.execute(
        ExecutionConfig(symbol="SOLUSDT", budget=300.0, mode="moderate"),
        options=PipelineOptions(save_to_disk=False, copy_clipboard=False),
    )

    assert res_base.facts.vwap.r_vwap_365d_available is True
    assert res_base.facts.vwap.available_closed_days == 375
    assert res_base.facts.vwap.r_vwap_365d == pytest.approx(109.25)
    assert "365-Day Rolling VWAP (365D R-VWAP" in res_base.rendered_prompt
    assert "109.2500" in res_base.rendered_prompt
    assert "[DI BAWAH HARGA -> KANDIDAT SUPPORT]" in res_base.rendered_prompt

    # Mutasi ekstrem pada Running Candle tidak boleh mengubah nilai Q-VWAP maupun 365D R-VWAP
    mutated_daily = list(daily_rows[:-1]) + [
        _make_binance_kline_row(running_dt, 90.0, 999.0, 50.0, 90.0, 999_999_999.0)
    ]
    session_mut = _make_mock_http_session(daily_rows=mutated_daily, weekly_rows=weekly_rows)
    pipeline_mut = PromptPipeline(data_client=MarketDataClient(session=session_mut))
    res_mut = pipeline_mut.execute(
        ExecutionConfig(symbol="SOLUSDT", budget=300.0, mode="moderate"),
        options=PipelineOptions(save_to_disk=False, copy_clipboard=False),
    )

    assert res_mut.facts.vwap.q_vwap == pytest.approx(res_base.facts.vwap.q_vwap)
    assert res_mut.facts.vwap.q_vwap_upper_1 == pytest.approx(res_base.facts.vwap.q_vwap_upper_1)
    assert res_mut.facts.vwap.q_vwap_lower_2 == pytest.approx(res_base.facts.vwap.q_vwap_lower_2)
    assert res_mut.facts.vwap.r_vwap_365d == pytest.approx(109.25)
    # Tag posisi berubah mengikuti harga terkini (90.0 < 109.25 -> RESISTANCE)
    assert "109.2500 (Deviasi harga saat ini: -17.62%) [>= HARGA TERKINI -> RESISTANCE / DILARANG JADI LIMIT BUY]" in res_mut.rendered_prompt


def test_pipeline_vwap_graceful_degradation_young_coin_empty_quarter_and_zero_volume():
    """Slice 3: Degradasi anggun ke N/A untuk koin muda <365 hari, kuartal kosong, dan volume nol."""
    # 3a. Koin muda dari fixture statis (300 baris -> 299 candle tertutup, 25 candle di 2024-Q4)
    with open(os.path.join(FIXTURES_DIR, "mock_klines_daily.json")) as f:
        fixture_daily = json.load(f)
    with open(os.path.join(FIXTURES_DIR, "mock_klines_weekly.json")) as f:
        fixture_weekly = json.load(f)

    session_young = _make_mock_http_session(daily_rows=fixture_daily, weekly_rows=fixture_weekly)
    res_young = PromptPipeline(data_client=MarketDataClient(session=session_young)).execute(
        ExecutionConfig(symbol="SOLUSDT", budget=300.0, mode="moderate"),
        options=PipelineOptions(save_to_disk=False, copy_clipboard=False),
    )

    assert session_young.get.call_count == 5
    assert res_young.facts.vwap.r_vwap_365d is None
    assert res_young.facts.vwap.r_vwap_365d_available is False
    assert res_young.facts.vwap.available_closed_days == 299
    assert res_young.facts.vwap.quarter_label == "2024-Q4"
    assert res_young.facts.vwap.quarter_candles_count == 25
    assert "Level: N/A (Riwayat candle harian tertutup baru 299 dari 365 hari yang dibutuhkan)" in res_young.rendered_prompt
    assert "Q-VWAP +2σ: 181.0578 [>= HARGA TERKINI -> RESISTANCE / DILARANG JADI LIMIT BUY]" in res_young.rendered_prompt
    assert "Q-VWAP Mean: 179.4712" in res_young.rendered_prompt

    # 3b. Hari pertama kuartal baru (running candle 2024-10-01, seluruh candle tertutup berakhir 2024-09-30)
    q3_start = datetime(2024, 9, 1, 0, 0, tzinfo=timezone.utc)
    day1_rows = [
        _make_binance_kline_row(q3_start + timedelta(days=i), 50.0, 55.0, 45.0, 50.0, 1000.0)
        for i in range(30)
    ]
    day1_rows.append(
        _make_binance_kline_row(datetime(2024, 10, 1, 0, 0, tzinfo=timezone.utc), 52.0, 54.0, 51.0, 53.0, 200.0)
    )
    weekly_rows = [
        _make_binance_kline_row(datetime(2024, 5, 20, 0, 0, tzinfo=timezone.utc) + timedelta(weeks=i), 50.0, 55.0, 45.0, 50.0, 5000.0)
        for i in range(20)
    ]
    session_empty_q = _make_mock_http_session(daily_rows=day1_rows, weekly_rows=weekly_rows)
    res_empty_q = PromptPipeline(data_client=MarketDataClient(session=session_empty_q)).execute(
        ExecutionConfig(symbol="SOLUSDT", mode="moderate"),
        options=PipelineOptions(save_to_disk=False, copy_clipboard=False),
    )

    assert res_empty_q.facts.vwap.quarter_label == "2024-Q4"
    assert res_empty_q.facts.vwap.quarter_candles_count == 0
    assert res_empty_q.facts.vwap.q_vwap is None
    assert "Level: N/A (Belum ada candle harian tertutup atau volume bernilai nol pada kuartal UTC berjalan sejak 2024-10-01)" in res_empty_q.rendered_prompt

    # 3c. Volume nol pada seluruh 365+ hari tertutup dan kuartal berjalan
    zero_vol_start = datetime(2024, 10, 1, 0, 0, tzinfo=timezone.utc)
    zero_vol_rows = [
        _make_binance_kline_row(zero_vol_start + timedelta(days=i), 100.0, 105.0, 95.0, 100.0, 0.0)
        for i in range(366)
    ]
    session_zero_vol = _make_mock_http_session(daily_rows=zero_vol_rows, weekly_rows=weekly_rows)
    res_zero_vol = PromptPipeline(data_client=MarketDataClient(session=session_zero_vol)).execute(
        ExecutionConfig(symbol="SOLUSDT", mode="moderate"),
        options=PipelineOptions(save_to_disk=False, copy_clipboard=False),
    )

    assert res_zero_vol.facts.vwap.q_vwap is None
    assert res_zero_vol.facts.vwap.r_vwap_365d is None
    assert res_zero_vol.facts.vwap.r_vwap_365d_available is False
    assert "365 dari 365" not in res_zero_vol.rendered_prompt
    assert "Total volume 365 hari tertutup bernilai nol" in res_zero_vol.rendered_prompt


def test_pipeline_vwap_idr_dual_currency_and_young_coin_rule():
    """Slice 4: Mode IDR merender seluruh level Q-VWAP & 365D R-VWAP dalam Dual-Currency Display dan Aturan Koin Muda."""
    start_dt = datetime(2024, 10, 3, 0, 0, tzinfo=timezone.utc)
    daily_rows = []
    # 363 hari tertutup pertama: TP=100, vol=100
    for i in range(363):
        daily_rows.append(
            _make_binance_kline_row(start_dt + timedelta(days=i), 100.0, 110.0, 90.0, 100.0, 100.0)
        )
    # 2 hari Q4 2025 (2025-10-01 & 2025-10-02): TP=120 & TP=200 dengan vol=1850 -> Q-VWAP=160, std=40, R-VWAP=105.55
    daily_rows.append(
        _make_binance_kline_row(datetime(2025, 10, 1, 0, 0, tzinfo=timezone.utc), 120.0, 130.0, 110.0, 120.0, 1850.0)
    )
    daily_rows.append(
        _make_binance_kline_row(datetime(2025, 10, 2, 0, 0, tzinfo=timezone.utc), 200.0, 210.0, 190.0, 200.0, 1850.0)
    )
    # Running candle (2025-10-03), current_price=180.0
    daily_rows.append(
        _make_binance_kline_row(datetime(2025, 10, 3, 0, 0, tzinfo=timezone.utc), 180.0, 185.0, 175.0, 180.0, 200.0)
    )

    weekly_rows = [
        _make_binance_kline_row(datetime(2024, 5, 20, 0, 0, tzinfo=timezone.utc) + timedelta(weeks=i), 100.0, 110.0, 90.0, 100.0, 5000.0)
        for i in range(60)
    ]

    session_idr = _make_mock_http_session(daily_rows=daily_rows, weekly_rows=weekly_rows, fx_rate_idr=16000.0)
    result = PromptPipeline(data_client=MarketDataClient(session=session_idr)).execute(
        ExecutionConfig(symbol="SOLIDR", budget=2_000_000.0, currency="IDR", mode="moderate"),
        options=PipelineOptions(save_to_disk=False, copy_clipboard=False),
    )

    # 6 panggilan HTTP: 1d, 1w, fng, 1d SOLBTC, 1w SOLBTC, dan Indodax FX rate
    assert session_idr.get.call_count == 6
    prompt = result.rendered_prompt
    assert "SOL/IDR" in prompt
    assert "Q-VWAP +2σ: Rp 3.840.000 (~$240.00 USDT) [>= HARGA TERKINI -> RESISTANCE / DILARANG JADI LIMIT BUY]" in prompt
    assert "Q-VWAP +1σ: Rp 3.200.000 (~$200.00 USDT) [>= HARGA TERKINI -> RESISTANCE / DILARANG JADI LIMIT BUY]" in prompt
    assert "Q-VWAP Mean: Rp 2.560.000 (~$160.00 USDT) (Deviasi harga saat ini: +12.50%) [DI BAWAH HARGA -> KANDIDAT SUPPORT]" in prompt
    assert "Q-VWAP -1σ: Rp 1.920.000 (~$120.00 USDT) [DI BAWAH HARGA -> KANDIDAT SUPPORT]" in prompt
    assert "Q-VWAP -2σ: Rp 1.280.000 (~$80.0000 USDT) [DI BAWAH HARGA -> KANDIDAT SUPPORT]" in prompt
    assert "Level: Rp 1.688.800 (~$105.55 USDT) (Deviasi harga saat ini: +70.54%) [DI BAWAH HARGA -> KANDIDAT SUPPORT]" in prompt
    assert "Q-VWAP, dan 365D R-VWAP" in prompt


def test_pipeline_vwap_idr_micro_coin_adaptive_formatting():
    """Verifikasi Adaptive Price Formatting (< Rp 100) untuk level Q-VWAP pada mode IDR."""
    q3_start = datetime(2024, 9, 1, 0, 0, tzinfo=timezone.utc)
    daily_rows = [
        _make_binance_kline_row(q3_start + timedelta(days=i), 0.001, 0.0011, 0.0009, 0.001, 1000.0)
        for i in range(30)
    ]
    # Q4 2024: TP=0.002 & TP=0.004 (vol=100 each) -> mean=0.003, std=0.001
    daily_rows.append(
        _make_binance_kline_row(datetime(2024, 10, 1, 0, 0, tzinfo=timezone.utc), 0.002, 0.0021, 0.0019, 0.002, 100.0)
    )
    daily_rows.append(
        _make_binance_kline_row(datetime(2024, 10, 2, 0, 0, tzinfo=timezone.utc), 0.004, 0.0041, 0.0039, 0.004, 100.0)
    )
    daily_rows.append(
        _make_binance_kline_row(datetime(2024, 10, 3, 0, 0, tzinfo=timezone.utc), 0.0035, 0.0036, 0.0034, 0.0035, 100.0)
    )

    weekly_rows = [
        _make_binance_kline_row(datetime(2024, 5, 20, 0, 0, tzinfo=timezone.utc) + timedelta(weeks=i), 0.001, 0.0011, 0.0009, 0.001, 5000.0)
        for i in range(20)
    ]

    session_micro = _make_mock_http_session(daily_rows=daily_rows, weekly_rows=weekly_rows, fx_rate_idr=16000.0)
    result = PromptPipeline(data_client=MarketDataClient(session=session_micro)).execute(
        ExecutionConfig(symbol="PEPEIDR", budget=50_000.0, currency="IDR", mode="moderate"),
        options=PipelineOptions(save_to_disk=False, copy_clipboard=False),
    )

    prompt = result.rendered_prompt
    assert "Q-VWAP +2σ: Rp 80,00 (~$0.005000 USDT) [>= HARGA TERKINI -> RESISTANCE / DILARANG JADI LIMIT BUY]" in prompt
    assert "Q-VWAP +1σ: Rp 64,00 (~$0.004000 USDT) [>= HARGA TERKINI -> RESISTANCE / DILARANG JADI LIMIT BUY]" in prompt
    assert "Q-VWAP Mean: Rp 48,00 (~$0.003000 USDT)" in prompt
    assert "Q-VWAP -1σ: Rp 32,00 (~$0.002000 USDT) [DI BAWAH HARGA -> KANDIDAT SUPPORT]" in prompt
    assert "Q-VWAP -2σ: Rp 16,00 (~$0.001000 USDT) [DI BAWAH HARGA -> KANDIDAT SUPPORT]" in prompt


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


def test_prompt_pipeline_enforces_entry_overlap_guardrail_distance_usdt():
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

    assert "ENTRY OVERLAP GUARDRAIL" in quant_section
    assert "Entry Overlap Guardrail (Market Buy vs Level 1)" in quant_section
    assert "Harga Terkini - Level 1 >= 5.0000 USDT" in quant_section
    assert "0.5x ATR-14" in quant_section
    assert "95.0000" in quant_section

    assert "Harga Terkini - Level 1 >= 5.0000 USDT" in self_check_section
    assert "0.5x ATR-14" in self_check_section


def test_prompt_pipeline_enforces_entry_overlap_guardrail_and_staleness_dual_currency_idr():
    """Memastikan guardrail timeline sync dan Entry Overlap Guardrail terformat Dual-Currency Display untuk mode IDR."""
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


def _make_full_anchor_crash_rows(
    running_close: float = 110.0,
    running_high: float = 115.0,
    running_low: float = 105.0,
    running_volume: float = 100.0,
) -> tuple[list, list]:
    """Menyusun data klines sintetis lengkap (375 closed days + 204 closed weeks) dengan angka eksak.

    Nilai baseline tertutup yang terverifikasi matematis:
    - ATR-14 = 10.0
    - Q-VWAP (2025-Q4: 2025-10-01 TP=96, 2025-10-02 TP=102, vol=1850 each) = 99.0, std = 3.0 -> Q-VWAP -2σ = 93.0
    - 365D R-VWAP = (363*100*100 + 1850*96 + 1850*102) / 40000 = 99.9075
    - 200W SMA = 75.0
    """
    start_dt = datetime(2024, 9, 23, 0, 0, tzinfo=timezone.utc)
    daily_rows = []
    # 10 hari sebelum jendela 365 hari (harga 500 & volume 10000, harus diabaikan oleh 365D R-VWAP)
    for i in range(10):
        daily_rows.append(
            _make_binance_kline_row(start_dt + timedelta(days=i), 500.0, 505.0, 495.0, 500.0, 10000.0)
        )
    # 363 hari pertama dalam jendela 365D (2024-10-03 s/d 2025-09-30): TP=100, TR=10, vol=100
    for i in range(10, 373):
        daily_rows.append(
            _make_binance_kline_row(start_dt + timedelta(days=i), 100.0, 105.0, 95.0, 100.0, 100.0)
        )
    # 2 hari Q4 2025 (2025-10-01 & 2025-10-02): TR tetap 10.0 agar ATR-14 = 10.0 eksak
    daily_rows.append(
        _make_binance_kline_row(datetime(2025, 10, 1, 0, 0, tzinfo=timezone.utc), 100.0, 100.0, 90.0, 98.0, 1850.0)
    )
    daily_rows.append(
        _make_binance_kline_row(datetime(2025, 10, 2, 0, 0, tzinfo=timezone.utc), 98.0, 108.0, 98.0, 100.0, 1850.0)
    )
    # Candle running (2025-10-03)
    daily_rows.append(
        _make_binance_kline_row(
            datetime(2025, 10, 3, 0, 0, tzinfo=timezone.utc),
            running_close,
            running_high,
            running_low,
            running_close,
            running_volume,
        )
    )

    weekly_start = datetime(2021, 11, 1, 0, 0, tzinfo=timezone.utc)
    weekly_rows = [
        _make_binance_kline_row(weekly_start + timedelta(weeks=i), 75.0, 80.0, 70.0, 75.0, 5000.0)
        for i in range(205)
    ]
    return daily_rows, weekly_rows


def test_pipeline_emergency_crash_contingency_usdt_with_macro_anchors_and_closed_hygiene():
    """Slice 1: Prompt USDT memuat Emergency Crash Contingency Plan dengan jangkar makro & higiene Closed-Candle."""
    daily_rows, weekly_rows = _make_full_anchor_crash_rows(
        running_close=110.0,
        running_high=120.0,
        running_low=25.0,
        running_volume=999_999_999.0,
    )
    mock_session = _make_mock_http_session(daily_rows=daily_rows, weekly_rows=weekly_rows)
    pipeline = PromptPipeline(data_client=MarketDataClient(session=mock_session))
    fixed_utc = datetime(2025, 10, 3, 12, 0, 0, tzinfo=timezone.utc)

    result = pipeline.execute(
        ExecutionConfig(symbol="SOLUSDT", budget=300.0, mode="moderate"),
        options=PipelineOptions(save_to_disk=False, copy_clipboard=False, snapshot_time=fixed_utc),
    )

    assert mock_session.get.call_count == 5
    prompt = result.rendered_prompt

    assert "Order Invalidation & Re-anchoring Protocol" in prompt
    invalidation_section = prompt.split("Order Invalidation & Re-anchoring Protocol", maxsplit=1)[1]
    contingency_section = invalidation_section.split("Self-Check Validasi Kuantitatif", maxsplit=1)[0]

    # Blok wajib Emergency Crash Contingency Plan di dalam Order Invalidation Protocol
    assert "Emergency Crash Contingency Plan" in contingency_section
    # Pemicu penurunan deras berbasis Closed-Candle Baseline + konfirmasi volume [CLOSED] > 1.5x
    assert "Closed-Candle Baseline" in contingency_section
    assert "[CLOSED]" in contingency_section
    assert "> 1.5x" in contingency_section
    assert "[RUNNING / UNCLOSED]" in contingency_section
    # Pembatalan jaring atas (Level 1 - Level 2)
    assert "Level 1" in contingency_section
    assert "Level 2" in contingency_section
    # Jangkar ekstrem konkret + proyeksi -3.0x s/d -5.0x ATR-14
    assert "Q-VWAP -2σ" in contingency_section
    assert "93.0000 USDT" in contingency_section
    assert "365D R-VWAP" in contingency_section
    assert "99.9075 USDT" in contingency_section
    assert "200W SMA" in contingency_section
    assert "75.0000 USDT" in contingency_section
    assert "-3.0x s/d -5.0x ATR-14" in contingency_section
    assert "80.0000 USDT" in contingency_section
    assert "60.0000 USDT" in contingency_section
    # Penegakan Minimum Notional Consolidation mode USDT
    assert "Minimum Notional Consolidation" in contingency_section
    assert "10.00 USDT" in contingency_section
    # Self-Check ikut memvalidasi Emergency Crash Contingency Plan
    self_check_section = prompt.split("Self-Check Validasi Kuantitatif", maxsplit=1)[1]
    assert "Emergency Crash Contingency Plan" in self_check_section


def test_pipeline_emergency_crash_contingency_usdt_small_budget_and_young_coin():
    """Slice 2: Budget kecil USDT (< 20.00 USDT) memicu konsolidasi darurat dan koin muda fallback aman dari N/A."""
    # 32 hari Q3 + 2 hari Q4 tertutup + 1 running candle (< 365 hari -> 365D R-VWAP N/A)
    start_dt = datetime(2025, 8, 30, 0, 0, tzinfo=timezone.utc)
    daily_rows = [
        _make_binance_kline_row(start_dt + timedelta(days=i), 100.0, 105.0, 95.0, 100.0, 100.0)
        for i in range(32)
    ]
    daily_rows.append(
        _make_binance_kline_row(datetime(2025, 10, 1, 0, 0, tzinfo=timezone.utc), 100.0, 100.0, 90.0, 98.0, 1850.0)
    )
    daily_rows.append(
        _make_binance_kline_row(datetime(2025, 10, 2, 0, 0, tzinfo=timezone.utc), 98.0, 108.0, 98.0, 100.0, 1850.0)
    )
    daily_rows.append(
        _make_binance_kline_row(datetime(2025, 10, 3, 0, 0, tzinfo=timezone.utc), 110.0, 112.0, 108.0, 110.0, 200.0)
    )
    # 20 minggu (< 200 minggu -> 200W SMA N/A)
    weekly_rows = [
        _make_binance_kline_row(datetime(2025, 5, 12, 0, 0, tzinfo=timezone.utc) + timedelta(weeks=i), 95.0, 100.0, 90.0, 95.0, 5000.0)
        for i in range(20)
    ]

    mock_session = _make_mock_http_session(daily_rows=daily_rows, weekly_rows=weekly_rows)
    pipeline = PromptPipeline(data_client=MarketDataClient(session=mock_session))
    fixed_utc = datetime(2025, 10, 3, 12, 0, 0, tzinfo=timezone.utc)

    result = pipeline.execute(
        ExecutionConfig(symbol="HYPE", budget=15.0, currency="USDT", mode="aggressive"),
        options=PipelineOptions(save_to_disk=False, copy_clipboard=False, snapshot_time=fixed_utc),
    )

    assert mock_session.get.call_count == 5
    prompt = result.rendered_prompt
    invalidation_section = prompt.split("Order Invalidation & Re-anchoring Protocol", maxsplit=1)[1]
    contingency_section = invalidation_section.split("Self-Check Validasi Kuantitatif", maxsplit=1)[0]

    # Koin muda: 365D R-VWAP & 200W SMA bernilai N/A, tetap punya Q-VWAP -2σ & -3.0x/-5.0x ATR-14
    assert "`365D R-VWAP` (N/A)" in contingency_section
    assert "`200W SMA` (N/A)" in contingency_section
    assert "93.0000 USDT" in contingency_section
    assert "80.0000 USDT" in contingency_section
    assert "60.0000 USDT" in contingency_section
    # Budget kecil 15.00 USDT < 20.00 USDT memicu Minimum Notional Consolidation aktif
    assert "KONSOLIDASI AKTIF" in contingency_section
    assert "15.00 USDT < 20.00 USDT" in contingency_section
    assert "1 order tangkap ekstrem tunggal" in contingency_section
    assert "10.00 USDT" in contingency_section


def test_pipeline_emergency_crash_contingency_idr_sufficient_and_small_budget():
    """Slice 3: Mode IDR memakai Dual-Currency Display pada jangkar ekstrem dan menegakkan Local Minimum Notional Rp 10.000."""
    daily_rows, weekly_rows = _make_full_anchor_crash_rows(
        running_close=110.0,
        running_high=115.0,
        running_low=105.0,
        running_volume=100.0,
    )
    fixed_utc = datetime(2025, 10, 3, 12, 0, 0, tzinfo=timezone.utc)

    # 3a. Budget IDR mencukupi (Rp 1.500.000 >= Rp 20.000)
    session_ok = _make_mock_http_session(daily_rows=daily_rows, weekly_rows=weekly_rows, fx_rate_idr=18000.0)
    res_ok = PromptPipeline(data_client=MarketDataClient(session=session_ok)).execute(
        ExecutionConfig(symbol="SOLIDR", budget=1_500_000.0, currency="IDR", mode="moderate"),
        options=PipelineOptions(save_to_disk=False, copy_clipboard=False, snapshot_time=fixed_utc),
    )

    assert session_ok.get.call_count == 6
    prompt_ok = res_ok.rendered_prompt
    inval_ok = prompt_ok.split("Order Invalidation & Re-anchoring Protocol", maxsplit=1)[1]
    cont_ok = inval_ok.split("Self-Check Validasi Kuantitatif", maxsplit=1)[0]

    assert "Emergency Crash Contingency Plan" in cont_ok
    assert "Closed-Candle Baseline" in cont_ok
    assert "[CLOSED] > 1.5x" in cont_ok
    assert "[RUNNING / UNCLOSED]" in cont_ok
    # Dual-Currency Display untuk seluruh jangkar ekstrem dan batas atas < Harga Terkini
    assert "Rp 1.980.000 (~$110.00 USDT)" in cont_ok
    assert "Rp 1.674.000 (~$93.0000 USDT)" in cont_ok
    assert "Rp 1.798.335 (~$99.9075 USDT)" in cont_ok
    assert "Rp 1.350.000 (~$75.0000 USDT)" in cont_ok
    assert "Rp 1.440.000 (~$80.0000 USDT) s/d Rp 1.080.000 (~$60.0000 USDT)" in cont_ok
    assert "Dual-Currency Display: Harga Rp ... (~$... USDT)" in cont_ok
    # Local Minimum Notional Rp 10.000 & toleransi Tokocrypto Rp 20.000 tanpa pemicu konsolidasi aktif
    assert "Local Minimum Notional" in cont_ok
    assert "Rp 10.000" in cont_ok
    assert "Rp 20.000" in cont_ok
    assert "KONSOLIDASI AKTIF" not in cont_ok

    # 3b. Budget IDR kecil (Rp 15.000 < Rp 20.000) memicu konsolidasi darurat aktif ke 1 order tunggal
    session_small = _make_mock_http_session(daily_rows=daily_rows, weekly_rows=weekly_rows, fx_rate_idr=18000.0)
    res_small = PromptPipeline(data_client=MarketDataClient(session=session_small)).execute(
        ExecutionConfig(symbol="SOLIDR", budget=15_000.0, currency="IDR", mode="moderate"),
        options=PipelineOptions(save_to_disk=False, copy_clipboard=False, snapshot_time=fixed_utc),
    )

    prompt_small = res_small.rendered_prompt
    inval_small = prompt_small.split("Order Invalidation & Re-anchoring Protocol", maxsplit=1)[1]
    cont_small = inval_small.split("Self-Check Validasi Kuantitatif", maxsplit=1)[0]

    assert "KONSOLIDASI AKTIF" in cont_small
    assert "Rp 15.000 < Rp 20.000" in cont_small
    assert "1 order tangkap ekstrem tunggal" in cont_small
    assert "Rp 10.000" in cont_small


def test_pipeline_emergency_crash_contingency_micro_idr_breached_qvwap_and_no_budget():
    """Slice 4: Koin mikro IDR menjaga Adaptive Price Formatting, menandai Q-VWAP -2σ tertembus, dan memblokir target <= 0."""
    q3_start = datetime(2024, 9, 1, 0, 0, tzinfo=timezone.utc)
    daily_rows = [
        _make_binance_kline_row(q3_start + timedelta(days=i), 0.004, 0.0045, 0.0035, 0.004, 100.0)
        for i in range(30)
    ]
    # Q4 2024: TP=0.0040 & TP=0.0046 (vol=100) -> mean=0.0043, std=0.0003, Q-VWAP -2σ=0.0037; TR=0.0010 -> ATR-14=0.0010
    daily_rows.append(
        _make_binance_kline_row(datetime(2024, 10, 1, 0, 0, tzinfo=timezone.utc), 0.004, 0.0045, 0.0035, 0.004, 100.0)
    )
    daily_rows.append(
        _make_binance_kline_row(datetime(2024, 10, 2, 0, 0, tzinfo=timezone.utc), 0.004, 0.0050, 0.0040, 0.0048, 100.0)
    )
    # Running candle 0.0035 < Q-VWAP -2σ (0.0037), -3x ATR=0.0005 (>0), -5x ATR=-0.0015 (<=0 harus disembunyikan)
    daily_rows.append(
        _make_binance_kline_row(datetime(2024, 10, 3, 0, 0, tzinfo=timezone.utc), 0.0035, 0.0036, 0.0034, 0.0035, 250.0)
    )
    weekly_rows = [
        _make_binance_kline_row(datetime(2024, 5, 20, 0, 0, tzinfo=timezone.utc) + timedelta(weeks=i), 0.004, 0.0045, 0.0035, 0.004, 5000.0)
        for i in range(20)
    ]

    session_micro = _make_mock_http_session(daily_rows=daily_rows, weekly_rows=weekly_rows, fx_rate_idr=16000.0)
    result = PromptPipeline(data_client=MarketDataClient(session=session_micro)).execute(
        ExecutionConfig(symbol="PEPEIDR", budget=None, currency="IDR", mode="conservative"),
        options=PipelineOptions(save_to_disk=False, copy_clipboard=False, snapshot_time=datetime(2024, 10, 3, 12, 0, tzinfo=timezone.utc)),
    )

    prompt = result.rendered_prompt
    inval_section = prompt.split("Order Invalidation & Re-anchoring Protocol", maxsplit=1)[1]
    cont_section = inval_section.split("Self-Check Validasi Kuantitatif", maxsplit=1)[0]

    assert "Rp 59,20 (~$0.003700 USDT), >= Harga Terkini: sudah tertembus sehingga gunakan jangkar lebih dalam" in cont_section
    assert "mulai Rp 8,00 (~$0.000500 USDT), tetap bernilai > 0" in cont_section
    assert "-Rp" not in cont_section
    assert "-$" not in cont_section
    assert "Minimum Notional Consolidation" in cont_section
    assert "alokasi minimal 10.00" not in prompt


@pytest.mark.parametrize("currency", ["USDT", "IDR"])
def test_pipeline_emergency_crash_contingency_guards_non_positive_qvwap_lower_2(currency):
    """Ketika varians kuartal tinggi membuat Q-VWAP -2σ <= 0, guardrail menolaknya sebagai target beli."""
    q3_start = datetime(2025, 9, 1, 0, 0, tzinfo=timezone.utc)
    daily_rows = [
        _make_binance_kline_row(q3_start + timedelta(days=i), 50.0, 55.0, 45.0, 50.0, 100.0)
        for i in range(30)
    ]
    # Q4 2025: TP=10 & TP=90 (vol sama) -> mean=50, std=40, Q-VWAP -2σ = -30.0 (<= 0)
    daily_rows.append(
        _make_binance_kline_row(datetime(2025, 10, 1, 0, 0, tzinfo=timezone.utc), 10.0, 11.0, 9.0, 10.0, 100.0)
    )
    daily_rows.append(
        _make_binance_kline_row(datetime(2025, 10, 2, 0, 0, tzinfo=timezone.utc), 90.0, 95.0, 85.0, 90.0, 100.0)
    )
    daily_rows.append(
        _make_binance_kline_row(datetime(2025, 10, 3, 0, 0, tzinfo=timezone.utc), 80.0, 82.0, 78.0, 80.0, 200.0)
    )
    weekly_rows = [
        _make_binance_kline_row(datetime(2025, 5, 12, 0, 0, tzinfo=timezone.utc) + timedelta(weeks=i), 50.0, 55.0, 45.0, 50.0, 5000.0)
        for i in range(20)
    ]

    mock_session = _make_mock_http_session(daily_rows=daily_rows, weekly_rows=weekly_rows, fx_rate_idr=16000.0)
    symbol = "SOLIDR" if currency == "IDR" else "SOLUSDT"
    budget = 500_000.0 if currency == "IDR" else 300.0
    result = PromptPipeline(data_client=MarketDataClient(session=mock_session)).execute(
        ExecutionConfig(symbol=symbol, budget=budget, currency=currency, mode="moderate"),
        options=PipelineOptions(save_to_disk=False, copy_clipboard=False, snapshot_time=datetime(2025, 10, 3, 12, 0, tzinfo=timezone.utc)),
    )

    assert result.facts is not None
    assert result.facts.vwap is not None
    assert result.facts.vwap.q_vwap_lower_2 == pytest.approx(-30.0)
    assert result.facts.guardrails is not None
    assert result.facts.guardrails.q_vwap_lower_2_target is None

    prompt = result.rendered_prompt
    inval_section = prompt.split("Order Invalidation & Re-anchoring Protocol", maxsplit=1)[1]
    cont_section = inval_section.split("Self-Check Validasi Kuantitatif", maxsplit=1)[0]

    assert "-Rp" not in cont_section
    assert "-$" not in cont_section
    assert "-30." not in cont_section
    assert "`Q-VWAP -2σ` atau" in cont_section
    assert "`Q-VWAP -2σ` (N/A (<= 0))" in cont_section


def test_resolve_execution_guardrails_edge_boundaries():
    """Memastikan resolve_execution_guardrails menjaga seluruh target <= 0 atau tidak tersedia menjadi None."""
    facts = IndicatorFacts(
        symbol="TESTUSDT",
        current_price=10.0,
        price_range_30d=PriceRange30D(low=5.0, high=15.0, percentile=50.0),
        sma_200w=50.0,
        sma_200w_available=False,
        atr_14_daily=0.0,
        min_notional=10000.0,
        vwap=VWAPFacts(
            q_vwap=20.0,
            q_vwap_lower_2=0.0,
            r_vwap_365d=30.0,
            r_vwap_365d_available=False,
        ),
    )

    guardrails = resolve_execution_guardrails(facts)
    assert guardrails.half_atr == 0.0
    assert guardrails.max_l1_price is None
    assert guardrails.crash_3x_price is None
    assert guardrails.crash_5x_price is None
    assert guardrails.q_vwap_lower_2_target is None
    assert guardrails.r_vwap_365d_target is None
    assert guardrails.sma_200w_target is None
    assert guardrails.consolidation_threshold == 20000.0

