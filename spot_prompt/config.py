"""Konfigurasi default dan konstanta endpoint untuk spot-prompt."""

# Endpoint API Publik Gratis (Tanpa Auth / API Key)
BINANCE_API_BASE = "https://api.binance.com"
BINANCE_KLINES_PATH = "/api/v3/klines"

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

# Profil Risiko Eksekusi
RISK_MODES = ["conservative", "moderate", "aggressive"]
DEFAULT_MODE = "moderate"
DEFAULT_CURRENCY = "USDT"
