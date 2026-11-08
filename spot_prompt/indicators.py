"""Modul kompatibilitas mundur untuk indikator teknikal."""

from spot_prompt.analyzer import (
    RawFactsAnalyzer,
    _calculate_atr,
    _calculate_bollinger_bands,
    _calculate_ema,
    _calculate_mini_candles,
    _calculate_price_range_30d,
    _calculate_rsi,
    _calculate_sma,
    _calculate_volume_poc,
)

calculate_sma = _calculate_sma
calculate_ema = _calculate_ema
calculate_rsi = _calculate_rsi
calculate_bollinger_bands = _calculate_bollinger_bands
calculate_atr = _calculate_atr
calculate_volume_poc = _calculate_volume_poc
calculate_price_range_30d = _calculate_price_range_30d
calculate_mini_candles = _calculate_mini_candles
extract_indicator_facts = RawFactsAnalyzer.extract_facts
