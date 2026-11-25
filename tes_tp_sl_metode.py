import unittest

import config
import penilai_ai
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

    def test_tp_atr_persen(self):
        config.TP_METHOD = "atr"
        config.TP_ATR_PERCENT = 100
        data = {"atr": 10}
        self.assertEqual(penilai_ai.tp_untuk(data, 1, 100), 110)
        self.assertEqual(penilai_ai.tp_untuk(data, -1, 100), 90)

    def test_sl_atr_persen(self):
        config.SL_METHOD = "atr"
        config.SL_ATR_PERCENT = 50
        self.assertEqual(penilai_ai.buffer_sl({"atr": 10}), 5)

    def test_sl_support_resistance_tanpa_buffer_atr(self):
        config.SL_METHOD = "sr"
        self.assertEqual(penilai_ai.buffer_sl({"atr": 10}), 0)

    def test_support_resistance_tp(self):
        config.TP_METHOD = "sr"
        config.TP_MODE = "sr_lawan"
        data = {
            "level_atas": [110, 120],
            "level_bawah": [90, 80],
        }
        self.assertEqual(penilai_ai.tp_untuk(data, 1, 100), 110)
        self.assertEqual(penilai_ai.tp_untuk(data, -1, 100), 90)

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
