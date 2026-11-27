"""Strategi Trend Grid Sederhana.

Klasifikasi (hanya 3 kondisi):
  - Bullish : struktur HH+HL + EMA9 > EMA21 + ADX >= ADX_TREND_MIN  -> Long grid
  - Bearish : struktur LH+LL + EMA9 < EMA21 + ADX >= ADX_TREND_MIN  -> Short grid
  - Sideways: selain itu                                            -> SKIP

Grid (di dalam range HL..HH):
  range  = HH - HL
  jarak  = max(GRID_SPACING_ATR * ATR, range / 5)
  Long : level_k = HL + (k + 0.5) * jarak   (selama level < harga dan level < HH)
  Short: level_k = HH - (k + 0.5) * jarak   (selama level > harga dan level > HL)
  SL  : satu SL untuk seluruh grid = HL - SL_BUFFER_ATR*ATR (long) / HH + ... (short)
  TP  : HH (long) / HL (short)
"""
from __future__ import annotations

import config

TREN_W = 4  # jendela pivot (candle kiri/kanan) untuk struktur puncak/lembah


# ---------------------------------------------------------------- indikator dasar
def ema(nilai, n):
    k = 2 / (n + 1)
    e = nilai[0]
    hasil = []
    for x in nilai:
        e = x * k + e * (1 - k)
        hasil.append(e)
    return hasil


def rsi_seri(closes, n=14):
    rs = [None] * len(closes)
    g = l = 0.0
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        if i <= n:
            g += max(d, 0) / n
            l += max(-d, 0) / n
        else:
            g = (g * (n - 1) + max(d, 0)) / n
            l = (l * (n - 1) + max(-d, 0)) / n
        if i >= n:
            rs[i] = 100.0 if l == 0 else 100 - 100 / (1 + g / l)
    return rs


def atr(c, n=14):
    tr = []
    for i in range(1, len(c)):
        tr.append(max(
            c[i]["h"] - c[i]["l"],
            abs(c[i]["h"] - c[i - 1]["c"]),
            abs(c[i]["l"] - c[i - 1]["c"]),
        ))
    if len(tr) < n:
        return sum(tr) / len(tr) if tr else 0.0
    return sum(tr[-n:]) / n


def pivot(c, w=3):
    """Daftar nilai puncak dan lembah (tanpa indeks). Dipertahankan untuk kompatibilitas."""
    ph, pl = [], []
    for i in range(w, len(c) - w):
        H = L = True
        for j in range(1, w + 1):
            if c[i]["h"] <= c[i - j]["h"] or c[i]["h"] <= c[i + j]["h"]:
                H = False
            if c[i]["l"] >= c[i - j]["l"] or c[i]["l"] >= c[i + j]["l"]:
                L = False
        if H:
            ph.append(c[i]["h"])
        if L:
            pl.append(c[i]["l"])
    return ph, pl


def swing(c, w=TREN_W):
    """Puncak dan lembah beserta indeks: ([(idx, harga)], [(idx, harga)])."""
    ph, pl = [], []
    for i in range(w, len(c) - w):
        H = L = True
        for j in range(1, w + 1):
            # kiri boleh sama (>=), kanan harus lebih rendah (>): puncak kembar -> ambil yang terakhir
            if c[i]["h"] < c[i - j]["h"] or c[i]["h"] <= c[i + j]["h"]:
                H = False
            if c[i]["l"] > c[i - j]["l"] or c[i]["l"] >= c[i + j]["l"]:
                L = False
        if H:
            ph.append((i, c[i]["h"]))
        if L:
            pl.append((i, c[i]["l"]))
    return ph, pl


def adx(c, n=14):
    """Average Directional Index (Wilder). Nilai ADX terakhir (0-100)."""
    if len(c) < n + 2:
        return 0.0
    plus_dm, minus_dm, tr_list = [], [], []
    for i in range(1, len(c)):
        up = c[i]["h"] - c[i - 1]["h"]
        down = c[i - 1]["l"] - c[i]["l"]
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
        tr_list.append(max(
            c[i]["h"] - c[i]["l"],
            abs(c[i]["h"] - c[i - 1]["c"]),
            abs(c[i]["l"] - c[i - 1]["c"]),
        ))

    def wilder_smooth(data, period):
        if len(data) < period:
            return []
        out = [sum(data[:period])]
        for i in range(period, len(data)):
            out.append(out[-1] - (out[-1] / period) + data[i])
        return out

    atr_s = wilder_smooth(tr_list, n)
    plus_s = wilder_smooth(plus_dm, n)
    minus_s = wilder_smooth(minus_dm, n)
    if not atr_s or not plus_s or not minus_s:
        return 0.0

    dx = []
    for a, p, m in zip(atr_s, plus_s, minus_s):
        if a <= 0:
            dx.append(0.0)
            continue
        plus_di = 100.0 * p / a
        minus_di = 100.0 * m / a
        denom = plus_di + minus_di
        dx.append(0.0 if denom == 0 else 100.0 * abs(plus_di - minus_di) / denom)

    if len(dx) < n:
        return sum(dx) / len(dx) if dx else 0.0
    adx_val = sum(dx[:n]) / n
    for i in range(n, len(dx)):
        adx_val = ((adx_val * (n - 1)) + dx[i]) / n
    return adx_val


def klaster(level, toleransi):
    hasil, grup = [], []
    for x in sorted(level):
        if grup and x - grup[-1] > toleransi:
            hasil.append(sum(grup) / len(grup))
            grup = []
        grup.append(x)
    if grup:
        hasil.append(sum(grup) / len(grup))
    return hasil


# ---------------------------------------------------------------- klasifikasi tren
def klasifikasi_tren(c):
    """arah: 1=bullish, -1=bearish, 0=sideways (skip). Disertai metadata struktur."""
    kosong = {
        "arah": 0, "label": "sideways", "adx": 0.0, "struktur": 0, "ema_bias": 0,
        "puncak": [], "lembah": [], "alasan": "data kurang",
    }
    if len(c) < 40:
        return kosong

    cl = [x["c"] for x in c]
    e9, e21 = ema(cl, 9), ema(cl, 21)
    adx_val = adx(c, int(getattr(config, "ADX_PERIOD", 14)))
    adx_min = float(getattr(config, "ADX_TREND_MIN", 20))

    ph, pl = swing(c, TREN_W)
    struktur = 0
    if len(ph) >= 2 and len(pl) >= 2:
        if ph[-1][1] > ph[-2][1] and pl[-1][1] > pl[-2][1]:
            struktur = 1   # HH + HL
        elif ph[-1][1] < ph[-2][1] and pl[-1][1] < pl[-2][1]:
            struktur = -1  # LH + LL
    ema_bias = 1 if e9[-1] > e21[-1] else (-1 if e9[-1] < e21[-1] else 0)

    arah, alasan = 0, []
    if struktur == 0:
        alasan.append("struktur campur")
    if struktur != 0 and ema_bias != struktur:
        alasan.append("EMA berlawanan struktur")
    if adx_val < adx_min:
        alasan.append(f"ADX {adx_val:.1f} < {adx_min:g}")
    if struktur != 0 and ema_bias == struktur and adx_val >= adx_min:
        arah = struktur

    return {
        "arah": arah,
        "label": "bullish" if arah > 0 else ("bearish" if arah < 0 else "sideways"),
        "adx": adx_val,
        "struktur": struktur,
        "ema_bias": ema_bias,
        "puncak": ph[-2:],
        "lembah": pl[-2:],
        "alasan": ", ".join(alasan) or "ok",
    }


# ---------------------------------------------------------------- HL / HH dan grid
def batas_range(c, arah, ph, pl):
    """(HL, HH) untuk arah tren. HL = dasar grid, HH = puncak grid."""
    if arah > 0:
        # Long: HL = higher low terakhir; HH = puncak tertinggi sejak HL / swing high terakhir
        i_hl, hl = pl[-1]
        hh = max(ph[-1][1], max(x["h"] for x in c[i_hl:]))
        return hl, hh
    # Short: HH = lower high terakhir (SL di atasnya); HL = dasar terendah sejak puncak itu
    i_hh, hh = ph[-1]
    hl = min(pl[-1][1], min(x["l"] for x in c[i_hh:]))
    return hl, hh


def bangun_grid(arah, harga, hl, hh, atr_val):
    """Level grid deret aritmatika di dalam range HL..HH. Return list (nama, harga)."""
    if arah == 0 or atr_val <= 0 or hh <= hl:
        return []
    rng = hh - hl
    spacing_atr = float(getattr(config, "GRID_SPACING_ATR", 0.4))
    jarak = max(spacing_atr * atr_val, rng / 5)
    near = float(getattr(config, "NEAR_ATR_MULT", 3.0)) * atr_val
    maks = int(getattr(config, "GRID_MAX_LEVELS", 5))

    level = []
    k = 0
    if arah > 0:
        while True:
            h = hl + (k + 0.5) * jarak
            if h >= hh or h >= harga:
                break
            if harga - h <= near:
                level.append(h)
            k += 1
        level.sort(reverse=True)           # terdekat harga dulu
        prefix = "S"
    else:
        while True:
            h = hh - (k + 0.5) * jarak
            if h <= hl or h <= harga:
                break
            if h - harga <= near:
                level.append(h)
            k += 1
        level.sort()                       # terdekat harga dulu
        prefix = "R"
    level = level[:maks]
    return [(f"{prefix}{i + 1}", h) for i, h in enumerate(level)]


# ---------------------------------------------------------------- analisis utama
def analisis(c, arah=None, near_pct=None, score_min=None, near_mode=None,
             near_atr_mult=None, c30=None):
    """Analisis satu token. Parameter selain `c` dan `arah` dipertahankan agar
    pemanggil lama tetap jalan; strategi baru memakai nilai dari config.

    arah: None = deteksi otomatis. 1/-1 = petunjuk dari universe; jika deteksi
    tidak sama dengan petunjuk, token dinyatakan tidak layak (tren_or_range gagal).
    """
    score_min = float(config.SCORE_MIN if score_min is None else score_min)
    tren = klasifikasi_tren(c)
    arah_det = tren["arah"]
    harga = c[-1]["c"] if c else 0.0
    atr_val = atr(c, 14) if c else 0.0
    adx_val = tren["adx"]
    adx_min = float(getattr(config, "ADX_TREND_MIN", 20))
    ts = c[-1]["t"] if c else None

    hl = hh = None
    grid = []
    ph = pl = []
    if len(c) >= 40:
        ph, pl = swing(c, TREN_W)
    if arah_det != 0 and ph and pl:
        hl, hh = batas_range(c, arah_det, ph, pl)
        grid = bangun_grid(arah_det, harga, hl, hh, atr_val)
    range_atr = ((hh - hl) / atr_val) if (hh is not None and atr_val > 0) else 0.0

    # candle ekstrem: body candle terakhir terlalu besar (relatif ATR)
    ekstrem = False
    if c and atr_val > 0:
        body = abs(c[-1]["c"] - c[-1]["o"])
        ekstrem = body > float(getattr(config, "EXTREME_BODY_ATR", 2.5)) * atr_val

    cocok_petunjuk = arah in (None, 0) or arah == arah_det
    range_min = float(getattr(config, "RANGE_MIN_ATR", 2.0))
    jarak_atr = None
    if grid and atr_val > 0:
        jarak_atr = min(abs(harga - h) for _, h in grid) / atr_val

    syarat = [
        arah_det != 0 and cocok_petunjuk,   # trend_or_range (tren jelas, bukan sideways)
        arah_det != 0 and adx_val >= adx_min,  # adx_ok
        range_atr >= range_min,             # range_ok
        False,                              # minimum_score (diisi setelah skor dihitung)
        bool(grid),                         # grid_available (dekat zona grid)
    ]

    # skor 0-100 untuk pengurutan kandidat
    rincian = []
    s_tren = 30 if syarat[0] else 0
    s_adx = (15 + min(10.0, max(0.0, adx_val - adx_min))) if syarat[1] else 0
    if grid and atr_val > 0 and jarak_atr is not None:
        s_dekat = 20 * max(0.0, 1 - jarak_atr / max(float(getattr(config, "NEAR_ATR_MULT", 3.0)), 0.1))
    else:
        s_dekat = 0
    s_range = 15 if syarat[2] else 0
    s_tenang = 0 if ekstrem else 10
    for nama, v in (("tren", s_tren), ("adx", s_adx), ("dekat_grid", s_dekat),
                    ("range", s_range), ("tanpa_ekstrem", s_tenang)):
        rincian.append((nama, round(v, 1)))
    mentah = int(round(s_tren + s_adx + s_dekat + s_range + s_tenang))
    syarat[3] = mentah >= score_min

    layak = all(syarat) and not ekstrem

    if not grid:
        zona = "tanpa_grid"
    elif jarak_atr is not None and jarak_atr <= 1.0:
        zona = "dekat_grid"
    else:
        zona = "dalam_jangkauan"

    cl = [x["c"] for x in c]
    rsi_all = rsi_seri(cl) if len(cl) > 15 else []
    rsi_val = rsi_all[-1] if rsi_all else None

    return {
        "arah": arah_det,
        "label": tren["label"],
        "harga": harga,
        "atr": atr_val,
        "adx": adx_val,
        "HL": hl,
        "HH": hh,
        "range_atr": range_atr,
        "grid": grid,
        "syarat": syarat,
        "layak": layak,
        "ekstrem": ekstrem,
        "mentah": mentah,
        "skor": mentah,
        "zona": zona,
        "rincian": rincian,
        "rsi": rsi_val,
        "candle_timestamp": ts,
        "jarak_atr": jarak_atr,
        "jarak_sr": (min(abs(harga - h) for _, h in grid) / harga * 100) if (grid and harga) else 0.0,
        "dasar": [tren["struktur"] != 0, tren["ema_bias"] != 0 and tren["ema_bias"] == tren["struktur"], adx_val >= adx_min],
        "layak_persen": bool(layak),
        "layak_atr": bool(layak),
        "tren_info": {
            "tren": tren["struktur"],
            "puncak": [p for _, p in tren["puncak"]],
            "lembah": [p for _, p in tren["lembah"]],
        },
        "alasan_tren": tren["alasan"],
    }
