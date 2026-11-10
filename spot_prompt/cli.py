"""Antarmuka baris perintah (CLI) spot-prompt menggunakan Click."""

import sys
from typing import Any, Callable, List, Optional, Tuple

from spot_prompt.config import (
    DEFAULT_CURRENCY,
    DEFAULT_MODE,
    RISK_MODES,
    SUPPORTED_CURRENCIES,
)
from spot_prompt.models import ExecutionConfig
from spot_prompt.normalizer import (
    resolve_pair_and_currency,
    sanitize_budget_input,
)

# Pasangan (nama_modul_import, nama_paket_pip) untuk dependensi runtime inti CLI.
_REQUIRED_RUNTIME_PACKAGES: Tuple[Tuple[str, str], ...] = (
    ("click", "click"),
    ("requests", "requests"),
    ("pandas", "pandas"),
    ("numpy", "numpy"),
    ("jinja2", "jinja2"),
    ("pyperclip", "pyperclip"),
)

_STARTUP_IMPORT_ERROR: Optional[str] = None
try:
    import click
    from spot_prompt.data_client import (
        FALLBACK_REASON_BLOCKED,
        FALLBACK_REASON_SHORT_CIRCUIT,
        DataFetchError,
        ProviderConnectionError,
    )
    from spot_prompt.pipeline import PipelineOptions, PromptPipeline
except ImportError as exc:
    click = None  # type: ignore[assignment]
    PromptPipeline = None  # type: ignore[assignment,misc]
    PipelineOptions = None  # type: ignore[assignment,misc]
    DataFetchError = Exception  # type: ignore[assignment,misc]
    ProviderConnectionError = Exception  # type: ignore[assignment,misc]
    FALLBACK_REASON_BLOCKED = "blocked"
    FALLBACK_REASON_SHORT_CIRCUIT = "short_circuit"
    _STARTUP_IMPORT_ERROR = exc.name or str(exc)


def _find_missing_dependencies() -> List[str]:
    """Memeriksa modul runtime wajib lewat __import__ agar simulasi pengujian tetap terdeteksi."""
    missing: List[str] = []
    for module_name, package_name in _REQUIRED_RUNTIME_PACKAGES:
        try:
            __import__(module_name)
        except ImportError:
            missing.append(package_name)
    if _STARTUP_IMPORT_ERROR and _STARTUP_IMPORT_ERROR not in missing:
        missing.append(_STARTUP_IMPORT_ERROR)
    return missing


def _format_missing_dependency_message(missing_packages: List[str]) -> str:
    """Menyusun pesan galat instalasi yang ramah tanpa traceback mentah."""
    package_list = ", ".join(missing_packages)
    return (
        f"\n❌ Dependensi runtime spot-prompt belum terpasang: {package_list}\n\n"
        "Pastikan Anda menggunakan Python >= 3.10 dan virtual environment sudah aktif,\n"
        "lalu jalankan salah satu perintah berikut:\n"
        "  1. Instalasi paket CLI penuh (mengaktifkan perintah 'spot-prompt'):\n"
        "     pip install -e .\n"
        "  2. Instalasi dependensi pustaka saja (jalankan lewat 'python -m spot_prompt'):\n"
        "     pip install -r requirements.txt\n\n"
        "Catatan: spot-prompt adalah utilitas Zero-Auth single-paste tanpa SDK atau API Key LLM.\n"
    )


def _ensure_runtime_dependencies() -> None:
    """Menghentikan eksekusi CLI dengan pesan instalasi ramah bila dependensi hilang."""
    missing = _find_missing_dependencies()
    if missing:
        message = _format_missing_dependency_message(missing)
        if click is not None and "click" not in missing:
            click.echo(message, err=True)
        else:
            print(message, file=sys.stderr)
        sys.exit(1)


if _STARTUP_IMPORT_ERROR is not None or click is None:
    def make_fallback_logger(symbol_name: str) -> Callable[[str, str, Optional[Any]], None]:
        """Logger placeholder saat dependensi runtime CLI belum lengkap."""
        def on_fallback_provider(prev: str, next_prov: str, reason: Optional[Any] = None) -> None:
            return None

        return on_fallback_provider

    def main(*args: Any, **kwargs: Any) -> None:
        """Titik masuk pengganti saat dependensi runtime gagal diimpor."""
        _ensure_runtime_dependencies()
else:
    def make_fallback_logger(symbol_name: str) -> Callable[[str, str, Optional[Any]], None]:
        """Membuat callback logger fallback yang menampilkan pesan transisi sesuai alasan kegagalan."""
        def on_fallback_provider(prev: str, next_prov: str, reason: Optional[Any] = None) -> None:
            if "Indodax" in prev or "CoinGecko" in next_prov:
                click.echo(
                    f"  ⚠️  {click.style(f'Koneksi ke {prev} gagal.', fg='yellow')} "
                    f"Mengalihkan penarikan kurs ke {click.style(next_prov, fg='yellow', bold=True)}..."
                )
            elif reason in ("short_circuit", FALLBACK_REASON_SHORT_CIRCUIT):
                click.echo(
                    f"  ⚡ {click.style(f'Domain {prev} dilewati (short-circuit).', fg='yellow')} "
                    f"Mengalihkan ke {click.style(next_prov, fg='yellow', bold=True)}..."
                )
            elif reason in ("blocked", FALLBACK_REASON_BLOCKED) or isinstance(reason, ProviderConnectionError):
                click.echo(
                    f"  ⚠️  {click.style(f'Akses ke {prev} diblokir atau gagal koneksi.', fg='yellow')} "
                    f"Mengalihkan ke {click.style(next_prov, fg='yellow', bold=True)}..."
                )
            else:
                click.echo(
                    f"  ℹ️  Simbol '{symbol_name}' tidak ditemukan di {prev}. "
                    f"Mengalihkan ke {click.style(next_prov, fg='yellow')}..."
                )

        return on_fallback_provider

    def run_interactive_prompts() -> ExecutionConfig:
        """Menjalankan wizard interaktif jika CLI dijalankan tanpa argumen."""
        click.echo("\n🎯 === Spot DCA Prompt Generator (Interactive Mode) ===\n")

        raw_symbol = click.prompt("Masukkan simbol koin (contoh: SOL, BTC, BTCIDR, ETH, SUI)", type=str)
        _, _, auto_curr = resolve_pair_and_currency(raw_symbol)

        currency = click.prompt(
            "Pilih mata uang budget",
            type=click.Choice(SUPPORTED_CURRENCIES, case_sensitive=False),
            default=auto_curr,
            show_default=True,
        ).upper()

        budget_prompt_text = (
            f"Masukkan budget akumulasi periode ini dalam {currency} (contoh: {'1.500.000' if currency == 'IDR' else '300'}, tekan Enter untuk lewati)"
        )
        budget_input = click.prompt(
            budget_prompt_text,
            default="",
            show_default=False,
        )
        budget: Optional[float] = None
        if budget_input.strip():
            budget = sanitize_budget_input(budget_input)
            if budget is None:
                click.echo("⚠️  Format budget tidak valid, melanjutkan tanpa nominal angka spesifik.")

        mode = click.prompt(
            "Pilih profil risiko DCA",
            type=click.Choice(RISK_MODES, case_sensitive=False),
            default=DEFAULT_MODE,
            show_default=True,
        )

        return ExecutionConfig(
            symbol=raw_symbol,
            budget=budget,
            currency=currency,
            mode=mode.lower(),
        )

    @click.command(context_settings=dict(help_option_names=["-h", "--help"]))
    @click.option(
        "-s", "--symbol",
        type=str,
        default=None,
        help="Simbol koin (misal: SOL, BTC, BTCIDR, SOL/IDR, SOLUSDT).",
    )
    @click.option(
        "-b", "--budget",
        type=str,
        default=None,
        help="Nominal budget DCA periode ini (misal: 300, 1500000, atau 1.500.000).",
    )
    @click.option(
        "-c", "--currency",
        type=click.Choice(SUPPORTED_CURRENCIES, case_sensitive=False),
        default=DEFAULT_CURRENCY,
        help="Mata uang budget (default: USDT). Pilihan: USDT, IDR.",
    )
    @click.option(
        "-r", "--fx-rate",
        type=float,
        default=None,
        help="Nilai tukar manual USDT/IDR (misal: 16200.0) untuk override kurs live.",
    )
    @click.option(
        "-m", "--mode",
        type=click.Choice(RISK_MODES, case_sensitive=False),
        default=DEFAULT_MODE,
        help="Profil risiko akumulasi (conservative / moderate / aggressive).",
    )
    @click.option(
        "-p", "--proxy",
        type=str,
        default=None,
        help="URL proxy HTTP/HTTPS/SOCKS5 (misal: http://127.0.0.1:7890).",
    )
    @click.option(
        "-o", "--output-dir",
        type=click.Path(),
        default="./output",
        help="Direktori tujuan penyimpanan berkas prompt .md (default: ./output).",
    )
    @click.option(
        "--stdout",
        is_flag=True,
        default=False,
        help="Cetak seluruh isi teks prompt langsung ke terminal (ideal untuk Google Colab/headless).",
    )
    @click.option(
        "--no-clipboard",
        is_flag=True,
        default=False,
        help="Jangan menyalin prompt ke clipboard sistem secara otomatis (gunakan di Colab/headless).",
    )
    def main(
        symbol: Optional[str],
        budget: Optional[str],
        currency: str,
        fx_rate: Optional[float],
        mode: str,
        proxy: Optional[str],
        output_dir: str,
        stdout: bool,
        no_clipboard: bool,
    ) -> None:
        """Spot DCA Prompt Generator (Zero-Auth single-paste) untuk LLM hilir.

        Mengambil data pasar publik gratis (Binance Spot, MEXC Spot, Binance Futures,
        Gate.io Spot, Alternative.me, serta kurs USDT/IDR Indodax/CoinGecko) tanpa
        API Key bursa maupun ketergantungan SDK/API Key LLM apa pun. Hasilnya berupa
        prompt siap tempel (single-paste) ke ChatGPT, Claude, Gemini, atau DeepSeek.

        Mendukung denominasi USDT dan Rupiah (IDR) via Hybrid IDR Valuation.
        Untuk lingkungan Google Colab/headless, jalankan dengan --no-clipboard --stdout.
        """
        _ensure_runtime_dependencies()
        try:
            if symbol is None:
                config = run_interactive_prompts()
                if fx_rate is not None:
                    config.fx_rate = fx_rate
            else:
                parsed_budget = sanitize_budget_input(budget) if budget is not None else None
                config = ExecutionConfig(
                    symbol=symbol,
                    budget=parsed_budget,
                    currency=currency.upper(),
                    mode=mode.lower(),
                    fx_rate=fx_rate,
                )

            click.echo(f"\n🚀 Memproses analisis Spot DCA untuk: {click.style(config.symbol, bold=True, fg='cyan')}")
            click.echo("  ⏳ Mengambil data pasar dan mengalkulasi fakta teknikal...")

            pipeline = PromptPipeline()
            options = PipelineOptions(
                proxy=proxy,
                output_dir=output_dir,
                save_to_disk=True,
                copy_clipboard=not no_clipboard,
                on_fallback=make_fallback_logger(config.symbol),
            )

            result = pipeline.execute(config, options=options)

            click.echo(f"  ✅ Data klines diperoleh dari {click.style(result.source_exchange, fg='green', bold=True)}.")
            if result.facts and result.facts.currency == "IDR" and result.facts.fx_rate:
                rate_int = int(round(result.facts.fx_rate))
                click.echo(f"  💵 Kurs acuan USDT/IDR: {click.style(f'Rp {rate_int:,}'.replace(',', '.'), fg='green', bold=True)}")

            if result.saved_filepath:
                click.echo(f"  ✅ Prompt berhasil disimpan ke: {click.style(result.saved_filepath, fg='green')}")

            if not no_clipboard:
                if result.copied_to_clipboard:
                    click.echo("  📋 " + click.style("Prompt telah disalin ke clipboard! Siap di-paste ke LLM.", fg='green', bold=True))
                else:
                    click.echo("  ℹ️  Tidak dapat menyalin ke clipboard (lingkungan headless atau tool clipboard tidak terdeteksi).")

            if stdout:
                click.echo("\n" + "=" * 80)
                click.echo(result.rendered_prompt)
                click.echo("=" * 80 + "\n")

            click.echo(f"\n✨ Selesai! Kamu tinggal menempelkan prompt tersebut ke ChatGPT, Claude, Gemini, atau DeepSeek.\n")

        except DataFetchError as dfe:
            click.echo(f"\n❌ {click.style('Kesalahan Pengambilan Data:', fg='red', bold=True)} {dfe}", err=True)
            sys.exit(1)
        except Exception as exc:
            click.echo(f"\n❌ {click.style('Terjadi Kesalahan:', fg='red', bold=True)} {exc}", err=True)
            sys.exit(1)


if __name__ == "__main__":
    main()
