# spot-prompt

`spot-prompt` adalah **CLI Python sekali-jalan (single-run)** yang mengambil data pasar kripto dari **provider publik read-only tanpa API Key** (Binance Spot REST API & Alternative.me), menghitung **indikator teknikal valuasi & volatilitas secara deterministik**, menyuntikkannya ke dalam template prompt terstruktur, lalu **menulis prompt akhir ke berkas `.md` di `./output`** dan **menyalinnya ke clipboard sistem**.

Alat ini adalah **utilitas penyiapan data (data-preparation utility)** untuk LLM teks di hilir (seperti ChatGPT, Claude, Gemini, atau DeepSeek). Alat ini **tidak melakukan keputusan beli/jual secara otomatis**, melainkan menyajikan fakta pasar objektif agar LLM dapat menyusun strategi akumulasi bulanan (**Smart DCA**) yang terukur.

---

## Mengapa Repositori Ini Dibuat?

Banyak investor kripto melakukan **DCA Buta (Blind DCA)**—membeli di tanggal tertentu tanpa mempedulikan apakah harga sedang berada di puncak jenuh beli (*overbought*) atau di area diskon ekstrem. Sebaliknya, menyuruh LLM membaca ratusan baris data angka mentah sering kali menyebabkan halusinasi matematika dan pemborosan kuota *token*.

`spot-prompt` hadir dengan tiga prinsip utama:

1. **100% Gratis & Tanpa API Key (Zero-Auth):**
   - Mengambil data *candlestick* `1d` dan `1w` langsung dari endpoint publik **Binance Spot API** (`/api/v3/klines`).
   - Mengambil sentimen pasar dari API publik **Alternative.me** (Crypto Fear & Greed Index).
   - Menghitung performa relatif koin terhadap Bitcoin (`<COIN>BTC` atau rasio sintetis) tanpa ketergantungan API pihak ketiga yang ketat batasannya.
2. **Tanpa Ketergantungan API LLM Berbayar:**
   Tool ini tidak memanggil endpoint AI berbayar. Anda cukup menjalankan satu perintah CLI, lalu menempelkan (*paste*) prompt yang otomatis disalin ke clipboard ke AI favorit Anda (termasuk versi gratis).
3. **Deterministik & Ringan (Pure Pandas/NumPy):**
   Seluruh kalkulasi teknikal dihitung secara lokal tanpa dependensi biner C eksternal seperti `TA-Lib`.

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
   - **Performa Relatif 30 Hari vs BTC** (untuk altcoin) atau kinerja historis absolut (jika menganalisis BTC).
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
- Simbol koin yang ingin diakumulasi (misal: `SOL`, `BTC`, `ETH`, `SUI`).
- Alokasi budget periode ini (misal: `500`).
- Profil risiko DCA (`conservative`, `moderate`, `aggressive`).

### 2. Mode Perintah Cepat (Direct Flags)
Eksekusi langsung dalam satu baris perintah:

```bash
# Akumulasi SOL dengan budget $300 (Profil Agresif)
spot-prompt --symbol SOL --budget 300 --mode aggressive

# Akumulasi BTC dengan profil konservatif
spot-prompt -s BTC -b 500 -m conservative

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

---

## Lisensi

Didistribusikan di bawah lisensi MIT.
