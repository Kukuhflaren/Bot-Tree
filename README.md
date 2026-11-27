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
├── cek_risk_universe.py   # cek risk + universe
├── demo_phase7.py         # uji order Demo satu setup
├── uji_paper_demo.py      # preflight paper/demo
├── uji_demo_unified.py    # loop Demo terpadu
├── reset_demo_data.py     # reset state Demo (aman)
├── dashboard_server.py    # dashboard web (opsional)
├── watchlist.json
├── requirements.txt
├── docs/phases/           # dokumentasi tahap lama
├── archive/               # tes & skrip lama (tidak dihapus)
└── Website/
```

## Persyaratan

- Python 3.10 atau lebih baru.
- Paket di `requirements.txt`: `ccxt`, `python-dotenv`, `pandas`, `requests`.
- Windows 10/11 (CMD) atau Termux Android.
- Akun Bitget **UTA Demo** — API key dengan izin baca + trade saja (jangan aktifkan withdraw).
- Jangan menaruh API key di source code atau commit `.env`.

## Instalasi

### Windows (CMD)

```bat
cd /d "D:\Projek Aplikasi Ipeh\Bot Tree"
py -3.12 -m venv venv
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
copy env.example .env
notepad .env
```

### Termux (Android)

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

## Konfigurasi `.env` (strategi baru)

Salin dari `env.example`. Parameter penting:

| Kelompok | Variabel | Default |
|---|---|---|
| Mode | `MODE` | `demo` atau `paper` |
| Timeframe | `CANDLE_TIMEFRAME` | `5m` |
| Modal | `MODAL_DEMO_USDT` | `40` |
| Leverage | `LEVERAGE` | `4` |
| Risk | `RISK_PER_SETUP_PCT` | `2.5` |
| Tren | `ADX_TREND_MIN` | `18` |
| Sideways | `RANGE_MIN_ATR` | `3.0` |
| Grid | `GRID_SPACING_ATR`, `GRID_MAX_LEVELS` | `0.45`, `6` |
| SL | `SL_BUFFER_ATR` | `0.35` |
| Fee & RR | `FEE_ROUNDTRIP_PCT`, `RR_MIN` | `0.12`, `1.1` |
| Hold | `MAX_HOLD_HOURS` | `3` |

---

## Langkah menjalankan (Paper → Demo)

Jalankan dari folder project dengan **venv aktif**.

### Langkah 0 — Siapkan `.env`

Isi kredensial **Demo** saja (bukan Live):

```dotenv
MODE=demo
DRY_RUN=off
DEMO_API=on
DEMO_CONFIRM=UJI_DEMO_SAYA_PAHAM
DEMO_LOOP_EXECUTION_VERIFIED=off
BITGET_API_KEY=<Demo API key>
BITGET_SECRET_KEY=<Demo secret>
BITGET_PASSPHRASE=<Demo passphrase>
BITGET_UTA=on
CANDLE_TIMEFRAME=5m
```

`DEMO_LOOP_EXECUTION_VERIFIED` biarkan `off` sampai uji manual order selesai.

---

### Langkah 1 — Cek koneksi

Memeriksa ticker publik dan saldo (jika key terisi). **Tidak mengirim order.**

```bash
python cek_koneksi.py
```

---

### Langkah 2 — Saring universe

Membuat / memperbarui `daftar_40.json` dari volume, watchlist, dan filter.

```bash
python penyaring.py
```

Opsional — cek risk & keanggotaan universe:

```bash
python cek_risk_universe.py
```

---

### Langkah 3 — Generate sinyal (strategi Trend + Range Grid)

Membaca `daftar_40.json`, menganalisis candle, menulis `signal.json`.

```bash
python signal_engine.py
```

Periksa hasil:

```bash
python -c "import json; s=json.load(open('signal.json')); print('bot_ready:', s.get('bot_ready_count')); print('reject:', s.get('rejection_counts'))"
```

Jika `bot_ready_count` masih 0, longgarkan sedikit di `.env` (mis. `ADX_TREND_MIN=15`, `RANGE_MIN_ATR=2.5`, `SCORE_MIN=35`) lalu ulangi langkah 3.

---

### Langkah 4 — Paper (simulasi lokal, tanpa order exchange)

```bash
python paper.py --status
python paper.py
python paper.py --loop
python scanner.py --sekali
python scanner.py --interval 300
```

---

### Langkah 5 — Preflight Demo (tanpa mengirim order)

Memeriksa fee, spread, depth, net bps, geometri TP/SL.

```bash
python uji_paper_demo.py --once --demo-preflight
```

Pastikan tidak ada penolakan kritis (spread terlalu lebar, depth kurang, net di bawah `DEMO_MIN_NET_BPS`).

---

### Langkah 6 — Uji satu order Demo secara manual

Hanya setelah langkah 1–5 aman. Ganti placeholder dengan angka setup nyata dari `signal.json`:

```bash
python demo_phase7.py BTC LONG ENTRY SL TP NOTIONAL --send
```

Contoh konsep (jangan copy angka sembarangan):

```bash
python demo_phase7.py BTC LONG 95000 94500 96000 20 --send
```

Periksa di Bitget Demo: order ID, fill/partial, fee, TP/SL, cancel bila perlu.

Jika status submit tidak jelas → **hentikan**, rekonsiliasi manual, jangan retry buta.

---

### Langkah 7 — Loop Demo (setelah uji manual lulus)

1. Ubah di `.env`:

```dotenv
DEMO_LOOP_EXECUTION_VERIFIED=on
```

2. Jalankan loop:

```bash
python uji_demo_unified.py --days 14 --interval 300 --send-demo
```

Tanpa mengirim order:

```bash
python uji_demo_unified.py --once
```

`Ctrl+C` hanya menghentikan proses lokal — order/posisi di exchange bisa tetap aktif.

---

### Langkah 8 — Reset data Demo (opsional)

Hanya jika runner sudah berhenti dan akun Demo bersih:

```bash
python reset_demo_data.py --confirm RESET_DEMO_BERSIH
```

Tool membuat backup di `demo_backups/` sebelum mereset state.

---

## Ringkasan perintah cepat

| Tujuan | Perintah |
|---|---|
| Koneksi | `python cek_koneksi.py` |
| Universe | `python penyaring.py` |
| Sinyal | `python signal_engine.py` |
| Paper sekali | `python paper.py` |
| Scanner | `python scanner.py --interval 300` |
| Preflight Demo | `python uji_paper_demo.py --once --demo-preflight` |
| Order Demo 1 setup | `python demo_phase7.py SYMBOL SIDE ENTRY SL TP NOTIONAL --send` |
| Loop Demo | `python uji_demo_unified.py --days 14 --interval 300 --send-demo` |
| Reset Demo | `python reset_demo_data.py --confirm RESET_DEMO_BERSIH` |

## File arsip

| Lokasi | Isi |
|---|---|
| `docs/phases/` | Dokumentasi fase lama |
| `archive/tests/` | Skrip `tes_*.py` lama |
| `archive/scripts/` | AI selector lama & skrip eksperimen |
| `archive/data_samples/` | Sample JSON / log lama |

File di arsip **tidak dihapus**.

## Peringatan

- Ini eksperimen, bukan nasihat keuangan.
- Paper ≠ eksekusi exchange; Demo ≠ Live.
- Fee, funding, dan slippage dapat menghapus edge yang terlihat di uji singkat.
- Jangan commit file `.env` atau kunci API.
- Jangan aktifkan izin withdraw pada API key.
