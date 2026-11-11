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
AI_MODEL_CARI = os.getenv("AI_MODEL_CARI", "").strip()
AI_MAX_CALLS_PER_DAY = int(_f("AI_MAX_CALLS_PER_DAY", 24))
AI_MAX_TOKENS_PER_HARI = int(_f("AI_MAX_TOKENS_PER_HARI", 30000))

MODAL_DEMO_USDT = _f("MODAL_DEMO_USDT", 10)
MODAL_LIVE_USDT = _f("MODAL_LIVE_USDT", 5)
MODAL_USDT = MODAL_LIVE_USDT if MODE == "live" else MODAL_DEMO_USDT
LEVERAGE = _f("LEVERAGE", 5)
# Persen modal yang dialokasikan per setup (margin). Notional ≈ margin * leverage.
RISK_PER_SETUP_PCT = _f("RISK_PER_SETUP_PCT", 5.0)
TP_PERCENT = _f("TP_PERCENT", 0.25)  # cadangan; TP utama di S/R lawan (kerangka v2)
SL_POINTS = _f("SL_POINTS", 50)
SCORE_MIN = _f("SCORE_MIN", 50)
RR_MIN = _f("RR_MIN", 1.0)
RISK_ATR_MIN = _f("RISK_ATR_MIN", 1.0)
RISK_ATR_MAX = _f("RISK_ATR_MAX", 2.5)
NEAR_SR_PERCENT = _f("NEAR_SR_PERCENT", 0.5)
NEAR_MODE = os.getenv("NEAR_MODE", "atr").strip().lower()
if NEAR_MODE not in ("atr", "persen"):
    raise SystemExit("NEAR_MODE di .env harus atr atau persen.")
NEAR_ATR_MULT = _f("NEAR_ATR_MULT", 2.5)

MAX_DAILY_LOSS_USDT = _f("MAX_DAILY_LOSS_USDT", 2)
MAX_OPEN_TOKENS = int(_f("MAX_OPEN_TOKENS", 1))
DRY_RUN = os.getenv("DRY_RUN", "on").strip().lower() != "off"
MAX_CONSECUTIVE_LOSSES = int(_f("MAX_CONSECUTIVE_LOSSES", 3))
KILL_SWITCH = os.getenv("KILL_SWITCH", "off").strip().lower() == "on"

# --- Penyaring / universe ---
PENYARING_VOL_MIN_USDT = _f("PENYARING_VOL_MIN_USDT", 5000000)
PENYARING_TOP_VOLUME = int(_f("PENYARING_TOP_VOLUME", 60))
JUMLAH_PER_SISI = int(_f("JUMLAH_PER_SISI", 20))
UBAH_MAKS_SKOR = _f("UBAH_MAKS_SKOR", 0)
# off = semua (minus blacklist) | only = hanya isi watchlist.json
WATCHLIST_MODE = os.getenv("WATCHLIST_MODE", "only").strip().lower()
if WATCHLIST_MODE not in ("off", "only"):
    raise SystemExit("WATCHLIST_MODE di .env harus off atau only.")
WATCHLIST_FILE = os.getenv("WATCHLIST_FILE", "watchlist.json").strip()

_raw_bl = os.getenv(
    "TOKEN_BLACKLIST",
    "CSOP,CSOPSK,2L,2S,3L,3S,5L,5S,UP,DOWN,BULL,BEAR,"
    "NVDA,TSLA,AAPL,MSFT,GOOGL,META,AMZN,AMD,INTC,COIN,MSTR,QQQ,SPY,TQQQ,SQQQ,"
    "SOXL,SOXS,XAU,XAG,XAUT,PAXG,CL,BZ,NATGAS,COPPER,SP500,SPX",
)
TOKEN_BLACKLIST = [x.strip().upper() for x in _raw_bl.split(",") if x.strip()]
