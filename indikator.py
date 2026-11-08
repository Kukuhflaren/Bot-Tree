"""Fase 3: indikator dan skor sinyal (port dari dashboard demo). Murni Python, tanpa pandas.
Candle = dict dengan kunci: t (waktu), o, h, l, c, v."""


PIVOT_W = 10  # jendela puncak/lembah untuk support/resistance (10 x 5m = 50 menit)
GRID_MAKS_ATR = 12  # titik grid lebih jauh dari 12 x ATR dari harga dibuang (hampir tidak akan terisi)
TREN_W = 5    # jendela lebih pendek khusus untuk menilai tren (respons lebih cepat)


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


def macd_hist(closes):
    e12, e26 = ema(closes, 12), ema(closes, 26)
    m = [a - b for a, b in zip(e12, e26)]
    sg = ema(m, 9)
    return [a - b for a, b in zip(m, sg)]


def sar(c):
    """Parabolic SAR. Mengembalikan (nilai_sar, apakah_di_bawah_harga)."""
    sr, su = [c[0]["l"]], [True]
    naik, af, ep, s = True, 0.02, c[0]["h"], c[0]["l"]
    for i in range(1, len(c)):
        s += af * (ep - s)
        if naik:
            if c[i]["l"] < s:
                naik, s, ep, af = False, ep, c[i]["l"], 0.02
            elif c[i]["h"] > ep:
                ep, af = c[i]["h"], min(af + 0.02, 0.2)
        else:
            if c[i]["h"] > s:
                naik, s, ep, af = True, ep, c[i]["h"], 0.02
            elif c[i]["l"] < ep:
                ep, af = c[i]["l"], min(af + 0.02, 0.2)
        sr.append(s)
        su.append(naik)
    return sr, su


def pivot(c, w=3):
    """Titik puncak (ph) dan lembah (pl) lokal."""
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


def atr(c, n=14):
    tr = []
    for i in range(1, len(c)):
        tr.append(max(c[i]["h"] - c[i]["l"], abs(c[i]["h"] - c[i - 1]["c"]), abs(c[i]["l"] - c[i - 1]["c"])))
    return sum(tr[-n:]) / n


def klaster(level, toleransi):
    """Gabungkan level yang berdekatan (selisih <= toleransi) menjadi satu level (rata-rata)."""
    hasil, grup = [], []
    for x in sorted(level):
        if grup and x - grup[-1] > toleransi:
            hasil.append(sum(grup) / len(grup))
            grup = []
        grup.append(x)
    if grup:
        hasil.append(sum(grup) / len(grup))
    return hasil


def _titik_grid(p, s, kandidat, cadangan, jarak_min, jarak_maks):
    """Pilih sampai 3 titik limit yang berada di sisi benar dari harga (bullish: di bawah,
    bearish: di atas) dan tidak kembar (selisih >= jarak_min). Kandidat sesuai urutan titik 1-2-3;
    kalau ada yang kembar atau di sisi salah, diganti level cadangan berikutnya."""
    hasil = []

    def boleh(h):
        if (s > 0 and h >= p) or (s < 0 and h <= p):
            return False
        if abs(h - p) > jarak_maks:
            return False
        return all(abs(h - x[1]) >= jarak_min for x in hasil)

    for nama, h in kandidat:
        if len(hasil) < 3 and boleh(h):
            hasil.append((nama, h))
    for nama, h in cadangan:
        if len(hasil) >= 3:
            break
        if boleh(h):
            hasil.append((nama, h))
    return hasil


def zona(skor):
    if skor >= 100:
        return "Persiapan tutup"
    if skor >= 90:
        return "Eksekusi"
    if skor >= 70:
        return "Persiapan"
    if skor >= 50:
        return "Pantau"
    return "Abaikan"


def _batas(x, maks):
    return max(0, min(maks, x))


def analisis(c, arah, dekat_sr_persen=0.5, skor_min=50, mode="persen", dekat_atr=1.5):
    """c = candle yang SUDAH TUTUP (buang candle terakhir yang masih berjalan).
    arah: 1 = bullish, -1 = bearish (dari pilihan AI)."""
    if len(c) < 60:
        raise ValueError("Butuh minimal 60 candle.")
    s = arah
    cl = [x["c"] for x in c]
    e9, e21 = ema(cl, 9), ema(cl, 21)
    rs, mh = rsi_seri(cl), macd_hist(cl)
    _, su = sar(c)
    ph, pl = pivot(c, PIVOT_W)
    rata_tr = atr(c)
    tol = 0.5 * rata_tr
    pht, plt = pivot(c, TREN_W)
    L = c[-1]
    p = L["c"]

    bawah = sorted([x for x in klaster(pl, tol) if x < p], reverse=True)
    atas = sorted([x for x in klaster(ph, tol) if x > p])
    S1 = bawah[0] if bawah else p * 0.99
    S2 = bawah[1] if len(bawah) > 1 else p * 0.98
    R1 = atas[0] if atas else p * 1.01
    R2 = atas[1] if len(atas) > 1 else p * 1.02
    HL = pl[-1] if pl else p * 0.985
    HH = ph[-1] if ph else p * 1.015

    rsi = rs[-1]
    rp = round(_batas((rsi - 50) if s > 0 else (50 - rsi), 20))
    ep = (10 if e9[-1] * s > e21[-1] * s else 0) + (10 if p * s > e9[-1] * s else 0)
    mp = (10 if mh[-1] * s > 0 else 0) + (10 if mh[-1] * s > mh[-2] * s else 0)
    sp = 20 if su[-1] == (s > 0) else 0

    badan = abs(L["c"] - L["o"])
    rata = sum(abs(x["c"] - x["o"]) for x in c[-21:-1]) / 20
    rentang = (L["h"] - L["l"]) or 1e-9
    posisi = (L["c"] - L["l"]) / rentang if s > 0 else (L["h"] - L["c"]) / rentang
    cdp = (8 if (L["c"] - L["o"]) * s > 0 else 0) + (6 if badan > rata else 0) + (6 if posisi > 0.66 else 0)
    ekstrem = badan / L["o"] > 0.012 and badan > 4 * rata
    mentah = rp + ep + mp + sp + cdp

    tr = 0
    if len(pht) > 1 and len(plt) > 1:
        if pht[-1] > pht[-2] and plt[-1] > plt[-2]:
            tr = 1
        elif pht[-1] < pht[-2] and plt[-1] < plt[-2]:
            tr = -1
    selisih = (p - S1) if s > 0 else (R1 - p)
    jarak = selisih / p * 100  # dalam persen harga
    jarak_atr = selisih / rata_tr  # dalam kelipatan ATR
    ok_persen = jarak <= dekat_sr_persen
    ok_atr = jarak_atr <= dekat_atr
    dasar = [
        tr == s,
        (e9[-1] - e21[-1]) * s / p > 0.0003,
        mh[-1] * s > 0 and mh[-1] * s > mh[-2] * s,
    ]
    syarat = dasar + [ok_atr if mode == "atr" else ok_persen]
    jarak_min = max(0.5 * rata_tr, p * 0.0005)
    jarak_maks = GRID_MAKS_ATR * rata_tr
    # Hanya level NYATA (dari puncak/lembah di chart) yang boleh jadi titik grid, bukan nilai cadangan
    if s > 0:
        kand = [(f"S{i + 1}", x) for i, x in enumerate(bawah[:2])] + ([("HL", HL)] if pl else [])
        cad = [(f"S{i + 3}", x) for i, x in enumerate(bawah[2:])]
    else:
        kand = [(f"R{i + 1}", x) for i, x in enumerate(atas[:2])] + ([("HH", HH)] if ph else [])
        cad = [(f"R{i + 3}", x) for i, x in enumerate(atas[2:])]
    grid = _titik_grid(p, s, kand, cad, jarak_min, jarak_maks)
    skor = 100 if ekstrem else min(mentah, 99)
    return {
        "harga": p, "S1": S1, "S2": S2, "R1": R1, "R2": R2, "HL": HL, "HH": HH,
        "mentah": mentah, "skor": skor, "zona": zona(skor), "ekstrem": ekstrem,
        "syarat": syarat, "jarak_sr": jarak, "jarak_atr": jarak_atr, "dasar": dasar,
        "layak_persen": all(dasar) and ok_persen and not ekstrem and mentah >= skor_min and len(grid) >= 1,
        "layak_atr": all(dasar) and ok_atr and not ekstrem and mentah >= skor_min and len(grid) >= 1,
        "layak": all(syarat) and not ekstrem and mentah >= skor_min,
        "rincian": [("RSI", rp), ("EMA", ep), ("MACD", mp), ("SAR", sp), ("Candle", cdp)],
        "rsi": rsi, "atr": rata_tr, "grid": grid, "tren_info": {"puncak": pht[-2:], "lembah": plt[-2:], "tren": tr},
    }
