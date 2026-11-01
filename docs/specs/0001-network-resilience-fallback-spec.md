# Spec: Network Resilience, Domain Short-Circuit, and Proxy Tunneling for Multi-Exchange Fallback

> Issue: [#1](https://github.com/KaleksananBarqi/spot-prompt-cli/issues/1) · Label: `ready-for-agent`

## Problem Statement

Pengguna CLI yang berada di wilayah atau jaringan internet dengan sensor atau pemblokiran terhadap Binance (seperti pemblokiran domain/IP oleh ISP di Indonesia atau pemblokiran regional oleh Cloudflare/WAF berupa HTTP 403/451) mengalami kegagalan dan kebingungan saat menjalankan analisis Smart DCA:
1. Terminal memberikan informasi yang salah, melaporkan bahwa simbol token tidak ditemukan (`SymbolNotFoundError`), padahal token tersebut valid dan masalah sebenarnya adalah koneksi yang diblokir.
2. Ketika bursa utama Binance diblokir, sistem membuang waktu tunggu latensi hingga 10 detik untuk mencoba endpoint derivatif Binance (Binance Futures), meskipun domain induk sudah jelas tidak dapat dijangkau.
3. Metrik komparasi pasar terhadap Bitcoin (`Performa Relatif vs BTC` dan performa BTC 30/90 hari) hilang sepenuhnya dari prompt evaluasi LLM karena fungsi pengambil data benchmark BTC masih bergantung secara kaku pada Binance Spot tanpa dukungan rantai fallback.
4. Pengguna tidak memiliki cara langsung untuk menyuntikkan proxy lokal (misalnya SOCKS5/HTTP tunnel) melalui baris perintah tanpa mengubah konfigurasi proxy global sistem operasi.

## Solution

Membangun lapisan ketahanan jaringan (*Network Resilience*) komprehensif pada arsitektur rantai fallback:
1. Membedakan secara tegas antara galat simbol tidak terdaftar dengan galat koneksi/pemblokiran bursa.
2. Mengimplementasikan *Domain-Level Short-Circuit* untuk secara otomatis melompati bursa turunan dalam satu domain induk jika domain tersebut terbukti tidak dapat diakses pada sesi yang bersangkutan.
3. Menyelaraskan pengambilan data benchmark BTC dengan rantai fallback multi-bursa sehingga data komparasi pasar tetap lengkap meskipun Binance tidak dapat diakses.
4. Menyediakan opsi *Proxy Tunneling* melalui antarmuka baris perintah (`--proxy`) untuk memfasilitasi pengguna yang ingin melewati pemblokiran secara aman dan langsung.
5. Menampilkan diagnosis galat akhir yang cerdas dan transparan saat terjadi kegagalan total.

## User Stories

1. As a CLI user in a restricted region, I want the CLI to clearly inform me if an exchange is blocked or unreachable due to network issues, so that I do not mistakenly assume the coin symbol is invalid.
2. As a CLI user in a restricted region, I want the system to automatically fallback to alternative spot exchanges (such as MEXC or Gate.io) when Binance is blocked, so that I can still generate Smart DCA prompts seamlessly.
3. As a CLI user experiencing domain-level censorship, I want the fallback chain to automatically skip Binance Futures if Binance Spot has already failed due to network blocking, so that I do not waste unnecessary timeout latency waiting for an endpoint that is already known to be unreachable.
4. As a downstream LLM receiving the generated prompt, I want the Raw Facts Layer to contain complete BTC benchmark and relative performance metrics even when Binance is blocked, so that I can evaluate whether the coin is outperforming the benchmark market structure.
5. As a CLI user running behind a local VPN or proxy client, I want to specify an ad-hoc proxy URL via a command-line flag, so that all outbound HTTP requests are routed through the proxy tunnel without modifying my global operating system network configuration.
6. As a CLI user without an explicit proxy flag, I want the CLI to respect standard system environment variables (`HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`), so that my existing terminal environment setup works out of the box.
7. As a CLI user analyzing a newly listed meme coin while Binance is blocked, I want the CLI to fetch the coin candlestick data and the BTC benchmark data from alternative exchanges without crashing, so that I can make timely accumulation decisions.
8. As an offline user or someone with total internet disconnection, I want the CLI to diagnose that all exchanges failed due to network connectivity issues rather than claiming the symbol does not exist, so that I know to reconnect my internet before trying again.
9. As a developer extending the CLI, I want custom exception classes that cleanly distinguish between client bad requests, unlisted symbols, and transport/network blocking errors, so that error handling logic remains decoupled and maintainable.
10. As a CLI user, I want the in-memory domain block state to only persist for the duration of a single execution run, so that if I turn on a VPN or switch to a non-censored Wi-Fi network, subsequent CLI runs will naturally re-attempt the primary exchange.
11. As a CLI user, I want graceful degradation if BTC benchmark data is completely unavailable across all exchanges, so that I still receive an actionable DCA prompt for my target coin instead of suffering a complete application crash.
12. As a CLI user, I want clear, colorized terminal status logs showing the transition between tiers and the exact reason for fallback, so that I have complete visibility into the health of my network connections and data sources.

## Implementation Decisions

- **Hierarki Galat Domain**: Memperkenalkan tipe galat khusus `ProviderConnectionError` (turunan dari galat pengambil data utama) untuk menangani status HTTP 403, 451, seluruh kode status HTTP 5xx, serta kegagalan transportasi seperti connection refused, connection reset, timeout, dan kegagalan resolusi DNS. Sementara `SymbolNotFoundError` dibatasi ketat untuk respons HTTP 400 dan 404.
- **In-Memory Domain Short-Circuit**: Menyediakan pelacak domain yang tidak dapat dijangkau dalam memori selama siklus hidup satu kali eksekusi perintah CLI. Ketika domain bursa induk terkonfirmasi memicu `ProviderConnectionError`, penyedia lain yang bernaung di bawah domain yang sama otomatis dilewati (*bypassed*) ke tier berikutnya.
- **Rantai Fallback Terpadu untuk Benchmark BTC**: Fungsi ekstraksi kinerja historis BTC dialihkan dari ketergantungan bursa tunggal ke mekanisme rantai fallback multi-bursa yang sama, dengan penanganan *graceful degradation* yang mengembalikan nilai kosong jika seluruh bursa gagal.
- **Injeksi Sesi dan Proxy Tunneling**: Parameter konfigurasi proxy disematkan pada fungsi pembuatan sesi HTTP dan dihubungkan ke opsi antarmuka baris perintah (`--proxy` / `-p`).
- **Evaluasi Diagnosis Kegagalan Akhir**: Ketika rantai fallback kehabisan penyedia data, modul penarik data memeriksa agregat riwayat galat dari setiap tier untuk menentukan pesan diagnosis akhir (apakah murni kegagalan jaringan, murni simbol tidak ditemukan, atau kombinasi keduanya).

## Testing Decisions

- **Definisi Pengujian Berkualitas**: Pengujian hanya memverifikasi perilaku eksternal (*observable behavior*) dan kontrak antarmuka publik, bukan detail implementasi privat. Pengujian wajib 100% bebas ketergantungan jaringan (*network-free*) sesuai prinsip ADR 0003, menggunakan simulasi sesi HTTP tiruan (*mock session*).
- **Titik Seam Pengujian**: Titik seam tertinggi yang digunakan adalah penyuntikan `requests.Session` pada modul pengambil data publik serta antarmuka perintah CLI runner. Satu seam ini mampu mengisolasi seluruh interaksi jaringan tanpa perlu membuat seam tambahan.
- **Modul yang Diuji**:
  - Modul pengambil data publik: simulasi respons HTTP 403, 451, 5xx, timeout, verifikasi pelompatan domain short-circuit, dan fallback BTC.
  - Modul CLI: verifikasi flag `--proxy`, verifikasi pesan log terminal yang membedakan alasan fallback, dan diagnosis galat akhir.
- **Prioritas & Bukti Terdahulu (*Prior Art*)**: Memperluas rangkaian pengujian mock session yang telah terbukti pada rangkaian test suite fallback bursa sebelumnya (ADR 0004).

## Out of Scope

- Implementasi auto-retry dengan exponential backoff yang agresif (dihindari agar latensi respons CLI tetap instan di bawah batas toleransi pengguna).
- Penyimpanan persisten status pemblokiran ke file disk atau database lokal.
- Integrasi VPN internal atau protokol DNS-over-HTTPS kustom.
- Perubahan pada formula perhitungan indikator teknikal (SMA, EMA, RSI, Volume Profile POC, ATR).

## Further Notes

- Semua bursa alternatif yang digunakan tetap mematuhi prinsip Zero-API-Key Public REST (tanpa memerlukan autentikasi atau token rahasia).
- Istilah dan definisi yang digunakan dalam spesifikasi ini tunduk pada terminologi kanonikal dalam `GLOSSARY.md` dan keputusan arsitektur `docs/adr/0005-network-resilience-and-domain-short-circuit.md`.
