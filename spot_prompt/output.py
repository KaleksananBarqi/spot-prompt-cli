"""Modul kompatibilitas mundur untuk penanganan output berkas dan clipboard."""

from spot_prompt.pipeline import PromptPipeline

_pipeline = PromptPipeline()


def generate_output_filename(symbol: str) -> str:
    from datetime import datetime, timezone
    now_utc = datetime.now(timezone.utc)
    ts_str = now_utc.strftime("%Y-%m-%d-%H-%M-%S-UTC")
    return f"{symbol.upper()}-SPOT-DCA-{ts_str}.md"


def save_prompt_to_file(content: str, symbol: str, output_dir: str = "./output") -> str:
    return _pipeline._save_to_file(content, symbol, output_dir)


def copy_to_clipboard(content: str) -> bool:
    return _pipeline._copy_clipboard(content)
