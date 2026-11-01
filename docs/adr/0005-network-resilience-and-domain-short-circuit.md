# 0005 - Network Resilience, Domain Short-Circuit, and Proxy Tunneling

## Status
Accepted

## Context
ADR 0004 mengimplementasikan rantai fallback multi-bursa untuk menangani koin yang belum listing di Binance Spot. Namun, rantai tersebut mengasumsikan seluruh kegagalan bersumber dari `SymbolNotFoundError` (HTTP 400). Saat pengguna berada di jaringan yang memblokir Binance (pemblokiran DNS/IP oleh ISP seperti TrustPositif di Indonesia, atau HTTP 403/451 Cloudflare Geo-blocking), sistem mengalami tiga kelemahan:
1. Menampilkan pesan log yang keliru seolah simbol tidak terdaftar.
2. Membuang latensi timeout 10 detik di Tier 3 (Binance Futures) meskipun domain `*.binance.com` sudah terbukti tidak dapat dijangkau.
3. Kehilangan data metrik benchmark BTC karena fungsi perhitungan komparasi BTC memanggil Binance Spot secara *hardcoded* tanpa fallback.

## Decision
1. **Diferensiasi Galat Jaringan vs Simbol**:
   - Memperkenalkan `ProviderConnectionError` untuk merangkum kegagalan fisik jaringan (DNS, connection reset, timeout), penolakan akses/blokir wilayah (HTTP 403, HTTP 451), dan gangguan server bursa (HTTP 5xx).
   - Mempertahankan `SymbolNotFoundError` khusus untuk HTTP 400 dan 404 (simbol/pair tidak valid).
2. **Domain-Level Short-Circuit**:
   - Jika koneksi ke Binance Spot gagal akibat `ProviderConnectionError`, sistem mencatat domain `binance.com` ke dalam *in-memory session state* (`unreachable_domains`) dan secara otomatis melompati (*skip*) Tier 3 (Binance Futures) untuk langsung beralih ke Gate.io Spot tanpa penalti latensi *timeout*.
3. **Penyelarasan Fallback Benchmark BTC**:
   - Mengalihkan pengambilan data acuan BTC pada `fetch_btc_performance` dan `fetch_relative_performance_vs_btc` agar menggunakan `fetch_market_klines_with_fallback("BTCUSDT")` dengan *graceful degradation* (tetap menghasilkan prompt jika BTC gagal total).
4. **Proxy Tunneling & Diagnosis Cerdas**:
   - Menyediakan argumen CLI `-p` / `--proxy` opsional yang disuntikkan ke `requests.Session` untuk *bypass* sensor/blokir lokal.
   - Memberikan diagnosis akhir yang membedakan kegagalan jaringan total vs simbol tidak ditemukan.

## Consequences
- CLI tetap tangguh dan informatif saat pengguna berada di jaringan yang memblokir bursa tertentu.
- Waktu eksekusi saat bursa utama diblokir tetap responsif berkat *short-circuit* domain.
- Metrik perbandingan pasar (BTC 30d/90d & relative performance) tetap terisi lengkap melalui bursa alternatif (MEXC/Gate.io).
- Seluruh pengujian tetap berjalan 100% *network-free* melalui mock session.
