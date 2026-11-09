"""Konfigurasi default dan konstanta endpoint untuk spot-prompt."""

# Endpoint API Publik Gratis (Tanpa Auth / API Key)
BINANCE_API_BASE = "https://api.binance.com"
BINANCE_KLINES_PATH = "/api/v3/klines"

# Fallback Exchanges (Zero-API-Key Public REST)
BINANCE_FUTURES_API_BASE = "https://fapi.binance.com"
BINANCE_FUTURES_KLINES_PATH = "/fapi/v1/klines"

MEXC_API_BASE = "https://api.mexc.com"
MEXC_KLINES_PATH = "/api/v3/klines"

GATEIO_API_BASE = "https://api.gateio.ws"
GATEIO_CANDLESTICKS_PATH = "/api/v4/spot/candlesticks"

# Local FX Anchor Endpoints (Zero-API-Key USDT/IDR)
INDODAX_TICKER_USDTIDR_URL = "https://indodax.com/api/ticker/usdtidr"
COINGECKO_SIMPLE_PRICE_USDTIDR_URL = "https://api.coingecko.com/api/v3/simple/price?ids=tether&vs_currencies=idr"

ALTERNATIVE_ME_FNG_URL = "https://api.alternative.me/fng/?limit=1"

# Request Settings
DEFAULT_TIMEOUT_SECONDS = 10
USER_AGENT = "spot-prompt-cli/0.1.0"

# Periode & Window Kalkulasi
SMA_200W_WINDOW = 200
SMA_200D_WINDOW = 200
EMA_50D_WINDOW = 50
RSI_WINDOW = 14
BOLLINGER_WINDOW = 20
BOLLINGER_STD_DEV = 2.0
ATR_WINDOW = 14
POC_DAYS = 90
POC_BINS = 100
VALUE_AREA_PCT = 0.70

# Guardrail Eksekusi Order
MIN_NOTIONAL_USDT = 10.0
MIN_NOTIONAL_IDR = 10000.0

# Profil Risiko Eksekusi
RISK_MODES = ["conservative", "moderate", "aggressive"]
DEFAULT_MODE = "moderate"
DEFAULT_CURRENCY = "USDT"
SUPPORTED_CURRENCIES = ["USDT", "IDR"]
