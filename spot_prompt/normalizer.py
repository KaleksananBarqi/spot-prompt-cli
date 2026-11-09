"""Utilitas normalisasi dan sanitasi simbol pasangan aset pasar crypto dan input pengguna."""

import re
from typing import Any, Optional, Tuple

KNOWN_QUOTES = ("USDT", "USDC", "FDUSD", "BUSD", "BTC", "ETH", "EUR", "TRY", "IDR")


def normalize_symbol(raw_input: str, default_quote: str = "USDT") -> str:
    """Mengubah format input simbol pengguna menjadi format standar.

    Contoh:
        'sol'        -> 'SOLUSDT'
        'SOL'        -> 'SOLUSDT'
        'sol/usdt'   -> 'SOLUSDT'
        'sol-usdt'   -> 'SOLUSDT'
        'sol_usdc'   -> 'SOLUSDC'
        'SOLUSDT'    -> 'SOLUSDT'
        'btc'        -> 'BTCUSDT'
        'btcidr'     -> 'BTCIDR'
    """
    if not raw_input:
        raise ValueError("Simbol tidak boleh kosong.")

    # Bersihkan whitespace dan ubah ke huruf besar
    cleaned = raw_input.strip().upper()

    # Hilangkan separator umum seperti '/', '-', '_'
    cleaned = re.sub(r"[\s/\-_]", "", cleaned)

    # Cek apakah sudah berakhiran salah satu quote currency yang dikenal
    for quote in KNOWN_QUOTES:
        if cleaned.endswith(quote) and len(cleaned) > len(quote):
            return cleaned

    # Jika tidak memiliki quote currency, tambahkan default quote (misal USDT)
    return f"{cleaned}{default_quote.upper()}"


def extract_base_asset(normalized_symbol: str) -> str:
    """Mengekstrak nama base asset dari simbol pasangan aset.

    Membersihkan separator dan memotong quote currency yang dikenali.

    Contoh:
        'SOLUSDT' -> 'SOL'
        'BTCUSDT' -> 'BTC'
        'ETHBTC'  -> 'ETH'
        'BTCIDR'  -> 'BTC'
        'BTC/IDR' -> 'BTC'
        'SOL-USDT'-> 'SOL'
    """
    cleaned = re.sub(r"[\s/\-_]", "", normalized_symbol.strip().upper())
    for quote in KNOWN_QUOTES:
        if cleaned.endswith(quote) and len(cleaned) > len(quote):
            return cleaned[: -len(quote)]
    return cleaned


def resolve_pair_and_currency(
    raw_symbol: str,
    explicit_currency: Optional[str] = None,
) -> Tuple[str, str, str]:
    """Menyelesaikan pasangan global likuid, base asset, dan mata uang eksekusi.

    Mengembalikan:
        (global_symbol, base_asset, resolved_currency)

    Contoh:
        resolve_pair_and_currency('BTCIDR') -> ('BTCUSDT', 'BTC', 'IDR')
        resolve_pair_and_currency('SOL', 'IDR') -> ('SOLUSDT', 'SOL', 'IDR')
        resolve_pair_and_currency('SOLUSDT') -> ('SOLUSDT', 'SOL', 'USDT')
    """
    normalized = normalize_symbol(raw_symbol)
    base = extract_base_asset(normalized)

    # Cek apakah simbol secara eksplisit meminta IDR
    if normalized.endswith("IDR"):
        resolved_currency = "IDR"
        global_symbol = f"{base}USDT"
    elif explicit_currency and explicit_currency.strip().upper() == "IDR":
        resolved_currency = "IDR"
        global_symbol = f"{base}USDT"
    else:
        resolved_currency = (explicit_currency or "USDT").strip().upper()
        global_symbol = normalized

    return global_symbol, base, resolved_currency


def format_display_symbol(base_asset: str, currency: str) -> str:
    """Menghasilkan label format tampilan pasangan aset untuk pengguna dan prompt."""
    if currency.upper() == "IDR":
        return f"{base_asset.upper()}/IDR"
    return f"{base_asset.upper()}{currency.upper()}"


def sanitize_budget_input(raw_budget: Any) -> Optional[float]:
    """Membersihkan dan mem-parsing nominal budget dari berbagai format penulisan.

    Mendukung format angka Indonesia (misal: '1.500.000', '1.500.000,50', 'Rp 2.000.000')
    maupun format standar internasional ('1500000', '1500000.50', '1,500,000').

    Contoh:
        '1.500.000'    -> 1500000.0
        'Rp 2.500.000' -> 2500000.0
        '1,500,000'    -> 1500000.0
        '300'          -> 300.0
        '10.50'        -> 10.50
        ''             -> None
    """
    if raw_budget is None:
        return None

    if isinstance(raw_budget, (int, float)):
        val = float(raw_budget)
        return val if val >= 0 else None

    text = str(raw_budget).strip()
    if not text:
        return None

    # Hapus prefix mata uang seperti Rp, IDR, USDT, $, dsb.
    cleaned = re.sub(r"(?i)^(rp|idr|usdt|\$)\s*", "", text).strip()
    cleaned = re.sub(r"(?i)\s*(idr|usdt)$", "", cleaned).strip()

    if not cleaned:
        return None

    # Evaluasi pemisah titik (.) dan koma (,)
    has_dot = "." in cleaned
    has_comma = "," in cleaned

    if has_dot and has_comma:
        last_dot = cleaned.rfind(".")
        last_comma = cleaned.rfind(",")
        if last_comma > last_dot:
            # Format Indonesia: 1.500.000,50 (titik = ribuan, koma = desimal)
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            # Format US: 1,500,000.50 (koma = ribuan, titik = desimal)
            cleaned = cleaned.replace(",", "")
    elif has_dot:
        parts = cleaned.split(".")
        if len(parts) > 2:
            # Lebih dari satu titik: jelas ribuan (1.500.000)
            cleaned = cleaned.replace(".", "")
        elif len(parts) == 2:
            # Tepat satu titik: misal 1.500 atau 10.50
            if len(parts[1]) == 3 and parts[0].isdigit() and int(parts[0]) >= 1:
                cleaned = cleaned.replace(".", "")
            else:
                pass
    elif has_comma:
        parts = cleaned.split(",")
        if len(parts) > 2:
            # Lebih dari satu koma: ribuan (1,500,000)
            cleaned = cleaned.replace(",", "")
        elif len(parts) == 2:
            if len(parts[1]) == 3 and parts[0].isdigit() and int(parts[0]) >= 1:
                cleaned = cleaned.replace(",", "")
            else:
                # Koma desimal (misal 10,50)
                cleaned = cleaned.replace(",", ".")

    try:
        val = float(cleaned)
        return val if val >= 0 else None
    except ValueError:
        return None


def is_btc_symbol(normalized_symbol: str) -> bool:
    """Mengecek apakah simbol yang diperiksa adalah Bitcoin itu sendiri."""
    base = extract_base_asset(normalized_symbol)
    return base == "BTC"


def to_gateio_currency_pair(normalized_symbol: str) -> str:
    """Mengubah simbol standar (misal SOLUSDT) menjadi format Gate.io (SOL_USDT).

    Contoh:
        'SOLUSDT'      -> 'SOL_USDT'
        'FARTCOINUSDT' -> 'FARTCOIN_USDT'
        'BTCUSDC'      -> 'BTC_USDC'
    """
    for quote in KNOWN_QUOTES:
        if normalized_symbol.endswith(quote) and len(normalized_symbol) > len(quote):
            base = normalized_symbol[:-len(quote)]
            return f"{base}_{quote}"
    return normalized_symbol
