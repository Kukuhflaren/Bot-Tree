# Bot-Tree

Bot sinyal dan eksperimen trading futures USDT Bitget UTA. Bot menyaring universe, menganalisis candle, membuat rencana grid dengan TP/SL, menjalankan simulasi paper, dan menyediakan jalur Demo yang dibatasi oleh gate risiko.

> **Status:** gunakan paper dan Demo saja. Eksekusi Live belum tersedia. Belum ada bukti bahwa strategi menghasilkan edge setelah biaya dan slippage; hasil uji singkat bukan jaminan keuntungan atau nasihat keuangan.

## Fitur bot

- Penyaring universe berdasarkan volume, watchlist, blacklist, dan batas perubahan harga.
- Indikator EMA, RSI, MACD, SAR, ATR, VWAP, support/resistance, dan konfirmasi tren.
- Risk gate: batas posisi terbuka, rugi harian, rugi beruntun, kill switch, RR, dan risk ATR.
- Rencana entry grid dengan pilihan TP/SL berbasis S/R atau ATR.
- Scanner berulang untuk **paper**; scanner tidak mengirim order exchange.
- Simulasi paper dengan trade-through, batas partisipasi volume candle, partial fill, slippage, fee estimasi, TP/SL, dan state.
- Signal engine Phase 5 formula-only; AI tidak menentukan sinyal engine.
- Jurnal paper append-only dan laporan evaluasi Phase 6.
- Preflight Demo dengan estimasi net bps, fee, funding, spread, depth, serta pembatas post-only.
- Rekonsiliasi order/posisi Demo, pencatatan fill/fee/funding aktual, cancel terverifikasi, dan time-exit reduce-only.
- Reset state Demo dengan pemeriksaan exchange dan backup; jurnal audit dipertahankan.

## Tahap pengembangan

| Urutan | Tahap | Cakupan dan status |
|---|---|---|
| 1 | Koneksi | Pemeriksaan ticker publik dan koneksi/saldo Bitget; tidak membuat order. |
| A | Risk dan universe | Risk gate, watchlist, blacklist, volume dan ukuran posisi. |
| B | Sinyal teknikal | Candle, indikator, syarat entry, grid, TP/SL dan validasi RR/risk ATR. |
| C | Scanner | Siklus paper berulang; bukan loop order Demo. |
| D | Paper | Simulasi fill/partial/slippage/fee dan state; asumsi candle bukan bukti eksekusi nyata. |
| E | Sizing dan preflight | Minimum order, precision, contract size, geometri TP/SL dan batas notional. |
| 5 | Signal engine | Pipeline formula-only yang menghasilkan `signal.json`. |
| 6 | Evaluasi paper | Jurnal, metrik, drawdown dan safety gate; perlu observasi yang cukup. |
| 7 | Bitget Demo | Filter biaya/pasar, post-only, rekonsiliasi dan time-exit; uji UTA Demo end-to-end masih wajib. |

## Yang sudah ada

- Implementasi lokal untuk tahap 1, A–E, 5, 6, dan fondasi tahap 7.
- Konfigurasi terpusat di `config.py` dan contoh konfigurasi di `env.example`.
- Tes offline untuk sizing, indikator, simulator, Phase 6, Demo lifecycle, dan reset.
- Entry Demo menyaring estimasi net setelah fee masuk/keluar, dampak order book, dan estimasi funding.
- Status order yang belum pasti menahan runner; kegagalan API tidak dianggap sebagai akun kosong.
- Reset Demo hanya membersihkan state runner setelah akun terverifikasi bersih; backup state dan jurnal dibuat lebih dulu.

## Yang belum ada

- Verifikasi independen bahwa skema UTA Bitget, TP/SL, partial fill, cancel, post-only, funding, dan time-exit bekerja seperti yang diharapkan di akun Demo.
- Bukti statistik strategi dari paper yang cukup lama dan cukup banyak trade.
- Eksekusi Live dan safeguard modal asli; jangan gunakan `MODE=live` untuk mengirim order.
- Strategi scalping timer/candle, grid scalping, swing, dan grid swing sebagai engine terpisah. Implementasi saat ini berpusat pada grid.
- Evaluasi empiris bahwa AI menambah edge; AI opsional bukan penentu formula signal engine.
- Dashboard dan kontrol melalui web belum menjadi bagian panduan operasional ini.

## Persyaratan

- Python 3.10 atau lebih baru.
- Paket di `requirements.txt`: `ccxt`, `python-dotenv`, `pandas`, dan `requests`.
- Windows 10/11 dengan Command Prompt, atau Termux Android yang mendukung versi Python dan dependensi tersebut.
- Koneksi internet untuk data pasar dan API Bitget.
- Akun Bitget UTA. Untuk pengujian privat gunakan **Demo API Key** dengan izin baca dan trade saja; jangan aktifkan izin withdraw.
- Jangan menaruh API key pada source code, README, atau file JSON hasil eksperimen.

Termux merupakan lingkungan tambahan, bukan platform yang sudah disertifikasi. Pastikan dependensi dapat di-import dan jalankan tes offline sebelum menggunakannya.

## Instalasi

### Windows — Command Prompt (CMD)

Buka Command Prompt, masuk ke folder project, lalu buat virtual environment:

```bat
cd /d "D:\Projek Aplikasi Ipeh\Bot Tree"
py -3.12 -m venv venv
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
copy env.example .env
notepad .env
```

Jika `py -3.12` tidak tersedia, gunakan `python -m venv venv` setelah memastikan `python --version` menunjukkan Python 3.10+. Jangan membagikan `.env`.

### Android — Termux

Pasang Termux dari sumber resmi yang Anda gunakan, lalu siapkan Python dan editor. Letakkan salinan project di `~/bot-tree` (melalui Git atau transfer file); jalankan bot dari direktori home Termux, bukan langsung dari penyimpanan bersama.

```bash
# 1. Update repositori Termux
pkg update && pkg upgrade -y

# 2. Instal Python, Git, dan Editor
pkg install python git nano -y

# 3. PENTING: Instal cryptography versi Termux (mencegah error PyLong_Type)
pkg install python-cryptography -y

# 4. Masuk ke folder home (jika belum)
cd ~

# 5. Clone repositori (jika belum punya) atau masuk ke foldernya
# git clone https://github.com/Kukuhflaren/Bot-Tree.git
cd Bot-Tree

# 6. Buat Virtual Environment DENGAN akses sistem (--system-site-packages)
# Ini wajib agar venv bisa melihat python-cryptography yang tadi diinstal
python -m venv --system-site-packages venv

# 7. Aktifkan venv
source venv/bin/activate

# 8. Instal ccxt tanpa dependensi bawaan (mencegah error orjson)
pip install --no-deps ccxt

# 9. Instal dependensi pendukung secara manual
pip install python-dotenv certifi requests aiohttp yarl typing_extensions

# 10. Verifikasi instalasi (Pastikan tidak ada error)
python -c "import ccxt; print('CCXT Siap, versi:', ccxt.__version__)"

# 11. Salin file contoh
cp env.example .env

# 12. Buka file .env dengan editor nano
nano .env

# 13. Kunci CPU (wajib untuk Android)
termux-wake-lock

```

Apabila pemasangan `pandas` atau paket lain gagal pada versi Termux/Python Anda, jangan lanjut ke Demo. Selesaikan kompatibilitas dependensi terlebih dahulu. Verifikasi paket:

```bash
python -c "import ccxt, pandas, requests, dotenv; print('dependensi OK')"
```

## Konfigurasi penting `.env`

Salin dari `env.example`. Baris berikut adalah nilai awal eksperimen, bukan tarif atau eksekusi yang dijamin.

| Kelompok | Variabel | Keterangan |
|---|---|---|
| Mode | `MODE=paper` atau `MODE=demo` | Gunakan paper sebagai awal. Pengiriman Live belum tersedia. |
| Kunci | `BITGET_API_KEY`, `BITGET_SECRET_KEY`, `BITGET_PASSPHRASE` | Untuk Demo, isi hanya kredensial Demo. |
| UTA | `BITGET_UTA=on` | Format akun UTA. |
| Gate Demo | `DEMO_API=on`, `DEMO_CONFIRM=UJI_DEMO_SAYA_PAHAM`, `DRY_RUN=off` | Syarat konfigurasi untuk pengiriman Demo. |
| Gate loop | `DEMO_LOOP_EXECUTION_VERIFIED=off` | Biarkan `off` sampai seluruh uji manual Demo lulus. |
| Fee asumsi | `DEMO_MAKER_FEE_BPS=6`, `DEMO_TAKER_FEE_BPS=6` | Asumsi awal; sesuaikan dengan fee tier yang terverifikasi. |
| Net minimum | `DEMO_MIN_NET_BPS=15` | Tolak setup dengan estimasi net di bawah nilai ini. |
| Order book | `DEMO_MAX_SPREAD_BPS=10`, `DEMO_MIN_BOOK_DEPTH_MULTIPLE=5`, `DEMO_BOOK_MAX_AGE_SECONDS=3` | Batas spread, depth dua sisi, dan umur snapshot. |
| Time-exit | `DEMO_MAX_HOLD_HOURS=5` | Batas waktu dihitung sejak fill pertama. |
| Paper fill | `PAPER_FILL_THROUGH_BPS=1`, `PAPER_FILL_PARTICIPATION_PCT=1` | Syarat trade-through dan batas volume candle untuk simulasi. |
| Risk | `MODAL_DEMO_USDT`, `LEVERAGE`, `RISK_PER_SETUP_PCT`, `MAX_OPEN_TOKENS`, `MAX_DAILY_LOSS_USDT`, `MAX_CONSECUTIVE_LOSSES`, `KILL_SWITCH` | Batas ukuran dan penghentian entry. |
| TP/SL | `TP_MODE`, `TP_METHOD`, `TP_ATR_PERCENT`, `SL_METHOD`, `SL_ATR_PERCENT`, `SL_BUFFER_ATR`, `RR_MIN`, `RISK_ATR_MIN`, `RISK_ATR_MAX` | Pilihan perhitungan TP/SL dan validasi risk. |
| Universe | `WATCHLIST_MODE`, `WATCHLIST_FILE`, `TOKEN_BLACKLIST`, `EXCLUDE_RWA`, `UBAH_IDEAL_SKOR`, `PENYARING_VOL_MIN_USDT`, `PENYARING_TOP_VOLUME`, `JUMLAH_PER_SISI` | Konfigurasi penyaringan token. `EXCLUDE_RWA=on` membuang saham/ETF/komoditas sesi kecuali yang ada di watchlist. |
| AI | `USE_AI=off`, `AI_PROVIDER`, key provider dan batas panggilan | AI opsional; signal engine tetap formula-only. |

Estimasi funding menggunakan funding rate saat ini. Saat trade ditutup, runner meminta funding history aktual; jika data fill, fee, atau funding yang diperlukan tidak tersedia, PnL tidak difinalisasi dan entry berikutnya ditahan.

## Perintah utama — urutan tahap

Jalankan dari folder `Bot Tree` dengan virtual environment aktif. Perintah yang mengakses API hanya membaca data kecuali perintah Demo yang secara eksplisit diberi opsi kirim.

### 1. Koneksi

```bash
python cek_koneksi.py
```

Memeriksa ticker publik dan, bila kredensial ada, membaca saldo. Skrip ini tidak mengirim order.

### A. Risk dan universe

```bash
python tes_bitget_orders.py
python cek_risk_universe.py
python penyaring.py
```

`penyaring.py` mengambil data pasar untuk membuat/menyegarkan `daftar_40.json`.

### B. Indikator, kelayakan, dan TP/SL

```bash
python tes_indikator.py
python tes_tp_sl_metode.py
python cek_kelayakan.py
python ai_kelayakan.py
```

`cek_kelayakan.py` memeriksa kandidat dari `daftar_40.json`; untuk simbol tertentu, misalnya `python cek_kelayakan.py BTC ETH`. AI bersifat opsional:

```bash
python ai_pemilih.py --tanpa-ai
python penilai_ai.py --jumlah 8
python ai_kelayakan.py --pakai-ai
```

Pemilih/penilai AI tidak wajib untuk pipeline formula-only; pastikan `USE_AI=off` jika ingin menghindari panggilan provider.

### C. Scanner paper

```bash
python scanner.py --sekali
python scanner.py --interval 300
```

`--interval 300` mengulang siklus **paper** tiap 5 menit; ini bukan runner order Demo. Untuk hanya memantau posisi paper tanpa membuka baru, gunakan `--no-buka`.

### D. Paper engine dan simulasi

```bash
python tes_paper_partial.py
python tes_paper_slippage.py
python paper.py --status
python paper.py
python paper.py --loop
```

`paper.py` mengubah `state.json`. Simpan backup sebelum eksperimen; jangan menghapus posisi paper aktif hanya untuk merapikan folder.

### E. Sizing dan preflight

```bash
python tes_bitget_orders.py
python uji_paper_demo.py --once
python uji_paper_demo.py --once --demo-preflight
```

Preflight Demo meminta data order book/funding terkini dan tidak mengirim order. Rencana satu simbol dapat ditinjau dengan:

```bash
python demo_phase7.py BTC LONG ENTRY SL TP NOTIONAL
```

Ganti `ENTRY SL TP NOTIONAL` dengan angka dari setup yang benar-benar sedang ditinjau; jangan menjalankan placeholder tersebut apa adanya.

### 5. Formula signal engine

```bash
python signal_engine.py
```

Membaca kandidat `daftar_40.json`, menulis `signal.json`, dan tidak mengirim order. AI tidak digunakan oleh engine ini.

### 6. Evaluasi paper dan jurnal

```bash
python tes_phase6.py
python paper_phase6.py --once
python paper_phase6.py --days 14 --interval 300
python paper_metrics.py --journal paper_trades.jsonl --capital 30 --min-trades 30 --min-days 7 --max-dd-pct 25 --slippage-bps-per-side 1
```

Evaluasi 1–2 minggu tetap hanya sampel uji. Gate bawaan laporan memerlukan minimal 30 trade tertutup, 7 hari, expectancy positif dan drawdown maksimum 25%; lolos gate bukan izin untuk Live.

### 7. Bitget Demo

Mulai dengan tes offline dan runner tanpa `--send-demo`:

```bash
python tes_demo_phase7.py
python tes_uji_demo_unified.py
python tes_reset_demo_data.py
python uji_demo_unified.py --once
```

Lihat [Langkah uji Demo](#langkah-uji-demo-phase-7) sebelum mengirim order. Jangan gunakan `--send` atau `--send-demo` sebelum uji sandbox manual, rekonsiliasi, post-only, partial fill, TP/SL, cancel, timeout/restart, dan time-exit dinyatakan lulus.

## Langkah uji Demo (Phase 7)

Gunakan akun dan API key **Bitget Demo khusus**. Jangan gunakan key Live. Pemeriksaan kosong atas open orders/positions tidak membuktikan bahwa submit lama telah ditolak; periksa juga order history dan client order ID.

### 1. Pastikan state lama sudah direkonsiliasi

Hentikan runner dan periksa posisi, open orders, order history, serta status client ID yang tersimpan di `demo_test_state.json`. Jika ada `submission_uncertain`, jangan menjalankan loop baru dan jangan menghapus/reset state sampai statusnya jelas.

### 2. Siapkan konfigurasi Demo

```dotenv
MODE=demo
DRY_RUN=off
DEMO_API=on
DEMO_CONFIRM=UJI_DEMO_SAYA_PAHAM
DEMO_LOOP_EXECUTION_VERIFIED=off
BITGET_API_KEY=<Demo API key>
BITGET_SECRET_KEY=<Demo secret>
BITGET_PASSPHRASE=<Demo passphrase>
```

Isi placeholder secara lokal di `.env`, bukan di terminal yang direkam, source code, atau README. Izin API cukup baca/trade; withdraw harus nonaktif.

### 3. Jalankan tes offline dan pipeline prasyarat

```bash
python tes_demo_phase7.py
python tes_uji_demo_unified.py
python tes_paper_partial.py
python tes_paper_slippage.py
python tes_phase6.py
python cek_koneksi.py
python penyaring.py
python cek_risk_universe.py
python cek_kelayakan.py
python signal_engine.py
```

Tes offline tidak mengirim order. Periksa `signal.json` dan hasil kelayakan secara manual.

### 4. Periksa preflight tanpa mengirim

```bash
python uji_paper_demo.py --once --demo-preflight
```

Periksa nilai net bps, fee asumsi, funding, spread, depth, umur order book, contract size, jumlah kontrak, serta geometri TP/SL. Setup ditolak bila data order book/funding tidak tersedia, spread/depth melewati batas, atau net di bawah `DEMO_MIN_NET_BPS`.

### 5. Uji order secara manual di Sandbox

Sebelum satu order kecil sekalipun, verifikasi dokumentasi UTA v3 dan hasil request/response di akun Demo. Adapter meminta `postOnly`; pemetaan lokal CCXT bukan bukti bahwa bursa menerima atau menolak order marketable dengan perilaku yang benar.

Jika operator sudah siap untuk tes tersebut, gunakan setup terverifikasi dan `--send`:

```bash
python demo_phase7.py BTC LONG ENTRY SL TP NOTIONAL --send
```

Ganti semua placeholder dengan nilai setup aktual. Periksa exchange order ID, maker-only, jumlah/fill parsial, harga rata-rata, fee, TP/SL, cancel, restart, dan funding. Jika status submit tidak pasti, hentikan runner dan rekonsiliasi manual; jangan retry.

### 6. Jalankan loop Demo hanya setelah validasi

Hanya setelah semua tes manual di atas selesai, ubah `DEMO_LOOP_EXECUTION_VERIFIED=on` pada `.env`:

```bash
python uji_demo_unified.py --days 14 --interval 300 --send-demo
```

Runner merekonsiliasi exchange sebelum pipeline dan entry. Ia memindai tiap 5 menit; setelah 6 jam idle tanpa posisi terisi, pipeline dapat diulang jika order pending yang terlacak sudah dibatalkan dan dikonfirmasi. Posisi yang melewati `DEMO_MAX_HOLD_HOURS` ditutup dengan market reduce-only sejak waktu fill pertama. Order/fee/funding yang belum jelas memblokir entry baru. `Ctrl+C` hanya menghentikan proses, bukan bukti order/posisi sudah selesai.

### 7. Reset data eksperimen Demo

Reset hanya setelah runner dihentikan dan posisi, open orders, serta riwayat order Demo sudah diverifikasi bersih secara manual:

```bash
python tes_reset_demo_data.py
python reset_demo_data.py --confirm RESET_DEMO_BERSIH
```

Tool menolak bila API gagal atau masih ada posisi/open order. Jika lolos, tool membuat backup di `demo_backups/<timestamp>/`, menginisialisasi ulang hanya `demo_test_state.json`, dan mempertahankan `demo_test_trades.jsonl`. Jangan menghapus file state secara manual untuk mengatasi status order yang belum pasti.

## Struktur file

| Tahap/kategori | File penting | Peran |
|---|---|---|
| Konfigurasi | `config.py`, `env.example`, `.env` | Pengaturan; `.env` lokal dan rahasia, jangan commit. |
| 1 / A | `cek_koneksi.py`, `risk.py`, `universe.py`, `penyaring.py`, `cek_risk_universe.py`, `watchlist.json` | Koneksi, risk gate, universe, dan penyaringan. |
| B / 5 | `data_pasar.py`, `indikator.py`, `cek_kelayakan.py`, `signal_engine.py` | Data pasar, indikator, filter setup, dan sinyal formula. |
| C / D | `scanner.py`, `paper.py`, `state.py` | Scanner dan paper state; tidak mengirim order exchange. |
| E | `bitget_orders.py`, `uji_paper_demo.py` | Sizing dan preflight tanpa submit. |
| 6 | `paper_phase6.py`, `paper_journal.py`, `paper_metrics.py` | Runner, jurnal append-only, dan metrik paper. |
| 7 | `demo_phase7.py`, `trade_costs.py`, `uji_demo_unified.py`, `reset_demo_data.py`, `PHASE7.md` | Adapter, biaya/pasar, lifecycle Demo, reset aman, dan checklist. |
| Tes | `tes_*.py` | Tes offline dan pemeriksaan per fase. |
| Eksperimen lama | `tidak_terpakai/` | Skrip/JSON legacy yang dipilih sudah dihapus; folder dapat tetap ada dalam keadaan kosong. |

### File JSON dan jurnal eksperimen

Jangan pindahkan file yang dibaca skrip tanpa sekaligus memperbarui path kode dan tes.

| File | Kategori | Perlakuan |
|---|---|---|
| `watchlist.json` | Input konfigurasi | Pertahankan; dipakai penyaring/universe. |
| `daftar_40.json`, `daftar_ai.json`, `signal.json`, `penilai_ai.json` | Output turunan | Dapat dibuat ulang melalui pipeline; `.gitignore` agar tidak bercampur dengan source. |
| `ai_pemakaian.json`, `log_penilai.jsonl` | Penggunaan/jurnal AI | Data runtime; arsipkan bila diperlukan untuk eksperimen. |
| `state.json` | State paper | Jangan hapus saat ada posisi paper aktif. |
| `paper_trades.jsonl` | Jurnal audit paper | Append-only; backup sebelum eksperimen baru, jangan edit selama evaluasi. |
| `demo_test_state.json` | State lifecycle Demo | Pertahankan sampai semua client order ID dan status exchange tuntas. |
| `demo_test_trades.jsonl` | Jurnal audit Demo | Pertahankan; reset Demo tidak menghapus jurnal ini. |
| Output eksperimen di `tidak_terpakai/` | File legacy | Skrip dan tiga output JSON yang disetujui sudah dihapus; output baru tidak dibuat karena skrip eksperimennya sudah tidak ada. |

File runtime yang tercantum di `.gitignore` tetap berada di komputer; aturan ignore hanya mencegahnya ikut commit baru. File legacy yang dihapus: enam skrip dan tiga JSON di folder `tidak_terpakai/`; file state/jurnal eksperimen aktif tidak disentuh.

## Prinsip operasional

- `.env` tidak boleh dibagikan atau dimasukkan ke repository.
- API key tidak boleh memiliki izin withdraw.
- Verifikasi exchange sebelum restart; order pending/posisi dapat tetap aktif setelah proses dihentikan.
- Simpan backup jurnal paper dan state sebelum eksperimen baru.
- Jangan memakai hasil paper/Demo sebagai jaminan hasil Live; pengiriman Live belum diimplementasikan.
