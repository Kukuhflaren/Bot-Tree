"""Fase C — Scanner continuous.

Loop yang:
  1. (Opsional) refresh sinyal lewat penyaring + penilai
  2. Menjalankan satu siklus paper (update posisi + coba buka baru)
  3. Menunggu interval, lalu ulang

Tidak mengirim order ke Bitget. Hanya paper + state.json.

Pakai:
  python scanner.py                     # loop default (300 detik ≈ 1 candle 5m)
  python scanner.py --interval 60       # tiap 60 detik
  python scanner.py --sekali            # satu putaran saja
  python scanner.py --refresh-sinyal    # jalankan penilai_ai tiap putaran (butuh AI key)
  python scanner.py --no-buka           # hanya update posisi terbuka
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import datetime, timezone

import config
import paper
import risk
import state as st


def _waktu() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def refresh_sinyal(jumlah: int = 8) -> bool:
    """Jalankan penilai_ai.py untuk refresh penilai_ai.json.

    Mengembalikan True jika sukses. Gagal (no key / error) tidak menghentikan scanner.
    """
    print(f"[{_waktu()}] Refresh sinyal (penilai_ai --jumlah {jumlah})...")
    try:
        r = subprocess.run(
            [sys.executable, "penilai_ai.py", "--jumlah", str(jumlah)],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "")[-300:]
            print(f"  penilai_ai gagal (code={r.returncode}): {err}")
            return False
        print("  penilai_ai OK")
        return True
    except subprocess.TimeoutExpired:
        print("  penilai_ai timeout")
        return False
    except Exception as e:
        print(f"  penilai_ai error: {type(e).__name__}: {e}")
        return False


def satu_putaran(
    state: dict,
    *,
    buka_baru: bool = True,
    do_refresh: bool = False,
    jumlah_penilai: int = 8,
) -> None:
    """Satu putaran scanner: optional refresh + paper cycle + status."""
    print(f"\n=== {_waktu()} ===")
    print(st.ringkasan(state))

    if do_refresh:
        refresh_sinyal(jumlah_penilai)

    # Risk gate info (tidak memaksa stop loop — paper sendiri yang menolak buka)
    boleh, alasan = risk.boleh_order_baru(state)
    if not boleh:
        print(f"  Risk gate: TOLAK buka baru — {alasan}")
    else:
        print("  Risk gate: OK")

    if config.SL_BUFFER_ATR > 0:
        print(f"  SL: {config.SL_BUFFER_ATR}×ATR | RISK_ATR [{config.RISK_ATR_MIN}, {config.RISK_ATR_MAX}] | TP={config.TP_MODE}")
    else:
        print(
            f"  SL: {config.SL_POINTS:.0f} poin | "
            f"RISK_ATR [{config.RISK_ATR_MIN}, {config.RISK_ATR_MAX}] | TP={config.TP_MODE}"
        )

    paper.satu_siklus(state, buka_baru=buka_baru and boleh)
    paper.tampil_status(state)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scanner continuous Bot-Tree (Fase C)")
    parser.add_argument("--interval", type=int, default=300, help="Detik antar putaran (default 300 ≈ 5m)")
    parser.add_argument("--sekali", action="store_true", help="Satu putaran lalu keluar")
    parser.add_argument("--refresh-sinyal", action="store_true", help="Jalankan penilai_ai tiap putaran")
    parser.add_argument("--jumlah", type=int, default=8, help="Jumlah token ke penilai_ai")
    parser.add_argument("--no-buka", action="store_true", help="Jangan buka posisi baru")
    args = parser.parse_args()

    print("Bot-Tree Scanner (Fase C)")
    print(f"  MODE={config.MODE} | MODAL={config.MODAL_USDT} USDT | LEV={config.LEVERAGE}x")
    print(f"  DRY_RUN={config.DRY_RUN} | interval={args.interval}s | refresh={args.refresh_sinyal}")
    print()

    state = st.muat()

    if args.sekali:
        satu_putaran(
            state,
            buka_baru=not args.no_buka,
            do_refresh=args.refresh_sinyal,
            jumlah_penilai=args.jumlah,
        )
        st.simpan(state)
        return

    print(f"Loop aktif. Ctrl+C untuk berhenti.\n")
    try:
        while True:
            satu_putaran(
                state,
                buka_baru=not args.no_buka,
                do_refresh=args.refresh_sinyal,
                jumlah_penilai=args.jumlah,
            )
            st.simpan(state)
            print(f"  tidur {args.interval}s...")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nScanner dihentikan.")
        st.simpan(state)


if __name__ == "__main__":
    main()
