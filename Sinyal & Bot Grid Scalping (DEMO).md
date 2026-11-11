
# Sinyal & Bot Grid Scalping

DEMO · PAPER

Harga di halaman ini hasil simulasi acak, bukan harga pasar. Untuk data live dan order sungguhan, perlu backend (Python) yang memegang API key.

Harga menyentuh zona entry → pasang grid + SL di luar struktur
     │
     ├─ Bounce ke TP (S/R lawan) → tutup, cari setup baru
     │
     └─ Tembus SL → tutup rugi, hitung consecutive loss
              │
              ├─ Masih di bawah MAX_CONSECUTIVE & daily loss → boleh cari token lain
              └─ Batas tercapai → STOP (kill / istirahat sesi)

# Sistematis Bot dan AI
┌─────────────────────────────────────────────────────────┐
│  LOOP OTOMATIS (Python, tanpa chat)                     │
│                                                         │
│  1. Penyaring likuiditas          → bot                 │
│  2. Pemilih kandidat (opsional AI)→ bot + AI (hemat)    │
│  3. Skor + grid + RR + VWAP       → bot (hakim utama)   │
│  4. Second opinion                → AI (hanya jika bot  │
│                                       bilang layak)     │
│  5. Eksekusi order / paper        → bot                 │
│  6. Monitor TP (HH/HL) / SL       → bot                 │
│  7. Setelah TP → cari token baru  → ulang dari 1        │
└─────────────────────────────────────────────────────────┘

# Langkah demi langkah (mulai sekarang)
1. Buka folder di VS Code, lalu buka Terminal.
2. Jalankan python -m venv venv, lalu venv\Scripts\activate
3. Jalankan python cek_koneksi.py.

# Hasil Demo 
1. python cek_koneksi.py
2. python tes_indikator.py
3. python lihat_aset.py
4.1 python cek_fase_a.py
4.2 python penyaring.py
5. python tes_ai.py
6. [x] python ai_pemilih.py (hasil AI hanya mengulang kata-kata saja)
percobaan 1 - Ai mencari dan menilai token sendiri
7. [x] python eksperimen_ai.py --jumlah 3 (hasil AI tidak bisa karena tidak di dukung)
percobaan 2 - Ai mencari berita dari token hasil penyaringan
8. [x] python berita.py 
9. [x] python eksperimen_berita.py --jumlah 5
percobaan 3 - AI sebagai penilai
10. python penilai_ai.py

# Ceklis pengembangan
Fase 0: Akun dan keamanan
 [✓] Buat API key Bitget dengan izin baca + trade saja, tanpa withdraw. Bitget butuh 3 nilai: key, secret, passphrase.
 [✓] Buat API key AI dengan batas biaya (budget 5 USDT).
 [✓] Saldo akun UTA = modal bot saja (misalnya 25 USDT).
 [✓] Kerangka proyek
 [✓] Dashboard demo (simulasi, belum data nyata)
 [✓] Rancangan strategi: skor 5 komponen, zona, dan syarat masuk bot.

Fase 1: Lingkungan
 [✓] Install Python dan VS Code.
 [✓] Buat folder proyek, lalu python -m venv venv.
 [✓] Jalankan pip install -r requirements.txt.
 [✓] .env isi.

Fase 2: Koneksi baca-saja
 [✓] Jalankan python cek_koneksi.py, sampai data publik dan login API sama-sama OK.

Fase 3: Data dan indikator
 [✓] Ambil candle 5m lewat ccxt.
 [✓] Pindahkan hitungan RSI, EMA, MACD, SAR, dan S/R dari demo ke Python.
 [✓] python tes_indikator.py jalan tanpa error
 [✓] Angka skor dan harga masuk akal. Bandingkan harga dengan yang tampil di aplikasi Bitget.
 [✓] Cek RSI satu token dengan chart Bitget atau TradingView. Hasilnya tidak harus sama persis, tapi harus dekat.
 [✓] Indikator dan Data pasar OK

Fase 4: Pemilih token AI
 [] Prompt yang mengembalikan JSON (20 bullish + 20 bearish).
 [] Pasang batas panggilan per hari dan cache hasilnya.
 [] Siapkan cadangan kalau AI error (misalnya error 429 seperti sebelumnya): pakai daftar terakhir atau skor teknikal saja.
 [] 4a: Penyaring tanpa AI.
 [] 4b: AI sebagai pemilih.

 Fase peralihan A : Fondasi risk & universe
 [] RISK_ATR_MIN / RISK_ATR_MAX aktif — sudah
 [] MAX_OPEN_TOKENS = 1
 [] Risk per setup ≤ 5% modal (notional disesuaikan leverage)
 [] MAX_DAILY_LOSS + MAX_CONSECUTIVE_LOSSES + KILL_SWITCH dihormati di semua path order

Fase B — Aturan entry/exit final (tulis di config, bukan di kepala)
 [] Entry: hanya jika dekat S/R (NEAR) + tren 30m ok + MACD 30m ok + VWAP ok
 [] SL: 50 poin di luar HL/HH dan lolos risk_atr
 [] TP default: level S/R berlawanan (C1), dokumentasikan di README
 [] Skor 80–100 tidak memaksa entry jika jarak ke level besar
 [] Tidak ada average down otomatis tanpa batas

Fase C — Indikator & data
 [] Candle 30m untuk tren + MACD (sumber utama bias)
 [] Candle 5m untuk grid & jarak ke S/R
 [] VWAP konsisten definisinya (session vs rolling — pilih satu)
 [] Uji silang RSI/EMA/MACD vs TradingView/Bitget (sudah sebagian)
 [] Unit test kecil: geometri RR, risk_atr, sl_salah_sisi

Fase 5: Mesin sinyal
 [] mesin_sinyal.py: pipeline penyaring → analisis → hanya yang layak_bot_final
 [] Output state.json / sinyal.json (waktu, simbol, arah, entry levels, SL, TP, risk_atr, RR)
 [] AI dimatikan di path default (flag USE_AI=off)
 [] Skor 5 komponen dan zona (Pantau, Persiapan, Eksekusi, Persiapan tutup).
 [] Empat syarat masuk bot.

Fase 6: Paper trading
 [] Setiap sinyal layak dicatat seolah terisi (entry, SL, TP)
 [] Simulasi fill realistis (slippage kecil + fee taker×2)
 [] Hitung: winrate, avg R, expectancy, max DD, trade/hari, % idle
 [] Pisahkan hasil: major (BTC/ETH/SOL…) vs alt
 [] Hentikan paper jika consecutive loss / daily loss tersentuh (uji pengaman)

Kriteria lolos paper (contoh ketat):
1. Expectancy > 0 setelah fee
2. Max DD dalam batas yang Anda terima (mis. ≤ 20–30% modal paper)
3. Bukan hanya 3 trade “beruntung”

 [] Jalankan 1–2 minggu dan catat semua trade ke file.
 [] Hitung hasil bersih setelah fee dan slippage.

Fase 7: Demo Bitget
 [] Order format UTA v3 benar
 [] TP/SL di sisi bursa
 [] Min size order dicek
 [] DRY_RUN off hanya dengan Demo API Key
 [] Samakan hasil demo vs paper (selisih wajar = slippage)
 [] Order dikirim ke akun demo (DRY_RUN=off hanya dengan Demo API Key).
 [] Pastikan format order API v3 UTA benar.

Fase 8: Pengaman order nyata
 [] TP/SL dipasang di sisi bursa.
 [] Cek ukuran order minimum.
 [] Uji KILL_SWITCH, batas rugi harian, dan rugi beruntun.

Fase 9: Uang asli, bertahap
 [] Mulai 5–10 USDT dulu.
 [] Tentukan syarat naik modal dan syarat berhenti sebelum mulai.
 [] Syarat naik modal tertulis (mis. +X% net setelah N hari)
 [] Syarat stop tertulis (DD, consecutive loss, atau “tidak ada edge 2 minggu”)
 [] Log harian wajib dibaca (bukan diabaikan)

Fase 10: Pengembangan lanjutan
 [] Dashboard lokal yang membaca state.json.
 [] Saham US token (rToken), setelah simbol dan jamnya dicek.
 [] AI hanya second opinion pada setup yang sudah layak bot
 [] Ukur: apakah veto AI mengurangi loss di paper/demo
 [] Jika tidak menambah edge → tetap USE_AI=off

 