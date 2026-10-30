"""Penanganan output berkas dan penyalinan ke papan klip (clipboard)."""

from datetime import datetime, timezone
import os
from typing import Optional
import pyperclip


def generate_output_filename(symbol: str) -> str:
    """Menghasilkan nama berkas unik dengan timestamp UTC."""
    now_utc = datetime.now(timezone.utc)
    ts_str = now_utc.strftime("%Y-%m-%d-%H-%M-%S-UTC")
    return f"{symbol.upper()}-SPOT-DCA-{ts_str}.md"


def save_prompt_to_file(
    content: str,
    symbol: str,
    output_dir: str = "./output",
) -> str:
    """Menyimpan konten prompt ke dalam berkas Markdown di direktori output."""
    os.makedirs(output_dir, exist_ok=True)
    filename = generate_output_filename(symbol)
    filepath = os.path.join(output_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    return os.path.abspath(filepath)


def copy_to_clipboard(content: str) -> bool:
    """Menyalin konten prompt ke papan klip sistem (best-effort)."""
    try:
        pyperclip.copy(content)
        return True
    except Exception:
        # Menangani sistem headless tanpa display server / xclip / wl-copy
        return False
