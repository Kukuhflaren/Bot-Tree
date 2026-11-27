"""Membaca semua pengaturan dari file .env. Tidak ada API key di dalam kode."""
import os
import sys

from dotenv import load_dotenv

load_dotenv()  # membaca file .env di folder yang sama


def _siapkan_konsol() -> None:
    """Windows memakai cp1252 saat stdout di-pipe. UTF-8 mencegah UnicodeEncodeError pada log."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            continue


_siapkan_konsol()


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

CANDLE_TIMEFRAME = os.getenv("CANDLE_TIMEFRAME", "").strip().lower()
if CANDLE_TIMEFRAME not in ("5m", "15m", "30m"):
    raise SystemExit("CANDLE_TIMEFRAME di .env harus 5m, 15m, atau 30m.")

DEMO_API = os.getenv("DEMO_API", "off").strip().lower() == "on"
DEMO_CONFIRM = os.getenv("DEMO_CONFIRM", "").strip()
DEMO_LOOP_EXECUTION_VERIFIED = os.getenv("DEMO_LOOP_EXECUTION_VERIFIED", "off").strip().lower() == "on"
DEMO_MAKER_FEE_BPS = os.getenv("DEMO_MAKER_FEE_BPS", "")
DEMO_TAKER_FEE_BPS = os.getenv("DEMO_TAKER_FEE_BPS", "")
DEMO_MIN_NET_BPS = os.getenv("DEMO_MIN_NET_BPS", "")
DEMO_MAX_SPREAD_BPS = os.getenv("DEMO_MAX_SPREAD_BPS", "")
DEMO_MIN_BOOK_DEPTH_MULTIPLE = os.getenv("DEMO_MIN_BOOK_DEPTH_MULTIPLE", "")
DEMO_MAX_HOLD_HOURS = os.getenv("DEMO_MAX_HOLD_HOURS", "")
DEMO_BOOK_MAX_AGE_SECONDS = os.getenv("DEMO_BOOK_MAX_AGE_SECONDS", "")
PAPER_FILL_THROUGH_BPS = os.get.env("PAPER_FILL_THROUGH_BPS", "")
PAPER_FILL_PARTICIPATION_PCT = os.getenv("PAPER_FILL_PARTICIPATION_PCT", "")

BITGET_API_KEY = os.getenv("BITGET_API_KEY", "")
BITGET_SECRET_KEY = os.getenv("BITGET_SECRET_KEY", "")
BITGET_PASSPHRASE = os.getenv("BITGET_PASSPHRASE", "")
BITGET_UTA = os.getenv("BITGET_UTA", "on").strip().lower() != "off"

AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini").strip().lower()
AI_ENABLED = os.getenv("USE_AI", "off").strip().lower() == "on"
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

# --- Modal & Risk (rekomendasi strategi baru) ---
MODAL_DEMO_USDT = os.getenv("MODAL_DEMO_USDT", "")
MODAL_LIVE_USDT = os.getenv("MODAL_LIVE_USDT", "")
MODAL_USDT = MODAL_LIVE_USDT if MODE == "live" else MODAL_DEMO_USDT
LEVERAGE = os.getenv("LEVERAGE", "")
RISK_PER_SETUP_PCT = os.getenv("RISK_PER_SETUP_PCT", "")

# --- Strategi Trend + Range Grid (ATR Arithmetic) ---
ADX_PERIOD = int(os.getenv("ADX_PERIOD", ""))
ADX_TREND_MIN = os.getenv("ADX_TREND_MIN", "")
ADX_SIDEWAYS_MAX = os.getenv("ADX_SIDEWAYS_MAX", "")
RANGE_MIN_ATR = os.getenv("RANGE_MIN_ATR", "")

GRID_SPACING_ATR = os.getenv("GRID_SPACING_ATR", "")
GRID_MAX_LEVELS = int(os.getenv("GRID_MAX_LEVELS", ""))
SL_BUFFER_ATR = os.getenv("SL_BUFFER_ATR", "")

FEE_ROUNDTRIP_PCT = os.getenv("FEE_ROUNDTRIP_PCT", "")
RR_MIN = os.getenv("RR_MIN", "")
# Risk ATR ≈ (entry−SL)/ATR. Minimum praktis ≈ GRID_SPACING_ATR + SL_BUFFER_ATR.
# Jangan set RISK_ATR_MIN lebih besar dari itu atau level dekat HL/HH selalu ditolak.
RISK_ATR_MIN = os.getenv("RISK_ATR_MIN", "")
RISK_ATR_MAX = os.getenv("RISK_ATR_MAX", "")

# Kompatibilitas lama (masih dibaca beberapa modul)
TP_PERCENT = os.getenv("TP_PERCENT", "")
SL_POINTS = os.getenv("SL_POINTS", "")
TP_MODE = os.getenv("TP_MODE", "struktur").strip().lower()
if TP_MODE not in ("sr_lawan", "struktur", "persen"):
    raise SystemExit("TP_MODE di .env harus sr_lawan, struktur, atau persen.")
TP_METHOD = os.getenv("TP_METHOD", "sr").strip().lower()
if TP_METHOD not in ("sr", "atr"):
    raise SystemExit("TP_METHOD di .env harus sr atau atr.")
TP_ATR_PERCENT = os.getenv("TP_ATR_PERCENT", "")
SL_METHOD = os.getenv("SL_METHOD", "atr").strip().lower()
if SL_METHOD not in ("sr", "atr"):
    raise SystemExit("SL_METHOD di .env harus sr atau atr.")
SL_ATR_PERCENT = os.getenv("SL_ATR_PERCENT", "")
SCORE_MIN = os.getenv("SCORE_MIN", "")
NEAR_SR_PERCENT = os.getenv("NEAR_SR_PERCENT", "")
NEAR_MODE = os.getenv("NEAR_MODE", "atr").strip().lower()
if NEAR_MODE not in ("atr", "persen"):
    raise SystemExit("NEAR_MODE di .env harus atr atau persen.")
NEAR_ATR_MULT = os.getenv("NEAR_ATR_MULT", "")

# --- Pengaman ---
MAX_DAILY_LOSS_USDT = os.getenv("MAX_DAILY_LOSS_USDT", "")
MAX_OPEN_TOKENS = int(os.getenv("MAX_OPEN_TOKENS", ""))
DRY_RUN = os.getenv("DRY_RUN", "on").strip().lower() != "off"
MAX_CONSECUTIVE_LOSSES = int(os.getenv("MAX_CONSECUTIVE_LOSSES", ""))
KILL_SWITCH = os.getenv("KILL_SWITCH", "off").strip().lower() == "on"
MAX_HOLD_HOURS = os.getenv("MAX_HOLD_HOURS", "")

# --- Penyaring / universe ---
PENYARING_VOL_MIN_USDT = os.getenv("PENYARING_VOL_MIN_USDT", "")
PENYARING_TOP_VOLUME = int(os.getenv("PENYARING_TOP_VOLUME", ""))
JUMLAH_PER_SISI = int(os.getenv("JUMLAH_PER_SISI", ""))
UBAH_MAKS_SKOR = os.getenv("UBAH_MAKS_SKOR", "")
UBAH_IDEAL_SKOR = os.getenv("UBAH_IDEAL_SKOR", "")
EXCLUDE_RWA = os.getenv("EXCLUDE_RWA", "on").strip().lower() != "off"
WATCHLIST_MODE = os.getenv("WATCHLIST_MODE", "prefer").strip().lower()
if WATCHLIST_MODE not in ("off", "prefer", "only"):
    raise SystemExit("WATCHLIST_MODE di .env harus off, prefer, atau only.")
WATCHLIST_FILE = os.getenv("WATCHLIST_FILE", "watchlist.json").strip()

_raw_bl = os.getenv("TOKEN_BLACKLIST", "")
TOKEN_BLACKLIST = [x.strip().upper() for x in _raw_bl.split(",") if x.strip()]
