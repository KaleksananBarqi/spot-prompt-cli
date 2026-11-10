# Spot Prompt CLI

Utilitas baris perintah (CLI) deterministik untuk mengekstrak indikator teknikal valuasi dan data sentimen pasar kripto berbasis data publik gratis, menyuntikkannya ke dalam template prompt terstruktur untuk memandu LLM merumuskan strategi akumulasi bulanan (Smart DCA).

## Language

**Smart DCA**:
Pendekatan akumulasi aset berkala yang membagi porsi eksekusi (market buy vs limit order) dan level harga entri berdasarkan posisi valuasi harga dan volatilitas, bukan sekadar pembelian buta pada tanggal tetap.
_Avoid_: Blind DCA, Regular DCA, Dollar Cost Averaging polos

**Raw Facts Layer**:
Kumpulan data metrik dan indikator hasil komputasi matematis objektif tanpa opini yang disuntikkan ke dalam prompt untuk dianalisis oleh LLM.
_Avoid_: Trading signal, AI opinion, prediction

**Point of Control (POC)**:
Tingkat harga dengan akumulasi volume transaksi terbesar dalam rentang observasi 90 hari terakhir.
_Avoid_: Support level, order block, liquidity zone

**Value Area (VAH & VAL)**:
Rentang harga dalam distribusi volume 90 hari yang merangkum 70% dari total akumulasi volume transaksi di sekitar Point of Control, dibatasi oleh Value Area High (VAH) di batas atas dan Value Area Low (VAL) di batas bawah.
_Avoid_: Support/resistance band, Bollinger volume

**%B (Bollinger %B)**:
Metrik kuantitatif yang mengukur posisi harga saat ini terhadap pita Bollinger Bands: `(Price - Lower) / (Upper - Lower)`.
_Avoid_: BB Position, oversold indicator

**200W SMA**:
Rata-rata pergerakan sederhana (Simple Moving Average) berbasis candle mingguan (200 minggu) yang berfungsi sebagai garis valuasi makro siklus pasar.
_Avoid_: Long-term trendline, weekly line

**200D SMA**:
Rata-rata pergerakan sederhana berbasis candle harian (200 hari) untuk mengukur deviasi harga terhadap rata-rata jangka menengah-panjang.
_Avoid_: Daily trend, 200 MA

**50D EMA**:
Rata-rata pergerakan eksponensial (Exponential Moving Average) 50 hari untuk mengukur tren momentum jangka menengah.
_Avoid_: Mid-term MA, short EMA

**ATR-14 (Average True Range)**:
Rata-rata rentang volatilitas pergerakan harga 14 hari terakhir untuk menentukan jarak pemasangan jaring bawah (limit order) yang realistis.
_Avoid_: Volatility index, price spread

**Crypto Fear & Greed Index**:
Indeks sentimen pasar kripto berskala 0 hingga 100 dari alternative.me yang mengukur ketakutan (fear) dan keserakahan (greed) pelaku pasar secara umum.
_Avoid_: Market sentiment, sentiment score

**Execution Mode (Profil Risiko)**:
Preferensi alokasi akumulasi pengguna (`aggressive`, `moderate`, `conservative`) yang diinjeksikan sebagai arahan ke prompt agar LLM menyesuaikan porsi market buy vs limit order.
_Avoid_: Strategy type, bot mode

**Skor Kelayakan Beli**:
Indeks komposit berskala 1 hingga 100 yang merepresentasikan tingkat kelayakan akumulasi spot saat ini berdasarkan diskon valuasi, momentum, volatilitas, dan sentimen (100 = zona akumulasi paling optimal, 1 = zona sangat jenuh beli/mahal).
_Avoid_: Price prediction score, sinyal beli mutlak

**Order Invalidation Protocol**:
Kondisi batas tiga arah—meliputi pelarian harga ke atas (*Upside Runaway*), kerusakan struktur makro ke bawah (*Downside Breakdown*), dan kedaluwarsa akhir siklus (*Cycle Expiry*)—yang memicu pembatalan atau penataan ulang jaring limit order yang belum terisi.
_Avoid_: Stop loss spot, cutloss level, single breakdown trigger

**Minimum Notional Consolidation**:
Aturan peleburan atau pembulatan alokasi order agar setiap titik eksekusi memenuhi ambang batas nominal minimum bursa tanpa menyisakan pecahan dana tanggung yang ditolak sistem.
_Avoid_: Dust order, sub-minimum split

**Price Binning**:
Metode pembagian rentang harga ke dalam interval diskrit berjarak sama untuk mengagregasi volume dari deret OHLCV harian dalam menghitung Point of Control.
_Avoid_: Volume clustering, orderbook depth

**Symbol Normalizer**:
Komponen sanitasi input yang mengubah berbagai variasi penulisan pasangan aset (misalnya `sol`, `sol/usdt`, `SOL-USDT`) menjadi format kanonikal bursa (`SOLUSDT`).
_Avoid_: Pair parser, ticker converter

**Performa Relatif vs BTC**:
Metrik komparatif 30 hari yang mengukur apakah koin berkinerja lebih kuat (outperforming) atau lebih lemah (underperforming) dibandingkan pergerakan harga Bitcoin.
_Avoid_: BTC dominance alt, altcoin strength

**Mini Candle Snapshot**:
Ringkasan ringkas candle harian terakhir (tanggal, penutupan, persentase perubahan harian, dan rasio volume) yang disertakan pada prompt untuk memberi LLM konteks aksi harga mikro terkini.
_Avoid_: Raw OHLC table, candlestick list

**Running Candle (Unclosed Candle)**:
Candlestick periode berjalan yang sesi perdagangannya belum ditutup sehingga harga penutupan, rentang gerak, dan volumenya masih bersifat sementara (provisional).
_Avoid_: Anomali likuiditas kering, daily close final

**Closed-Candle Baseline**:
Acuan deret candlestick yang sesi perdagangannya telah resmi berakhir pada penutupan periode harian maupun mingguan, bebas dari distorsi volume parsial atau fluktuasi sementara sesi berjalan.
_Avoid_: Repainting indicator, live-candle average

**ProviderConnectionError**:
Kondisi galat di mana bursa tidak dapat dihubungi karena kendala koneksi fisik, pemblokiran regional (HTTP 451), proteksi Cloudflare/WAF (HTTP 403), kegagalan DNS, atau tenggat waktu (timeout).
_Avoid_: Symbol not found, bad pair, invalid request

**Domain-Level Short-Circuit**:
Mekanisme optimasi rantai fallback yang otomatis melompati bursa lain dalam domain yang sama (misal Binance Futures jika Binance Spot sudah gagal koneksi) untuk menghindari penalti latensi timeout berulang.
_Avoid_: Blind retry, linear traversal

**Proxy Tunneling**:
Rute transmisi perantara HTTP/SOCKS yang disuntikkan secara eksplisit via antarmuka baris perintah untuk mengalirkan permintaan API melewati pembatasan sensor atau blokir ISP.
_Avoid_: VPN hook, internal proxy

**Hybrid IDR Valuation**:
Metode kalkulasi valuasi teknikal kuantitatif yang memanfaatkan likuiditas global bursa tier-1 (pasangan USDT) untuk mengekstrak indikator makro bebas bias, kemudian mentranslasikan level harga dan alokasi ke dalam mata uang Rupiah menggunakan kurs bursa domestik real-time.
_Avoid_: Pure local chart analysis, direct IDR klines, rupiah-only technicals

**FX Anchor Rate**:
Nilai tukar spot Tether terhadap Rupiah (USDT/IDR) yang ditarik secara real-time dari bursa domestik (Indodax) untuk menjembatani konversi data fakta pasar global ke nominal eksekusi lokal.
_Avoid_: Static exchange rate, fiat bank rate, USD/IDR forex

**Local Minimum Notional**:
Ambang batas nilai transaksi minimum yang diwajibkan oleh bursa kripto lokal di Indonesia (misalnya Rp 10.000 pada Indodax atau Rp 20.000 pada Tokocrypto) untuk mencegah penolakan orderbook pada saat penempatan limit order.
_Avoid_: Global notional, 10 USDT minimum, flat exchange fee

**Dual-Currency Display**:
Penyajian level harga dan alokasi modal dengan mata uang Rupiah (IDR) sebagai acuan eksekusi orderbook lokal primer, didampingi nilai ekuivalen global (USDT) di dalam tanda kurung untuk memandu verifikasi teknikal model bahasa (LLM).
_Avoid_: Single currency output, pure fiat format

**Adaptive Price Formatting**:
Logika pemformatan angka harga yang secara dinamis membulatkan ke bilangan bulat berpemisah ribuan jika harga aset >= Rp 100 (seperti BTC, ETH, SOL), dan mempertahankan presisi desimal signifikan jika harga aset < Rp 100 (koin mikro/meme).
_Avoid_: Static 4-decimal fiat, arbitrary rounding

**Quarterly VWAP (Q-VWAP)**:
Harga rata-rata tertimbang volume (*Volume-Weighted Average Price*) yang dijangkarkan pada candle harian tertutup pertama dalam kuartal kalender UTC berjalan (`Q1: Jan–Mar`, `Q2: Apr–Jun`, `Q3: Jul–Sep`, `Q4: Okt–Des`), lengkap dengan pita deviasi standar tertimbang volume (`±1σ` dan `±2σ`) untuk memetakan area nilai wajar dan regangan statistik jangka menengah.
_Avoid_: Intraday VWAP, session VWAP, arbitrary anchored VWAP

**365D Rolling VWAP (365D R-VWAP)**:
Harga rata-rata tertimbang volume bergulir selama 365 hari candle harian tertutup terakhir yang berfungsi sebagai jangkar valuasi makro tahunan berbasis volume (terdegradasi ke `N/A` jika riwayat candle harian tertutup koin kurang dari 365 hari).
_Avoid_: Yearly simple average, unclosed rolling VWAP

**Data Snapshot Timestamp**:
Stempel waktu pengambilan fakta pasar (disajikan dalam format `UTC` beserta ekuivalen `WIB / UTC+7`) yang disematkan langsung di dalam isi teks prompt sebagai acuan usia snapshot sebelum rencana dieksekusi.
_Avoid_: Undated prompt, local clock only, implicit execution time

**Pre-Execution Staleness Check**:
Protokol pemeriksaan kesegaran wajib sebelum mengeksekusi rencana Smart DCA guna memastikan harga pasar aktual tidak menyentuh `Level 1` atau bergeser signifikan (`>= 0.5x ATR-14`) dari harga snapshot; apabila kondisi tersebut terpenuhi, pengguna wajib men-generate ulang prompt sebelum bertransaksi.
_Avoid_: Blind delayed execution, stale limit placement

**Entry Overlap Guardrail**:
Batasan jarak kuantitatif minimum antara `Harga Terkini` (porsi `Market Buy`) dan `Limit Order Level 1` sebesar `Harga Terkini - Level 1 >= 0.5x ATR-14` (selaras dengan jarak antar-level `L1 > L2 > L3 >= 0.5x ATR-14`) guna mencegah penumpukan alokasi di titik harga yang sama (*front-heavy execution*).
_Avoid_: Zero-gap limit buy, overlapping market and L1 entry, front-heavy clustering

**Emergency Crash Contingency Plan**:
Sub-protokol darurat di dalam *Order Invalidation Protocol* untuk merespons penurunan harga sangat deras akibat berita negatif atau *macro shock*, mencakup pemicu berbasis *Closed-Candle Baseline* (seperti penutupan di bawah `Q-VWAP -2σ` atau tembus support makro dengan lonjakan volume candle `[CLOSED] > 1.5x`), pembatalan jaring *Limit Order* atas (`Level 1`–`Level 2`) yang belum terisi, serta realokasi sisa modal ke jangkar tangkap ekstrem (`365D R-VWAP`, `200W SMA`, atau proyeksi `-3.0x s/d -5.0x ATR-14`) sambil tetap menegakkan *Minimum Notional Consolidation* (`10.00 USDT` atau *Local Minimum Notional* `Rp 10.000`).
_Avoid_: Panic market sell, blind dip buying, unclosed-candle crash trigger, dust emergency split
