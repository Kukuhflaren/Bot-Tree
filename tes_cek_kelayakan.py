import unittest

import cek_kelayakan


class SusunTokenTests(unittest.TestCase):
    def test_all_unique_symbols_and_watchlist_first(self):
        data = {
            "bullish": [
                {"simbol": "BTC/USDT:USDT"},
                {"simbol": "ETH/USDT:USDT"},
            ],
            "bearish": [
                {"simbol": "ETH/USDT:USDT"},
                {"simbol": "SOL/USDT:USDT"},
            ],
        }

        self.assertEqual(
            cek_kelayakan.susun_token(data, ["SOL", "BTC", "OUTSIDE"]),
            ["SOL", "BTC", "ETH"],
        )

    def test_no_watchlist_preserves_bullish_then_bearish_order(self):
        data = {
            "bullish": [{"simbol": "ETH/USDT:USDT"}],
            "bearish": [
                {"simbol": "BTC/USDT:USDT"},
                {"simbol": "ETH/USDT:USDT"},
            ],
        }

        self.assertEqual(cek_kelayakan.susun_token(data, []), ["ETH", "BTC"])


if __name__ == "__main__":
    unittest.main()
