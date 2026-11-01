"""Antarmuka baris perintah (CLI) spot-prompt menggunakan Click."""

import sys
from typing import Any, Optional, Set
import click

from spot_prompt.config import DEFAULT_CURRENCY, DEFAULT_MODE, RISK_MODES
from spot_prompt.data_fetcher import (
    DataFetchError,
    ProviderConnectionError,
    fetch_btc_performance,
    fetch_fear_and_greed,
    fetch_market_klines_with_fallback,
    fetch_relative_performance_vs_btc,
    get_default_session,
)
from spot_prompt.indicators import extract_indicator_facts
from spot_prompt.models import ExecutionConfig
from spot_prompt.normalizer import is_btc_symbol, normalize_symbol
from spot_prompt.output import copy_to_clipboard, save_prompt_to_file
from spot_prompt.template_renderer import render_spot_prompt


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
            # Jalankan wizard interaktif jika tidak ada simbol yang diberikan
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

        # Inisialisasi session dengan opsi proxy dan pelacak domain unreachable bersama
        session = get_default_session(proxy=proxy)
        unreachable_domains: Set[str] = set()

        def on_fallback_provider(prev: str, next_prov: str, reason: Optional[Any] = None) -> None:
            if reason == "blocked" or isinstance(reason, ProviderConnectionError):
                click.echo(
                    f"  ⚠️  {click.style(f'Akses ke {prev} diblokir atau gagal koneksi.', fg='yellow')} "
                    f"Mengalihkan ke {click.style(next_prov, fg='yellow', bold=True)}..."
                )
            elif reason == "short_circuit":
                click.echo(
                    f"  ⚡ {click.style(f'Domain {prev} dilewati (short-circuit).', fg='yellow')} "
                    f"Mengalihkan ke {click.style(next_prov, fg='yellow', bold=True)}..."
                )
            else:
                click.echo(
                    f"  ℹ️  Simbol '{config.symbol}' tidak ditemukan di {prev}. "
                    f"Mengalihkan ke {click.style(next_prov, fg='yellow')}..."
                )

        # 1. Tarik Candlestick Harian (1d) dan Mingguan (1w) dengan fallback otomatis
        click.echo("  ⏳ Mengambil data klines 1d & 1w...")
        df_daily, df_weekly, source_exchange = fetch_market_klines_with_fallback(
            config.symbol,
            session=session,
            on_fallback=on_fallback_provider,
            unreachable_domains=unreachable_domains,
        )
        click.echo(f"  ✅ Data klines diperoleh dari {click.style(source_exchange, fg='green', bold=True)}.")

        # 2. Tarik Indeks Sentimen Fear & Greed
        click.echo("  ⏳ Mengambil indeks Crypto Fear & Greed...")
        fg_score, fg_text = fetch_fear_and_greed(session=session)

        # 3. Tarik Performa vs Benchmark BTC
        click.echo("  ⏳ Mengalkulasi konteks performa relatif vs BTC...")
        perf_vs_btc = None
        btc_30d, btc_90d = None, None
        if is_btc_symbol(config.symbol):
            btc_30d, btc_90d = fetch_btc_performance(
                session=session,
                unreachable_domains=unreachable_domains,
                on_fallback=on_fallback_provider,
            )
        else:
            perf_vs_btc = fetch_relative_performance_vs_btc(
                config.symbol,
                df_daily,
                session=session,
                unreachable_domains=unreachable_domains,
                on_fallback=on_fallback_provider,
            )

        # 4. Kalkulasi Fakta Indikator
        click.echo("  ⏳ Menghitung indikator valuasi, momentum, dan Volume Profile POC...")
        facts = extract_indicator_facts(
            symbol=config.symbol,
            df_daily=df_daily,
            df_weekly=df_weekly,
            fear_greed=(fg_score, fg_text),
            perf_vs_btc_30d=perf_vs_btc,
            btc_perf_30d=btc_30d,
            btc_perf_90d=btc_90d,
            source_exchange=source_exchange,
        )

        # 5. Render Template Prompt
        rendered_prompt = render_spot_prompt(facts, config)

        # 6. Simpan ke Berkas Output
        saved_path = save_prompt_to_file(rendered_prompt, config.symbol, output_dir=output_dir)
        click.echo(f"  ✅ Prompt berhasil disimpan ke: {click.style(saved_path, fg='green')}")

        # 7. Salin ke Clipboard
        if not no_clipboard:
            copied = copy_to_clipboard(rendered_prompt)
            if copied:
                click.echo("  📋 " + click.style("Prompt telah disalin ke clipboard! Siap di-paste ke LLM.", fg='green', bold=True))
            else:
                click.echo("  ℹ️  Tidak dapat menyalin ke clipboard (lingkungan headless atau tool clipboard tidak terdeteksi).")

        # 8. Cetak ke stdout jika diminta
        if stdout:
            click.echo("\n" + "=" * 80)
            click.echo(rendered_prompt)
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
