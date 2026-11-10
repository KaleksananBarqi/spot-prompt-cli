"""Modul kompatibilitas mundur (backward-compatibility wrapper) untuk data_fetcher."""

from typing import Any, Callable, Optional, Set, Tuple
import pandas as pd
import requests

from spot_prompt.data_client import (
    FALLBACK_REASON_BLOCKED,
    FALLBACK_REASON_NOT_FOUND,
    FALLBACK_REASON_SHORT_CIRCUIT,
    DataFetchError,
    MarketContext,
    MarketDataClient,
    ProviderConnectionError,
    SymbolNotFoundError,
    _find_next_reachable_provider,
    create_default_session,
    parse_binance_like_klines,
    parse_gateio_candlesticks,
)

get_default_session = create_default_session


def fetch_binance_spot_klines(
    symbol: str,
    interval: str,
    limit: int = 500,
    session: Optional[requests.Session] = None,
) -> pd.DataFrame:
    client = MarketDataClient(session=session)
    return client._fetch_binance_spot(symbol, interval, limit)


fetch_binance_klines = fetch_binance_spot_klines


def fetch_mexc_klines(
    symbol: str,
    interval: str,
    limit: int = 500,
    session: Optional[requests.Session] = None,
) -> pd.DataFrame:
    client = MarketDataClient(session=session)
    return client._fetch_mexc_spot(symbol, interval, limit)


def fetch_binance_futures_klines(
    symbol: str,
    interval: str,
    limit: int = 500,
    session: Optional[requests.Session] = None,
) -> pd.DataFrame:
    client = MarketDataClient(session=session)
    return client._fetch_binance_futures(symbol, interval, limit)


def fetch_gateio_klines(
    symbol: str,
    interval: str,
    limit: int = 500,
    session: Optional[requests.Session] = None,
) -> pd.DataFrame:
    client = MarketDataClient(session=session)
    return client._fetch_gateio_spot(symbol, interval, limit)


def fetch_market_klines_with_fallback(
    symbol: str,
    daily_limit: int = 500,
    weekly_limit: int = 300,
    session: Optional[requests.Session] = None,
    on_fallback: Optional[Callable[..., None]] = None,
    unreachable_domains: Optional[Set[str]] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame, str]:
    client = MarketDataClient(session=session, on_fallback=on_fallback)
    if unreachable_domains is not None:
        client.unreachable_domains = unreachable_domains
    res = client.fetch_market_klines(symbol, daily_limit=daily_limit, weekly_limit=weekly_limit)
    if unreachable_domains is not None:
        unreachable_domains.update(client.unreachable_domains)
    return res


def fetch_fear_and_greed(session: Optional[requests.Session] = None) -> Tuple[Optional[int], Optional[str]]:
    client = MarketDataClient(session=session)
    return client.fetch_fear_and_greed()


def fetch_btc_performance(
    session: Optional[requests.Session] = None,
    unreachable_domains: Optional[Set[str]] = None,
    on_fallback: Optional[Callable[..., None]] = None,
) -> Tuple[Optional[float], Optional[float]]:
    client = MarketDataClient(session=session, on_fallback=on_fallback)
    if unreachable_domains is not None:
        client.unreachable_domains = unreachable_domains
    res = client.fetch_btc_performance()
    if unreachable_domains is not None:
        unreachable_domains.update(client.unreachable_domains)
    return res


def fetch_relative_performance_vs_btc(
    symbol: str,
    df_symbol_daily: pd.DataFrame,
    session: Optional[requests.Session] = None,
    unreachable_domains: Optional[Set[str]] = None,
    on_fallback: Optional[Callable[..., None]] = None,
) -> Optional[float]:
    client = MarketDataClient(session=session, on_fallback=on_fallback)
    if unreachable_domains is not None:
        client.unreachable_domains = unreachable_domains
    res = client.fetch_relative_performance_vs_btc(symbol, df_symbol_daily)
    if unreachable_domains is not None:
        unreachable_domains.update(client.unreachable_domains)
    return res
