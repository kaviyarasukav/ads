"""
Multi-Timeframe EMA Perpetual Futures Backtest Runner (Folder B)
================================================================
Evaluates EMA strategies across 3 timeframe resolutions in H1 2026:
- 5m  (52,128 bars)
- 30m (8,688 bars)
- 1h  (4,344 bars)

Outputs:
- B/results/multi_timeframe_ema_leaderboard.csv (Master comparison across all 3 timeframes)
"""

import os
import sys
import json
import time
import pandas as pd
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from main_source_data.data_loader import load_candle_data
from indicators.ema import calculate_ema, build_ema_matrix
from strategies.strategy_ema import (
    generate_ema_sar_signals,
    generate_ema_cross_price_signals,
    generate_single_ema_price_signals
)
from execution.futures_engine import simulate_futures_trading

RESULTS_DIR = os.path.join(BASE_DIR, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

def run_multi_timeframe_backtest():
    print("=" * 85)
    print("STARTING MULTI-TIMEFRAME EMA FUTURES SIMULATION (5M, 30M, 1H - H1 2026)")
    print("=" * 85)

    test_timeframes = ["5m", "30m", "1h"]
    test_pairs = [
        (9, 21), (12, 26), (20, 50), (20, 100), (20, 200),
        (50, 100), (50, 200), (100, 200), (207, 224), (209, 223)
    ]
    single_emas = [20, 50, 82, 100, 200]

    all_summaries = []

    for tf in test_timeframes:
        t0 = time.time()
        df = load_candle_data(tf)
        open_p = df["open"].values
        close_p = df["close"].values
        timestamps = df["datetime"].values
        print(f"\n[{tf.upper()}] Loaded {len(df):,} candles ({df['datetime'].min()} to {df['datetime'].max()})...")

        # Build EMA Matrix for this timeframe
        ema_matrix, period_to_idx = build_ema_matrix(close_p, min_p=5, max_p=250)

        # 1. Method 1: EMA Cross SAR
        for f_p, s_p in test_pairs:
            f_ema = ema_matrix[period_to_idx[f_p]]
            s_ema = ema_matrix[period_to_idx[s_p]]
            signals = generate_ema_sar_signals(f_ema, s_ema)
            
            name = f"EMA_SAR_{f_p}_{s_p}_{tf}"
            summary, trades, _ = simulate_futures_trading(
                open_p, close_p, timestamps, signals, timeframe=tf, strategy_name=name
            )
            summary["strategy_base"] = f"EMA_SAR_{f_p}_{s_p}"
            summary["method"] = "Method 1: SAR"
            summary["fast_ema"] = f_p
            summary["slow_ema"] = s_p
            all_summaries.append(summary)

            if (f_p, s_p) in [(100, 200), (50, 200), (209, 223)]:
                pd.DataFrame(trades).to_csv(os.path.join(RESULTS_DIR, f"trades_{name}.csv"), index=False)

        # 2. Method 2: EMA Cross + Price Confirmation
        for f_p, s_p in test_pairs:
            f_ema = ema_matrix[period_to_idx[f_p]]
            s_ema = ema_matrix[period_to_idx[s_p]]
            signals = generate_ema_cross_price_signals(close_p, f_ema, s_ema)
            
            name = f"EMA_CONFIRMED_{f_p}_{s_p}_{tf}"
            summary, trades, _ = simulate_futures_trading(
                open_p, close_p, timestamps, signals, timeframe=tf, strategy_name=name
            )
            summary["strategy_base"] = f"EMA_CONFIRMED_{f_p}_{s_p}"
            summary["method"] = "Method 2: Cross+Price"
            summary["fast_ema"] = f_p
            summary["slow_ema"] = s_p
            all_summaries.append(summary)

        # 3. Method 3: Single EMA Price
        for p in single_emas:
            ema = ema_matrix[period_to_idx[p]]
            signals = generate_single_ema_price_signals(close_p, ema)
            
            name = f"SINGLE_EMA_{p}_{tf}"
            summary, trades, _ = simulate_futures_trading(
                open_p, close_p, timestamps, signals, timeframe=tf, strategy_name=name
            )
            summary["strategy_base"] = f"SINGLE_EMA_{p}"
            summary["method"] = "Method 3: Single EMA"
            summary["fast_ema"] = p
            summary["slow_ema"] = None
            all_summaries.append(summary)

    # Output Combined Multi-Timeframe Leaderboard
    df_results = pd.DataFrame(all_summaries).sort_values(by="total_return_pct", ascending=False)
    leaderboard_csv = os.path.join(RESULTS_DIR, "multi_timeframe_ema_leaderboard.csv")
    df_results.to_csv(leaderboard_csv, index=False)

    print("\n" + "=" * 90)
    print("TOP 15 MULTI-TIMEFRAME EMA FUTURES STRATEGIES (5M vs 30M vs 1H)")
    print("=" * 90)
    cols = ["strategy", "timeframe", "method", "total_return_pct", "max_drawdown_pct", "sharpe", "sortino", "win_rate_pct", "profit_factor", "total_trades"]
    print(df_results[cols].head(15).to_string(index=False))
    print("=" * 90)
    print(f"Full Multi-Timeframe Leaderboard saved to: {leaderboard_csv}")

if __name__ == "__main__":
    run_multi_timeframe_backtest()
