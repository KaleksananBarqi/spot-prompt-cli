"""Unit test untuk Click CLI (spot_prompt/cli.py)."""

import json
import os
from unittest.mock import MagicMock, patch
import pytest
from click.testing import CliRunner

from spot_prompt.cli import main
from spot_prompt.data_fetcher import ProviderConnectionError, SymbolNotFoundError

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.fixture
def mock_fixtures():
    with open(os.path.join(FIXTURES_DIR, "mock_klines_daily.json")) as f:
        daily_json = json.load(f)
    with open(os.path.join(FIXTURES_DIR, "mock_fng.json")) as f:
        fng_json = json.load(f)
    return daily_json, fng_json


def test_cli_help():
    """CLI menampilkan pesan bantuan dengan opsi --proxy / -p."""
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "--proxy" in result.output
    assert "-p" in result.output


def test_cli_proxy_option_passed_to_session():
    """CLI menerima opsi -p / --proxy dan membuat session dengan proxy yang sesuai."""
    runner = CliRunner()
    with patch("spot_prompt.cli.get_default_session") as mock_get_session, \
         patch("spot_prompt.cli.fetch_market_klines_with_fallback") as mock_fetch_klines, \
         patch("spot_prompt.cli.fetch_fear_and_greed") as mock_fetch_fng, \
         patch("spot_prompt.cli.fetch_relative_performance_vs_btc") as mock_fetch_rel, \
         patch("spot_prompt.cli.save_prompt_to_file", return_value="output/test.md"), \
         patch("spot_prompt.cli.copy_to_clipboard", return_value=True):

        # Mock return dataframe
        from spot_prompt.data_fetcher import parse_binance_like_klines
        with open(os.path.join(FIXTURES_DIR, "mock_klines_daily.json")) as f:
            daily_json = json.load(f)
        df_dummy = parse_binance_like_klines(daily_json)

        mock_fetch_klines.return_value = (df_dummy, df_dummy, "Binance Spot")
        mock_fetch_fng.return_value = (50, "Neutral")
        mock_fetch_rel.return_value = 10.5

        result = runner.invoke(main, ["-s", "SOL", "--proxy", "http://127.0.0.1:8888", "--no-clipboard"])
        assert result.exit_code == 0
        mock_get_session.assert_called_once_with(proxy="http://127.0.0.1:8888")


def test_cli_terminal_log_blocked_warning_on_connection_error():
    """Terminal menampilkan peringatan akses diblokir/gagal koneksi jika fallback bursa
    disebabkan oleh ProviderConnectionError atau reason='blocked'."""
    runner = CliRunner()

    with patch("spot_prompt.cli.get_default_session"), \
         patch("spot_prompt.cli.fetch_market_klines_with_fallback") as mock_fetch_klines, \
         patch("spot_prompt.cli.fetch_fear_and_greed", return_value=(50, "Neutral")), \
         patch("spot_prompt.cli.fetch_relative_performance_vs_btc", return_value=5.0), \
         patch("spot_prompt.cli.save_prompt_to_file", return_value="output/test.md"), \
         patch("spot_prompt.cli.copy_to_clipboard", return_value=True):

        from spot_prompt.data_fetcher import parse_binance_like_klines
        with open(os.path.join(FIXTURES_DIR, "mock_klines_daily.json")) as f:
            daily_json = json.load(f)
        df_dummy = parse_binance_like_klines(daily_json)

        def fake_fetch(symbol, session=None, on_fallback=None, unreachable_domains=None):
            if on_fallback:
                # Simulasikan Binance Spot diblokir
                on_fallback("Binance Spot", "MEXC Spot", "blocked")
            return (df_dummy, df_dummy, "MEXC Spot")

        mock_fetch_klines.side_effect = fake_fetch

        result = runner.invoke(main, ["-s", "SOL", "--no-clipboard"])
        assert result.exit_code == 0
        assert "diblokir" in result.output.lower() or "gagal koneksi" in result.output.lower()
        assert "Binance Spot" in result.output
        assert "MEXC Spot" in result.output


def test_cli_terminal_log_short_circuit():
    """Terminal mencatat bahwa domain dilewati (short-circuit) ketika fallback callback
    menerima reason='short_circuit'."""
    runner = CliRunner()

    with patch("spot_prompt.cli.get_default_session"), \
         patch("spot_prompt.cli.fetch_market_klines_with_fallback") as mock_fetch_klines, \
         patch("spot_prompt.cli.fetch_fear_and_greed", return_value=(50, "Neutral")), \
         patch("spot_prompt.cli.fetch_relative_performance_vs_btc", return_value=5.0), \
         patch("spot_prompt.cli.save_prompt_to_file", return_value="output/test.md"), \
         patch("spot_prompt.cli.copy_to_clipboard", return_value=True):

        from spot_prompt.data_fetcher import parse_binance_like_klines
        with open(os.path.join(FIXTURES_DIR, "mock_klines_daily.json")) as f:
            daily_json = json.load(f)
        df_dummy = parse_binance_like_klines(daily_json)

        def fake_fetch(symbol, session=None, on_fallback=None, unreachable_domains=None):
            if on_fallback:
                on_fallback("Binance Spot", "MEXC Spot", "short_circuit")
            return (df_dummy, df_dummy, "MEXC Spot")

        mock_fetch_klines.side_effect = fake_fetch

        result = runner.invoke(main, ["-s", "SOL", "--no-clipboard"])
        assert result.exit_code == 0
        assert "short-circuit" in result.output.lower() or "dilewati" in result.output.lower()


def test_cli_terminal_log_not_found():
    """Terminal menampilkan info bahwa simbol tidak ditemukan jika reason='not_found'."""
    runner = CliRunner()

    with patch("spot_prompt.cli.get_default_session"), \
         patch("spot_prompt.cli.fetch_market_klines_with_fallback") as mock_fetch_klines, \
         patch("spot_prompt.cli.fetch_fear_and_greed", return_value=(50, "Neutral")), \
         patch("spot_prompt.cli.fetch_relative_performance_vs_btc", return_value=5.0), \
         patch("spot_prompt.cli.save_prompt_to_file", return_value="output/test.md"), \
         patch("spot_prompt.cli.copy_to_clipboard", return_value=True):

        from spot_prompt.data_fetcher import parse_binance_like_klines
        with open(os.path.join(FIXTURES_DIR, "mock_klines_daily.json")) as f:
            daily_json = json.load(f)
        df_dummy = parse_binance_like_klines(daily_json)

        def fake_fetch(symbol, session=None, on_fallback=None, unreachable_domains=None):
            if on_fallback:
                on_fallback("Binance Spot", "MEXC Spot", "not_found")
            return (df_dummy, df_dummy, "MEXC Spot")

        mock_fetch_klines.side_effect = fake_fetch

        result = runner.invoke(main, ["-s", "SOL", "--no-clipboard"])
        assert result.exit_code == 0
        assert "tidak ditemukan di Binance Spot" in result.output


def test_cli_short_proxy_option_passed():
    """CLI menerima opsi singkat -p dan meneruskan nilai proxy ke session."""
    runner = CliRunner()
    with patch("spot_prompt.cli.get_default_session") as mock_get_session, \
         patch("spot_prompt.cli.fetch_market_klines_with_fallback") as mock_fetch_klines, \
         patch("spot_prompt.cli.fetch_fear_and_greed", return_value=(50, "Neutral")), \
         patch("spot_prompt.cli.fetch_relative_performance_vs_btc", return_value=1.0), \
         patch("spot_prompt.cli.save_prompt_to_file", return_value="output/test.md"), \
         patch("spot_prompt.cli.copy_to_clipboard", return_value=True):

        from spot_prompt.data_fetcher import parse_binance_like_klines
        with open(os.path.join(FIXTURES_DIR, "mock_klines_daily.json")) as f:
            daily_json = json.load(f)
        df_dummy = parse_binance_like_klines(daily_json)
        mock_fetch_klines.return_value = (df_dummy, df_dummy, "Binance Spot")

        result = runner.invoke(main, ["-s", "BTC", "-p", "socks5://127.0.0.1:1080", "--no-clipboard"])
        assert result.exit_code == 0
        mock_get_session.assert_called_once_with(proxy="socks5://127.0.0.1:1080")


def test_cli_error_diagnosis_on_network_failure():
    """Terminal menampilkan diagnosis kegagalan jaringan dan rekomendasi flag --proxy saat DataFetchError."""
    runner = CliRunner()
    with patch("spot_prompt.cli.get_default_session"), \
         patch("spot_prompt.cli.fetch_market_klines_with_fallback") as mock_fetch_klines:

        mock_fetch_klines.side_effect = ProviderConnectionError(
            "Gagal terhubung ke seluruh bursa (Binance Spot, MEXC Spot, Binance Futures, Gate.io Spot) "
            "akibat kendala jaringan atau pemblokiran akses. Periksa koneksi internet Anda atau gunakan flag --proxy."
        )

        result = runner.invoke(main, ["-s", "SOL", "--no-clipboard"])
        assert result.exit_code != 0
        assert "Kesalahan Pengambilan Data" in result.output
        assert "--proxy" in result.output

