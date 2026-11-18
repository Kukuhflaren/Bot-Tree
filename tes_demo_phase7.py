"""Offline Phase 7 configuration and payload tests. No API or order is sent."""
from __future__ import annotations

import demo_phase7


def test_demo_confirm_text_constant():
    assert demo_phase7.CONFIRMATION_TEXT == "UJI_DEMO_SAYA_PAHAM"
    print("[OK] demo confirmation string is explicit")


def test_ccxt_symbol_normalization():
    assert demo_phase7.ccxt_symbol("BTC") == "BTC/USDT:USDT"
    assert demo_phase7.ccxt_symbol("BTC/USDT:USDT") == "BTC/USDT:USDT"
    print("[OK] CCXT symbol normalization")


def test_live_mode_never_accepted_by_demo_gate(monkeypatch):
    old_mode = demo_phase7.config.MODE
    demo_phase7.config.MODE = "live"
    try:
        accepted, reason = demo_phase7._demo_config_ok()
        assert not accepted
        assert "demo" in reason.lower()
    finally:
        demo_phase7.config.MODE = old_mode
    print("[OK] live MODE is rejected by demo adapter")


def main():
    test_demo_confirm_text_constant()
    test_ccxt_symbol_normalization()
    test_live_mode_never_accepted_by_demo_gate(None)
    print("All Phase 7 offline tests passed")


if __name__ == "__main__":
    main()
