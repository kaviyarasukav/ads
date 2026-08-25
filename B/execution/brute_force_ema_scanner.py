"""
Master Brute-Force EMA Grid Scanner (40+ Feature Suite)
======================================================
Executes exhaustive brute-force grid sweep for EMA periods 5 to 200 across 5m, 30m, and 1h.
Outputs:
- B/results/master_ema_brute_force_superset.csv (40+ quantitative metrics per setup)
- B/results/master_ema_all_trades_detailed_log.csv (Detailed trade tickets with exact EMA entry/exit levels)
"""

import os
import sys
import time
import pandas as pd
import numpy as np
from typing import List

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from main_source_data.data_loader import load_candle_data
from indicators.ema import build_ema_matrix
from strategies.strategy_ema import generate_ema_sar_signals
from execution.futures_engine import simulate_futures_trading_full

RESULTS_DIR = os.path.join(BASE_DIR, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

def run_master_brute_force_sweep(min_p: int = 5, max_p: int = 200, step: int = 5, timeframes: List[str] = ["5m", "30m", "1h"]):
    print("=" * 90)
    print(f"STARTING COMPREHENSIVE BRUTE-FORCE EMA FUTURES SWEEP (PERIODS {min_p} TO {max_p})")
    print("=" * 90)

    periods = list(range(min_p, max_p + 1, step))
    total_pairs = sum(1 for f in periods for s in periods if s > f)
    print(f"Grid Size: {len(periods)} periods -> {total_pairs:,} combinations per timeframe.")

    all_summaries = []
    all_trades = []
    t_start = time.time()

    for tf in timeframes:
        print(f"\n--- Processing Timeframe: {tf.upper()} ---")
        df = load_candle_data(tf)
        open_p = df["open"].values
        close_p = df["close"].values
        timestamps = df["datetime"].values

        # Build full EMA matrix for this timeframe
        ema_matrix, period_to_idx = build_ema_matrix(close_p, min_p=min_p, max_p=max_p)

        done_count = 0
        for f_p in periods:
            for s_p in periods:
                if s_p <= f_p:
                    continue

                f_ema = ema_matrix[period_to_idx[f_p]]
                s_ema = ema_matrix[period_to_idx[s_p]]
                signals = generate_ema_sar_signals(f_ema, s_ema)

                name = f"EMA_SAR_{f_p}_{s_p}_{tf}"
                summary, trades, _ = simulate_futures_trading_full(
                    open_p, close_p, timestamps, signals,
                    timeframe=tf, strategy_name=name,
                    fast_p=f_p, slow_p=s_p, method="Stop-and-Reverse (SAR)",
                    record_details=True
                )
                all_summaries.append(summary)
                all_trades.extend(trades)
                done_count += 1

        print(f"[{tf.upper()}] Evaluated {done_count:,} combinations successfully.")

    total_time = time.time() - t_start
    print(f"\nTotal Sweep Time: {total_time:.2f}s across {len(all_summaries):,} strategy runs.")

    # 1. Master Superset Report (40+ features)
    df_master = pd.DataFrame(all_summaries).sort_values(by="Total_Return_Pct", ascending=False)
    master_csv = os.path.join(RESULTS_DIR, "master_ema_brute_force_superset.csv")
    df_master.to_csv(master_csv, index=False)
    print(f"Master Superset Report saved: {master_csv} ({len(df_master):,} records with {len(df_master.columns)} features)")

    # 2. Complete Detailed Trade Log
    df_trades = pd.DataFrame(all_trades)
    trades_csv = os.path.join(RESULTS_DIR, "master_ema_all_trades_detailed_log.csv")
    df_trades.to_csv(trades_csv, index=False)
    print(f"Detailed Trade Log saved: {trades_csv} ({len(df_trades):,} trade tickets)")

    print("\n" + "=" * 90)
    print("TOP 10 BEST PERFORMING STRATEGIES FROM COMPREHENSIVE SWEEP (H1 2026)")
    print("=" * 90)
    top_cols = ["Strategy", "Timeframe", "Fast_EMA", "Slow_EMA", "Total_Return_Pct", "Max_Drawdown_Pct", "Sharpe_Ratio", "Sortino_Ratio", "Composite_Score", "Win_Rate_Pct", "Profit_Factor", "Total_Trades"]
    print(df_master[top_cols].head(10).to_string(index=False))
    print("=" * 90)

if __name__ == "__main__":
    run_master_brute_force_sweep()
