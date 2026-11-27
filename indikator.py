"""Strategi Trend + Range Grid (ATR Arithmetic).

Klasifikasi:
  - Bullish  : struktur HH+HL + EMA9>EMA21 + ADX >= ADX_TREND_MIN  → Long grid
  - Bearish  : struktur LH+LL + EMA9<EMA21 + ADX >= ADX_TREND_MIN  → Short grid
  - Sideways : ADX lemah / struktur tidak jelas, boleh masuk jika range >= RANGE_MIN_ATR × ATR

Grid:
  spacing = GRID_SPACING_ATR × ATR (deret aritmatika otomatis)
  SL di luar HL/HH = SL_BUFFER_ATR × ATR
"""
from __future__ import annotations

import config

PIVOT_W = 8
TREN_W = 5


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


def klasifikasi_tren(c):
    """Kembalikan arah: 1=bullish, -1=bearish, 0=sideways + metadata."""
    if len(c) < 40:
        return {
            "arah": 0, "label": "sideways", "adx": 0.0,
            "struktur": 0, "ema_bias": 0, "alasan": "data kurang",
        }

    cl = [x["c"] for x in c]
    e9, e21 = ema(cl, 9), ema(cl, 21)
    adx_val = adx(c, int(getattr(config, "ADX_PERIOD", 14)))
... 