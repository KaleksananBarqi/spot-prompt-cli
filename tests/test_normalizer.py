"""Unit test untuk normalizer simbol aset."""

import pytest
from spot_prompt.normalizer import (
    extract_base_asset,
    format_display_symbol,
    is_btc_symbol,
    normalize_symbol,
    resolve_pair_and_currency,
    sanitize_budget_input,
    to_gateio_currency_pair,
)


def test_normalize_symbol_variations():
    assert normalize_symbol("sol") == "SOLUSDT"
    assert normalize_symbol("SOL") == "SOLUSDT"
    assert normalize_symbol("sol/usdt") == "SOLUSDT"
    assert normalize_symbol("sol-usdt") == "SOLUSDT"
    assert normalize_symbol("SOL_USDT") == "SOLUSDT"
    assert normalize_symbol("btc") == "BTCUSDT"
    assert normalize_symbol("eth/usdc") == "ETHUSDC"
    assert normalize_symbol("SOLUSDT") == "SOLUSDT"
    assert normalize_symbol("adaeur") == "ADAEUR"
    assert normalize_symbol("btcidr") == "BTCIDR"


def test_resolve_pair_and_currency():
    # IDR suffix auto-detection (3-tuple contract)
    g_sym, base, curr = resolve_pair_and_currency("btcidr")
    assert g_sym == "BTCUSDT"
    assert base == "BTC"
    assert curr == "IDR"
    assert format_display_symbol(base, curr) == "BTC/IDR"

    g_sym, base, curr = resolve_pair_and_currency("SOL/IDR")
    assert g_sym == "SOLUSDT"
    assert base == "SOL"
    assert curr == "IDR"
    assert format_display_symbol(base, curr) == "SOL/IDR"

    # Explicit currency flag
    g_sym, base, curr = resolve_pair_and_currency("sol", explicit_currency="IDR")
    assert g_sym == "SOLUSDT"
    assert base == "SOL"
    assert curr == "IDR"

    # Default USDT
    g_sym, base, curr = resolve_pair_and_currency("sol")
    assert g_sym == "SOLUSDT"
    assert base == "SOL"
    assert curr == "USDT"
    assert format_display_symbol(base, curr) == "SOLUSDT"


def test_sanitize_budget_input():
    assert sanitize_budget_input(None) is None
    assert sanitize_budget_input("") is None
    assert sanitize_budget_input(500) == 500.0
    assert sanitize_budget_input(1500000.5) == 1500000.5
    assert sanitize_budget_input("300") == 300.0
    assert sanitize_budget_input("10.50") == 10.50
    assert sanitize_budget_input("1.500.000") == 1500000.0
    assert sanitize_budget_input("1.500.000,50") == 1500000.50
    assert sanitize_budget_input("Rp 2.000.000") == 2000000.0
    assert sanitize_budget_input("Rp2500000") == 2500000.0
    assert sanitize_budget_input("1,500,000") == 1500000.0
    assert sanitize_budget_input("1,500,000.50") == 1500000.50
    assert sanitize_budget_input("invalid") is None


def test_normalize_empty_symbol():
    with pytest.raises(ValueError):
        normalize_symbol("")


def test_extract_base_asset():
    assert extract_base_asset("SOLUSDT") == "SOL"
    assert extract_base_asset("BTCUSDT") == "BTC"
    assert extract_base_asset("ETHUSDC") == "ETH"
    assert extract_base_asset("BNBBTC") == "BNB"
    assert extract_base_asset("BTCIDR") == "BTC"
    assert extract_base_asset("BTC/IDR") == "BTC"
    assert extract_base_asset("SOL-USDT") == "SOL"


def test_is_btc_symbol():
    assert is_btc_symbol("BTCUSDT") is True
    assert is_btc_symbol("BTCUSDC") is True
    assert is_btc_symbol("BTCIDR") is True
    assert is_btc_symbol("BTC/IDR") is True
    assert is_btc_symbol("BTC-USDT") is True
    assert is_btc_symbol("SOLUSDT") is False
    assert is_btc_symbol("ETHUSDT") is False


def test_to_gateio_currency_pair():
    assert to_gateio_currency_pair("SOLUSDT") == "SOL_USDT"
    assert to_gateio_currency_pair("FARTCOINUSDT") == "FARTCOIN_USDT"
    assert to_gateio_currency_pair("BTCUSDC") == "BTC_USDC"
    assert to_gateio_currency_pair("CUSTOM") == "CUSTOM"
