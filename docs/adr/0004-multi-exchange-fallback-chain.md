# 0004 - Multi-Exchange Public REST Fallback Chain

## Status
Accepted

## Context
Binance Spot adalah bursa aset kripto dengan likuiditas terbesar di dunia, namun banyak aset baru, koin komunitas (*meme coins* seperti FARTCOIN), atau altcoin bertaraf *low-to-mid cap* belum atau tidak terdaftar di pasar Binance Spot (`api.binance.com`). Saat pengguna meminta analisis DCA untuk token semacam ini, sistem sebelumnya langsung mengembalikan galat `Invalid symbol` (HTTP 400).

Pengguna memerlukan mekanisme pemulihan otomatis (*fallback chain*) tanpa mengorbankan prinsip utama proyek: **Zero-API-Key Public REST** (tanpa login, tanpa API key berbayar, bebas marginal cost).

## Decision
Kami mengimplementasikan rantai fallback multi-bursa (*Multi-Exchange Fallback Chain*) yang deterministik dengan hierarki prioritas:
1. **Tier 1 (Utama): Binance Spot REST API** (`https://api.binance.com/api/v3/klines`)
   - Standar emas pasar spot global.
2. **Tier 2 (Fallback 1): MEXC Spot Public REST API** (`https://api.mexc.com/api/v3/klines`)
   - Pasar spot paling komprehensif untuk token baru dan koin meme. Tetap merupakan transaksi pasar *spot* nyata. Format klines kompatibel v3 (interval mingguan menggunakan `1W`).
3. **Tier 3 (Fallback 2): Binance USDⓈ-M Futures REST API** (`https://fapi.binance.com/fapi/v1/klines`)
   - Banyak token viral memiliki kontrak perpetual futures di Binance meskipun belum listing di spot. Likuiditas masif dan infrastruktur identik.
4. **Tier 4 (Fallback 3): Gate.io Spot REST API** (`https://api.gateio.ws/api/v4/spot/candlesticks`)
   - Bursa cadangan dengan ribuan pasangan pasar spot. Format simbol disesuaikan (`BASE_QUOTE`).

Jika simbol tidak ditemukan di satu tier (`SymbolNotFoundError` / HTTP 400 / 404), sistem secara transparan beralih ke tier berikutnya dan memberikan umpan balik log informatif di antarmuka CLI serta menyematkan label bursa asal pada dokumen prompt yang dihasilkan (`facts.source_exchange`).

## Consequences
- Token seperti FARTCOIN, GOAT, MOODENG, dll., dapat langsung dianalisis tanpa konfigurasi manual.
- Pengguna tetap tidak memerlukan API key atau akun bursa apa pun.
- Seluruh 27 unit test tetap berjalan 100% *network-free* dengan *mock session*.
