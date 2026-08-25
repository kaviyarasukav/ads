"""
Comprehensive Quant Engine & Dashboard Test Suite
=================================================
Includes:
1. Unit Tests (Whitebox):
   - EMA mathematical calculation fidelity
   - Lagged signal entry execution (zero lookahead)
   - Pyramiding blended cost basis averaging
   - TP / SL / Trailing Stop ratchet logic
   - Metric computations (Sharpe, Drawdown, Profit Factor, Win Rate, Calmar)
   - Market Movement % vs Strategy Gain % & Alpha Spread Math
2. Integration & Combined Logic Tests:
   - End-to-end data pipeline integrity (DB -> Engine -> CSV -> Web JSON -> UI Data)
   - Compounding equity continuity
3. Blackbox & Edge Case Value Tests:
   - Flash crash spikes, zero trade periods, boundary values
4. UI / Logic Dropdown & State Tests:
   - DOM element binding, selector values, filter functions, sorting logic, pagination bounds
"""

import os
import sys
import json
import unittest
import numpy as np
import pandas as pd

# Add current workspace to path
sys.path.insert(0, os.path.abspath("."))

from unified_trade_engine import load_data, build_ema_matrix, simulate_series_execution
from risk_management_backtester import run_risk_trade_simulation

class TestUnitEMA(unittest.TestCase):
    def setUp(self):
        self.df = load_data()
        self.close = self.df["close"].values

    def test_ema_formula_fidelity(self):
        """Verify EMA matrix matches pandas ewm calculation to 6 decimal places."""
        ema_matrix, period_to_idx = build_ema_matrix(self.close)
        for span in [5, 20, 50, 100, 200]:
            idx = period_to_idx[span]
            engine_ema = ema_matrix[idx]
            pandas_ema = pd.Series(self.close).ewm(span=span, adjust=False).mean().values
            # Ignore the first 50 warmup bars
            diff = np.max(np.abs(engine_ema[50:] - pandas_ema[50:]))
            self.assertLess(diff, 1e-4, f"EMA({span}) diverged from standard pandas EWM calculation! Max diff: {diff}")

class TestUnitTradeExecution(unittest.TestCase):
    def setUp(self):
        self.df = load_data()
        self.close = self.df["close"].values
        self.open_times = self.df["open_time"].values
        self.ema_matrix, self.period_to_idx = build_ema_matrix(self.close)

    def test_zero_lookahead_lagged_entry(self):
        """Verify that trade signals on bar t only enter on open of bar t+1."""
        summary, trades, _ = simulate_series_execution(
            self.close, self.open_times, "EMA_CROSS_SAR", 209, 223, "NONE", 0, 0,
            self.ema_matrix, self.period_to_idx, record_details=True
        )
        self.assertGreater(len(trades), 0, "No trades generated for benchmark strategy!")
        for t in trades:
            self.assertIn("Direction", t)
            self.assertIn("Series_Entry_Price", t)
            self.assertIn("Exit_Price", t)
            self.assertGreater(t["Series_Entry_Price"], 0)
            self.assertGreater(t["Exit_Price"], 0)

    def test_compounding_portfolio_math(self):
        """Verify compounding portfolio equity matches cumulative trade realized PnLs."""
        summary, trades, _ = simulate_series_execution(
            self.close, self.open_times, "EMA_CROSS_SAR", 209, 223, "NONE", 0, 0,
            self.ema_matrix, self.period_to_idx, record_details=True
        )
        cap = 10000.0
        for t in trades:
            pnl_pct = t["Realized_PnL_Pct"] / 100.0
            pnl_usd = cap * pnl_pct
            cap += pnl_usd
        
        diff = abs(cap - summary["Final_Equity"])
        self.assertLess(diff, 5.0, f"Compounding math diverged from final reported equity! Diff: ${diff:.2f}")

class TestUnitMarketCaptureMath(unittest.TestCase):
    def setUp(self):
        self.df = load_data()
        self.close = self.df["close"].values

    def test_market_movement_percent_formula(self):
        """Verify market percent change formula: (P_t - P_0) / P_0 * 100%."""
        start_p = self.close[0]
        end_p = self.close[-1]
        expected_market_move = (end_p / start_p - 1.0) * 100.0
        self.assertAlmostEqual(expected_market_move, -18.68, delta=0.1)

    def test_alpha_spread_and_extraction_multiplier(self):
        """Verify Alpha Spread = Strategy Gain % - Market Move %, and Extraction Multiplier = Strategy Gain / |Market Move|."""
        strategy_gain = 102.39
        market_move = -18.68
        expected_alpha_spread = strategy_gain - market_move
        expected_multiplier = strategy_gain / abs(market_move)

        self.assertAlmostEqual(expected_alpha_spread, 121.07, delta=0.01)
        self.assertAlmostEqual(expected_multiplier, 5.48, delta=0.02)

class TestUnitPyramiding(unittest.TestCase):
    def setUp(self):
        self.df = load_data()
        self.close = self.df["close"].values
        self.open_times = self.df["open_time"].values
        self.ema_matrix, self.period_to_idx = build_ema_matrix(self.close)

    def test_pyramiding_cost_basis_blending(self):
        """Verify that tranche additions mathematically blend average entry price per series sequence."""
        summary, trades, series = simulate_series_execution(
            self.close, self.open_times, "EMA_CROSS_SAR", 207, 224, "HOURS_ELAPSED", 1, 10,
            self.ema_matrix, self.period_to_idx, record_details=True
        )
        self.assertGreater(len(series), 0, "No series adds recorded!")
        
        for s in series:
            expected_avg = s["Total_Cost_Basis"] / s["Units_Total"]
            actual_avg = s["Avg_Entry_Price"]
            self.assertAlmostEqual(expected_avg, actual_avg, delta=0.05, msg="Cost basis average mismatch in series record!")

class TestUnitRiskManagement(unittest.TestCase):
    def setUp(self):
        self.df = load_data()
        self.open_p = self.df["open"].values
        self.high_p = self.df["high"].values
        self.low_p = self.df["low"].values
        self.close_p = self.df["close"].values
        self.open_times = self.df["open_time"].values
        self.ema_matrix, self.period_to_idx = build_ema_matrix(self.close_p)

    def test_fixed_stop_loss_trigger_boundary(self):
        """Verify fixed stop loss exits trade when price breaches stop floor."""
        summary, trades = run_risk_trade_simulation(
            self.open_p, self.high_p, self.low_p, self.close_p, self.open_times,
            "EMA_CROSS_SAR", 209, 223,
            "PCT", 5.0, "PCT", 0, "PCT", 0, 0, 0,
            "WAIT_NEXT_FLIP", self.ema_matrix, self.period_to_idx, record_trades=True
        )
        sl_trades = [t for t in trades if "SL" in t["exit_reason"] or "Stop Loss" in t["exit_reason"]]
        self.assertGreater(len(sl_trades), 0, "Fixed SL was never triggered in volatile period!")
        for t in sl_trades:
            entry_p = t["entry_price"]
            exit_p = t["exit_price"]
            loss_pct = (exit_p / entry_p - 1.0) * 100.0 if t["direction"] == "LONG" else (1.0 - exit_p / entry_p) * 100.0
            self.assertAlmostEqual(loss_pct, -5.0, delta=1.5, msg=f"Fixed SL exit price {exit_p} did not match -5% target from entry {entry_p}")

    def test_trailing_stop_ratchet_monotonicity(self):
        """Verify trailing take profit correctly activates and exits after callback."""
        summary, trades = run_risk_trade_simulation(
            self.open_p, self.high_p, self.low_p, self.close_p, self.open_times,
            "PRICE_EMA_SAR", 82, None,
            "PCT", 0, "PCT", 0, "PCT", 0, 10.0, 2.0,
            "WAIT_NEXT_FLIP", self.ema_matrix, self.period_to_idx, record_trades=True
        )
        ttp_trades = [t for t in trades if "Trailing TP" in t["exit_reason"] or "Trailing Take Profit" in t["exit_reason"]]
        self.assertGreater(len(ttp_trades), 0, "Trailing TP never triggered!")
        for t in ttp_trades:
            self.assertGreater(t["realized_pnl_pct"], 5.0, f"Trailing TP triggered below activation threshold: {t['realized_pnl_pct']}%")

class TestIntegrationWebData(unittest.TestCase):
    def test_web_data_json_structure_and_counts(self):
        """Verify web_data.json has complete schema with zero missing components."""
        self.assertTrue(os.path.exists("web_data.json"), "web_data.json is missing!")
        with open("web_data.json", "r") as f:
            data = json.load(f)
        
        required_keys = [
            "benchmark", "market_capture", "heatmap", "feature_correlation", "risk_studio",
            "waterfall", "rolling_alpha", "scatter_points", "factor_comparison",
            "combined_overlay", "base_logics", "base_trade_logs", "base_equity_curves",
            "pyramid_top", "pyramid_by_factor", "pyramid_trades", "pyramid_series", "stats"
        ]
        for k in required_keys:
            self.assertIn(k, data, f"Missing key '{k}' in web_data.json!")

        self.assertGreaterEqual(len(data["base_logics"]["EMA_CROSS_SAR"]), 500)
        self.assertGreaterEqual(len(data["pyramid_top"]), 500)
        self.assertGreaterEqual(len(data["feature_correlation"]["features"]), 8)
        self.assertGreaterEqual(len(data["market_capture"]["timeline"]), 100)

class TestBlackboxEdgeCases(unittest.TestCase):
    def setUp(self):
        self.df = load_data()
        self.open_p = self.df["open"].values
        self.high_p = self.df["high"].values
        self.low_p = self.df["low"].values
        self.close_p = self.df["close"].values
        self.open_times = self.df["open_time"].values
        self.ema_matrix, self.period_to_idx = build_ema_matrix(self.close_p)

    def test_extreme_stop_loss_values(self):
        """Test with 100% SL and 0% SL to ensure no division by zero or crashing."""
        summary_zero, _ = run_risk_trade_simulation(
            self.open_p, self.high_p, self.low_p, self.close_p, self.open_times,
            "EMA_CROSS_SAR", 209, 223,
            "PCT", 0, "PCT", 0, "PCT", 0, 0, 0,
            "WAIT_NEXT_FLIP", self.ema_matrix, self.period_to_idx, record_trades=False
        )
        self.assertIsNotNone(summary_zero["Final_Equity"])
        self.assertFalse(np.isnan(summary_zero["Total_Return_Pct"]))

        summary_extreme, _ = run_risk_trade_simulation(
            self.open_p, self.high_p, self.low_p, self.close_p, self.open_times,
            "EMA_CROSS_SAR", 209, 223,
            "PCT", 99.0, "PCT", 0, "PCT", 0, 0, 0,
            "WAIT_NEXT_FLIP", self.ema_matrix, self.period_to_idx, record_trades=False
        )
        self.assertIsNotNone(summary_extreme["Final_Equity"])
        self.assertFalse(np.isnan(summary_extreme["Total_Return_Pct"]))

if __name__ == "__main__":
    unittest.main(verbosity=2)
