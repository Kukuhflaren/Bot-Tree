"""Membaca semua pengaturan dari file .env. Tidak ada API key di dalam kode."""
import os
from dotenv import load_dotenv

load_dotenv()  # membaca file .env di folder yang sama


def _f(nama, default):
    try:
        return float(os.getenv(nama, default))
    except ValueError:
        raise SystemExit(f"Nilai {nama} di .env bukan angka.")


MODE = os.getenv("MODE", "paper").strip().lower()
if MODE not in ("paper", "demo", "live"):
    raise SystemExit("MODE di .env harus paper, demo, atau live.")
if MODE == "live" and os.getenv("LIVE_CONFIRM", "") != "SAYA_PAHAM_RISIKONYA":
    raise SystemExit("MODE=live butuh LIVE_CONFIRM=SAYA_PAHAM_RISIKONYA di .env.")

BITGET_API_KEY = os.getenv("BITGET_API_KEY", "")
BITGET_SECRET_KEY = os.getenv("BITGET_SECRET_KEY", "")
BITGET_PASSPHRASE = os.getenv("BITGET_PASSPHRASE", "")
BITGET_UTA = os.getenv("BITGET_UTA", "on").strip().lower() != "off"

AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini").strip().lower()
AI_KEYS = {
    "gemini": os.getenv("GEMINI_API_KEY", ""),
    "claude": os.getenv("ANTHROPIC_API_KEY", ""),
    "grok": os.getenv("XAI_API_KEY", ""),
    "gpt": os.getenv("OPENAI_API_KEY", ""),
}
AI_MODEL = os.getenv("AI_MODEL", "").strip()
AI_MODEL_CARI = os.getenv("AI_MODEL_CARI", "").strip()  # model khusus untuk eksperimen dengan pencarian Google
AI_MAX_CALLS_PER_DAY = int(_f("AI_MAX_CALLS_PER_DAY", 24))
AI_MAX_TOKENS_PER_HARI = int(_f("AI_MAX_TOKENS_PER_HARI", 30000))

MODAL_DEMO_USDT = _f("MODAL_DEMO_USDT", 10)
MODAL_LIVE_USDT = _f("MODAL_LIVE_USDT", 5)
MODAL_USDT = MODAL_LIVE_USDT if MODE == "live" else MODAL_DEMO_USDT
LEVERAGE = _f("LEVERAGE", 5)
TP_PERCENT = _f("TP_PERCENT", 0.25)  # legacy; TP utama sekarang di HH/HL
SL_POINTS = _f("SL_POINTS", 50)
SCORE_MIN = _f("SCORE_MIN", 50)
RR_MIN = _f("RR_MIN", 1.0)  # minimum reward:risk per titik grid (setelah TP di HH/HL)
NEAR_SR_PERCENT = _f("NEAR_SR_PERCENT", 0.5)
NEAR_MODE = os.getenv("NEAR_MODE", "atr").strip().lower()
if NEAR_MODE not in ("atr", "persen"):
    raise SystemExit("NEAR_MODE di .env harus atr atau persen.")
NEAR_ATR_MULT = _f("NEAR_ATR_MULT", 1.5)

MAX_DAILY_LOSS_USDT = _f("MAX_DAILY_LOSS_USDT", 2)
MAX_OPEN_TOKENS = int(_f("MAX_OPEN_TOKENS", 1))
DRY_RUN = os.getenv("DRY_RUN", "on").strip().lower() != "off"
MAX_CONSECUTIVE_LOSSES = int(_f("MAX_CONSECUTIVE_LOSSES", 3))

# --- Penyaring 24 jam  ---
PENYARING_VOL_MIN_USDT = _f("PENYARING_VOL_MIN_USDT", 5000000)
PENYARING_TOP_VOLUME = int(_f("PENYARING_TOP_VOLUME", 60))
JUMLAH_PER_SISI = int(_f("JUMLAH_PER_SISI", 20))
UBAH_MAKS_SKOR = _f("UBAH_MAKS_SKOR", 0)
KILL_SWITCH = os.getenv("KILL_SWITCH", "off").strip().lower() == "on"
