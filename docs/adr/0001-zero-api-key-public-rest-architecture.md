# 0001 - Zero-API-Key Public REST Architecture for Spot DCA Prompt Generation

## Status
Accepted

## Context
Alat ini dirancang untuk menyiapkan data dan menyusun prompt analisis DCA akumulasi bulanan bagi LLM hilir. Pengguna membutuhkan alur yang bebas friksi, gratis selamanya, tanpa memerlukan pendaftaran API Key berbayar atau akun bursa, dan tidak mengikat pengguna ke penyedia LLM API tertentu.

## Decision
Kami memutuskan:
1. Mengambil data pasar hanya dari endpoint publik gratis tanpa autentikasi (Binance Spot REST API `/api/v3/klines` dan Alternative.me `/fng/`).
2. Menghitung kinerja koin terhadap Bitcoin (`<COIN>BTC`) langsung dari pair Binance Spot terkait atau rasio silang terhadap `BTCUSDT`, tanpa memanggil pihak ketiga seperti CoinGecko untuk menghindari batasan rate limit.
3. Menjalankan seluruh kalkulasi indikator secara lokal dan deterministik di sisi klien menggunakan Python/Pandas.
4. Menghasilkan prompt teks akhir berbasis file Markdown dan menyalinnya ke papan klip (clipboard) alih-alih mengeksekusi panggilan LLM API langsung.

## Consequences
- Tidak ada biaya operasional (zero marginal cost) dan zero setup credential untuk pengguna.
- Terhindar dari kegagalan autentikasi atau kuota API berbayar.
- Bergantung pada kestabilan endpoint publik Binance dan Alternative.me (dilindungi dengan penanganan graceful dan timeout).
- Pengguna tetap memegang kendali penuh untuk menempelkan prompt ke model AI mana pun (ChatGPT, Claude, Gemini, DeepSeek, model lokal).
