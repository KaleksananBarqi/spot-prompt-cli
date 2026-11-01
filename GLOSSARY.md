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
Tingkat harga dengan akumulasi volume transaksi terbesar dalam rentang observasi 90 hari terakhir, dihitung melalui metode price binning mekanis.
_Avoid_: Support level, order block, liquidity zone

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

**Price Binning**:
Metode pembagian rentang harga ke dalam interval diskrit berjarak sama untuk mengagregasi volume dari deret OHLCV harian dalam menghitung Point of Control.
_Avoid_: Volume clustering, orderbook depth

**Symbol Normalizer**:
Komponen sanitasi input yang mengubah berbagai variasi penulisan pasangan aset (misalnya `sol`, `sol/usdt`, `SOL-USDT`) menjadi format kanonikal bursa (`SOLUSDT`).
_Avoid_: Pair parser, ticker converter

**Performa Relatif vs BTC**:
Metrik komparatif 30 hari yang mengukur apakah koin berkinerja lebih kuat (outperforming) atau lebih lemah (underperforming) dibandingkan pergerakan harga Bitcoin.
_Avoid_: BTC dominance alt, altcoin strength

**Invalidation Level**:
Batas harga atau kondisi teknikal spesifik di mana rencana jaring bawah (limit order) harus dibatalkan karena struktur pasar telah rusak secara fundamental.
_Avoid_: Stop loss spot, cutloss level

**Mini Candle Snapshot**:
Ringkasan ringkas 5 candle harian terakhir (tanggal, penutupan, persentase perubahan harian, dan rasio volume) yang disertakan pada prompt untuk memberi LLM konteks aksi harga mikro terkini.
_Avoid_: Raw OHLC table, candlestick list

**ProviderConnectionError**:
Kondisi galat di mana bursa tidak dapat dihubungi karena kendala koneksi fisik, pemblokiran regional (HTTP 451), proteksi Cloudflare/WAF (HTTP 403), kegagalan DNS, atau tenggat waktu (timeout).
_Avoid_: Symbol not found, bad pair, invalid request

**Domain-Level Short-Circuit**:
Mekanisme optimasi rantai fallback yang otomatis melompati bursa lain dalam domain yang sama (misal Binance Futures jika Binance Spot sudah gagal koneksi) untuk menghindari penalti latensi timeout berulang.
_Avoid_: Blind retry, linear traversal

**Proxy Tunneling**:
Rute transmisi perantara HTTP/SOCKS yang disuntikkan secara eksplisit via antarmuka baris perintah untuk mengalirkan permintaan API melewati pembatasan sensor atau blokir ISP.
_Avoid_: VPN hook, internal proxy
