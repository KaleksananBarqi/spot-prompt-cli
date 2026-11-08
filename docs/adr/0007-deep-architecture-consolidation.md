# 0007 - Deep Architecture Refactoring: Pipeline, Client, and Analyzer Consolidation

## Status
Accepted

## Context
Seiring bertambahnya fitur ketahanan jaringan (*multi-exchange fallback chain*, isolasi *closed-candle baseline*, dan evaluasi *domain short-circuit*), basis kode `spot-prompt-cli` mengalami friksi arsitektur:
1. **Kebocoran State Pemanggil (*State Leakage*):** Objek `unreachable_domains: Set[str]` dan session HTTP dialokasikan secara manual oleh pemanggil di `cli.py` dan diteruskan secara longgar (*loose threading*) ke tiga fungsi berbeda di `data_fetcher.py`.
2. **Orkestrasi Dangkal pada Lapisan Presentasi:** Modul `cli.py` mengoordinasikan 7 fungsi berbeda melintasi modul-modul pembungkus dangkal (`template_renderer.py`, `output.py`), sehingga menyulitkan penggunaan programatik non-CLI.
3. ***Mock Sprawl* pada Pengujian:** Berkas `tests/test_cli.py` terpaksa mem-patch 6 fungsi privat internal sekaligus hanya untuk menguji alur perintah CLI.

## Decision
Kami memutuskan merefaktor basis kode menjadi arsitektur modul mendalam (*deep modules*) berbasis prinsip *Codebase Design*:
1. **PromptPipeline (`spot_prompt/pipeline.py`):** Modul mendalam yang menyatukan seluruh orkestrasi perakitan prompt (penarikan data, komputasi fakta indikator, rendering Jinja2, dan penulisan disk) di balik satu *interface* tunggal: `PromptPipeline.execute(config, options) -> PromptResult`.
2. **MarketDataClient (`spot_prompt/data_client.py`):** Modul *ports & adapters* yang mengenkapsulasi status domain *short-circuit*, sesi HTTP, konfigurasi proxy, dan hierarki fallback bursa. Menghilangkan kebocoran state pelacak domain ke pemanggil dan menyediakan metode tunggal `fetch_context(symbol) -> MarketContext`.
3. **RawFactsAnalyzer (`spot_prompt/analyzer.py`):** Modul analisis deterministik murni (*in-process*) yang menyerap seluruh fungsi kalkulasi matematika teknikal dan menjamin isolasi *Closed-Candle Baseline* di balik metode `analyze_context(context) -> IndicatorFacts`.
4. **Pembersihan Rangkaian Pengujian (*The Interface is the Test Surface*):** Mengganti *mock sprawl* di `tests/test_cli.py` dengan pengujian langsung pada *interface* `PromptPipeline`, serta menambahkan `tests/test_pipeline.py`.
5. **Kompatibilitas Mundur (*Zero Breakage*):** Mempertahankan `data_fetcher.py`, `indicators.py`, `template_renderer.py`, dan `output.py` sebagai lapisan delegasi transparan agar tidak merusak pemanggil lama.

## Consequences
- *Leverage* pemanggil meningkat drastis: baik CLI maupun integrasi masa depan (seperti Telegram bot atau skrip otomatisasi) cukup memanggil satu metode `PromptPipeline.execute()`.
- State koneksi bursa dan status *short-circuit* terlindungi rapat (*high locality*).
- Pengujian menjadi tangguh, bebas dari kerapuhan *internal monkey-patching*.
