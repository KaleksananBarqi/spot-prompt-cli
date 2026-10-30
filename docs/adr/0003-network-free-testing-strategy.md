# 0003 - Network-Free Testing Strategy with Golden Fixtures

## Status
Accepted

## Context
Alat ini bergantung pada data publik dari bursa dan penyedia indeks (Binance REST API dan Alternative.me). Menjalankan unit test dengan melakukan permintaan HTTP langsung ke API publik akan menyebabkan *flaky tests* akibat gangguan jaringan internet, batasan *rate limit*, atau perubahan harga dinamis secara real-time yang merusak asersi numerik pengujian.

## Decision
Kami memutuskan seluruh rangkaian pengujian (*pytest suite*) wajib dirancang 100% bebas jaringan (*network-free*):
1. Menggunakan berkas *fixture* JSON lokal statis yang meniru respons klines Binance dan data Fear & Greed.
2. Menguji seluruh fungsi kalkulasi indikator secara terisolasi terhadap deret angka yang diketahui (*golden values*).
3. Melakukan *mocking* pada lapisan HTTP client (`requests`) dalam pengujian *data fetcher* dan alur integrasi CLI.

## Consequences
- Pengujian berjalan deterministik, instan (< 1 detik), dan dapat dieksekusi secara offline.
- Tidak ada risiko IP terblokir akibat *rate limiting* saat menjalankan tes berulang kali.
- Pengembang perlu memperbarui fixture jika skema API eksternal mengalami perubahan struktur data di masa mendatang.
