# 0008 - Hybrid IDR Valuation and Local Exchange Support

## Status
Accepted

## Context
Mayoritas investor dan penabung kripto di Indonesia (spot accumulators) melakukan pembelian aset secara berkala (DCA) melalui bursa kripto lokal berizin Bappebti (seperti Indodax dan Tokocrypto) menggunakan mata uang Rupiah (IDR).

Namun, penyusunan strategi Smart DCA berbasis data teknikal murni pada pasangan aset lokal (`*IDR`) menghadapi sejumlah kendala struktural:
1. **Likuiditas Tipis dan Volume Terfragmentasi:** Pasangan koin altcoin terhadap IDR di bursa lokal memiliki volume perdagangan yang jauh lebih rendah dibanding bursa global tier-1, rentan terhadap lonjakan selisih harga (*spread*) lebar dan sumbu anomali (*illiquid wick*) yang mendistorsi indikator momentum.
2. **Keterbatasan Riwayat Data Makro:** Banyak pasangan koin IDR belum memiliki riwayat perdagangan hingga 200 minggu atau 200 hari di bursa domestik, sehingga kalkulasi valuasi makro siklus seperti **200W SMA** dan **Volume Profile POC 90H** sering kali tidak dapat dihitung atau bernilai bias.
3. **Distorsi Inflasi / Nilai Tukar Fiat:** Fluktuasi nilai tukar Rupiah terhadap Dolar AS tercampur ke dalam grafik harga koin IDR, mengaburkan level-level teknikal murni yang disepakati oleh konsensus pasar kripto global.
4. **Ketidakcocokan Guardrail Minimum Order:** Bursa global menetapkan batas minimum transaksi spot sekitar $10.00 USDT (~Rp 160.000), sedangkan bursa lokal memiliki ambang batas minimum eksekusi jauh lebih rendah, yaitu Rp 10.000 (Indodax) atau Rp 20.000 (Tokocrypto).

## Decision
Kami memutuskan mengimplementasikan arsitektur **Hybrid IDR Valuation**:
1. **Mesin Valuasi Global (Global Quantitative Engine):** Seluruh kalkulasi indikator matematis objektif (200W SMA, 200D SMA, 50D EMA, Volume Profile 90H POC/VAH/VAL, Bollinger Bands %B, RSI 14, dan ATR-14) tetap diekstrak dari likuiditas global bursa tier-1 (Binance Spot / MEXC / Binance Futures / Gate.io) pada pasangan USDT.
2. **Jangkar Kurs Spot Domestik (FX Anchor Rate):** Menghubungkan modul klien ke endpoint publik bursa lokal (Indodax Ticker `usdtidr`) tanpa autentikasi/API key untuk menarik kurs spot Tether/Rupiah secara *real-time*. Jika Indodax mengalami kendala jaringan atau *timeout*, sistem otomatis beralih ke *fallback* publik CoinGecko Simple Price (`tether` to `idr`). Pengguna juga dapat memasukkan nilai kurs manual via opsi `--fx-rate`.
3. **Penyajian Dual-Currency & Pemformatan Adaptif:** Output prompt menyajikan harga primer dalam Rupiah (IDR) untuk eksekusi praktis pada orderbook lokal, didampingi ekuivalen patokan USDT di dalam tanda kurung untuk memvalidasi posisi teknikal grafik acuan global. Format angka Rupiah dibuat adaptif: dibulatkan penuh tanpa desimal dengan pemisah ribuan titik untuk harga $\ge \text{Rp } 100$, dan mempertahankan desimal presisi untuk koin mikro $< \text{Rp } 100$.
4. **Penyesuaian Guardrail Minimum Notional:** Menetapkan batas kuantitatif `MIN_NOTIONAL_IDR = 10.000` (disertai panduan toleransi Rp 20.000 untuk Tokocrypto) saat mata uang eksekusi adalah IDR, sehingga pengguna dengan modal akumulasi terjangkau tetap dapat membagi jaring limit order tanpa penolakan orderbook bursa lokal.
5. **Sanitasi Simbol & Format Angka Rupiah:** Memperluas `Symbol Normalizer` agar otomatis mengenali sufiks `IDR` (misalnya `BTCIDR` atau `SOL-IDR`), mengarahkan pipeline data ke pair global `BTCUSDT`, menyetel `config.currency = "IDR"`, serta membersihkan pemisah ribuan pada input budget (misalnya `1.500.000` menjadi `1500000.0`).

## Consequences
- Analisis teknikal tetap 100% konsisten dengan konsensus likuiditas pasar kripto global tanpa kehilangan garis valuasi makro 200W SMA.
- Pengguna bursa lokal di Indonesia memperoleh prompt rencana akumulasi dengan level-level harga beli langsung dalam Rupiah, siap dipasang pada aplikasi bursa domestik.
- Penanganan jaringan berlapis memastikan ketersediaan data kurs tetap andal (*graceful degradation*).
- Menghilangkan friksi penolakan order bursa lokal berkat batas minimum notional yang diselaraskan dengan aturan pasar domestik.
