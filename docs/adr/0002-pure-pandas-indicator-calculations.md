# 0002 - Pure Pandas and NumPy for Technical Indicators

## Status
Accepted

## Context
Kalkulasi indikator teknikal (SMA, EMA, RSI, Bollinger Bands, ATR, dan Volume Profile POC) umumnya diimplementasikan menggunakan pustaka eksternal seperti `TA-Lib` atau `pandas-ta`. Namun, `TA-Lib` bergantung pada binary pustaka C yang sering kali gagal saat instalasi lintas platform (Windows, macOS ARM, Linux) tanpa toolchain build khusus. Sementara `pandas-ta` memiliki ketergantungan paket yang berat dan frekuensi pembaruan yang lambat.

## Decision
Kami memutuskan mengimplementasikan seluruh rumus indikator teknikal murni menggunakan operasi vektorisasi Pandas dan NumPy tanpa pustaka analisis teknikal pihak ketiga.

## Consequences
- Instalasi paket Python menjadi instan dan tanpa risiko kegagalan build native C.
- Basis kode tetap mandiri, transparan, dan mudah diverifikasi melalui unit test matematis.
- Tim bertanggung jawab memelihara implementasi rumus matematis indikator (Wilder's RSI, SMA/EMA rolling, BB, True Range, dan histogram POC).
