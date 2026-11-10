"""Eksperimen: berita nyata dari RSS + Gemini TANPA pencarian Google (cocok untuk tier gratis).

Alur:
  1. Baca token pilihan dari daftar_ai.json (dibuat ai_pemilih.py).
  2. Python mengambil judul berita terbaru tiap token dari Google News RSS (gratis).
  3. Gemini menilai dampak berita ke arah harga HANYA dari judul yang diberikan.
  4. Dicetak hasil, tautan berita untuk kamu cek sendiri, dan token yang terpakai.

Pakai:  python eksperimen_berita.py --jumlah 5      (N token per sisi)
Hanya membaca data. Tidak membuat order."""
import json
import sys

import ai_pemilih as ap
import berita as br
import config

FILE_DAFTAR = ap.FILE_HASIL
FILE_HASIL = "eksperimen_berita.json"


def muat_token(n):
    try:
        with open(FILE_DAFTAR, encoding="utf-8") as f:
            d = json.load(f)
    except FileNotFoundError:
        raise SystemExit("daftar_ai.json belum ada. Jalankan dulu: python ai_pemilih.py")
    token = []
    for kunci, arah in (("bullish", 1), ("bearish", -1)):
        for k in d[kunci][:n]:
            token.append({"nama": k["simbol"].split("/")[0].upper(), "arah": arah, "ubah": k["ubah_24j"]})
    return token


def buat_prompt(token, berita):
    blok = []
    for t in token:
        arah = "BULLISH" if t["arah"] > 0 else "BEARISH"
        judul = berita[t["nama"]]["berita"]
        baris = "\n".join(f"  - {b['judul']} ({b['sumber']}, {str(b['tanggal'])[:16]})" for b in judul) or "  (tidak ada berita ditemukan)"
        blok.append(f"{t['nama']} | pilihan: {arah} | ubah 24j: {t['ubah']:.2f}%\n{baris}")
    return """Kamu asisten analis berita untuk bot scalping futures. Di bawah ini judul berita terbaru (24 jam) untuk tiap token.

TUGAS: untuk tiap token nilai dampak berita ke arah harga, HANYA berdasarkan judul yang diberikan.
- dampak: "naik", "turun", "netral", atau "tidak jelas" (pakai "tidak jelas" jika tidak ada berita, atau judul tampak tidak terkait token itu karena nama ambigu).
- selaras: true jika dampak sejalan dengan arah pilihan (BULLISH=naik, BEARISH=turun), false jika berlawanan, null jika netral atau tidak jelas.
- katalis: satu kalimat maksimal 15 kata yang merangkum alasan dari judul, atau null.
- risiko: catatan risiko maksimal 10 kata, atau null.

ATURAN KERAS: jangan menambah informasi di luar judul. Jangan mengarang. Jawab HANYA JSON valid:
{"hasil":[{"simbol":"BTC","dampak":"naik","selaras":true,"katalis":"...","risiko":null}]}

DATA:
""" + "\n\n".join(blok)


def jalankan(n):
    ap.cek_jatah()
    token = muat_token(n)
    print(f"Mengambil berita untuk {len(token)} token dari RSS...")
    berita = br.ambil_banyak([t["nama"] for t in token], maks=3)
    ada = sum(1 for v in berita.values() if v["berita"])
    gagal = sum(1 for v in berita.values() if v["galat"])
    print(f"Berita ditemukan untuk {ada} dari {len(token)} token (gagal diambil: {gagal})")

    try:
        teks, jumlah_token = ap.panggil_ai(buat_prompt(token, berita))
    except Exception as ex:
        raise SystemExit(f"\nAI gagal: {type(ex).__name__}. Berita sudah tersimpan di cache (berita_cache.json), "
                         "jadi menjalankan ulang tidak mengambil berita lagi. Coba lagi nanti atau pakai model lain.")
    ap.catat_pakai(jumlah_token)
    
    jawaban = ap.ambil_json(teks)
    peta = {str(h.get("simbol", "")).split("/")[0].upper(): h for h in jawaban.get("hasil", [])}

    print(f"\n{'No':>2} {'Simbol':8} {'Arah':8} {'Ubah24j':>8} {'Dampak':11} {'Selaras':8} Katalis / Risiko")
    selaras = berlawanan = kabur = 0
    for i, t in enumerate(token, 1):
        h = peta.get(t["nama"], {})
        s = h.get("selaras")
        if s is True:
            selaras += 1
        elif s is False:
            berlawanan += 1
        else:
            kabur += 1
        catatan = " | ".join(x for x in (h.get("katalis"), h.get("risiko")) if x)
        print(f"{i:>2} {t['nama']:8} {'BULLISH' if t['arah'] > 0 else 'BEARISH':8} {t['ubah']:>7.2f}% "
              f"{str(h.get('dampak', '-')):11} {str(s) if s is not None else '-':8} {catatan}")

    print("\nBerita yang dipakai (cek sendiri kebenarannya):")
    for t in token:
        v = berita[t["nama"]]
        print(f"\n{t['nama']}" + (f"  [gagal: {v['galat']}]" if v["galat"] else ""))
        for b in v["berita"]:
            print(f"  - {b['judul']} ({b['sumber']})\n    {b['link']}")

    print(f"\nRINGKASAN: selaras {selaras} | berlawanan {berlawanan} | netral/tidak jelas {kabur}")
    if jumlah_token:
        print(f"Token panggilan ini: {jumlah_token} (sekitar {jumlah_token / len(token):.0f} per token)")
    pakai = ap._baca_pakai()
    print(f"Pemakaian hari ini: {pakai['token']} token, {pakai['jumlah']} panggilan "
          f"(batas harian gratis model ini 20 permintaan)")
    with open(FILE_HASIL, "w", encoding="utf-8") as f:
        json.dump({"token": token, "berita": berita, "jawaban": jawaban, "jumlah_token": jumlah_token},
                  f, indent=2, ensure_ascii=False)
    print(f"Tersimpan di {FILE_HASIL}")


if __name__ == "__main__":
    jumlah = 5
    if "--jumlah" in sys.argv:
        jumlah = int(sys.argv[sys.argv.index("--jumlah") + 1])
    jalankan(jumlah)
