# spot-prompt

`spot-prompt` adalah **CLI Python sekali-jalan (single-run) berarsitektur Zero-Auth single-paste** yang mengambil data pasar kripto dari **provider publik read-only tanpa API Key** melalui **Multi-Exchange Fallback Chain** (Binance Spot, MEXC Spot, Binance Futures, dan Gate.io Spot) serta Alternative.me, menghitung **indikator teknikal valuasi & volatilitas secara deterministik**, menyuntikkannya ke dalam template prompt terstruktur, lalu **menulis prompt akhir ke berkas `.md` di `./output`** dan **menyalinnya ke clipboard sistem**.

Alat ini adalah **utilitas penyiapan data (data-preparation utility) murni** dengan alur kerja **single-paste**:
- **Tanpa integrasi SDK LLM maupun API Key LLM apa pun** (tidak membutuhkan API Key OpenAI, Claude, Gemini, ataupun DeepSeek, dan tidak memerlukan setup model AI lokal).
- **Tanpa keputusan beli/jual otomatis**: alat ini hanya menyajikan fakta pasar objektif dalam satu prompt siap tempel (*single-paste*) ke jendela chat LLM favorit Anda agar LLM merumuskan strategi akumulasi bulanan (**Smart DCA**) yang terukur.

---

## Mengapa Repositori Ini Dibuat?

Banyak investor kripto melakukan **DCA Buta (Blind DCA)**—membeli di tanggal tertentu tanpa mempedulikan apakah harga sedang berada di puncak jenuh beli (*overbought*) atau di area diskon ekstrem. Sebaliknya, menyuruh LLM membaca ratusan baris data angka mentah sering kali menyebabkan halusinasi matematika dan pemborosan kuota *token*.

`spot-prompt` hadir dengan lima pilar utama:

1. **100% Gratis, Zero-Auth & Bebas API Key (Bursa maupun LLM):**
   - Mengambil data *candlestick* `1d` dan `1w` langsung dari endpoint REST publik tanpa registrasi, tanpa API key bursa, dan tanpa marginal cost.
   - Tidak memanggil API/SDK penyedia LLM mana pun—pengguna cukup menempelkan (*single-paste*) prompt yang dihasilkan ke ChatGPT, Claude, Gemini, atau DeepSeek.
   - Mengambil sentimen pasar dari API publik **Alternative.me** (Crypto Fear & Greed Index).
   - Menghitung performa relatif koin terhadap Bitcoin (`<COIN>BTC` atau rasio sintetis) dengan rantai fallback otomatis yang tahan gangguan.
2. **Dukungan Koin IDR & Bursa Lokal Indonesia (Hybrid IDR Valuation):**
   - Investor lokal di bursa Indonesia (seperti Indodax dan Tokocrypto) dapat langsung menabung dengan budget Rupiah (`-b 1.500.000` atau `Rp 2.000.000`) dan memasukkan pasangan lokal (`-s BTCIDR`, `SOL/IDR`).
   - Indikator valuasi makro dihitung dari likuiditas global bursa tier-1 (USDT) bebas bias, lalu dipetakan secara *real-time* via kurs spot **Indodax Ticker** (dengan *automatic fallback* ke **CoinGecko Simple Price**).
   - Menghasilkan prompt **Dual-Currency** (Rupiah primer + acuan USDT sekunder di tanda kurung) dengan batas **Minimum Notional** disesuaikan ke aturan bursa domestik (`Rp 10.000`).
3. **Multi-Exchange Fallback Chain Cerdas:**
   - Mendukung analisis koin yang belum terdaftar di Binance Spot (seperti koin komunitas/meme coins: FARTCOIN, GOAT, MOODENG) dengan mengalihkan permintaan data secara otomatis dan transparan ke bursa alternatif (MEXC, Binance Futures, Gate.io).
4. **Ketahanan Jaringan & Anti-Sensor (Network Resilience):**
   - Tahan terhadap sensor dan pemblokiran ISP lokal (seperti TrustPositif Kominfo, DNS error, HTTP 403 Cloudflare, dan HTTP 451 Geo-block).
   - Dilengkapi fitur **In-Memory Domain Short-Circuit**, **Proxy Tunneling** bawaan (`--proxy`), dan **Diagnosis Cerdas** terminal.
5. **Deterministik, Bebas Repainting & Anti-Halusinasi (Pure Pandas/NumPy):**
   - Seluruh kalkulasi teknikal dihitung secara lokal di atas **Closed-Candle Baseline** (bebas distorsi candle harian/mingguan yang belum tutup) tanpa ketergantungan API AI berbayar dan tanpa dependensi biner eksternal seperti `TA-Lib`.
   - Dilengkapi **Guardrail Kuantitatif** untuk mencegah LLM merekomendasikan *Limit Buy* di atas harga pasar, menumpuk order terlalu rapat, atau memecah budget di bawah batas *Minimum Notional* bursa (`10.00 USDT` atau `Rp 10.000`).

---

## Arsitektur Modul Mendalam (Deep Modules Architecture)

`spot-prompt` dibangun di atas arsitektur modul mendalam (*deep modules*) berbasis prinsip *Codebase Design* (lihat [ADR-0007](./docs/adr/0007-deep-architecture-consolidation.md)):

```
┌────────────────────────────────────────────────────────┐
│             Presentation: spot_prompt/cli.py           │  ← Thin CLI Adapter (Click & Prompts)
└───────────────────────────┬────────────────────────────┘
                            │ ExecutionConfig & PipelineOptions
                            ▼
┌────────────────────────────────────────────────────────┐
│          Pipeline: spot_prompt/pipeline.py             │  ← Deep PromptPipeline Module
├────────────────────────────────────────────────────────┤
│  • Session & Proxy Setup       • Jinja2 Rendering      │
│  • Fallback Transition Log     • File & Clipboard I/O  │
└──────────────┬──────────────────────────┬──────────────┘
               │                          │
               ▼                          ▼
┌───────────────────────────────┐ ┌───────────────────────────────┐
│ spot_prompt/data_client.py    │ │ spot_prompt/analyzer.py       │
├───────────────────────────────┤ ├───────────────────────────────┤
│ MarketDataClient              │ │ RawFactsAnalyzer              │
│ • Zero state leakage          │ │ • Closed-Candle Baseline      │
│ • 4-Exchange Fallback Chain   │ │ • SMA 200W/200D & EMA 50D     │
│ • Domain Short-Circuit        │ │ • 90D Volume Profile (VA/POC) │
│ • F&G and BTC Benchmark       │ │ • RSI 14D/14W, BB %B, ATR 14  │
└───────────────────────────────┘ └───────────────────────────────┘
```

1. **`PromptPipeline` (`spot_prompt/pipeline.py`):** Modul orkestrator mendalam yang menyatukan seluruh proses pembuatan prompt di balik antarmuka tunggal: `PromptPipeline.execute(config, options) -> PromptResult`.
2. **`MarketDataClient` (`spot_prompt/data_client.py`):** Modul *ports & adapters* yang mengenkapsulasi pelacak status domain (*short-circuit*), sesi jaringan, dan rantai fallback 4 bursa tanpa membocorkan state ke pemanggil.
3. **`RawFactsAnalyzer` (`spot_prompt/analyzer.py`):** Modul analisis deterministik murni (*in-process*) yang menyerap seluruh komputasi indikator dan mengunci isolasi *Closed-Candle Baseline*.
4. **Penggunaan Programatik (Library API):** Selain antarmuka terminal (CLI), `spot-prompt` kini dapat langsung diimpor dan digunakan di dalam skrip Python, bot Telegram, atau backend API:
   ```python
   from spot_prompt.models import ExecutionConfig
   from spot_prompt.pipeline import PipelineOptions, PromptPipeline

   pipeline = PromptPipeline()
   config = ExecutionConfig(symbol="SOLUSDT", budget=300.0, mode="moderate")
   options = PipelineOptions(save_to_disk=False, copy_clipboard=False)
   result = pipeline.execute(config, options=options)
   print(result.rendered_prompt)
   ```

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
   Jika akses ke domain Binance (`api.binance.com`) mengalami gangguan koneksi fisik, timeout, atau pemblokiran (HTTP 403/451), `MarketDataClient` mencatat domain tersebut sebagai *unreachable*. Sistem akan secara otomatis melompati (*skip*) Tier 3 (Binance Futures) langsung ke Gate.io Spot, memotong penalti latensi *timeout* 10 detik.
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
2. **Valuasi Siklus Makro (Closed-Candle Baseline):**
   - **200-Week SMA:** Standar emas valuasi siklus besar (dengan deviasi % dari harga saat ini; *fallback graceful* ke `N/A` jika koin berumur < 200 minggu tertutup).
   - **200-Day SMA & 50-Day EMA:** Garis rata-rata jangka menengah-panjang beserta persentase deviasinya dan *pre-tagging* otomatis apakah level berada di bawah harga (*kandidat support*) atau di atas harga (*overhead resistance*).
   - **Volume Profile 90 Hari (VAH, POC, VAL):** Area harga dengan akumulasi volume transaksi terbesar (`POC`) beserta batas 70% *Value Area* (`VAH` dan `VAL`) selama 3 bulan terakhir via algoritma *price binning* mekanis.
3. **Momentum & Volatilitas (Closed-Candle Baseline):**
   - **RSI (14) Daily & Weekly:** Mengukur kejenuhan jual/beli (*oversold/overbought*) dari candle tertutup bebas *intraday repainting*.
   - **Bollinger Bands (20, 2) & %B:** Mengukur posisi statistik harga live terhadap pita atas dan pita bawah tertutup.
   - **ATR (14) Daily:** Volatilitas harian dalam nominal dan persentase harga untuk panduan jarak minimal (`>= 0.5x ATR`) penempatan jaring bawah (*limit order*).
4. **Sentimen Pasar & Benchmark Makro:**
   - Skor **Crypto Fear & Greed Index** (0–100).
   - **Performa Relatif 30 Hari vs BTC** (untuk altcoin) atau kinerja historis absolut (jika menganalisis BTC) melalui rantai fallback multi-bursa.
5. **Mini Candle Snapshot:** Tabel mini 5 candle harian terakhir lengkap dengan status penutupan (`[CLOSED]` vs `[RUNNING / UNCLOSED]`), persentase perubahan harian, dan rasio volume terhadap rata-rata 20 hari tertutup.

---

## Guardrail Kuantitatif & Anti-Halusinasi LLM

Untuk memastikan output LLM dapat langsung dieksekusi di pasar spot tanpa cacat logika, `spot-prompt` menerapkan lima mekanisme pengaman deterministik (lihat [ADR-0006](./docs/adr/0006-closed-candle-baseline-and-quant-guardrails.md)):

1. **Pemisahan *Closed-Candle Baseline* vs *Live Price* (`1d` & `1w`):**
   - Harga terkini (`Current Price`) dan ekstrem 30 hari tetap membaca hingga detik ini (`iloc[-1]`), namun seluruh seri `200W SMA`, `200D SMA`, `50D EMA`, `RSI 14D/14W`, pita `Bollinger Bands`, `ATR-14`, `Volume Profile 90H`, dan rata-rata volume 20 hari dihitung murni dari candle yang **sudah tutup** (`iloc[:-1]`).
   - Mencegah distorsi *intraday repainting* (misal `ATR` atau rasio volume `0.17x` di pagi hari UTC yang sering disalahartikan LLM sebagai anomali keringnya likuiditas).
2. **Pre-Tagging Posisi Deterministik & Fallback *Free-Fall*:**
   - Setiap level indikator harga otomatis dilabeli oleh engine template:
     - `[DI BAWAH HARGA -> KANDIDAT SUPPORT]` jika `< Current Price`.
     - `[>= HARGA TERKINI -> RESISTANCE / DILARANG JADI LIMIT BUY]` jika `>= Current Price`.
   - Mencegah LLM terjebak *example anchoring* (merekomendasikan *Limit Buy* di `POC 90H` atau `Middle BB` yang posisinya sedang berada di atas harga pasar). Jika seluruh indikator berada di atas harga (*free-fall*), LLM diwajibkan menurunkan jaring murni berbasis kelipatan negatif `ATR-14`.
3. **Rubrik Skor Berbobot (40/35/25) & Hierarki Resolusi Konflik:**
   - Skor Kelayakan Beli (1–100) diikat pada bobot: **Valuasi Makro & Siklus (40 poin)**, **Momentum & Volatilitas (35 poin)**, serta **Sentimen & Price Action (25 poin)**.
   - Untuk koin muda (`200W SMA = N/A`), bobot otomatis direalokasikan ke `200D SMA`, `50D EMA`, dan `Volume Profile 90H`. Konflik antar-indikator diselesaikan dengan prioritas: `Makro/Weekly > Daily > Sentimen`.
4. **Matriks Alokasi 3 Mode, Spacing ATR, & Konsolidasi *Minimum Notional*:**
   - Porsi *Market Buy vs Limit Order* dikorelasikan langsung dengan rentang Skor Kelayakan sesuai `Execution Mode`:
     | Skor Kelayakan | `CONSERVATIVE` (Market Buy) | `MODERATE` (Market Buy) | `AGGRESSIVE` (Market Buy) |
     | :--- | :--- | :--- | :--- |
     | **< 40** | `0% – 10%` | `15% – 25%` | `25% – 35%` |
     | **40 – 60** | `15% – 25%` | `30% – 45%` | `45% – 60%` |
     | **61 – 80** | `30% – 45%` | `50% – 65%` | `65% – 80%` |
     | **> 80** | `50% – 60%` | `70% – 80%` | `85% – 100%` |
   - Jarak antar-level *Limit Order* diwajibkan minimal `0.5x ATR`, dengan perlindungan **Minimum Notional Consolidation** (`>= 10.00 USDT` per titik eksekusi; otomatis mengurangi jumlah level jaring atau melebur alokasi bila budget terbatas).
5. **Order Invalidation Protocol 3 Arah & Self-Check Aritmetika:**
   - Mencakup skenario **Invalidasi Atas (*Upside Runaway / Anti-Cash Drag*)**, **Invalidasi Bawah (*Bearish Structural Breakdown*)**, dan **Kedaluwarsa Siklus (*Cycle Expiry / Rollover*)**, ditutup dengan daftar periksa (*Self-Check*) validasi matematis.

---

## Instalasi

### Prasyarat & Perbedaan Mode Instalasi
- **Syarat Versi Python:** **`Python >= 3.10`** (periksa dengan `python --version` atau `python3 --version`).
- **Arsitektur Zero-Auth Single-Paste:** Proyek ini **tidak membutuhkan** API Key bursa, API Key LLM, maupun instalasi SDK AI (seperti `openai`/`anthropic`/`google-genai`).
- **Pilih salah satu metode instalasi:**
  | Metode | Perintah | Cara Menjalankan CLI | Keterangan |
  | :--- | :--- | :--- | :--- |
  | **Instalasi Paket CLI Penuh** *(Direkomendasikan)* | `pip install -e .` | `spot-prompt` atau `python -m spot_prompt` | Memasang seluruh dependensi sekaligus mendaftarkan perintah `spot-prompt` ke PATH environment aktif. |
  | **Dependensi Pustaka Saja** | `pip install -r requirements.txt` | `python -m spot_prompt` | Hanya memasang pustaka runtime (`requests`, `pandas`, `numpy`, `pyperclip`, `click`, `jinja2`, `python-dotenv`) tanpa mendaftarkan perintah `spot-prompt`. |

### 1. Kloning Repositori
```bash
git clone https://github.com/KaleksananBarqi/spot-prompt-cli.git
cd spot-prompt-cli
```

### 2. Setup di Linux / macOS
```bash
python3 --version  # Pastikan >= 3.10
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 3. Setup di Windows PowerShell
```powershell
python --version  # Pastikan Python >= 3.10
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```
> **Catatan Windows PowerShell:**
> - Jika `.\.venv\Scripts\Activate.ps1` diblokir oleh kebijakan eksekusi PowerShell, jalankan sekali: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, atau gunakan Command Prompt (`.\.venv\Scripts\activate.bat`).
> - Jika muncul `CommandNotFoundException: The term 'spot-prompt' is not recognized`, artinya virtual environment belum aktif atau Anda hanya menjalankan `pip install -r requirements.txt`. Aktifkan `.venv` lalu jalankan `pip install -e .`, atau jalankan langsung lewat `python -m spot_prompt`.

### 4. Panduan Cepat Google Colab & Lingkungan Headless
Di Google Colab atau server tanpa GUI (*headless*), tidak ada daemon clipboard sistem sehingga wajib menambahkan flag **`--no-clipboard --stdout`**:

```python
!git clone https://github.com/KaleksananBarqi/spot-prompt-cli.git
%cd spot-prompt-cli
!pip install -e .
# Alternatif jika hanya memasang pustaka: !pip install -r requirements.txt

# Jalankan tanpa clipboard dan cetak prompt langsung ke output sel:
!spot-prompt -s SOL -b 300 --no-clipboard --stdout
# Atau via modul Python langsung:
!python -m spot_prompt -s SOL -b 300 --no-clipboard --stdout
```

> **Klarifikasi Peringatan Dependensi Google Colab (`ipython 7.34.0`):**  
> Saat menjalankan `pip install` di Google Colab, pip terkadang menampilkan pesan konflik paket bawaan Colab seperti `ipython 7.34.0 requires jedi>=0.16, which is not installed`. Pesan tersebut berasal dari **lingkungan runtime pra-instal Google Colab**, **BUKAN** dari kode sumber maupun dependensi `spot-prompt`. Angka `7.34.0` adalah versi paket `ipython`, bukan syarat versi Python—`spot-prompt` hanya mensyaratkan **`Python >= 3.10`** dan tetap berjalan normal dengan `--no-clipboard --stdout`.

---

## Cara Penggunaan

> **Catatan:** Jika Anda memasang dependensi hanya melalui `pip install -r requirements.txt` (tanpa `pip install -e .`), ganti perintah `spot-prompt` pada seluruh contoh di bawah menjadi `python -m spot_prompt`.

### 1. Mode Interaktif (Wizard)
Jalankan perintah tanpa argumen untuk membuka wizard interaktif:
```bash
spot-prompt
# atau jika hanya memasang requirements.txt:
python -m spot_prompt
```
CLI akan menanyakan:
- Simbol koin yang ingin diakumulasi (misal: `SOL`, `BTC`, `BTCIDR`, `ETH`, `SUI`, `FARTCOIN`).
- Pilihan mata uang budget (`USDT` / `IDR`).
- Alokasi budget periode ini (misal: `500` atau `1.500.000`).
- Profil risiko DCA (`conservative`, `moderate`, `aggressive`).

### 2. Mode Perintah Cepat (Direct Flags)
Eksekusi langsung dalam satu baris perintah:

```bash
# Akumulasi SOL dengan budget $300 (Profil Agresif)
spot-prompt --symbol SOL --budget 300 --mode aggressive

# Akumulasi BTC dengan budget Rupiah di bursa lokal (Indodax/Tokocrypto)
spot-prompt -s BTCIDR -b 1.500.000

# Akumulasi SOL dengan budget Rupiah eksplisit via flag currency
spot-prompt -s SOL -b 2.000.000 -c IDR

# Override kurs live USDT/IDR secara manual
spot-prompt -s ETHIDR -b 3.000.000 -r 18000.0

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

# Lingkungan headless / Google Colab (tanpa clipboard + cetak ke stdout)
spot-prompt -s SOL -b 300 --no-clipboard --stdout
```

### 3. Pilihan Flag Lengkap
```text
Options:
  -s, --symbol TEXT               Simbol koin (misal: SOL, BTC, BTCIDR, SOL/IDR, SOLUSDT).
  -b, --budget TEXT               Nominal budget DCA periode ini (misal: 300, 1500000, atau 1.500.000).
  -c, --currency [USDT|IDR]       Mata uang budget (default: USDT). Pilihan: USDT, IDR.
  -r, --fx-rate FLOAT             Nilai tukar manual USDT/IDR (misal: 18000.0) untuk override kurs live.
  -m, --mode [conservative|moderate|aggressive]
                                  Profil risiko akumulasi (default: moderate).
  -p, --proxy TEXT                URL proxy HTTP/HTTPS/SOCKS5 (misal: http://127.0.0.1:7890).
  -o, --output-dir PATH           Direktori penyimpanan berkas prompt (default: ./output).
  --stdout                        Cetak seluruh isi teks prompt langsung ke terminal (ideal untuk Google Colab/headless).
  --no-clipboard                  Jangan menyalin prompt ke clipboard secara otomatis (gunakan di Colab/headless).
  -h, --help                      Tampilkan bantuan.
```

---

## Alur Kerja dengan LLM Hilir

1. Jalankan `spot-prompt -s BTCIDR -b 1.500.000`.
2. Buka antarmuka LLM favorit Anda (ChatGPT, Claude, Gemini, DeepSeek).
3. Tekan **Ctrl + V** (Paste) di kolom chat AI.
4. LLM akan memberikan:
   - **Skor Kelayakan Beli (1-100)** berbobot (`40/35/25`) beserta resolusi konflik indikator.
   - **Pembagian Porsi Budget:** Berapa persen dieksekusi sekarang (*Market Buy*) vs dipasang jaring bawah (*Limit Order*) sesuai matriks `Execution Mode`.
   - **1–3 Level Limit Order Spesifik (`< Current Price`):** Tingkat harga terukur berformat Dual-Currency (Rupiah primer + ekuivalen USDT di tanda kurung) dengan sub-alokasi `%` & nominal, jarak minimal `0.5x ATR`, dan perlindungan *Minimum Notional* bursa lokal (`>= Rp 10.000` atau `10.00 USDT`).
   - **Order Invalidation & Re-anchoring Protocol (3 Arah):** Pemicu *Upside Runaway (Anti-Cash Drag)*, *Bearish Breakdown*, dan *Cycle Expiry / Rollover*, dilengkapi *Self-Check* validasi aritmetika.

---

## Pengujian (Testing)

Rangkaian pengujian (*test suite*) dirancang **100% bebas jaringan (network-free)** dengan *mock fixtures* statis dan pengujian berbasis antarmuka seam (*interface-driven testing*):

```bash
pip install -e ".[dev]"
pytest
```

Seluruh unit dan integration tests mencakup pengujian:
- Parsing candlestick dan format ganda (Binance, MEXC, Gate.io).
- Rantai fallback multi-bursa dan in-memory domain short-circuit.
- Penarikan kurs spot USDT/IDR dengan fallback Indodax ➔ CoinGecko.
- Normalisasi simbol lokal IDR dan sanitasi fleksibel format budget ribuan Rupiah.
- Penanganan galat jaringan, status code discrimination, dan tunnel proxy.
- Kalkulasi indikator teknikal murni (*closed-candle baseline* & 70% *Value Area*).
- Modul orkestrasi `PromptPipeline` dan konsistensi file hasil render Dual-Currency.
- Antarmuka Click CLI dan interaktif wizard.

---

## Lisensi

Didistribusikan di bawah lisensi MIT.
