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
import os
import secrets
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
import uuid
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
AKSI_SAFE = {
    "scan_once": ("scanner.py", ["--sekali"]),
    "scanner_start": ("scanner.py", ["--interval", "300"]),
    "paper_status": ("paper.py", ["--status"]),
    "paper_cycle": ("paper.py", []),
    "paper_loop": ("paper.py", ["--loop", "--interval", "60"]),
    "refresh_filter": ("penyaring.py", []),
    "refresh_signal": ("signal_engine.py", []),
    "refresh_radar": ("penilai_ai.py", ["--jumlah", "8"]),
    "cek_kelayakan": ("cek_kelayakan.py", []),
    "cek_risk_universe": ("cek_risk_universe.py", []),
    "ai_kelayakan": ("ai_kelayakan.py", []),
    "uji_paper_demo": ("uji_paper_demo.py", ["--once"]),
    "uji_demo_unified": ("uji_demo_unified.py", ["--once"]),
}
AKSI_LIVE = {"live_scan_once", "live_scanner_start"}


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


def baris_penyaringan(folder: Path, penilai) -> list[dict]:
    data = baca_json(folder / "daftar_40.json")
    if not isinstance(data, dict):
        return []
    scores = {}
    for row in ((penilai or {}).get("snapshot") or []):
        if isinstance(row, dict) and row.get("simbol"):
            scores[str(row["simbol"]).strip().upper()] = row
    hasil = []
    seen = set()
    for sisi in ("bullish", "bearish"):
        for row in data.get(sisi, []) or []:
            if not isinstance(row, dict):
                continue
            simbol = str(row.get("simbol") or "").strip().upper()
            base = simbol.split("/")[0]
            if not base or base in seen:
                continue
            seen.add(base)
            score_row = scores.get(base)
            hasil.append({
                "simbol": base,
                "symbol_full": simbol,
                "arah": "BULLISH" if sisi == "bullish" else "BEARISH",
                "harga": row.get("harga"),
                "ubah_24j": row.get("ubah_24j"),
                "volume_24j_usdt": row.get("vol_24j_usdt"),
                "rasio_volume": row.get("rasio_vol"),
                "skor_bot": score_row.get("skor_bot") if score_row else None,
                "zona": score_row.get("zona") if score_row else None,
                "prioritas_watchlist": bool(row.get("prioritas_watchlist")),
            })
    return hasil


def kumpulkan(folder: Path) -> dict:
    state = baca_json(folder / "state.json")
    penilai = baca_json(folder / "penilai_ai.json")
    config_dashboard = baca_json(folder / "dashboard_config.json") or {}
    timeframe = config_dashboard.get("timeframe") or os.getenv("CANDLE_TIMEFRAME", "30m").lower()
    if timeframe not in ("5m", "15m", "30m"):
        timeframe = "30m"
    return {
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "signal": baca_json(folder / "signal.json"),
        "rows": baris_radar(penilai),
        "candidates": baris_penyaringan(folder, penilai),
        "timeframe": timeframe,
        "tp_method": config_dashboard.get("tp_method", os.getenv("TP_METHOD", "sr")),
        "tp_atr_percent": config_dashboard.get("tp_atr_percent", float(os.getenv("TP_ATR_PERCENT", "100"))),
        "sl_method": config_dashboard.get("sl_method", os.getenv("SL_METHOD", "atr")),
        "sl_atr_percent": config_dashboard.get("sl_atr_percent", float(os.getenv("SL_ATR_PERCENT", "50"))),
        "state": {k: state.get(k) for k in STATE_FIELD if k in state} if isinstance(state, dict) else None,
        "journal": baca_jurnal(folder / "paper_trades.jsonl"),
        "files": {n: waktu_file(folder / n) for n in
                  ("state.json", "signal.json", "penilai_ai.json", "paper_trades.jsonl")},
    }


class KontrolBot:
    def __init__(self, folder: Path, token: str, telegram_token: str = "", telegram_chat_id: str = ""):
        self.folder = folder
        self.token = token
        self.telegram_token = telegram_token
        self.telegram_chat_id = telegram_chat_id
        saved = baca_json(folder / "dashboard_config.json") or {}
        self.timeframe = saved.get("timeframe", "30m")
        if self.timeframe not in ("5m", "15m", "30m"):
            self.timeframe = "30m"
        self.tp_method = saved.get("tp_method", os.getenv("TP_METHOD", "sr"))
        self.tp_atr_percent = float(saved.get("tp_atr_percent", os.getenv("TP_ATR_PERCENT", "100")))
        self.sl_method = saved.get("sl_method", os.getenv("SL_METHOD", "atr"))
        self.sl_atr_percent = float(saved.get("sl_atr_percent", os.getenv("SL_ATR_PERCENT", "50")))
        self.jobs: dict[str, dict] = {}
        self.processes: dict[str, subprocess.Popen] = {}
        self.pending: dict[str, dict] = {}
        self.telegram_offset = None
        if telegram_token:
            threading.Thread(target=self._telegram_loop, daemon=True).start()

    def sah(self, handler) -> bool:
        return secrets.compare_digest(handler.headers.get("X-Bot-Token", ""), self.token)

    def _telegram_request(self, method: str, payload: dict) -> dict:
        url = f"https://api.telegram.org/bot{self.telegram_token}/{method}"
        data = urllib.parse.urlencode(payload).encode("utf-8")
        request = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))

    def kirim_persetujuan(self, approval_id: str, aksi: str) -> tuple[bool, str]:
        if not self.telegram_token or not self.telegram_chat_id:
            return False, "Telegram belum dikonfigurasi"
        keyboard = json.dumps({"inline_keyboard": [[
            {"text": "SETUJUI LIVE", "callback_data": f"approve:{approval_id}"},
            {"text": "TOLAK", "callback_data": f"reject:{approval_id}"},
        ]]})
        payload = {
            "chat_id": self.telegram_chat_id,
            "text": f"Persetujuan LIVE Bot-Tree\nAksi: {aksi}\nBerakhir 5 menit.",
            "reply_markup": keyboard,
        }
        try:
            result = self._telegram_request("sendMessage", payload)
            return (True, "Persetujuan dikirim ke Telegram") if result.get("ok") else (False, "Gagal mengirim Telegram")
        except Exception as exc:
            return False, f"Gagal mengirim Telegram: {type(exc).__name__}"

    def _telegram_loop(self):
        while True:
            try:
                params = {"timeout": "20", "allowed_updates": '["callback_query"]'}
                if self.telegram_offset is not None:
                    params["offset"] = str(self.telegram_offset)
                url = f"https://api.telegram.org/bot{self.telegram_token}/getUpdates?" + urllib.parse.urlencode(params)
                with urllib.request.urlopen(url, timeout=25) as response:
                    result = json.loads(response.read().decode("utf-8"))
                if not result.get("ok"):
                    time.sleep(5)
                    continue
                for update in result.get("result", []):
                    self.telegram_offset = update["update_id"] + 1
                    query = update.get("callback_query")
                    if not query:
                        continue
                    chat_id = str(query.get("message", {}).get("chat", {}).get("id", ""))
                    if chat_id and chat_id != str(self.telegram_chat_id):
                        continue
                    data = query.get("data", "")
                    if ":" not in data:
                        continue
                    keputusan, approval_id = data.split(":", 1)
                    item = self.pending.get(approval_id)
                    if item:
                        item["status"] = "approved" if keputusan == "approve" else "rejected"
                    try:
                        self._telegram_request("answerCallbackQuery", {"callback_query_id": query["id"], "text": "Diproses"})
                    except Exception:
                        pass
            except Exception:
                time.sleep(5)

    def jalankan_job(self, name: str, script: str, extra_args: list[str], diizinkan_live: bool = False):
        if diizinkan_live:
            state = baca_json(self.folder / "state.json") or {}
            if state.get("mode") != "live":
                return None, "Aksi live ditolak: state.json tidak berada pada mode live"
        job_id = uuid.uuid4().hex[:12]
        job = {"id": job_id, "name": name, "status": "running", "output": "", "exit": None}
        self.jobs[job_id] = job

        def worker():
            try:
                env = os.environ.copy()
                env["CANDLE_TIMEFRAME"] = self.timeframe
                env["TP_METHOD"] = self.tp_method
                env["TP_ATR_PERCENT"] = str(self.tp_atr_percent)
                env["SL_METHOD"] = self.sl_method
                env["SL_ATR_PERCENT"] = str(self.sl_atr_percent)
                env["TP_METHOD"] = self.tp_method
                env["TP_ATR_PERCENT"] = str(self.tp_atr_percent)
                env["SL_METHOD"] = self.sl_method
                env["SL_ATR_PERCENT"] = str(self.sl_atr_percent)
                process = subprocess.Popen(
                    [sys.executable, str(self.folder / script), *extra_args],
                    cwd=str(self.folder),
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                self.processes[name] = process
                output = process.communicate(timeout=600)[0]
                job["output"] = output[-10000:]
                job["exit"] = process.returncode
                job["status"] = "done" if process.returncode == 0 else "failed"
            except subprocess.TimeoutExpired:
                process.kill()
                job["status"] = "failed"
                job["output"] = "Job dihentikan setelah 10 menit."
            except Exception as exc:
                job["status"] = "failed"
                job["output"] = f"{type(exc).__name__}: {exc}"
            finally:
                self.processes.pop(name, None)

        threading.Thread(target=worker, daemon=True).start()
        return job_id, "Job dimulai"

    def mulai_scanner(self, name: str, live: bool = False):
        if name in self.processes:
            return None, "Scanner sudah berjalan"
        job_id = uuid.uuid4().hex[:12]
        job = {"id": job_id, "name": name, "status": "running", "output": "", "exit": None}
        self.jobs[job_id] = job

        def worker():
            try:
                env = os.environ.copy()
                env["CANDLE_TIMEFRAME"] = self.timeframe
                process = subprocess.Popen(
                    [sys.executable, str(self.folder / "scanner.py"), "--interval", "300"],
                    cwd=str(self.folder),
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                self.processes[name] = process
                output = process.communicate()[0]
                job["output"] = output[-10000:]
                job["exit"] = process.returncode
                job["status"] = "stopped"
            except Exception as exc:
                job["status"] = "failed"
                job["output"] = f"{type(exc).__name__}: {exc}"
            finally:
                self.processes.pop(name, None)

        threading.Thread(target=worker, daemon=True).start()
        return job_id, "Scanner dimulai"

    def stop_scanner(self) -> tuple[bool, str]:
        process = self.processes.get("scanner") or self.processes.get("live_scanner")
        if not process:
            return False, "Scanner tidak berjalan"
        process.terminate()
        return True, "Permintaan stop dikirim"

    def set_timeframe(self, timeframe: str) -> tuple[bool, str]:
        if timeframe not in ("5m", "15m", "30m"):
            return False, "Timeframe harus 5m, 15m, atau 30m"
        self.timeframe = timeframe
        try:
            saved = baca_json(self.folder / "dashboard_config.json") or {}
            saved["timeframe"] = timeframe
            jalur = self.folder / "dashboard_config.json"
            jalur.write_text(json.dumps(saved, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError as exc:
            return False, f"Pilihan tidak tersimpan: {type(exc).__name__}"
        return True, f"Timeframe candle diubah ke {timeframe}"

    def set_strategy(self, payload: dict) -> tuple[bool, str]:
        tp_method = str(payload.get("tp_method", "")).lower()
        sl_method = str(payload.get("sl_method", "")).lower()
        if tp_method not in ("sr", "atr") or sl_method not in ("sr", "atr"):
            return False, "Pilihan TP/SL harus sr atau atr"
        try:
            tp_atr_percent = float(payload.get("tp_atr_percent", self.tp_atr_percent))
            sl_atr_percent = float(payload.get("sl_atr_percent", self.sl_atr_percent))
        except (TypeError, ValueError):
            return False, "Persentase ATR TP/SL harus berupa angka"
        if not (1 <= tp_atr_percent <= 500 and 1 <= sl_atr_percent <= 500):
            return False, "Persentase ATR TP/SL harus antara 1% dan 500%"

        self.tp_method = tp_method
        self.tp_atr_percent = tp_atr_percent
        self.sl_method = sl_method
        self.sl_atr_percent = sl_atr_percent
        try:
            saved = baca_json(self.folder / "dashboard_config.json") or {}
            saved.update({
                "tp_method": tp_method,
                "tp_atr_percent": tp_atr_percent,
                "sl_method": sl_method,
                "sl_atr_percent": sl_atr_percent,
            })
            (self.folder / "dashboard_config.json").write_text(
                json.dumps(saved, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except OSError as exc:
            return False, f"Pilihan tidak tersimpan: {type(exc).__name__}"
        return True, "Pilihan TP/SL diperbarui"

    def minta_live(self, aksi: str) -> dict:
        approval_id = secrets.token_urlsafe(18)
        item = {"status": "pending", "aksi": aksi, "created": time.time()}
        self.pending[approval_id] = item
        terkirim, pesan = self.kirim_persetujuan(approval_id, aksi)
        if not terkirim:
            item["status"] = "failed"
        return {"approval_id": approval_id, "status": item["status"], "message": pesan}

    def status(self) -> dict:
        now = time.time()
        for approval_id, item in list(self.pending.items()):
            if now - item["created"] > 300 and item["status"] == "pending":
                item["status"] = "expired"
        return {
            "mode": (baca_json(self.folder / "state.json") or {}).get("mode"),
            "timeframe": self.timeframe,
            "tp_method": self.tp_method,
            "tp_atr_percent": self.tp_atr_percent,
            "sl_method": self.sl_method,
            "sl_atr_percent": self.sl_atr_percent,
            "scanner": bool(self.processes.get("scanner") or self.processes.get("live_scanner")),
            "telegram_configured": bool(self.telegram_token and self.telegram_chat_id),
            "jobs": list(self.jobs.values())[-20:],
            "pending": [
                {"approval_id": key, "status": value["status"], "aksi": value["aksi"]}
                for key, value in self.pending.items()
            ][-20:],
        }


def buat_handler(folder: Path, halaman: Path, cors_origin: str = "", kontrol: KontrolBot | None = None):
    class H(BaseHTTPRequestHandler):
        def _kirim(self, kode: int, tipe: str, isi: bytes):
            self.send_response(kode)
            self.send_header("Content-Type", tipe)
            self.send_header("Content-Length", str(len(isi)))
            self.send_header("Cache-Control", "no-store")
            if cors_origin:
                self.send_header("Access-Control-Allow-Origin", cors_origin)
                self.send_header("Vary", "Origin")
            self.end_headers()
            self.wfile.write(isi)

        def do_OPTIONS(self):  # noqa: N802
            if cors_origin:
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", cors_origin)
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Bot-Token")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
            else:
                self._kirim(404, "text/plain; charset=utf-8", b"Tidak ditemukan")

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
            elif jalur == "/api/control/status" and kontrol:
                if not kontrol.sah(self):
                    self._kirim(401, "application/json; charset=utf-8", b'{"error":"token tidak sah"}')
                else:
                    isi = json.dumps(kontrol.status(), ensure_ascii=False).encode("utf-8")
                    self._kirim(200, "application/json; charset=utf-8", isi)
            else:  # daftar putih: .env dan file lain tidak pernah disajikan
                self._kirim(404, "text/plain; charset=utf-8", b"Tidak ditemukan")

        def do_POST(self):  # noqa: N802
            if not kontrol:
                self._kirim(404, "text/plain; charset=utf-8", b"Tidak ditemukan")
                return
            if self.path.split("?", 1)[0] != "/api/control":
                self._kirim(404, "text/plain; charset=utf-8", b"Tidak ditemukan")
                return
            if not kontrol.sah(self):
                self._kirim(401, "application/json; charset=utf-8", b'{"error":"token tidak sah"}')
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                aksi = payload.get("action")
            except (ValueError, json.JSONDecodeError):
                self._kirim(400, "application/json; charset=utf-8", b'{"error":"payload JSON tidak valid"}')
                return

            if aksi in ("set_timeframe_5m", "set_timeframe_15m", "set_timeframe_30m"):
                timeframe = aksi.removeprefix("set_timeframe_")
                ok, pesan = kontrol.set_timeframe(timeframe)
                hasil = {"ok": ok, "message": pesan, "timeframe": kontrol.timeframe}
            elif aksi == "set_strategy":
                ok, pesan = kontrol.set_strategy(payload)
                hasil = {"ok": ok, "message": pesan,
                         "tp_method": kontrol.tp_method, "tp_atr_percent": kontrol.tp_atr_percent,
                         "sl_method": kontrol.sl_method, "sl_atr_percent": kontrol.sl_atr_percent}
            elif aksi == "stop_scanner":
                ok, pesan = kontrol.stop_scanner()
                hasil = {"ok": ok, "message": pesan}
            elif aksi in AKSI_SAFE:
                script, args = AKSI_SAFE[aksi]
                job_id, pesan = kontrol.jalankan_job(aksi, script, args)
                hasil = {"ok": bool(job_id), "job_id": job_id, "message": pesan}
            elif aksi == "scanner_start":
                job_id, pesan = kontrol.mulai_scanner("scanner")
                hasil = {"ok": bool(job_id), "job_id": job_id, "message": pesan}
            elif aksi in AKSI_LIVE:
                state = baca_json(folder / "state.json") or {}
                if state.get("mode") != "live":
                    hasil = {"ok": False, "message": "Aksi live ditolak: mode saat ini bukan live"}
                else:
                    hasil = {"ok": True, "message": "Menunggu persetujuan Telegram",
                             **kontrol.minta_live(aksi)}
                    if hasil["status"] == "pending":
                        approval_id = hasil["approval_id"]

                        def eksekusi_setelah_approve():
                            for _ in range(301):
                                item = kontrol.pending.get(approval_id)
                                if not item or item["status"] != "pending":
                                    break
                                time.sleep(1)
                            item = kontrol.pending.get(approval_id)
                            if item and item["status"] == "approved":
                                if aksi == "live_scan_once":
                                    kontrol.jalankan_job("live_scan_once", "scanner.py", ["--sekali"], True)
                                else:
                                    kontrol.mulai_scanner("live_scanner", True)

                        threading.Thread(target=eksekusi_setelah_approve, daemon=True).start()
            else:
                hasil = {"ok": False, "message": "Aksi tidak diizinkan"}
            isi = json.dumps(hasil, ensure_ascii=False).encode("utf-8")
            self._kirim(200, "application/json; charset=utf-8", isi)

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
    p.add_argument("--cors-origin", default="", help="origin website GitHub Pages, mis. https://nama.github.io")
    p.add_argument("--allow-all-cors", action="store_true", help="izinkan origin browser mana pun (tidak disarankan)")
    p.add_argument("--control-token", default=os.getenv("BOT_CONTROL_TOKEN", ""), help="token rahasia untuk API kontrol")
    p.add_argument("--telegram-token", default=os.getenv("TELEGRAM_BOT_TOKEN", ""), help="token bot Telegram")
    p.add_argument("--telegram-chat-id", default=os.getenv("TELEGRAM_CHAT_ID", ""), help="chat/user Telegram penerima persetujuan")
    a = p.parse_args()
    folder = Path(a.dir).resolve()
    halaman = skrip / HALAMAN if (skrip / HALAMAN).exists() else folder / HALAMAN
    cors_origin = "*" if a.allow_all_cors else a.cors_origin
    control_token = a.control_token or secrets.token_urlsafe(24)
    kontrol = KontrolBot(folder, control_token, a.telegram_token, a.telegram_chat_id)
    srv = ThreadingHTTPServer((a.host, a.port), buat_handler(folder, halaman, cors_origin, kontrol))
    url = f"http://{a.host}:{a.port}"
    print(f"Dashboard Bot-Tree aktif di {url}  (baca dari {folder})\nTekan Ctrl+C untuk berhenti.")
    if not a.control_token:
        print("BOT CONTROL TOKEN (simpan rahasia): " + control_token)
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
