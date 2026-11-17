# Bot-Tree

Bot sinyal dan (nanti) eksekusi untuk **futures USDT di Bitget (akun UTA)**. Bot memilih token, menilai setup secara teknikal dari candle asli, merencanakan grid limit lengkap dengan TP/SL, dan menjaga batas risiko. AI bersifat **opsional** (pemilih dan penilai kedua), bukan inti keputusan.

> **STATUS: tahap pengembangan.** Belum ada kode yang membuat order. Semua yang ada sekarang hanya **membaca data** atau **simulasi**. Jangan menjalankan dengan uang asli sebelum paper trading membuktikan hasil bersih positif setelah fee.
>
> Ini bukan nasihat keuangan dan tidak ada jaminan keuntungan.

## Tujuan
Trading **tanpa melibatkan perasaan**: semua entry, exit, dan risiko ditentukan rumus yang tertulis, diuji dulu di paper dan demo, baru uang asli dalam jumlah kecil.

## Yang sudah ada
- Koneksi Bitget (Demo API Key, UTA) dan pembacaan saldo
- Pengambil candle 5m dan 30m, serta indikator (EMA, RSI, MACD, SAR, ATR, VWAP, S/R, tren)
- Penyaring token berdasarkan data 24 jam, dengan universe (blacklist dan watchlist)
- AI pemilih 20 bullish + 20 bearish (Gemini/Claude/GPT/Grok), dengan cadangan rumus bila AI gagal
- Rencana grid (titik limit, SL, TP) dan validasi geometri risiko
- AI penilai (second opinion MASUK/TUNGGU/TOLAK)
- Modul risk (batas rugi harian, rugi beruntun, maksimal token terbuka, kill switch)
- Skrip cek: koneksi, indikator, fondasi risk, kelayakan ukuran order
- Eksperimen: berita RSS, CoinMarketCap keyless, pencarian Google Gemini (tidak tersedia di tier gratis)

## Yang belum ada
- Pemindai yang mencatat tiap candle (Fase C)
- Mesin paper trading (Fase D)
- Modul order ke Bitget: TP/SL di sisi bursa, ukuran order sesuai minimum (Fase E)
- Penyimpanan state (`state.json`) dan dashboard lokal yang membacanya

## Persyaratan
- Python 3.10+ (diuji di 3.14), Windows 10
- Paket: `ccxt`, `python-dotenv`, `requests` (juga `pandas` di `requirements.txt`, belum dipakai)
- Akun Bitget tipe **UTA**. API key: *Trade (Read & Write)* dan *Manage (Read-only)*. **Jangan aktifkan izin withdraw.** Untuk uji, pakai **Demo API Key**.
- Opsional: API key AI (Gemini dipakai sejauh ini)

## Instalasi
```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy env.example .env      (lalu isi .env, jangan pernah di-commit)
```

## Konfigurasi `.env` (nilai bawaan ada di `config.py`)
| Kelompok | Pengaturan penting |
|---|---|
| Mode | `MODE` = paper / demo / live; live wajib `LIVE_CONFIRM=SAYA_PAHAM_RISIKONYA` |
| Bitget | `BITGET_API_KEY`, `BITGET_SECRET_KEY`, `BITGET_PASSPHRASE`, `BITGET_UTA=on` |
| AI | `AI_PROVIDER`, key penyedia, `AI_MODEL`, `AI_MAX_CALLS_PER_DAY`, `AI_MAX_TOKENS_PER_HARI` |
| Modal | `MODAL_DEMO_USDT`, `MODAL_LIVE_USDT` (dipilih otomatis sesuai MODE), `LEVERAGE`, `RISK_PER_SETUP_PCT` (margin per setup, persen modal) |
| Rencana | `TP_MODE` (sr_lawan / struktur / persen), `TP_PERCENT`, `SL_POINTS`, `SL_BUFFER_ATR`, `RR_MIN`, `RISK_ATR_MIN`, `RISK_ATR_MAX` |
| Sinyal | `SCORE_MIN`, `NEAR_MODE` (atr / persen), `NEAR_ATR_MULT`, `NEAR_SR_PERCENT` |
| Pengaman | `DRY_RUN=on`, `KILL_SWITCH`, `MAX_OPEN_TOKENS`, `MAX_DAILY_LOSS_USDT`, `MAX_CONSECUTIVE_LOSSES` |
| Universe | `PENYARING_VOL_MIN_USDT`, `PENYARING_TOP_VOLUME`, `JUMLAH_PER_SISI`, `UBAH_MAKS_SKOR`, `WATCHLIST_MODE` (off / prefer / only), `WATCHLIST_FILE`, `TOKEN_BLACKLIST` |

Catatan: saat `MODE=demo`, modal dibaca dari `MODAL_DEMO_USDT`, bukan `MODAL_LIVE_USDT`.

## Cara menjalankan (urutan yang disarankan)
```
python cek_koneksi.py        # login dan saldo (hanya baca)
python cek_fase_a.py         # verifikasi parameter risk dan universe
python cek_kelayakan.py      # ukuran order vs minimum bursa, jarak SL vs ATR
python penyaring.py          # daftar bullish/bearish -> daftar_40.json
python ai_pemilih.py         # (opsional) AI memilih 20+20 -> daftar_ai.json
python penilai_ai.py --jumlah 8   # (opsional) hitung rencana + second opinion AI
python tes_indikator.py      # tabel skor dan syarat masuk beberapa token
```

## Struktur file
| File | Fungsi |
|---|---|
| `config.py` | Membaca semua pengaturan dari `.env` |
| `data_pasar.py` | Mengambil candle dari Bitget (data publik) |
| `indikator.py` | Indikator, skor, syarat masuk, titik grid, konfirmasi 30m |
| `penyaring.py`, `universe.py`, `watchlist.json` | Penyaringan token dan universe |
| `risk.py` | Ukuran posisi dan pengaman order baru |
| `ai_pemilih.py` | AI memilih token, dengan jatah harian dan cadangan rumus |
| `penilai_ai.py` | Rencana grid (TP/SL) dan penilaian AI |
| `cek_koneksi.py`, `cek_fase_a.py`, `cek_kelayakan.py`, `tes_*.py`, `lihat_aset.py` | Skrip uji dan pemeriksaan |
| `berita.py`, `eksperimen_*.py` | Eksperimen berita dan pencarian |
| `SISTEMATIKA.md`, `PENGEMBANGAN.md` | Dokumentasi rancangan dan catatan pengembangan |

Berkas keluaran (tidak di-commit): `daftar_40.json`, `daftar_ai.json`, `penilai_ai.json`, `log_penilai.jsonl`, `ai_pemakaian.json`, `berita_cache.json`, `eksperimen_*.json`, `cmc_contoh.json`.

## Keamanan
- API key hanya di `.env`; `.env` ada di `.gitignore`. Periksa dengan `git ls-files` dan `git log --all --oneline -- .env` (harus kosong).
- Kalau key pernah ter-commit, anggap bocor: hapus dan buat baru.
- Mulai dari paper, lalu demo, baru live dengan modal kecil. `DRY_RUN=on` secara bawaan.
- Akun UTA memakai margin **cross**: jaga saldo akun sebesar modal bot saja.
- Tanggung jawab penuh atas keputusan trading ada pada pemilik akun.
