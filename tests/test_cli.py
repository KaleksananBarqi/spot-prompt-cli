"""Unit test untuk Click CLI (spot_prompt/cli.py)."""

import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import MagicMock, patch
import pytest
from click.testing import CliRunner

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


def test_cli_help_explains_zero_auth_single_paste_and_headless():
    """Pesan bantuan CLI menegaskan arsitektur Zero-Auth single-paste tanpa SDK/API Key LLM."""
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    lower_out = result.output.lower()
    assert "zero-auth" in lower_out
    assert "single-paste" in lower_out
    assert "api key" in lower_out
    assert "sdk" in lower_out
    assert "--no-clipboard" in result.output
    assert "--stdout" in result.output
    assert "colab" in lower_out or "headless" in lower_out


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
        assert "Binance Futures" in result.output
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


def test_cli_dependency_guard_shows_friendly_install_hint_when_jinja2_missing(monkeypatch):
    """CLI menampilkan instruksi instalasi ramah tanpa traceback mentah saat dependensi hilang."""
    runner = CliRunner()
    monkeypatch.setitem(sys.modules, "jinja2", None)

    with patch(
        "spot_prompt.cli.PromptPipeline",
        side_effect=AssertionError("PromptPipeline tidak boleh dijalankan saat dependensi hilang"),
    ):
        result = runner.invoke(main, ["-s", "SOL", "--no-clipboard"])

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "jinja2" in result.output
    assert "pip install -e ." in result.output
    assert "pip install -r requirements.txt" in result.output
    assert "python -m spot_prompt" in result.output
    assert "Python >= 3.10" in result.output


@pytest.mark.parametrize(
    "module_target,missing_dep",
    [
        ("spot_prompt", "jinja2"),
        ("spot_prompt", "pandas"),
        ("spot_prompt", "click"),
        ("spot_prompt.cli", "jinja2"),
    ],
)
def test_cli_entrypoint_handles_missing_dependency_at_startup_without_traceback(
    module_target, missing_dep
):
    """Menjalankan titik masuk CLI saat startup tanpa dependensi mencetak pesan ramah tanpa traceback."""
    repo_root = str(Path(__file__).resolve().parent.parent)
    env = {**os.environ, "PYTHONPATH": repo_root}
    script = (
        "import runpy, sys; "
        f"sys.modules[{missing_dep!r}] = None; "
        "sys.argv = ['spot-prompt', '-s', 'SOL', '--no-clipboard']; "
        f"runpy.run_module({module_target!r}, run_name='__main__')"
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    combined = proc.stdout + proc.stderr
    assert proc.returncode == 1
    assert "Traceback" not in combined
    assert "ModuleNotFoundError" not in combined
    assert missing_dep in combined
    assert "pip install -e ." in combined
    assert "pip install -r requirements.txt" in combined


def test_cli_dependency_guard_when_pandas_missing_via_import_hook(monkeypatch):
    """Penjaga dependensi menangkap ModuleNotFoundError saat mode tanpa argumen dipanggil."""
    import builtins

    real_import = builtins.__import__

    def blocked_pandas_import(name, *args, **kwargs):
        if name == "pandas":
            raise ModuleNotFoundError("No module named 'pandas'", name="pandas")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_pandas_import)
    runner = CliRunner()

    with patch(
        "spot_prompt.cli.PromptPipeline",
        side_effect=AssertionError("PromptPipeline tidak boleh dijalankan saat dependensi hilang"),
    ):
        result = runner.invoke(main, [])

    assert result.exit_code == 1
    assert "Traceback" not in result.output
    assert "pandas" in result.output
    assert "pip install -e ." in result.output

