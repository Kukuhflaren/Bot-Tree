"""Tes cepat: apakah API key dan model AI bekerja, berapa lama responsnya, dan berapa token terpakai.
Hanya memakai beberapa token. Tidak dihitung dalam jatah harian."""
import time

import ai_pemilih as ap
import config

print(f"Penyedia: {config.AI_PROVIDER} | Model: {config.AI_MODEL or ap.MODEL_BAWAAN.get(config.AI_PROVIDER, '(kosong)')}")
mulai = time.time()
try:
    teks, token = ap.panggil_ai('Balas HANYA dengan JSON: {"ok": true}')
    print(f"Berhasil dalam {time.time() - mulai:.1f} detik. Token terpakai: {token}")
    print("Jawaban:", teks.strip()[:200])
except Exception as e:
    print(f"Gagal setelah {time.time() - mulai:.1f} detik: {type(e).__name__}: {e}")
