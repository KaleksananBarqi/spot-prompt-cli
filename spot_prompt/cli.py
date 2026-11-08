"""Antarmuka baris perintah (CLI) spot-prompt menggunakan Click."""

import sys
from typing import Any, Callable, Optional
import click

from spot_prompt.config import DEFAULT_CURRENCY, DEFAULT_MODE, RISK_MODES
from spot_prompt.data_client import (
    FALLBACK_REASON_BLOCKED,
    FALLBACK_REASON_SHORT_CIRCUIT,
    DataFetchError,
    ProviderConnectionError,
)
from spot_prompt.models import ExecutionConfig
from spot_prompt.normalizer import normalize_symbol
from spot_prompt.pipeline import PipelineOptions, PromptPipeline


def make_fallback_logger(symbol_name: str) -> Callable[[str, str, Optional[Any]], None]:
    """Membuat callback logger fallback yang menampilkan pesan transisi sesuai alasan kegagalan."""
    def on_fallback_provider(prev: str, next_prov: str, reason: Optional[Any] = None) -> None:
        if reason in ("short_circuit", FALLBACK_REASON_SHORT_CIRCUIT):
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

    raw_symbol = click.prompt("Masukkan simbol koin (contoh: SOL, BTC, ETH, SUI)", type=str)
    symbol = normalize_symbol(raw_symbol)

    budget_input = click.prompt(
        "Masukkan budget akumulasi periode ini (tekan Enter untuk lewati)",
        default="",
        show_default=False,
    )
    budget: Optional[float] = None
    if budget_input.strip():
        try:
            budget = float(budget_input.strip())
        except ValueError:
            click.echo("⚠️  Budget tidak valid, melanjutkan tanpa nominal angka spesifik.")

    mode = click.prompt(
        "Pilih profil risiko DCA",
        type=click.Choice(RISK_MODES, case_sensitive=False),
        default=DEFAULT_MODE,
        show_default=True,
    )

    return ExecutionConfig(
        symbol=symbol,
        budget=budget,
        currency=DEFAULT_CURRENCY,
        mode=mode.lower(),
    )


@click.command(context_settings=dict(help_option_names=["-h", "--help"]))
@click.option(
    "-s", "--symbol",
    type=str,
    default=None,
    help="Simbol koin (misal: SOL, BTC, ETH, SOLUSDT).",
)
@click.option(
    "-b", "--budget",
    type=float,
    default=None,
    help="Nominal budget DCA periode ini (misal: 300 atau 500).",
)
@click.option(
    "-c", "--currency",
    type=str,
    default=DEFAULT_CURRENCY,
    help="Mata uang budget (default: USDT).",
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
    help="Cetak seluruh isi teks prompt langsung ke terminal.",
)
@click.option(
    "--no-clipboard",
    is_flag=True,
    default=False,
    help="Jangan menyalin prompt ke clipboard sistem secara otomatis.",
)
def main(
    symbol: Optional[str],
    budget: Optional[float],
    currency: str,
    mode: str,
    proxy: Optional[str],
    output_dir: str,
    stdout: bool,
    no_clipboard: bool,
) -> None:
    """Spot DCA Prompt Generator untuk LLM hilir.

    Mengambil data pasar publik gratis dari Binance Spot dan Alternative.me,
    menghitung indikator teknikal (SMA 200W/200D, EMA 50D, Volume POC 90H, RSI,
    Bollinger Bands %B, ATR), lalu merender prompt evaluasi akumulasi bulanan.
    """
    try:
        if symbol is None:
            config = run_interactive_prompts()
        else:
            norm_symbol = normalize_symbol(symbol)
            config = ExecutionConfig(
                symbol=norm_symbol,
                budget=budget,
                currency=currency.upper(),
                mode=mode.lower(),
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
