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
python paper.py               # coba buka / update
# atau
   python paper.py --status   # Lihat status
   python paper.py            # Satu siklus (cek sinyal + update posisi yang ada)
   python paper.py --loop      # Loop terus (setiap 60 detik)
   python paper.py --no-buka   # Hanya update posisi, jangan buka baru
   python paper.py --reset      # Reset state (hati-hati)
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

# Sistematika Bot-Tree
## 1. Prinsip desain
| Prinsip | Arti praktis |
|---|---|
| Bot = hakim | Entry, exit, dan risiko dari rumus. AI hanya opsional (pemilih dan pendapat kedua), tidak mengeksekusi. |
| Universe sempit | Bukan 800 token. Hanya yang likuid; produk leveraged dan berbasis jam pasar dikecualikan lewat blacklist/watchlist. |
| Risk dulu | Ukuran posisi dan SL harus valid sebelum "skor bagus" dianggap. |
| Paper membuktikan | Parameter belum final sampai hasil bersih setelah fee positif. |
| Idle = fitur | Lebih baik tidak trade daripada memaksa masuk saat setup jauh dari level. |

## 2. Alur data
```
Bitget ticker 24 jam
   -> [1] PENYARING (likuiditas, universe, skor 24 jam) -> daftar_40.json
   -> [2] AI PEMILIH (opsional) 20 bullish + 20 bearish -> daftar_ai.json
                         (gagal/habis jatah -> cadangan rumus penyaring)
   -> [3] ANALISIS TEKNIKAL per token dari candle 5m (+30m): skor, syarat masuk
   -> [4] RENCANA GRID: titik limit, SL, TP, validasi geometri
   -> [5] AI PENILAI (opsional): MASUK / TUNGGU / TOLAK + alasan  (hanya pendapat)
   -> [6] RISK GATE: kill switch, token terbuka, rugi harian, rugi beruntun
   -> [7] EKSEKUSI (BELUM DIBANGUN): paper -> demo -> live
```

## 3. Penyaring (`penyaring.py`, `universe.py`)
1. Ambil semua ticker futures USDT (sekitar 885 kontrak).
2. Buang stablecoin, token kena **blacklist** (pola sama/awalan/akhiran), dan token di luar watchlist bila `WATCHLIST_MODE=only`.
3. Buang volume 24 jam di bawah `PENYARING_VOL_MIN_USDT`, lalu ambil `PENYARING_TOP_VOLUME` volume terbesar.
4. **Rasio volume** = volume 24 jam ÷ rata-rata volume 7 hari sebelumnya (volume koin × harga tutup harian, sebagai perkiraan USDT).
5. **Skor** = `|ubah 24j|` (dibatasi `UBAH_MAKS_SKOR` bila > 0) × `min(rasio volume, 3)` × bobot likuiditas `(log10(volume/1 juta) + 1)`.
6. Naik -> bullish, turun -> bearish; masing-masing diurutkan dan dipotong `JUMLAH_PER_SISI`. Mode `prefer` mendahulukan token watchlist.
7. Tanda `!` di tabel = perubahan 24 jam 30% atau lebih (hati-hati).

## 4. AI (opsional)
**Pemilih (`ai_pemilih.py`)**: menerima ringkasan angka sekitar 100 kandidat (satu baris per token), memilih N bullish dan N bearish beserta alasan singkat. Hasil **divalidasi**: simbol yang tidak ada dibuang, duplikat dibuang, kekurangan diisi dari rumus penyaring. Kalau AI error atau jatah habis, daftar penuh dari rumus. Jatah: `AI_MAX_CALLS_PER_DAY` dan `AI_MAX_TOKENS_PER_HARI`. Penyedia: Gemini, Claude, GPT, Grok (REST). Server sibuk (500/502/503/504) diulang otomatis 3 kali; kuota habis (429) tidak diulang.

**Penilai (`penilai_ai.py`)**: bot menghitung semuanya, K token terbaik dikirim ke AI sebagai ringkasan angka, AI memberi `MASUK/TUNGGU/TOLAK`, keyakinan 1-5, alasan yang wajib menyebut angka, dan risiko. Dicatat di `log_penilai.jsonl` untuk dievaluasi terhadap hasil nyata. AI **tidak** memprediksi harga dan tidak mengarang berita atau level.

## 5. Analisis teknikal (`indikator.py`)
Input: candle 5m yang **sudah tutup** (300 candle). Arah (bullish/bearish) dari daftar pilihan.

**Indikator**: EMA 9/21, RSI 14, histogram MACD (12,26,9), Parabolic SAR, ATR 14, VWAP kumulatif, puncak/lembah (pivot).

**Skor 0-100 = 5 komponen x 20 poin (searah dengan arah):**
| Komponen | Poin |
|---|---|
| RSI | jarak RSI dari 50 searah arah, maksimal 20 |
| EMA | 10 bila EMA9 di sisi benar EMA21, +10 bila harga di sisi benar EMA9 |
| MACD | 10 bila histogram searah, +10 bila menguat |
| SAR | 20 bila SAR di sisi benar |
| Candle | 8 searah, +6 body lebih besar dari rata-rata 20 candle, +6 close di 1/3 ujung range |

**Zona**: < 50 Abaikan | 50 Pantau | 70 Persiapan | 90 Eksekusi | 100 Persiapan tutup (hanya saat **lonjakan ekstrem**: body candle > 1,2% harga dan > 4x rata-rata). Catatan desain: skor 80-100 **bukan** sinyal entry; sering berarti harga sudah jauh dari level.

**Support/Resistance**: pivot jendela 10 candle, level berdekatan digabung (toleransi 0,5 x ATR). Hanya level **nyata**; nilai cadangan (harga x 1,01 dll.) tidak dipakai sebagai titik atau TP. HL/HH = lembah/puncak terakhir.

**Syarat masuk (semua harus benar):**
1. Tren struktur sesuai arah (pivot jendela 5: bullish HH+HL, bearish LH+LL)
2. EMA jelas (selisih EMA9-EMA21 searah, lebih dari 0,03% harga)
3. MACD 5m searah dan menguat
4. Dekat S/R (mode `atr`: jarak <= `NEAR_ATR_MULT` x ATR; mode `persen`: <= `NEAR_SR_PERCENT`)
5. VWAP mendukung arah
6. Konfirmasi tren 30 menit
7. Tidak lonjakan ekstrem, skor >= `SCORE_MIN`, minimal 1 titik grid

**Konfirmasi 30 menit**: versi lama memakai 6 candle 5m terakhir. Versi **Fase B** (`konfirmasi_htf`, diberi candle 30m asli): tren (struktur HH/HL 30m + EMA9 vs EMA21) dan MACD 30m searah (opsi `MACD30_MENGUAT`: harus menguat). Keterbatasan: tidak mendeteksi struktur pada tren lurus tanpa pullback, dan terlambat minimal 3 candle 30m. *Status: diuji dengan data palsu; belum dikonfirmasi dengan data nyata.*

## 6. Rencana grid
- **Titik masuk (limit)**: sampai 3 titik. Bullish: S1, S2, HL. Bearish: R1, R2, HH. Harus di sisi benar dari harga, tidak kembar (selisih >= 0,5 x ATR), dan tidak lebih jauh dari 12 x ATR. Kekurangan diganti level cadangan (S3/R3 dst.).
- **SL**: di luar HL (bullish) atau HH (bearish) sejauh `SL_POINTS` poin (1 poin = 0,01% harga) atau `SL_BUFFER_ATR` x ATR bila > 0.
- **TP** (`TP_MODE`): `sr_lawan` (S/R lawan terdekat yang nyata; default), `struktur` (HH/HL), `persen` (`TP_PERCENT` dari entry).
- **Titik valid** bila: ada TP nyata, SL tidak di sisi salah, risk dan reward > 0, RR >= `RR_MIN`, dan `risk_atr` (jarak entry ke SL dibagi ATR) di antara `RISK_ATR_MIN` dan `RISK_ATR_MAX`. Alasan penolakan dicatat di kolom `tolak`.

## 7. Risk gate dan ukuran (`risk.py`)
- `margin_per_setup = modal x RISK_PER_SETUP_PCT / 100`; `notional = margin x leverage`. (Catatan: nama parameter menyiratkan "risiko", tapi ini **margin**; risiko sebenarnya = notional x jarak SL.)
- `boleh_order_baru(state)` menolak bila: `KILL_SWITCH` aktif, jumlah token terbuka >= `MAX_OPEN_TOKENS`, rugi harian <= -`MAX_DAILY_LOSS_USDT`, atau rugi beruntun >= `MAX_CONSECUTIVE_LOSSES`.
- **Order minimum bursa**: tiap level butuh nilai di atas minimum token (contoh: BTC sekitar 6,5-7 USDT, SPCX sekitar 5 USDT). `cek_kelayakan.py` menghitung margin minimum dan menyarankan perbaikan (alokasi, modal, leverage, token).

## 8. Eksekusi (BELUM DIBANGUN)
Rencana: urutan **paper -> demo -> live**. Order limit dan TP/SL dipasang **di sisi bursa** (bukan hanya di laptop), ukuran memenuhi minimum bursa, satu token terbuka, leverage dan mode posisi diatur manual di aplikasi. Mode `live` hanya jalan dengan `LIVE_CONFIRM`, `DRY_RUN=off` yang disengaja, dan lolos risk gate.

## 9. Matriks keputusan "jika tidak terpantul"
```
Harga menyentuh zona entry -> pasang grid + SL di luar struktur
   |- Bounce ke TP (S/R lawan) -> tutup, cari setup baru
   |- Lonjakan ekstrem         -> persiapan tutup (tutup posisi, batalkan order tersisa)
   `- Tembus SL -> tutup rugi, hitung rugi beruntun
         |- di bawah batas rugi beruntun dan harian -> boleh cari token lain
         `- batas tercapai -> STOP (istirahat sesi)
```
Tidak ada averaging down tanpa batas dan tidak ada "tunggu pantul lagi".

## 10. Berkas keluaran
`daftar_40.json` (penyaring), `daftar_ai.json` (AI/cadangan), `penilai_ai.json` dan `log_penilai.jsonl` (penilai), `ai_pemakaian.json` (jatah AI harian), `berita_cache.json`, `eksperimen_*.json`, `cmc_contoh.json`. Semuanya di `.gitignore`.

## 11. Parameter yang belum final
Arti "50 poin" untuk token berharga berbeda, `TP_MODE`, `RISK_PER_SETUP_PCT` dan jumlah level, `MACD30_MENGUAT`, isi watchlist, asumsi fee (0,12% pulang-pergi belum diverifikasi), dan batas rugi harian. Semuanya harus ditentukan dari paper trading.
