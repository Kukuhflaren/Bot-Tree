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
AI_MAX_CALLS_PER_DAY = int(_f("AI_MAX_CALLS_PER_DAY", 24))

MODAL_USDT = _f("MODAL_USDT", 25)
LEVERAGE = _f("LEVERAGE", 5)
TP_PERCENT = _f("TP_PERCENT", 0.25)
SL_POINTS = _f("SL_POINTS", 50)
SCORE_MIN = _f("SCORE_MIN", 50)
NEAR_SR_PERCENT = _f("NEAR_SR_PERCENT", 0.5)

MAX_DAILY_LOSS_USDT = _f("MAX_DAILY_LOSS_USDT", 2)
MAX_OPEN_TOKENS = int(_f("MAX_OPEN_TOKENS", 1))
DRY_RUN = os.getenv("DRY_RUN", "on").strip().lower() != "off"
MAX_CONSECUTIVE_LOSSES = int(_f("MAX_CONSECUTIVE_LOSSES", 3))
KILL_SWITCH = os.getenv("KILL_SWITCH", "off").strip().lower() == "on"
