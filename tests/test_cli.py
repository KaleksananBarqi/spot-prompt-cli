"""Unit test untuk Click CLI (spot_prompt/cli.py)."""

import json
import os
from unittest.mock import MagicMock, patch
import pytest
import requests
from click.testing import CliRunner

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

from spot_prompt.cli import main, make_fallback_logger
from spot_prompt.data_client import (
    FALLBACK_REASON_BLOCKED,
    FALLBACK_REASON_NOT_FOUND,
    FALLBACK_REASON_SHORT_CIRCUIT,
    DataFetchError,
    ProviderConnectionError,
    SymbolNotFoundError,
)
from spot_prompt.pipeline import PipelineOptions, PromptResult


def test_cli_help():
    """CLI menampilkan pesan bantuan dengan opsi --proxy / -p."""
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "--proxy" in result.output
    assert "-p" in result.output


def test_cli_proxy_option_passed_to_pipeline():
    """CLI menerima opsi -p / --proxy dan meneruskannya ke PromptPipeline."""
    runner = CliRunner()
    with patch("spot_prompt.cli.PromptPipeline") as mock_pipeline_cls:
        mock_instance = MagicMock()
        mock_pipeline_cls.return_value = mock_instance
        mock_instance.execute.return_value = PromptResult(
            symbol="SOLUSDT",
            rendered_prompt="PROMPT CONTENT",
            saved_filepath="output/test.md",
            copied_to_clipboard=True,
            source_exchange="Binance Spot",
        )

        result = runner.invoke(main, ["-s", "SOL", "--proxy", "http://127.0.0.1:8888", "--no-clipboard"])
        assert result.exit_code == 0
        mock_instance.execute.assert_called_once()
        _, kwargs = mock_instance.execute.call_args
        options: PipelineOptions = kwargs["options"]
        assert options.proxy == "http://127.0.0.1:8888"
        assert options.copy_clipboard is False


def test_cli_short_proxy_option_passed():
    """CLI menerima opsi -p sebagai alias singkat dari --proxy."""
    runner = CliRunner()
    with patch("spot_prompt.cli.PromptPipeline") as mock_pipeline_cls:
        mock_instance = MagicMock()
        mock_pipeline_cls.return_value = mock_instance
        mock_instance.execute.return_value = PromptResult(
            symbol="SOLUSDT",
            rendered_prompt="PROMPT CONTENT",
            saved_filepath="output/test.md",
            copied_to_clipboard=True,
            source_exchange="Binance Spot",
        )

        result = runner.invoke(main, ["-s", "SOL", "-p", "socks5://127.0.0.1:1080", "--no-clipboard"])
        assert result.exit_code == 0
        mock_instance.execute.assert_called_once()
        _, kwargs = mock_instance.execute.call_args
        options: PipelineOptions = kwargs["options"]
        assert options.proxy == "socks5://127.0.0.1:1080"


def test_cli_terminal_log_blocked_warning_on_connection_error():
    """Terminal menampilkan peringatan akses diblokir/gagal koneksi jika fallback bursa
    disebabkan oleh ProviderConnectionError atau reason='blocked'."""
    runner = CliRunner()

    with patch("spot_prompt.cli.PromptPipeline") as mock_pipeline_cls:
        mock_instance = MagicMock()
        mock_pipeline_cls.return_value = mock_instance

        def fake_execute(config, options=None):
            if options and options.on_fallback:
                options.on_fallback("Binance Spot", "MEXC Spot", "blocked")
            return PromptResult(
                symbol=config.symbol,
                rendered_prompt="PROMPT CONTENT",
                saved_filepath="output/test.md",
                copied_to_clipboard=True,
                source_exchange="MEXC Spot",
            )

        mock_instance.execute.side_effect = fake_execute

        result = runner.invoke(main, ["-s", "SOL", "--no-clipboard"])
        assert result.exit_code == 0
        assert "diblokir" in result.output.lower() or "gagal koneksi" in result.output.lower()
        assert "Binance Spot" in result.output
        assert "MEXC Spot" in result.output


def test_cli_terminal_log_short_circuit():
    """Terminal mencatat bahwa domain dilewati (short-circuit) ketika fallback callback
    menerima reason='short_circuit'."""
    runner = CliRunner()

    with patch("spot_prompt.cli.PromptPipeline") as mock_pipeline_cls:
        mock_instance = MagicMock()
        mock_pipeline_cls.return_value = mock_instance

        def fake_execute(config, options=None):
            if options and options.on_fallback:
                options.on_fallback("Binance Futures", "Gate.io Spot", "short_circuit")
            return PromptResult(
                symbol=config.symbol,
                rendered_prompt="PROMPT CONTENT",
                saved_filepath="output/test.md",
                copied_to_clipboard=True,
                source_exchange="Gate.io Spot",
            )

        mock_instance.execute.side_effect = fake_execute

        result = runner.invoke(main, ["-s", "SOL", "--no-clipboard"])
        assert result.exit_code == 0
        assert "short-circuit" in result.output.lower() or "dilewati" in result.output.lower()
        assert "Domain Binance Futures" not in result.output
        assert "Penyedia Binance Futures" in result.output
        assert "Gate.io Spot" in result.output


def test_cli_terminal_log_not_found():
    """Terminal mencatat simbol tidak ditemukan ketika reason='not_found'."""
    runner = CliRunner()

    with patch("spot_prompt.cli.PromptPipeline") as mock_pipeline_cls:
        mock_instance = MagicMock()
        mock_pipeline_cls.return_value = mock_instance

        def fake_execute(config, options=None):
            if options and options.on_fallback:
                options.on_fallback("Binance Spot", "MEXC Spot", "not_found")
            return PromptResult(
                symbol=config.symbol,
                rendered_prompt="PROMPT CONTENT",
                saved_filepath="output/test.md",
                copied_to_clipboard=True,
                source_exchange="MEXC Spot",
            )

        mock_instance.execute.side_effect = fake_execute

        result = runner.invoke(main, ["-s", "FARTCOIN", "--no-clipboard"])
        assert result.exit_code == 0
        assert "tidak ditemukan" in result.output.lower()
        assert "Binance Spot" in result.output
        assert "MEXC Spot" in result.output


def test_cli_error_diagnosis_on_network_failure():
    """Terminal menampilkan diagnosis kegagalan jaringan saat DataFetchError."""
    runner = CliRunner()
    with patch("spot_prompt.cli.PromptPipeline") as mock_pipeline_cls:
        mock_instance = MagicMock()
        mock_pipeline_cls.return_value = mock_instance
        mock_instance.execute.side_effect = ProviderConnectionError(
            "Gagal terhubung ke seluruh bursa akibat kendala jaringan. Gunakan flag --proxy."
        )

        result = runner.invoke(main, ["-s", "SOL", "--no-clipboard"])
        assert result.exit_code == 1
        assert "Kesalahan Pengambilan Data:" in result.output
        assert "--proxy" in result.output


def test_cli_interactive_mode():
    """CLI dapat dijalankan secara interaktif dengan prompt wizard."""
    runner = CliRunner()
    with patch("spot_prompt.cli.PromptPipeline") as mock_pipeline_cls:
        mock_instance = MagicMock()
        mock_pipeline_cls.return_value = mock_instance
        mock_instance.execute.return_value = PromptResult(
            symbol="BTCUSDT",
            rendered_prompt="PROMPT BTC",
            saved_filepath="output/btc.md",
            copied_to_clipboard=True,
            source_exchange="Binance Spot",
        )

        # Input: Symbol, Currency (default Enter), Budget, Mode
        result = runner.invoke(main, input="BTC\nUSDT\n500\nmoderate\n")
        assert result.exit_code == 0
        assert "Memproses analisis Spot DCA untuk: BTC" in result.output


def test_cli_idr_options():
    """CLI mendukung simbol IDR, sanitasi budget ribuan, dan override fx-rate."""
    runner = CliRunner()
    with patch("spot_prompt.cli.PromptPipeline") as mock_pipeline_cls:
        mock_instance = MagicMock()
        mock_pipeline_cls.return_value = mock_instance
        mock_instance.execute.return_value = PromptResult(
            symbol="BTC/IDR",
            rendered_prompt="PROMPT BTC IDR",
            saved_filepath="output/btcidr.md",
            copied_to_clipboard=True,
            source_exchange="Binance Spot",
        )

        result = runner.invoke(main, ["-s", "BTCIDR", "-b", "1.500.000", "-r", "18050.0"])
        assert result.exit_code == 0
        assert "Memproses analisis Spot DCA untuk: BTCIDR" in result.output

        call_args = mock_instance.execute.call_args[0]
        config = call_args[0]
        assert config.symbol == "BTCIDR"
        assert config.budget == 1500000.0
        assert config.fx_rate == 18050.0


def test_cli_interactive_mode_idr():
    """Mode interaktif memungkinkan pemilihan mata uang IDR untuk koin reguler."""
    runner = CliRunner()
    with patch("spot_prompt.cli.PromptPipeline") as mock_pipeline_cls:
        mock_instance = MagicMock()
        mock_pipeline_cls.return_value = mock_instance
        mock_instance.execute.return_value = PromptResult(
            symbol="SOL/IDR",
            rendered_prompt="PROMPT SOL IDR",
            saved_filepath="output/solidr.md",
            copied_to_clipboard=True,
            source_exchange="Binance Spot",
        )

        # User memasukkan 'SOL', lalu memilih mata uang 'IDR'
        result = runner.invoke(main, input="SOL\nIDR\n2.000.000\naggressive\n")
        assert result.exit_code == 0
        assert "Memproses analisis Spot DCA untuk: SOL" in result.output

        call_args = mock_instance.execute.call_args[0]
        config = call_args[0]
        assert config.symbol == "SOL"
        assert config.currency == "IDR"
        assert config.budget == 2000000.0
        assert config.mode == "aggressive"


def test_cli_full_session_blocked_binance_clean_fallback_logs(tmp_path):
    """Sesi CLI penuh saat binance.com diblokir menampilkan satu peringatan blokir akurat
    tanpa log short-circuit berulang atau pesan not_found palsu saat menarik performa BTC."""
    with open(os.path.join(FIXTURES_DIR, "mock_klines_daily.json")) as f:
        daily_json = json.load(f)
    with open(os.path.join(FIXTURES_DIR, "mock_klines_weekly.json")) as f:
        weekly_json = json.load(f)
    with open(os.path.join(FIXTURES_DIR, "mock_fng.json")) as f:
        fng_json = json.load(f)

    def fake_get(url, params=None, timeout=None):
        mock_resp = MagicMock(spec=requests.Response)
        symbol = (params or {}).get("symbol", "")
        interval = (params or {}).get("interval", "")

        if "api.binance.com" in url:
            mock_resp.status_code = 403
            return mock_resp

        if "fapi.binance.com" in url:
            raise AssertionError("Binance Futures seharusnya dilewati (short-circuit)!")

        if "api.mexc.com" in url:
            if symbol in ("HYPEUSDT", "BTCUSDT"):
                mock_resp.status_code = 200
                mock_resp.json.return_value = weekly_json if interval.lower() == "1w" else daily_json
                mock_resp.raise_for_status.return_value = None
                return mock_resp
            mock_resp.status_code = 404
            return mock_resp

        if "gateio.ws" in url or "api.gateio.ws" in url:
            mock_resp.status_code = 404
            return mock_resp

        if "fng" in url:
            mock_resp.status_code = 200
            mock_resp.json.return_value = fng_json
            mock_resp.raise_for_status.return_value = None
            return mock_resp

        mock_resp.status_code = 404
        return mock_resp

    mock_sess = MagicMock(spec=requests.Session)
    mock_sess.get.side_effect = fake_get

    runner = CliRunner()
    with patch("spot_prompt.data_client.create_default_session", return_value=mock_sess):
        result = runner.invoke(
            main,
            ["-s", "HYPE", "-m", "aggressive", "-o", str(tmp_path), "--no-clipboard"],
        )

    assert result.exit_code == 0, result.output
    assert result.output.count("Akses ke Binance Spot diblokir atau gagal koneksi.") == 1
    assert "short-circuit" not in result.output.lower()
    assert "Domain Binance Spot" not in result.output
    assert "tidak ditemukan di MEXC Spot" not in result.output
    assert "Data klines diperoleh dari MEXC Spot." in result.output


