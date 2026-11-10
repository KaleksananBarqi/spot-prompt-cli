"""Unit test untuk PromptPipeline, MarketDataClient, dan RawFactsAnalyzer."""

from datetime import datetime, timedelta, timezone
import json
import os
from unittest.mock import MagicMock
import pandas as pd
import pytest
import requests

from spot_prompt.analyzer import RawFactsAnalyzer
from spot_prompt.data_client import MarketContext, MarketDataClient
from spot_prompt.models import ExecutionConfig
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
