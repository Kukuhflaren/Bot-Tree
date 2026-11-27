import unittest

import config
import penilai_ai
import dashboard_server
import tempfile
from pathlib import Path


class TpSlMetodeTests(unittest.TestCase):
    def setUp(self):
        self.original_tp_method = getattr(config, "TP_METHOD", "sr")
        self.original_tp_atr = getattr(config, "TP_ATR_PERCENT", 100.0)
        self.original_sl_method = getattr(config, "SL_METHOD", "atr")
        self.original_sl_atr = getattr(config, "SL_ATR_PERCENT", 50.0)

    def tearDown(self):
        config.TP_METHOD = self.original_tp_method
        config.TP_ATR_PERCENT = self.original_tp_atr
        config.SL_METHOD = self.original_sl_method
        config.SL_ATR_PERCENT = self.original_sl_atr

    def test_tp_di_struktur_hh_hl(self):
        """Strategi baru: TP utama di HH (long) dan HL (short)."""
        data = {"HH": 110, "HL": 90, "atr": 10}
        self.assertEqual(penilai_ai.tp_untuk(data, 1, 100), 110)
        self.assertEqual(penilai_ai.tp_untuk(data, -1, 100), 90)

    def test_sl_buffer_atr(self):
        """SL di luar HL/HH sejauh SL_BUFFER_ATR x ATR."""
        self.assertAlmostEqual(penilai_ai.buffer_sl({"atr": 10}), config.SL_BUFFER_ATR * 10)

    def test_satu_sl_dan_tp_untuk_seluruh_grid(self):
        a = {"arah": 1, "harga": 101.0, "atr": 1.0, "HL": 98.0, "HH": 106.0,
             "grid": [("S1", 100.0), ("S2", 99.0)]}
        grid = penilai_ai.rencana(a, 1)
        self.assertEqual({g["sl"] for g in grid}, {round(98.0 - config.SL_BUFFER_ATR, 5)})
        self.assertEqual({g["tp"] for g in grid}, {106.0})

    def test_dashboard_strategy_persisted(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            kontrol = dashboard_server.KontrolBot(Path(temp_dir), "test-token")
            ok, _ = kontrol.set_strategy({
                "tp_method": "atr",
                "tp_atr_percent": 125,
                "sl_method": "sr",
                "sl_atr_percent": 50,
            })
            self.assertTrue(ok)
            self.assertEqual(kontrol.tp_method, "atr")
            self.assertEqual(kontrol.tp_atr_percent, 125)
            self.assertEqual(kontrol.sl_method, "sr")


if __name__ == "__main__":
    unittest.main()
