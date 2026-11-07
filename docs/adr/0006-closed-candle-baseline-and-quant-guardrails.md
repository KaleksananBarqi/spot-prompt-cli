# 0006 - Closed-Candle Baseline, Value Area 90D, and Quantitative DCA Guardrails

## Status
Accepted

## Context
Evaluasi terhadap output prompt generasi pertama mengungkap empat celah sistematis ketika dianalisis oleh LLM hilir:
1. **Kontaminasi *Running Candle* (*Unclosed Candle*):** Endpoint klines publik bursa (Binance, MEXC, Gate.io) selalu menyertakan candle harian (`1d`) dan mingguan (`1w`) yang masih berjalan pada indeks terakhir (`iloc[-1]`). Menghitung indikator langsung di atas seluruh deret menyebabkan distorsi pada `ATR-14`, `RSI`, `Bollinger Bands`, dan rasio volume rata-rata 20 hari (misal rasio volume terbaca `0.17x` di pagi hari UTC dan disalahartikan oleh LLM sebagai anomali keringnya likuiditas).
2. **Jebakan *Example Anchoring* pada Limit Order:** Penyebutan indikator spesifik di dalam contoh format output (seperti `POC 90H` atau `Middle BB`) memicu LLM merekomendasikan *Limit Buy* di atas harga pasar saat koin sedang terkoreksi, yang di pasar spot akan langsung tereksekusi sebagai *Market Order*. Selain itu, ketiadaan batas bawah distribusi volume membuat LLM kehilangan referensi struktural saat harga berada di bawah `POC 90H`.
3. **Absennya Rubrik Skor, Sub-Alokasi Jaring, & Konsolidasi *Minimum Notional*:** Skor kelayakan 1–100 belum memiliki bobot terukur maupun korelasi tegas terhadap porsi *Market Buy* untuk ketiga `Execution Mode` (`conservative`, `moderate`, `aggressive`), serta berisiko memecah budget kecil menjadi order di bawah batas minimum bursa (`10.00 USDT`).
4. **Invalidasi Satu Arah:** Konsep pembatalan order sebelumnya hanya mencakup keruntuhan struktur bawah (*bearish breakdown*), mengabaikan risiko *Upside Runaway (Cash Drag)* dan kedaluwarsa siklus bulanan (*Cycle Expiry*).

Alternatif seperti memisahkan *System vs User Prompt* untuk API bot, menyuruh LLM mencetak *Order Ticket* mikro (`stepSize`, `qty` pecahan, `fee`), atau memindahkan kalkulasi skor kelayakan sepenuhnya ke kode Python ditolak karena bertentangan dengan arsitektur *single-paste zero-auth* (ADR 0001) dan pemisahan peran *Raw Facts Layer* vs penalaran LLM.

## Decision
Kami memutuskan:
1. **Closed-Candle Baseline dengan Live Price Separation:** Memisahkan harga terkini (`current_price` dan ekstrem 30 hari dari baris live `iloc[-1]`) dari baseline kalkulasi indikator teknikal. Seluruh seri `200W SMA`, `200D SMA`, `50D EMA`, `RSI 14 Daily/Weekly`, `Bollinger Bands`, `ATR-14`, `Volume Profile 90H`, dan rata-rata volume 20 hari dihitung murni menggunakan candle yang sudah ditutup (`iloc[:-1]`), sedangkan persentase deviasi MA dan posisi `%B` tetap diukur dari `current_price` live terhadap baseline tertutup tersebut. Baris pada tabel *Mini Candle Snapshot* dilabeli eksplisit antara `[CLOSED]` dan `[RUNNING / UNCLOSED]`.
2. **Ekspansi Volume Profile 90H (VAH, POC, VAL) & Pre-Tagging Posisi Deterministik:** Memperluas distribusi *price binning* 90 hari untuk mengekstrak 70% *Value Area* (`VAH` dan `VAL`) di sekitar `POC`. Pada template prompt, Python/Jinja2 menyematkan label posisi faktual pada setiap level indikator (`< Current Price` sebagai kandidat support vs `>= Current Price` sebagai *overhead resistance* yang dilarang dijadikan titik *Limit Buy*), dengan aturan fallback ke kelipatan negatif `ATR-14` apabila seluruh indikator berada di atas harga (*free-fall*).
3. **Rubrik Skor Berbobot, Matriks Mode Dinamis, & Konsolidasi Minimum Notional:** Menetapkan rubrik skor 100 poin (`40` Valuasi Makro/Siklus, `35` Momentum/Volatilitas, `25` Sentimen/Price Action) dengan realokasi otomatis bila `200W SMA` bernilai `N/A` dan hierarki resolusi konflik `Makro/Weekly > Daily > Sentimen`. Template menyuntikkan matriks korelasi Skor-ke-Market-Buy sesuai `Execution Mode` aktif, mewajibkan jarak antar-jaring minimal `0.5x ATR`, serta menerapkan *Minimum Notional Consolidation* (`>= 10.00 USDT` per order atau peleburan level jika budget terbatas).
4. **Order Invalidation Protocol Tiga Arah & Self-Check:** Memperluas protokol manajemen order menjadi tiga skenario (*Upside Runaway*, *Downside Structural Breakdown*, dan *Cycle Expiry/Rollover*) serta mewajibkan blok verifikasi aritmetika mandiri (*Self-Check*) di akhir output LLM.

## Consequences
- Nilai indikator teknikal harian dan mingguan menjadi konsisten sepanjang hari (bebas *intraday repainting*), sementara deviasi harga dan `%B` tetap responsif terhadap pergerakan harga detik ini.
- Risiko halusinasi *Limit Buy* di atas harga pasar dan pembagian order di bawah ambang batas bursa tereliminasi tanpa perlu mengambil metadata `exchangeInfo` per bursa.
- Alur kerja pengguna tetap 100% *single-paste* ke antarmuka chat LLM mana pun tanpa dependensi pustaka tambahan di luar Pandas, NumPy, dan Jinja2.
