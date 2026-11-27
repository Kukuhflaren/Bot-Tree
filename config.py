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

CANDLE_TIMEFRAME = os.getenv("CANDLE_TIMEFRAME", "5m").strip().lower()
if CANDLE_TIMEFRAME not in ("5m", "15m", "30m"):
    raise SystemExit("CANDLE_TIMEFRAME di .env harus 5m, 15m, atau 30m.")

DEMO_API = os.getenv("DEMO_API", "off").strip().lower() == "on"
DEMO_CONFIRM = os.getenv("DEMO_CONFIRM", "").strip()
DEMO_LOOP_EXECUTION_VERIFIED = os.getenv("DEMO_LOOP_EXECUTION_VERIFIED", "off").strip().lower() == "on"
DEMO_MAKER_FEE_BPS = _f("DEMO_MAKER_FEE_BPS", 6)
DEMO_TAKER_FEE_BPS = _f("DEMO_TAKER_FEE_BPS", 6)
DEMO_MIN_NET_BPS = _f("DEMO_MIN_NET_BPS", 15)
DEMO_MAX_SPREAD_BPS = _f("DEMO_MAX_SPREAD_BPS", 10)
DEMO_MIN_BOOK_DEPTH_MULTIPLE = _f("DEMO_MIN_BOOK_DEPTH_MULTIPLE", 5)
DEMO_MAX_HOLD_HOURS = _f("DEMO_MAX_HOLD_HOURS", 3)
DEMO_BOOK_MAX_AGE_SECONDS = _f("DEMO_BOOK_MAX_AGE_SECONDS", 3)
PAPER_FILL_THROUGH_BPS = _f("PAPER_FILL_THROUGH_BPS", 1)
PAPER_FILL_PARTICIPATION_PCT = _f("PAPER_FILL_PARTICIPATION_PCT", 1)

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
MODAL_DEMO_USDT = _f("MODAL_DEMO_USDT", 40)
MODAL_LIVE_USDT = _f("MODAL_LIVE_USDT", 40)
MODAL_USDT = MODAL_LIVE_USDT if MODE == "live" else MODAL_DEMO_USDT
LEVERAGE = _f("LEVERAGE", 4)
RISK_PER_SETUP_PCT = _f("RISK_PER_SETUP_PCT", 2.5)

# --- Strategi Trend + Range Grid (ATR Arithmetic) ---
ADX_PERIOD = int(_f("ADX_PERIOD", 14))
ADX_TREND_MIN = _f("ADX_TREND_MIN", 18)
ADX_SIDEWAYS_MAX = _f("ADX_SIDEWAYS_MAX", 18)
RANGE_MIN_ATR = _f("RANGE_MIN_ATR", 3.0)

GRID_SPACING_ATR = _f("GRID_SPACING_ATR", 0.45)
GRID_MAX_LEVELS = int(_f("GRID_MAX_LEVELS", 6))
SL_BUFFER_ATR = _f("SL_BUFFER_ATR", 0.35)

FEE_ROUNDTRIP_PCT = _f("FEE_ROUNDTRIP_PCT", 0.12)
RR_MIN = _f("RR_MIN", 1.1)
# Risk ATR ≈ (entry−SL)/ATR. Minimum praktis ≈ GRID_SPACING_ATR + SL_BUFFER_ATR.
# Jangan set RISK_ATR_MIN lebih besar dari itu atau level dekat HL/HH selalu ditolak.
RISK_ATR_MIN = _f("RISK_ATR_MIN", 0.5)
RISK_ATR_MAX = _f("RISK_ATR_MAX", 3.5)

# Kompatibilitas lama (masih dibaca beberapa modul)
TP_PERCENT = _f("TP_PERCENT", 0.25)
SL_POINTS = _f("SL_POINTS", 0)
TP_MODE = os.getenv("TP_MODE", "struktur").strip().lower()
if TP_MODE not in ("sr_lawan", "struktur", "persen"):
    raise SystemExit("TP_MODE di .env harus sr_lawan, struktur, atau persen.")
TP_METHOD = os.getenv("TP_METHOD", "sr").strip().lower()
if TP_METHOD not in ("sr", "atr"):
    raise SystemExit("TP_METHOD di .env harus sr atau atr.")
TP_ATR_PERCENT = _f("TP_ATR_PERCENT", 100.0)
SL_METHOD = os.getenv("SL_METHOD", "atr").strip().lower()
if SL_METHOD not in ("sr", "atr"):
    raise SystemExit("SL_METHOD di .env harus sr atau atr.")
SL_ATR_PERCENT = _f("SL_ATR_PERCENT", 35.0)
SCORE_MIN = _f("SCORE_MIN", 40)
NEAR_SR_PERCENT = _f("NEAR_SR_PERCENT", 0.5)
NEAR_MODE = os.getenv("NEAR_MODE", "atr").strip().lower()
if NEAR_MODE not in ("atr", "persen"):
    raise SystemExit("NEAR_MODE di .env harus atr atau persen.")
NEAR_ATR_MULT = _f("NEAR_ATR_MULT", 3.0)

# --- Pengaman ---
MAX_DAILY_LOSS_USDT = _f("MAX_DAILY_LOSS_USDT", 2.0)
MAX_OPEN_TOKENS = int(_f("MAX_OPEN_TOKENS", 1))
DRY_RUN = os.getenv("DRY_RUN", "on").strip().lower() != "off"
MAX_CONSECUTIVE_LOSSES = int(_f("MAX_CONSECUTIVE_LOSSES", 3))
KILL_SWITCH = os.getenv("KILL_SWITCH", "off").strip().lower() == "on"
MAX_HOLD_HOURS = _f("MAX_HOLD_HOURS", 3)

# --- Penyaring / universe ---
PENYARING_VOL_MIN_USDT = _f("PENYARING_VOL_MIN_USDT", 1000000)
PENYARING_TOP_VOLUME = int(_f("PENYARING_TOP_VOLUME", 100))
JUMLAH_PER_SISI = int(_f("JUMLAH_PER_SISI", 20))
UBAH_MAKS_SKOR = _f("UBAH_MAKS_SKOR", 20)
UBAH_IDEAL_SKOR = _f("UBAH_IDEAL_SKOR", 4)
EXCLUDE_RWA = os.getenv("EXCLUDE_RWA", "on").strip().lower() != "off"
WATCHLIST_MODE = os.getenv("WATCHLIST_MODE", "prefer").strip().lower()
if WATCHLIST_MODE not in ("off", "prefer", "only"):
    raise SystemExit("WATCHLIST_MODE di .env harus off, prefer, atau only.")
WATCHLIST_FILE = os.getenv("WATCHLIST_FILE", "watchlist.json").strip()

_raw_bl = os.getenv("TOKEN_BLACKLIST", "")
TOKEN_BLACKLIST = [x.strip().upper() for x in _raw_bl.split(",") if x.strip()]
