"""Modul orkestrasi perakitan prompt Spot DCA (Deep Prompt Pipeline)."""

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from typing import Any, Callable, Optional
import jinja2
import pyperclip

from spot_prompt.analyzer import RawFactsAnalyzer
from spot_prompt.data_client import MarketDataClient
from spot_prompt.models import ExecutionConfig, IndicatorFacts

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
DEFAULT_TEMPLATE_NAME = "spot_dca_prompt.j2"


@dataclass(frozen=True)
class PipelineOptions:
    """Opsi eksekusi teknis untuk PromptPipeline."""
    proxy: Optional[str] = None
    output_dir: str = "./output"
    save_to_disk: bool = True
    copy_clipboard: bool = True
    on_fallback: Optional[Callable[[str, str, Optional[Any]], None]] = None


@dataclass(frozen=True)
class PromptResult:
    """Hasil keluaran eksekusi pipeline prompt."""
    symbol: str
    rendered_prompt: str
    saved_filepath: Optional[str] = None
    copied_to_clipboard: bool = False
    source_exchange: str = "Binance Spot"
    facts: Optional[IndicatorFacts] = None


class PromptPipeline:
    """Modul mendalam yang mengorkestrasikan data, analisis indikator, perenderan, dan penyimpanan prompt."""

    def __init__(
        self,
        data_client: Optional[MarketDataClient] = None,
        template_dir: str = TEMPLATE_DIR,
        template_name: str = DEFAULT_TEMPLATE_NAME,
    ) -> None:
        self.data_client = data_client
        self.template_dir = template_dir
        self.template_name = template_name
        self._jinja_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(self.template_dir),
            autoescape=jinja2.select_autoescape(disabled_extensions=("j2",)),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def _render(self, facts: IndicatorFacts, config: ExecutionConfig) -> str:
        template = self._jinja_env.get_template(self.template_name)
        return template.render(facts=facts, config=config)

    def _save_to_file(self, content: str, symbol: str, output_dir: str) -> str:
        os.makedirs(output_dir, exist_ok=True)
        now_utc = datetime.now(timezone.utc)
        ts_str = now_utc.strftime("%Y-%m-%d-%H-%M-%S-UTC")
        filename = f"{symbol.upper()}-SPOT-DCA-{ts_str}.md"
        filepath = os.path.join(output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return os.path.abspath(filepath)

    def _copy_clipboard(self, content: str) -> bool:
        try:
            pyperclip.copy(content)
            return True
        except Exception:
            return False

    def execute(
        self,
        config: ExecutionConfig,
        options: Optional[PipelineOptions] = None,
    ) -> PromptResult:
        """Mengeksekusi siklus perakitan prompt penuh dari penarikan data hingga persistensi."""
        opts = options or PipelineOptions()
        client = self.data_client or MarketDataClient(
            proxy=opts.proxy,
            on_fallback=opts.on_fallback,
        )

        # 1. Ambil data pasar
        context = client.fetch_context(config.symbol)

        # 2. Analisis indikator fakta
        facts = RawFactsAnalyzer.analyze_context(context)

        # 3. Render template Jinja2
        rendered = self._render(facts, config)

        # 4. Simpan ke berkas jika diminta
        saved_path = None
        if opts.save_to_disk:
            saved_path = self._save_to_file(rendered, config.symbol, opts.output_dir)

        # 5. Salin ke clipboard jika diminta
        copied = False
        if opts.copy_clipboard:
            copied = self._copy_clipboard(rendered)

        return PromptResult(
            symbol=config.symbol,
            rendered_prompt=rendered,
            saved_filepath=saved_path,
            copied_to_clipboard=copied,
            source_exchange=context.source_exchange,
            facts=facts,
        )
