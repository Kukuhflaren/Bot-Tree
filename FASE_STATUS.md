# Status fase Bot-Tree

Diperbarui: 2026-11-18

| Fase | Isi | Status |
|------|-----|--------|
| **A** | Risk gate, universe, watchlist, blacklist | ✅ Siap (`cek_fase_a.py`) |
| **B** | Entry/SL/TP tertulis, konfirmasi 30m, grid validasi | ✅ Ada di `indikator.py` + `penilai_ai.py` |
| **C** | Scanner continuous | ✅ `scanner.py` |
| **D** | Paper engine (fill, partial, slippage, fee, state) | ✅ `paper.py` + `state.py` + unit test |
| **E** | Order nyata ke Bitget (limit + TP/SL bursa) | ❌ Belum — berikutnya |

## Temuan dari uji demo (2026-11-18)

1. **Koneksi demo OK** — saldo terbaca; `DRY_RUN=on`.
2. **Tidak ada setup layak** pada sesi uji — `tren_30m` / MACD / dekat S/R sering gagal (pasar sideways). Idle = perilaku yang diinginkan.
3. **SL_POINTS=50** sering membuat buffer SL > `RISK_ATR_MAX` (ATR 5m kecil). Default baru disarankan **40**, atau `SL_BUFFER_ATR=0.8`.
4. **Modal demo 25 USDT @ 5%** → margin 1.25; BTC min order ~1.29 margin → sedikit kurang. SPCX cukup. Naikkan sedikit `RISK_PER_SETUP_PCT` atau modal jika ingin trade BTC.
5. Simbol AI aneh (mis. `ANTHROPIC`) di-skip otomatis (`BadSymbol`).

## Perintah rutin

```bash
python cek_koneksi.py
python cek_fase_a.py
python cek_kelayakan.py
python penyaring.py
python ai_pemilih.py          # opsional
python penilai_ai.py --jumlah 8
python paper.py --status
python scanner.py --sekali
python scanner.py --loop      # atau default loop
```

## Sebelum Fase E

- Paper berjalan beberapa sesi dengan hasil bersih setelah fee (bukan hanya unit test).
- Parameter SL / RISK_ATR / SCORE_MIN disetel dari data nyata.
- Tetap `DRY_RUN=on` sampai siap demo order.
