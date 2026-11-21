"""Server dashboard Bot-Tree (hanya library standar Python 3.10+).

Menyajikan bot-tree-dashboard.html dan endpoint /api/data yang membaca
state.json, signal.json, penilai_ai.json, paper_trades.jsonl dari folder bot.
Hanya MEMBACA file. Tidak memanggil exchange dan tidak mengirim order.

Jalankan:   python dashboard_server.py
Buka:       http://127.0.0.1:8765
Opsi:       --port 9000   --dir C:\\jalur\\Bot-Tree   --buka
"""
from __future__ import annotations

import argparse
import json
import threading
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HALAMAN = "bot-tree-dashboard.html"
STATE_FIELD = ("mode", "diperbarui", "modal_awal", "modal_saat_ini", "daily_pnl_usdt",
               "consecutive_losses", "total_trades", "total_wins", "total_losses")
JURNAL_FIELD = ("event", "timestamp", "net_pnl_usdt", "trade_id")
SYARAT = ("tren", "ema", "macd", "dekat_sr", "vwap", "tren_30m")
KOMPONEN = ("RSI", "EMA", "MACD", "SAR", "Candle")
MAKS_JURNAL = 5000


def baca_json(jalur: Path):
    try:
        return json.loads(jalur.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def baca_jurnal(jalur: Path) -> list[dict]:
    hasil: list[dict] = []
    try:
        baris = jalur.read_text(encoding="utf-8").splitlines()[-MAKS_JURNAL:]
    except OSError:
        return hasil
    for b in baris:
        try:
            e = json.loads(b)
        except ValueError:
            continue
        if isinstance(e, dict):
            hasil.append({k: e.get(k) for k in JURNAL_FIELD})
    return hasil


def waktu_file(jalur: Path) -> str | None:
    try:
        return datetime.fromtimestamp(jalur.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
    except OSError:
        return None


def baris_radar(penilai) -> list[list]:
    """Format ringkas sama dengan kartu Radar Token di halaman."""
    snap = (penilai or {}).get("snapshot") or []
    hasil = []
    for x in sorted(snap, key=lambda r: -(r.get("skor_bot") or 0))[:10]:
        try:
            kom, syr = x.get("komponen_dari_20", {}), x.get("syarat", {})
            hasil.append([
                x["simbol"], "U" if x.get("arah") == "BULLISH" else "D", x.get("harga", 0),
                x.get("skor_bot", 0), x.get("zona", "-"),
                [kom.get(k, 0) for k in KOMPONEN], [int(bool(syr.get(k))) for k in SYARAT],
                x.get("rsi", 0), x.get("atr_persen", 0),
            ])
        except (KeyError, TypeError):
            continue
    return hasil


def kumpulkan(folder: Path) -> dict:
    state = baca_json(folder / "state.json")
    return {
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "signal": baca_json(folder / "signal.json"),
        "rows": baris_radar(baca_json(folder / "penilai_ai.json")),
        "state": {k: state.get(k) for k in STATE_FIELD if k in state} if isinstance(state, dict) else None,
        "journal": baca_jurnal(folder / "paper_trades.jsonl"),
        "files": {n: waktu_file(folder / n) for n in
                  ("state.json", "signal.json", "penilai_ai.json", "paper_trades.jsonl")},
    }


def buat_handler(folder: Path, halaman: Path):
    class H(BaseHTTPRequestHandler):
        def _kirim(self, kode: int, tipe: str, isi: bytes):
            self.send_response(kode)
            self.send_header("Content-Type", tipe)
            self.send_header("Content-Length", str(len(isi)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(isi)

        def do_GET(self):  # noqa: N802
            jalur = self.path.split("?", 1)[0]
            if jalur in ("/", "/index.html", "/" + HALAMAN):
                try:
                    self._kirim(200, "text/html; charset=utf-8", halaman.read_bytes())
                except OSError:
                    self._kirim(404, "text/plain; charset=utf-8", f"{HALAMAN} tidak ditemukan".encode())
            elif jalur == "/api/data":
                isi = json.dumps(kumpulkan(folder), ensure_ascii=False).encode("utf-8")
                self._kirim(200, "application/json; charset=utf-8", isi)
            else:  # daftar putih: .env dan file lain tidak pernah disajikan
                self._kirim(404, "text/plain; charset=utf-8", b"Tidak ditemukan")

        def log_message(self, *args):  # log senyap
            pass

    return H


def main() -> None:
    skrip = Path(__file__).resolve().parent
    p = argparse.ArgumentParser(description="Dashboard Bot-Tree (baca-saja)")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--host", default="127.0.0.1", help="biarkan 127.0.0.1 agar hanya laptop ini yang bisa akses")
    p.add_argument("--dir", default=str(skrip), help="folder berisi state.json dan signal.json")
    p.add_argument("--buka", action="store_true", help="buka browser otomatis")
    a = p.parse_args()
    folder = Path(a.dir).resolve()
    halaman = skrip / HALAMAN if (skrip / HALAMAN).exists() else folder / HALAMAN
    srv = ThreadingHTTPServer((a.host, a.port), buat_handler(folder, halaman))
    url = f"http://{a.host}:{a.port}"
    print(f"Dashboard Bot-Tree aktif di {url}  (baca dari {folder})\nTekan Ctrl+C untuk berhenti.")
    if a.buka:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nBerhenti.")
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
