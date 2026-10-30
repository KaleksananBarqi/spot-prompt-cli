"""Unit test untuk normalizer simbol aset."""

import pytest
from spot_prompt.normalizer import (
    extract_base_asset,
    is_btc_symbol,
    normalize_symbol,
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


def test_normalize_empty_symbol():
    with pytest.raises(ValueError):
        normalize_symbol("")


def test_extract_base_asset():
    assert extract_base_asset("SOLUSDT") == "SOL"
    assert extract_base_asset("BTCUSDT") == "BTC"
    assert extract_base_asset("ETHUSDC") == "ETH"
    assert extract_base_asset("BNBBTC") == "BNB"


def test_is_btc_symbol():
    assert is_btc_symbol("BTCUSDT") is True
    assert is_btc_symbol("BTCUSDC") is True
    assert is_btc_symbol("SOLUSDT") is False
    assert is_btc_symbol("ETHUSDT") is False


def test_to_gateio_currency_pair():
    assert to_gateio_currency_pair("SOLUSDT") == "SOL_USDT"
    assert to_gateio_currency_pair("FARTCOINUSDT") == "FARTCOIN_USDT"
    assert to_gateio_currency_pair("BTCUSDC") == "BTC_USDC"
    assert to_gateio_currency_pair("CUSTOM") == "CUSTOM"

