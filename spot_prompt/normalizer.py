"""Utilitas normalisasi dan sanitasi simbol pasangan aset pasar crypto."""

import re

KNOWN_QUOTES = ("USDT", "USDC", "FDUSD", "BUSD", "BTC", "ETH", "EUR", "TRY")


def normalize_symbol(raw_input: str, default_quote: str = "USDT") -> str:
    """Mengubah format input simbol pengguna menjadi format standar Binance Spot.

    Contoh:
        'sol'        -> 'SOLUSDT'
        'SOL'        -> 'SOLUSDT'
        'sol/usdt'   -> 'SOLUSDT'
        'sol-usdt'   -> 'SOLUSDT'
        'sol_usdc'   -> 'SOLUSDC'
        'SOLUSDT'    -> 'SOLUSDT'
        'btc'        -> 'BTCUSDT'
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
    """Mengekstrak nama base asset dari simbol yang ternormalisasi.

    Contoh:
        'SOLUSDT' -> 'SOL'
        'BTCUSDT' -> 'BTC'
        'ETHBTC'  -> 'ETH'
    """
    for quote in KNOWN_QUOTES:
        if normalized_symbol.endswith(quote):
            return normalized_symbol[: -len(quote)]
    return normalized_symbol


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

