# Bot-Tree

Bot sinyal dan eksperimen trading futures USDT Bitget UTA. Strategi utama: **Trend + Range Grid (ATR Arithmetic)** — klasifikasi bullish / bearish / sideways, grid otomatis berbasis ATR, dan filter Net RR setelah fee.

> **Status:** gunakan paper dan Demo saja. Eksekusi Live belum tersedia. Belum ada bukti bahwa strategi menghasilkan edge setelah biaya dan slippage; hasil uji singkat bukan jaminan keuntungan atau nasihat keuangan.

## Fitur bot

- Penyaring universe berdasarkan volume, watchlist, blacklist, dan batas perubahan harga.
- Klasifikasi tren sederhana: **bullish**, **bearish**, **sideways** (struktur HH/HL + EMA 9/21 + ADX).
- Sideways boleh masuk jika range `(HH−HL) ≥ RANGE_MIN_ATR × ATR`.
- Grid otomatis deret aritmatika: jarak level = `GRID_SPACING_ATR × ATR`.
- TP di struktur (HH untuk long, HL untuk short); SL di luar HL/HH = `SL_BUFFER_ATR × ATR`.
- Syarat masuk memakai **Net RR setelah fee** (`FEE_ROUNDTRIP_PCT`, `RR_MIN`).
- Risk gate: batas posisi terbuka, rugi harian, rugi beruntun, kill switch, risk ATR.
- Scanner berulang untuk **paper**; scanner tidak mengirim order exchange.
- Simulasi paper dengan trade-through, partial fill, slippage, fee estimasi, TP/SL, dan state.
- Signal engine formula-only; AI opsional (tidak menentukan sinyal engine).
- Preflight / rekonsiliasi Demo, time-exit, dan reset state dengan backup.

## Strategi (ringkas)

| Kondisi | Syarat | Aksi |
|---|---|---|
| Bullish | HH+HL + EMA9>EMA21 + ADX ≥ `ADX_TREND_MIN` | Long grid (beli di bawah harga) |
| Bearish | LH+LL + EMA9<EMA21 + ADX ≥ `ADX_TREND_MIN` | Short grid (jual di atas harga) |
| Sideways | ADX lemah / struktur tidak jelas | Range grid **hanya jika** range ≥ `RANGE_MIN_ATR` × ATR |

Keluar jika: tembus struktur (HL/HH), kena TP, time exit (`MAX_HOLD_HOURS`), atau candle ekstrem melawan arah.

## Struktur folder

```text
Bot-Tree/
├── config.py              # baca semua parameter dari .env
├── env.example            # contoh konfigurasi (salin ke .env)
├── indikator.py           # klasifikasi tren + grid ATR
├── penilai_ai.py          # rencana TP/SL, gate, snapshot
├── signal_engine.py       # pipeline → signal.json
├── penyaring.py           # universe → daftar_40.json
├── universe.py            # helper daftar_40 / watchlist
├── data_pasar.py          # candle & exchange publik
├── paper.py               # simulasi paper
├── scanner.py             # siklus paper berulang
├── state.py / state.json  # state bot
├── risk.py                # risk gate
├── bitget_orders.py       # sizing / order helper Bitget
├── trade_costs.py         # fee & biaya
├── cek_koneksi.py         # tes koneksi (tanpa order)
├── dashboard_server.py    # dashboard web (opsional)
├── watchlist.json
├── requirements.txt
├── docs/phases/           # dokumentasi tahap lama (arsip)
├── archive/
│   ├── tests/             # skrip tes lama (tidak dihapus)
│   ├── scripts/           # skrip eksperimen / fase lama
│   └── data_samples/      # sample JSON / log lama
└── Website/               # materi web tambahan
```

File di `archive/` dan `docs/phases/` **tidak dihapus** — hanya dipisah agar root tetap bersih.

## Tahap pengembangan

| Urutan | Tahap | Cakupan dan status |
|---|---|---|
| 1 | Koneksi | Pemeriksaan ticker publik dan koneksi/saldo Bitget; tidak membuat order. |
| A | Risk dan universe | Risk gate, watchlist, blacklist, volume dan ukuran posisi. |
| B | Sinyal teknikal | Trend/range, ADX, grid ATR, TP/SL struktur, Net RR setelah fee. |
| C | Scanner | Siklus paper berulang; bukan loop order Demo. |
| D | Paper | Simulasi fill/partial/slippage/fee dan state. |
| E | Sizing dan preflight | Minimum order, precision, geometri TP/SL dan batas notional. |
| 5 | Signal engine | Pipeline formula-only → `signal.json`. |
| 6 | Evaluasi paper | Jurnal, metrik, drawdown; perlu observasi yang cukup. |
| 7 | Bitget Demo | Filter biaya/pasar, post-only, rekonsiliasi dan time-exit. |

## Yang sudah ada

- Strategi Trend + Range Grid (ATR arithmetic) dengan parameter penuh di `.env`.
- Konfigurasi terpusat di `config.py` dan contoh di `env.example`.
- Pipeline: `penyaring.py` → `signal_engine.py` → paper/scanner.
- Fondasi Demo (sizing, fee assumption, state, risk gate).
- Arsip file lama di `archive/` dan `docs/phases/` (tidak dihapus).

## Yang belum ada

- Verifikasi end-to-end order Demo (TP/SL, partial, cancel, funding) di akun UTA.
- Bukti statistik edge setelah fee dari paper yang cukup panjang.
- Eksekusi Live; jangan pakai `MODE=live` untuk mengirim order uang asli.
- Dashboard sebagai panduan operasional resmi.

## Persyaratan

- Python 3.10 atau lebih baru.
- Paket di `requirements.txt`: `ccxt`, `python-dotenv`, `pandas`, dan `requests`.
- Windows 10/11 dengan Command Prompt, atau Termux Android.
- Koneksi internet untuk data pasar dan API Bitget.
- Akun Bitget UTA. Untuk uji privat pakai **Demo API Key** (baca + trade saja; jangan aktifkan withdraw).
- Jangan menaruh API key di source code, README, atau file JSON hasil eksperimen.

## Instalasi

### Windows — Command Prompt (CMD)

```bat
cd /d "D:\Projek Aplikasi Ipeh\Bot Tree"
py -3.12 -m venv venv
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
copy env.example .env
notepad .env
```

### Android — Termux

```bash
pkg update && pkg upgrade -y
pkg install python git nano python-cryptography -y
cd ~
# git clone https://github.com/Kukuhflaren/Bot-Tree.git
cd Bot-Tree
python -m venv --system-site-packages venv
source venv/bin/activate
pip install --no-deps ccxt
pip install python-dotenv certifi requests aiohttp yarl typing_extensions
cp env.example .env
nano .env
termux-wake-lock
```

Verifikasi:

```bash
python -c "import ccxt, requests, dotenv; print('dependensi OK')"
```

## Konfigurasi penting `.env`

Salin dari `env.example`. Nilai di bawah adalah default eksperimen strategi baru.

| Kelompok | Variabel | Default / keterangan |
|---|---|---|
| Mode | `MODE` | `paper` atau `demo` (Live belum siap) |
| Timeframe | `CANDLE_TIMEFRAME` | `5m` |
| Modal | `MODAL_DEMO_USDT`, `MODAL_LIVE_USDT` | `40` |
| Leverage | `LEVERAGE` | `4` |
| Risk | `RISK_PER_SETUP_PCT` | `2.5` (% modal per setup) |
| Tren | `ADX_TREND_MIN`, `ADX_SIDEWAYS_MAX` | `18` |
| Sideways | `RANGE_MIN_ATR` | `3.0` (minimal lebar range × ATR) |
| Grid | `GRID_SPACING_ATR`, `GRID_MAX_LEVELS` | `0.45`, `6` |
| SL | `SL_BUFFER_ATR` | `0.35` |
| Fee & RR | `FEE_ROUNDTRIP_PCT`, `RR_MIN` | `0.12`, `1.1` (Net RR) |
| Hold | `MAX_HOLD_HOURS` | `3` |
| Universe | `PENYARING_VOL_MIN_USDT`, `WATCHLIST_MODE` | volume min & mode watchlist |
| Pengaman | `MAX_OPEN_TOKENS`, `MAX_DAILY_LOSS_USDT`, `KILL_SWITCH` | batas risiko |
| Demo | `DEMO_API`, `DEMO_CONFIRM`, `DRY_RUN` | gate pengiriman Demo |

## Perintah utama

Jalankan dari folder project dengan venv aktif.

### 1. Koneksi

```bash
python cek_koneksi.py
```

### A. Universe

```bash
python penyaring.py
```

Menghasilkan / memperbarui `daftar_40.json`.

### B. Sinyal (strategi baru)

```bash
python signal_engine.py
```

Membaca `daftar_40.json`, menganalisis candle `CANDLE_TIMEFRAME`, menulis `signal.json`.

### C. Scanner paper

```bash
python scanner.py --sekali
python scanner.py --interval 300
```

### D. Paper

```bash
python paper.py --status
python paper.py
python paper.py --loop
```

### Demo (hati-hati)

Pastikan `MODE=demo`, kredensial Demo terisi, dan gate di `.env` sudah sesuai sebelum mengirim order. Jangan pakai kunci Live.

## File arsip

| Lokasi | Isi |
|---|---|
| `docs/phases/` | Dokumentasi fase lama (FASE_A, PHASE6, PHASE7, roadmap) |
| `archive/tests/` | Skrip `tes_*.py` lama |
| `archive/scripts/` | AI selector lama, uji demo unified, reset demo, dll. |
| `archive/data_samples/` | Sample JSON/log eksperimen lama |

Semua file di arsip **masih ada** dan bisa dipindah kembali ke root bila dibutuhkan.

## Peringatan

- Ini eksperimen, bukan nasihat keuangan.
- Paper ≠ eksekusi exchange; Demo ≠ Live.
- Fee, funding, dan slippage dapat menghapus edge yang terlihat di backtest singkat.
- Jangan commit file `.env` atau kunci API.
