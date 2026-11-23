# Bot-Tree

Bot sinyal dan eksekusi bertahap untuk **futures USDT di Bitget (akun UTA)**. Bot memilih token, menilai setup teknikal dari candle asli, merencanakan grid limit lengkap dengan TP/SL, dan membatasi risiko lewat aturan tertulis.

> **STATUS: pengembangan bertahap.** Fase 5–7 sudah memiliki fondasi kode, tetapi order nyata tetap tidak boleh dijalankan tanpa paper trading, verifikasi demo, dan review manual. Jangan menjalankan modal asli sebelum ada bukti positif setelah fee dan slippage.
>
> Ini bukan nasihat keuangan dan tidak ada jaminan keuntungan.

## Tujuan

Trading tanpa melibatkan perasaan: entry, exit, dan risiko ditentukan rumus. Setiap tahap harus diuji—paper, demo, lalu live dalam modal kecil—sebelum beralih ke tahap berikutnya.

## Status fase

| Fase | Isi | Status |
|---|---|---|
| A | Risk gate, universe, watchlist, blacklist | Siap |
| B | Entry/SL/TP tertulis dan konfirmasi 30m | Siap |
| C | Scanner continuous | Siap |
| D | Paper engine: fill, partial, slippage, fee, state | Siap |
| E | Sizing/perhitungan minimum dan rencana order | Fondasi selesai; pengiriman exchange sengaja dinonaktifkan |
| 5 | Signal engine, AI default off, skor dan zona | Siap |
| 6 | Journal tahan lama, metrik paper dan safety stop | Implementasi ada; butuh run 1–2 minggu |
| 7 | Preflight dan adapter Bitget Demo UTA v3 | Fondasi ada; Demo API dan uji skema/TP/SL wajib |
| 8 | Safeguard modal asli | Belum diimplementasikan |
| 9 | Modal riil bertahap dan kriteria stop/scale | Belum diimplementasikan |
| 10 | Dashboard lokal, rTokens, AI second opinion terukur | Dashboard baca-saja tersedia; rTokens dan evaluasi AI belum |

Detail status terbaru tersedia di `FASE_STATUS.md`.

## Yang sudah ada

- Koneksi Bitget UTA dan pembacaan saldo
- Candle 5m/30m, EMA, RSI, MACD, SAR, ATR, VWAP, S/R, dan konfirmasi tren
- Penyaring token dengan universe, blacklist, dan watchlist
- Pemilih AI opsional dengan cadangan rumus
- Penilai AI sebagai second opinion (tidak mengendalikan keputusan)
- Modul risk, kill switch, batas rugi harian, dan rugi beruntun
- State management melalui `state.py` dan `state.json`
- Paper trading engine dengan grid, partial fill, slippage, fee, TP/SL
- Phase 5 `signal_engine.py` yang menghasilkan `signal.json`; `USE_AI=off`
- Phase 6 journal `paper_trades.jsonl`, runner, metrik dan gate evaluasi
- Phase 7 preflight dan adapter demo yang mengunci konfigurasi sebelum pengiriman
- Unit test untuk sizing, paper fill, Phase 6, dan preflight Demo

## Yang belum ada

- Verifikasi lapangan skema UTA v3 dan respons TP/SL Bitget
- Eksekusi Demo yang terverifikasi end-to-end
- Safeguard khusus modal asli dan roll-out bertahap
- Dukungan rToken/jam pasar dan bukti empiris edge AI
- Bukti empiris bahwa AI veto memberikan edge tambahan

## Persyaratan

- Python 3.10+
- Paket: `ccxt`, `python-dotenv`, `requests`, `pandas`
- Windows 10+ atau lingkungan Python yang sesuai
- Akun Bitget UTA
- API key memiliki izin Trade/Read & Write yang dibutuhkan; jangan aktifkan Withdraw
- Untuk uji, gunakan **Demo API Key**, bukan live key

## Instalasi

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy env.example .env
```

Isi `.env`, jangan pernah meng-commit API key atau rahasia.

## Konfigurasi penting `.env`

| Kelompok | Pengaturan |
|---|---|
| Mode | `MODE=paper`, `demo`, atau `live`; live wajib `LIVE_CONFIRM=SAYA_PAHAM_RISIKONYA` |
| Bitget | `BITGET_API_KEY`, `BITGET_SECRET_KEY`, `BITGET_PASSPHRASE`, `BITGET_UTA=on` |
| Demo | `DEMO_API=on`, `DEMO_CONFIRM=UJI_DEMO_SAYA_PAHAM`, `DRY_RUN=off`; loop otomatis juga memerlukan `DEMO_LOOP_EXECUTION_VERIFIED=on` setelah validasi manual |
| AI | `USE_AI=off` default; `--pakai-ai` untuk mengaktifkan satu kali jalan, `--tanpa-ai` untuk menonaktifkan |
| Modal | `MODAL_DEMO_USDT`, `MODAL_LIVE_USDT`, `LEVERAGE`, `RISK_PER_SETUP_PCT` |
| Candle | `CANDLE_TIMEFRAME=5m|15m|30m` untuk analisis dan pemantauan bot |
| Strategi | `TP_MODE`, `TP_PERCENT`, `TP_METHOD=sr|atr`, `TP_ATR_PERCENT`, `SL_METHOD=sr|atr`, `SL_ATR_PERCENT`, `SL_POINTS`, `SL_BUFFER_ATR`, `RR_MIN`, `RISK_ATR_MIN`, `RISK_ATR_MAX` |
| Sinyal | `SCORE_MIN`, `NEAR_MODE`, `NEAR_ATR_MULT`, `NEAR_SR_PERCENT` |
| Pengaman | `DRY_RUN`, `KILL_SWITCH`, `MAX_OPEN_TOKENS`, `MAX_DAILY_LOSS_USDT`, `MAX_CONSECUTIVE_LOSSES` |
| Universe | `WATCHLIST_MODE`, `WATCHLIST_FILE`, `TOKEN_BLACKLIST`, batas volume dan jumlah per sisi |

## Perintah utama

```bash
python cek_koneksi.py

# Sinyal dan analisis
python penyaring.py
python tes_indikator.py
python signal_engine.py          # membaca langsung daftar_40.json, menulis signal.json

# Verifikasi fondasi
python cek_risk_universe.py
python ai_kelayakan.py
python ai_kelayakan.py --pakai-ai
python cek_kelayakan.py          # semua token daftar_40.json; watchlist di urutan pertama
python cek_kelayakan.py BTC ETH  # hanya token yang ditentukan

# AI opsional; formula tetap menjadi penentu kelayakan
python ai_pemilih.py             # tanpa AI secara default
python penilai_ai.py --jumlah 8  # analisis bot tanpa AI secara default

# Paper trading
python tes_paper_partial.py
python tes_paper_slippage.py
python paper.py --status
python paper.py
python paper.py --loop
python scanner.py --sekali
python scanner.py --interval 300 # scanner paper saja; bukan loop order Demo

# Phase 6 paper evaluation
python tes_phase6.py
python paper_phase6.py --once
python paper_phase6.py --days 14 --interval 300
python paper_metrics.py --journal paper_trades.jsonl --capital 30 --min-trades 30 --min-days 7 --max-dd-pct 25

# Untuk urutan uji Demo Phase 7, ikuti bagian "Langkah uji Demo" di bawah
```

`ai_pemilih.py` menampilkan kolom penyaring (`Ubah24j`, volume, `RasioVol`, `Skor`, `W`). AI tidak dipanggil kecuali diaktifkan. Paper trading, signal engine, dan tes indikator mengambil universe langsung dari daftar bullish/bearish di `daftar_40.json`; output `daftar_ai.json` dan `penilai_ai.json` bukan sumber kandidat paper.

Nilai entry/SL/TP, contract size, minimum notional, dan harga harus berasal dari setup bot serta market metadata bursa. Contoh pada langkah uji Demo di bawah hanya menunjukkan format perintah.

## Dashboard lokal

Dashboard hanya membaca file bot dan tidak mengirim order atau mengakses exchange:

```bash
python dashboard_server.py --buka
```

Buka `http://127.0.0.1:8765` jika browser tidak terbuka otomatis. 
Halaman memperbarui data setiap 3 detik melalui server lokal, menggunakan `signal.json`, `penilai_ai.json`, `state.json`, dan bila tersedia `paper_trades.jsonl`. Default server hanya mendengarkan `127.0.0.1`; jangan ubah `--host` ke alamat publik. Untuk port berbeda, gunakan `--port 9000`.

### Menampilkan dashboard dari GitHub Pages

GitHub Pages hanya menyimpan file statis dan tidak dapat membuka file atau port tablet secara langsung. Jalankan server dashboard di Termux, lalu buat tunnel HTTPS dari tablet ke port 8765.

```bash
# Di Termux
pkg update
pkg install python
termux-wake-lock
python dashboard_server.py --host 0.0.0.0 --port 8765 \
  --cors-origin https://Kukuhflaren.github.io
```

Jalankan tunnel di sesi Termux kedua. Contoh dengan Cloudflare Tunnel:

```bash
cloudflared tunnel --url http://127.0.0.1:8765
```

Salin URL `https://...trycloudflare.com` yang dicetak Cloudflare, lalu buka halaman GitHub Pages dengan parameter API:

```text
https://kukuhflaren.github.io/REPO/bot-tree-dashboard.html?api=https://...trycloudflare.com
```

Gunakan origin GitHub Pages tepat seperti `https://kukuhflaren.github.io`; `/REPO` tidak termasuk origin. Parameter `api` disimpan di browser. URL tunnel biasanya berubah setelah tunnel direstart.

Server tetap hanya membaca `state.json`, `signal.json`, `penilai_ai.json`, dan jurnal. Server tidak melayani `.env`, tidak mengirim order, dan tidak mengakses exchange. Jangan gunakan `--allow-all-cors` untuk penggunaan publik. Hentikan tunnel ketika tidak digunakan.

### Menjalankan bot dari dashboard

Server kontrol hanya menerima daftar aksi yang ditentukan. Perintah shell bebas tidak diterima.

```bash
# Generate token otomatis dan tampilkan di terminal
python dashboard_server.py --host 0.0.0.0 --port 8765 \
  --cors-origin https://Kukuhflaren.github.io

# Atau gunakan nilai rahasia dari .env
# BOT_CONTROL_TOKEN, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
```

Masukkan `BOT_CONTROL_TOKEN` pada panel Kontrol Bot di dashboard. Tombol aman dapat menjalankan satu putaran, scanner, paper engine, pembaruan penyaring, pembuatan `signal.json`, refresh penilai, dan pemeriksaan kelayakan.

Pilihan candle 5 menit, 15 menit, atau 30 menit tersedia di panel Kontrol Bot. Pilihan disimpan lokal sebagai `dashboard_config.json`, dikirim sebagai variabel proses `CANDLE_TIMEFRAME`, dan dipakai oleh penyaringan sinyal, penilai AI, signal engine, serta pemantauan paper. Scanner yang sedang berjalan perlu dihentikan dan dimulai ulang agar memakai candle baru.

Dashboard menampilkan token dari `daftar_40.json`, beserta harga terakhir, perubahan 24 jam, arah bullish/bearish, dan skor bot dari `penilai_ai.json`. Titik skor memakai warna: ungu 100–86, hijau 85–60, kuning 59–40, dan merah 39–0. Token watchlist ditandai `★`.

Eksekusi Live belum tersedia. Jangan gunakan tombol Live dashboard sebagai pengiriman order; fase safeguard dan rollout Live belum diimplementasikan.

TP dan SL dapat dipilih terpisah:

- **TP Support/Resistance** memakai level S/R lawan atau mode struktur yang sudah dikonfigurasi.
- **TP Persentase ATR** memakai jarak `TP_ATR_PERCENT / 100 × ATR` dari entry.
- **SL Support/Resistance** memakai garis HH untuk bearish atau HL untuk bullish.
- **SL Persentase ATR** memakai jarak `SL_ATR_PERCENT / 100 × ATR` di luar HL/HH.

Contoh: TP 100% ATR berarti jarak target satu ATR; SL 50% ATR berarti setengah ATR. Aturan RR dan batas risk ATR tetap memvalidasi setiap titik grid.

## Langkah uji Demo (Phase 7)

Ikuti urutan ini. Gunakan akun dan API key **Bitget Demo khusus**, bukan API key Live. Fase 7 belum membuktikan bahwa skema UTA v3 dan TP/SL bekerja di akun Anda.

### 1. Pastikan paper siap dan siapkan konfigurasi Demo

Selesaikan pengamatan paper terlebih dahulu (disarankan 1–2 minggu), tinjau metrik dan batas risikonya. Salin `env.example` menjadi `.env`, lalu isi konfigurasi berikut menggunakan kredensial Demo:

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

Jangan isi `DEMO_LOOP_EXECUTION_VERIFIED=on` dulu. API key cukup memiliki izin baca dan trade; jangan aktifkan izin withdraw.

### 2. Jalankan pemeriksaan lokal tanpa order

Dari folder `Bot Tree`, jalankan:

```bash
python tes_demo_phase7.py
python tes_uji_demo_unified.py
python tes_paper_partial.py
python tes_paper_slippage.py
```

Tes ini tidak mengirim order. Jika ada yang gagal, perbaiki dulu sebelum melanjutkan.

### 3. Verifikasi koneksi dan buat sinyal terbaru

```bash
python cek_koneksi.py
python penyaring.py
python cek_risk_universe.py
python cek_kelayakan.py
python signal_engine.py
```

Pastikan koneksi/saldo terbaca, periksa hasil kelayakan, lalu tinjau `signal.json`. AI kelayakan bersifat opsional:

```bash
python ai_kelayakan.py --pakai-ai
```

AI hanya memberi pendapat; gate formula tetap menentukan kelayakan.

### 4. Periksa preflight tanpa mengirim

Jalankan satu siklus paper dan preflight Demo:

```bash
python uji_paper_demo.py --once --demo-preflight
```

Perintah ini tidak mengirim order. Untuk melihat payload satu simbol, gunakan nilai entry, SL, TP, dan notional dari setup yang benar-benar sedang ditinjau:

```bash
python demo_phase7.py BTC LONG 65000 63000 68000 10
```

Angka di atas hanya contoh format—jangan menyalinnya sebagai harga trading. Preflight harus lolos batas minimum, presisi, dan geometri TP/SL.

### 5. Uji satu order Demo secara manual

Lanjutkan hanya setelah memeriksa dokumentasi resmi Bitget UTA v3 dan payload preflight. Jalankan perintah `demo_phase7.py` yang sama dengan langkah sebelumnya, tambahkan `--send`, lalu periksa hasil order di akun Demo. Uji satu order kecil terlebih dahulu; jangan lanjut jika status, jumlah kontrak, TP, atau SL tidak sesuai.

Sebelum mengaktifkan loop otomatis, validasi juga partial/full fill, pembatalan order pending, pemicu TP dan SL, serta rekonsiliasi setelah proses dimulai ulang. Checklist lengkap ada di `PHASE7.md`.

### 6. Jalankan loop Demo setelah semua pemeriksaan lulus

Hanya setelah seluruh validasi manual selesai, ubah `DEMO_LOOP_EXECUTION_VERIFIED=on` di `.env`, lalu mulai loop:

```bash
python uji_demo_unified.py --days 14 --interval 300 --send-demo
```

Runner mengulang pemeriksaan dan pipeline saat mulai, lalu memindai tiap 5 menit. Jika belum ada posisi terisi selama 6 jam, runner membatalkan order entry pending yang terlacak dan mengulang pipeline. Jika posisi sudah terisi, runner menunggu posisi selesai, membatalkan sisa order entry yang terlacak, lalu mencari setup berikutnya. Opsi `--refresh` menyegarkan penyaring dan sinyal pada setiap scan; tanpa opsi itu, pipeline penuh diulang saat mulai dan setelah periode idle.

Pantau `demo_test_state.json`, `demo_test_trades.jsonl`, dan jurnal paper. Jika koneksi atau rekonsiliasi gagal, runner menahan entry baru. **Ctrl+C hanya menghentikan proses; itu bukan bukti bahwa posisi atau order di exchange sudah ditutup/dibatalkan.** Periksa akun Demo sebelum menghentikan atau memulai ulang runner. Jangan gunakan mode Live.

## Struktur file

| File | Fungsi |
|---|---|
| `config.py` / `phase7_config.py` | Konfigurasi mode, risk, AI, dan demo |
| `cek_risk_universe.py` | Verifikasi risk dan universe dengan konfigurasi candle, TP, dan SL terbaru |
| `ai_kelayakan.py` | Cek kelayakan objektif independen; AI opsional tidak mengubah hasil formula |
| `uji_paper_demo.py` | Jalur terpadu aman Paper/Phase 6/preflight Phase 7 |
| `uji_demo_unified.py` | Jalur satu-perintah: scanner, Paper/Phase 6, dan order/monitoring Demo/Phase 7 |
| `data_pasar.py` | Candle dan data pasar publik |
| `indikator.py` | Indikator, skor lima komponen, zona, dan syarat masuk |
| `penyaring.py` / `universe.py` / `watchlist.json` | Universe dan penyaring |
| `risk.py` | Risk gate dan ukuran posisi |
| `ai_pemilih.py` / `penilai_ai.py` | AI pemilih dan second opinion opsional |
| `state.py` | State paper/demo/live |
| `paper.py` | Paper engine grid, fill, fee, dan PnL |
| `signal_engine.py` | Pipeline sinyal Phase 5, output `signal.json` |
| `dashboard_server.py` / `bot-tree-dashboard.html` | Dashboard lokal baca-saja dan endpoint data live |
| `paper_journal.py` / `paper_phase6.py` | Journal tahan lama dan runner Phase 6 |
| `paper_metrics.py` | Win rate, R, expectancy, DD, trades/day, idle dan segment |
| `bitget_orders.py` | Sizing dan preflight order minimum |
| `demo_phase7.py` | Preflight/sandbox adapter Demo yang terkunci |
| `tes_*.py` | Unit test dan skrip pemeriksaan |

Berkas keluaran atau berkas audit tidak boleh berisi rahasia API:
`state.json`, `signal.json`, `paper_trades.jsonl`, `daftar_40.json`, `daftar_ai.json`, `penilai_ai.json`, `log_penilai.jsonl`, `ai_pemakaian.json`, dan cache eksperimen.

## Sinyal dan syarat masuk

`signal_engine.py` menghasilkan sinyal hanya dari data bot, bukan dari prediksi AI. Empat syarat masuk wajib tetap melewati seluruh filter teknikal yang sudah ada: tren struktur, EMA jelas, MACD searah/menguat, dekat S/R, VWAP mendukung, dan konfirmasi tren 30m. Sinyal juga harus lolos skor minimum, tidak lonjakan ekstrem, dan minimal satu titik grid dengan TP/SL/RR/risk ATR yang valid.

Skor terdiri dari lima komponen masing-masing maksimal 20 poin:

| Komponen | Maksimum |
|---|---:|
| RSI | 20 |
| EMA | 20 |
| MACD | 20 |
| SAR | 20 |
| Candle | 20 |

Zona: `Abaikan` <50; `Pantau` 50–69; `Persiapan` 70–89; `Eksekusi` 90–99; `Persiapan tutup` 100 atau lonjakan ekstrem.

## Rencana grid dan sizing

- Bullish: titik masuk S1/S2/HL; SL di luar HL; TP mengikuti mode.
- Bearish: titik masuk R1/R2/HH; SL di luar HH; TP mengikuti mode.
- Setiap level ditolak bila SL salah sisi, risk/reward rusak, RR di bawah minimum, atau risk ATR di luar batas.
- Sizing harus memenuhi minimum notional dan presisi amount bursa.
- Level yang tidak cukup dilayani minimum dapat dikurangi dari grid.
- Rounding tidak boleh membuat posisi melebihi notional maksimum setup.

## Kriteria Phase 6

Phase 6 belum lulus hanya karena satu trade beruntung. Contoh gate bawaan:

- Lebih dari 30 trade tertutup
- Setidaknya 7 hari observasi (disarankan 1–2 minggu)
- Expectancy > 0 setelah fee paper dan estimasi slippage
- Maximum drawdown ≤ 25% modal paper sebagai contoh threshold awal
- Hasil net dibagi major asset dan altcoin
- Keluaran dilengkapi trades/day dan idle time
- Safety stop menghentikan entry baru saat `KILL_SWITCH`, rugi harian, atau rugi beruntun tercapai

Threshold boleh disesuaikan sebelum evaluasi dimulai, tetapi harus didokumentasikan dan tidak boleh diubah setelah melihat hasil.

## Jurnal Phase 6

`paper_phase6.py` menjadikan `paper_trades.jsonl` sebagai audit append-only. Setiap open dan close dicatat. Metrik membaca seluruh journal—bukan hanya 100 riwayat terakhir `state.json`. Lakukan backup jurnal harian.

Run 1–2 minggu masih merupakan evaluasi; passing paper tidak otomatis memberi izin menuju live.

## Gate Demo Phase 7

Demo hanya diperbolehkan bila semuanya terpenuhi:

- `MODE=demo`
- `DRY_RUN=off`
- `DEMO_API=on`
- `DEMO_CONFIRM=UJI_DEMO_SAYA_PAHAM`
- Key, secret, dan passphrase berasal dari **Demo API Key**

Untuk loop otomatis, `DEMO_LOOP_EXECUTION_VERIFIED=on` juga wajib; biarkan `off` sampai pengujian manual pada langkah uji Demo lulus. Live ditolak oleh adapter Demo. Sebelum mengirim Demo, verifikasi skema UTA v3 terbaru dari dokumentasi resmi Bitget, minimum order, contract size, payload TP/SL, partial fill, cancel, restart/reconciliation, dan timeout/duplikasi client ID.

Bandingkan hasil Demo terhadap paper: perbedaan yang wajar adalah slippage dan eksekusi aktual. Demo yang positive tidak menjamin live profit.

## Keamanan dan operasional

- `.env` ada dalam `.gitignore`; jangan commit atau screenshot rahasia.
- Jika key ter-commit, anggap bocor: hapus, revoke, dan buat key baru.
- Akun UTA memakai margin cross: isolasi modal bot dari dana lain.
- Live start criteria harus ditulis sebelum modal ditambah.
- Kriteria stop boleh mencakup drawdown, consecutive losses, atau tidak ada edge selama dua minggu.
- Catatan harian wajib ditinjau; idle adalah fitur, bukan kegagalan.

# Sistematika Bot-Tree

## Alur data

```text
Bitget ticker 24 jam
  -> Penyaring likuiditas/universe -> daftar_40.json
  -> Analisis teknikal 30m (langsung dari daftar_40.json)
  -> Grid entry + SL + TP
  -> Signal Engine formula-only -> signal.json
  -> Risk gate
  -> Paper trading / Phase 6 journal
  -> Demo adapter / Phase 7 preflight
  -> Live safeguards dan modal bertahap (belum diaktifkan)
```

## Matriks keputusan

```text
Harga menyentuh zona entry -> pasang grid + SL di luar struktur
  |- Bounce ke TP -> tutup dan cari setup baru
  |- Lonjakan ekstrem -> tutup/persiapan tutup dan batalkan sisa limit
  `- Tembus SL -> tutup rugi dan hitung rugi beruntun
       |- Batas rugi harian/runtun tercapai -> STOP entry baru
       `- Di bawah batas -> boleh evaluasi token lain
```

Tidak ada averaging down tanpa batas dan tidak ada pemaksaan entry ketika setup tidak matang.
