# spot-prompt

`spot-prompt` adalah **CLI Python sekali-jalan (single-run)** yang mengambil data pasar kripto dari **provider publik read-only tanpa API Key** melalui **Multi-Exchange Fallback Chain** (Binance Spot, MEXC Spot, Binance Futures, dan Gate.io Spot) serta Alternative.me, menghitung **indikator teknikal valuasi & volatilitas secara deterministik**, menyuntikkannya ke dalam template prompt terstruktur, lalu **menulis prompt akhir ke berkas `.md` di `./output`** dan **menyalinnya ke clipboard sistem**.

Alat ini adalah **utilitas penyiapan data (data-preparation utility)** untuk LLM teks di hilir (seperti ChatGPT, Claude, Gemini, atau DeepSeek). Alat ini **tidak melakukan keputusan beli/jual secara otomatis**, melainkan menyajikan fakta pasar objektif agar LLM dapat menyusun strategi akumulasi bulanan (**Smart DCA**) yang terukur.

---

## Mengapa Repositori Ini Dibuat?

Banyak investor kripto melakukan **DCA Buta (Blind DCA)**—membeli di tanggal tertentu tanpa mempedulikan apakah harga sedang berada di puncak jenuh beli (*overbought*) atau di area diskon ekstrem. Sebaliknya, menyuruh LLM membaca ratusan baris data angka mentah sering kali menyebabkan halusinasi matematika dan pemborosan kuota *token*.

`spot-prompt` hadir dengan empat pilar utama:

1. **100% Gratis & Tanpa API Key (Zero-Auth):**
   - Mengambil data *candlestick* `1d` dan `1w` langsung dari endpoint REST publik tanpa registrasi, tanpa API key berbayar, dan tanpa marginal cost.
   - Mengambil sentimen pasar dari API publik **Alternative.me** (Crypto Fear & Greed Index).
   - Menghitung performa relatif koin terhadap Bitcoin (`<COIN>BTC` atau rasio sintetis) dengan rantai fallback otomatis yang tahan gangguan.
2. **Multi-Exchange Fallback Chain Cerdas:**
   - Mendukung analisis koin yang belum terdaftar di Binance Spot (seperti koin komunitas/meme coins: FARTCOIN, GOAT, MOODENG) dengan mengalihkan permintaan data secara otomatis dan transparan ke bursa alternatif.
3. **Ketahanan Jaringan & Anti-Sensor (Network Resilience):**
   - Tahan terhadap sensor dan pemblokiran ISP lokal (seperti TrustPositif Kominfo, DNS error, HTTP 403 Cloudflare, dan HTTP 451 Geo-block).
   - Dilengkapi fitur **In-Memory Domain Short-Circuit**, **Proxy Tunneling** bawaan (`--proxy`), dan **Diagnosis Cerdas** terminal.
4. **Deterministik & Ringan (Pure Pandas/NumPy):**
   - Seluruh kalkulasi teknikal dihitung secara lokal tanpa ketergantungan API AI berbayar dan tanpa dependensi biner eksternal seperti `TA-Lib`.

---

## Arsitektur Multi-Exchange Fallback Chain

Jika sebuah koin belum terdaftar di bursa utama, `spot-prompt` secara deterministik menelusuri rantai fallback berikut:

```
[Tier 1: Binance Spot]
        │
   (Gagal / 404 / Blocked)
        ▼
[Tier 2: MEXC Spot]  ◄── (Paling lengkap untuk token baru & meme coins)
        │
   (Gagal / 404 / Blocked)
        ▼
[Tier 3: Binance USDⓈ-M Futures]  ◄── (Dilewati jika domain binance.com terblokir)
        │
   (Gagal / 404 / Blocked)
        ▼
[Tier 4: Gate.io Spot]  ◄── (Bursa cadangan komprehensif)
```

- **Tier 1 (Utama): Binance Spot REST API** (`api.binance.com`) — Standar emas likuiditas pasar spot global.
- **Tier 2 (Fallback 1): MEXC Spot REST API** (`api.mexc.com`) — Likuiditas pasar spot komprehensif untuk token baru dan koin komunitas.
- **Tier 3 (Fallback 2): Binance USDⓈ-M Futures REST API** (`fapi.binance.com`) — Alternatif kontrak perpetual likuiditas masif untuk token yang belum listing spot.
- **Tier 4 (Fallback 3): Gate.io Spot REST API** (`api.gateio.ws`) — Bursa cadangan dengan ribuan pasangan pasar spot.

> **Transparansi Penuh:** Sumber bursa yang digunakan (`source_exchange`) ditampilkan di log terminal dan dicantumkan pada metadata prompt markdown akhir.

---

## Ketahanan Jaringan & Anti-Blokir (Network Resilience)

Untuk pengguna di wilayah dengan pembatasan jaringan atau pemblokiran ISP:

1. **In-Memory Domain Short-Circuit:**
   Jika akses ke domain Binance (`api.binance.com`) mengalami gangguan koneksi fisik, timeout, atau pemblokiran (HTTP 403/451), CLI mencatat domain tersebut sebagai *unreachable*. Sistem akan secara otomatis melompati (*skip*) Tier 3 (Binance Futures) langsung ke Gate.io Spot, memotong penalti latensi *timeout* 10 detik.
2. **Proxy Tunneling Bawaan (`-p` / `--proxy`):**
   Mendukung perutean seluruh lalu lintas HTTP melalui tunnel proxy HTTP, HTTPS, maupun SOCKS5 (misal v2ray, Clash, atau SSH tunnel). CLI juga otomatis mendeteksi variabel lingkungan `ALL_PROXY` atau `all_proxy`.
3. **Penyelarasan Fallback Benchmark BTC:**
   Penarikan data acuan `BTCUSDT` untuk performa 30d/90d dan performa relatif koin vs BTC diselaraskan dengan rantai fallback multi-bursa dan *graceful degradation* (analisis koin tetap berjalan sukses meskipun data BTC gagal diakses).
4. **Diagnosis Cerdas Terminal:**
   Terminal membedakan alasan kegagalan dengan jelas (`blocked`, `short_circuit`, atau `not_found`). Jika seluruh bursa gagal dihubungi, sistem memberikan diagnosis edukatif apakah masalah disebabkan oleh pemblokiran jaringan (dengan rekomendasi memakai `--proxy`) atau simbol yang memang tidak ditemukan di bursa mana pun.

---

## Indikator & Fakta yang Diekstrak

Prompt yang dihasilkan menyuntikkan lapisan fakta objektif:

1. **Posisi Siklus 30 Hari:** Harga saat ini, rentang tertinggi/terendah 30 hari, serta persentil posisi harga bulanan (0%–100%).
2. **Valuasi Siklus Makro:**
   - **200-Week SMA:** Standar emas valuasi siklus besar (dengan deviasi % dari harga saat ini; *fallback graceful* ke `N/A` jika koin berumur < 200 minggu).
   - **200-Day SMA & 50-Day EMA:** Garis rata-rata jangka menengah-panjang beserta persentase deviasinya.
   - **Point of Control (POC) 90 Hari:** Area harga dengan akumulasi volume transaksi terbesar selama 3 bulan terakhir via algoritma *price binning* mekanis.
3. **Momentum & Volatilitas:**
   - **RSI (14) Daily & Weekly:** Mengukur kejenuhan jual/beli (*oversold/overbought*).
   - **Bollinger Bands (20, 2) & %B:** Mengukur posisi statistik harga terhadap pita atas dan pita bawah.
   - **ATR (14) Daily:** Volatilitas harian dalam nominal dan persentase harga untuk panduan penempatan jaring bawah (*limit order*).
4. **Sentimen Pasar & Benchmark Makro:**
   - Skor **Crypto Fear & Greed Index** (0–100).
   - **Performa Relatif 30 Hari vs BTC** (untuk altcoin) atau kinerja historis absolut (jika menganalisis BTC) melalui rantai fallback multi-bursa.
5. **Mini Candle Snapshot:** Tabel mini 5 candle harian terakhir lengkap dengan persentase perubahan harian dan rasio volume terhadap rata-rata 20 hari.

---

## Instalasi

### 1. Kloning Repositori
```bash
git clone https://github.com/KaleksananBarqi/spot-prompt-cli.git
cd spot-prompt-cli
```

### 2. Buat Virtual Environment & Pasang Dependensi
```bash
python3 -m venv .venv
source .venv/bin/activate  # Di Linux/macOS
# atau: .venv\Scripts\activate  # Di Windows PowerShell

pip install -e .
```

---

## Cara Penggunaan

### 1. Mode Interaktif (Wizard)
Jalankan perintah tanpa argumen untuk membuka wizard interaktif:
```bash
spot-prompt
```
CLI akan menanyakan:
- Simbol koin yang ingin diakumulasi (misal: `SOL`, `BTC`, `ETH`, `SUI`, `FARTCOIN`).
- Alokasi budget periode ini (misal: `500`).
- Profil risiko DCA (`conservative`, `moderate`, `aggressive`).

### 2. Mode Perintah Cepat (Direct Flags)
Eksekusi langsung dalam satu baris perintah:

```bash
# Akumulasi SOL dengan budget $300 (Profil Agresif)
spot-prompt --symbol SOL --budget 300 --mode aggressive

# Akumulasi BTC dengan profil konservatif
spot-prompt -s BTC -b 500 -m conservative

# Akumulasi koin komunitas/meme coin (otomatis fallback ke MEXC Spot)
spot-prompt -s FARTCOIN -b 100

# Menggunakan proxy lokal jika akses bursa diblokir ISP
spot-prompt -s SOL -b 300 --proxy http://127.0.0.1:7890

# Menggunakan proxy SOCKS5
spot-prompt -s BTC -b 500 -p socks5://127.0.0.1:1080

# Cetak prompt langsung ke terminal (stdout)
spot-prompt -s ETH --budget 250 --stdout
```

### 3. Pilihan Flag Lengkap
```text
Options:
  -s, --symbol TEXT               Simbol koin (misal: SOL, BTC, ETH, SOLUSDT).
  -b, --budget FLOAT              Nominal budget DCA periode ini (misal: 300 atau 500).
  -c, --currency TEXT             Mata uang budget (default: USDT).
  -m, --mode [conservative|moderate|aggressive]
                                  Profil risiko akumulasi (default: moderate).
  -p, --proxy TEXT                URL proxy HTTP/HTTPS/SOCKS5 (misal: http://127.0.0.1:7890).
  -o, --output-dir PATH           Direktori penyimpanan berkas prompt (default: ./output).
  --stdout                        Cetak prompt ke stdout terminal.
  --no-clipboard                  Jangan salin prompt ke clipboard secara otomatis.
  -h, --help                      Tampilkan bantuan.
```

---

## Alur Kerja dengan LLM Hilir

1. Jalankan `spot-prompt -s SOL -b 300`.
2. Buka antarmuka LLM favorit Anda (ChatGPT, Claude, Gemini, DeepSeek).
3. Tekan **Ctrl + V** (Paste) di kolom chat AI.
4. LLM akan memberikan:
   - **Skor Kelayakan Beli (1-100)** saat ini.
   - **Pembagian Porsi Budget:** Berapa persen dieksekusi sekarang (*Market Buy*) vs dipasang jaring bawah (*Limit Order*).
   - **2–3 Level Limit Order Spesifik:** Tingkat harga terukur berdasarkan kombinasi Lower Bollinger Band, POC 90H, MA deviasi, dan kelipatan ATR.
   - **Skenario Invalidation:** Batas pembatalan jaring order jika tren rusak fundamental.

---

## Pengujian (Testing)

Rangkaian pengujian (*test suite*) dirancang **100% bebas jaringan (network-free)** dengan *mock fixtures* statis:

```bash
pytest
```

Seluruh 106 unit test mencakup pengujian parsing candlestick seluruh bursa, rantai fallback, penanganan galat jaringan, domain short-circuit, opsi proxy CLI, kalkulasi indikator matematis, serta rendering template.

---

## Lisensi

Didistribusikan di bawah lisensi MIT.
