"""
Master Ultra-Fast Multi-Core Brute-Force EMA Grid Scanner (Folder B)
====================================================================
Utilizes all available CPU cores via multiprocessing + SciPy C-compiled EMA filters
+ zero-copy NumPy execution engine to sweep thousands of combinations in seconds.

Outputs:
- B/results/master_ema_brute_force_superset.csv (40+ quantitative metrics per setup)
- B/results/master_ema_all_trades_detailed_log.csv (Detailed trade tickets)
"""

import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from typing import List, Tuple, Dict, Any
import pandas as pd
import numpy as np

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from main_source_data.data_loader import load_candle_data
from indicators.ema import build_ema_matrix
from strategies.strategy_ema import generate_ema_sar_signals
from execution.futures_engine import simulate_futures_trading_full

RESULTS_DIR = os.path.join(BASE_DIR, "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

_WORKER_CACHE: Dict[str, Any] = {}

def _init_worker(tf: str, open_p: np.ndarray, close_p: np.ndarray, timestamps: np.ndarray, ema_matrix: np.ndarray, period_to_idx: Dict[int, int]):
    _WORKER_CACHE['tf'] = tf
    _WORKER_CACHE['open_p'] = open_p
    _WORKER_CACHE['close_p'] = close_p
    _WORKER_CACHE['timestamps'] = timestamps
    _WORKER_CACHE['ema_matrix'] = ema_matrix
    _WORKER_CACHE['period_to_idx'] = period_to_idx

def _worker_process_chunk(pair_chunk: List[Tuple[int, int]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    tf = _WORKER_CACHE['tf']
    open_p = _WORKER_CACHE['open_p']
    close_p = _WORKER_CACHE['close_p']
    timestamps = _WORKER_CACHE['timestamps']
    ema_matrix = _WORKER_CACHE['ema_matrix']
    period_to_idx = _WORKER_CACHE['period_to_idx']

    summaries = []
    trades_list = []
    
    for f_p, s_p in pair_chunk:
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
        summaries.append(summary)
        trades_list.extend(trades)

    return summaries, trades_list

def run_master_brute_force_sweep(min_p: int = 5, max_p: int = 200, step: int = 5, timeframes: List[str] = ["5m", "30m", "1h"]):
    num_cpus = min(16, os.cpu_count() or 4)
    print("=" * 90)
    print(f"PARALLEL BRUTE-FORCE EMA FUTURES SWEEP (PERIODS {min_p} TO {max_p}) ON {num_cpus} CPU CORES")
    print("=" * 90)

    periods = list(range(min_p, max_p + 1, step))
    all_pairs = [(f, s) for f in periods for s in periods if s > f]
    print(f"Grid Size: {len(periods)} periods -> {len(all_pairs):,} combinations per timeframe.")

    all_summaries = []
    all_trades = []
    t_start = time.time()

    # Split pairs into balanced chunks
    chunk_size = max(1, len(all_pairs) // (num_cpus * 4))
    pair_chunks = [all_pairs[i:i + chunk_size] for i in range(0, len(all_pairs), chunk_size)]

    for tf in timeframes:
        t0_tf = time.time()
        print(f"\n--- Processing Timeframe: {tf.upper()} ({num_cpus} parallel workers) ---")
        df = load_candle_data(tf)
        open_p = df["open"].values
        close_p = df["close"].values
        timestamps = df["datetime"].values

        # Build full EMA matrix for this timeframe once
        ema_matrix, period_to_idx = build_ema_matrix(close_p, min_p=min_p, max_p=max_p)

        with ProcessPoolExecutor(
            max_workers=num_cpus,
            initializer=_init_worker,
            initargs=(tf, open_p, close_p, timestamps, ema_matrix, period_to_idx)
        ) as executor:
            results = executor.map(_worker_process_chunk, pair_chunks)
            
            tf_count = 0
            for res_summaries, res_trades in results:
                all_summaries.extend(res_summaries)
                all_trades.extend(res_trades)
                tf_count += len(res_summaries)

        tf_elapsed = time.time() - t0_tf
        print(f"[{tf.upper()}] Evaluated {tf_count:,} combinations in {tf_elapsed:.2f}s ({tf_count/max(tf_elapsed,0.001):.0f} strats/sec).")

    total_time = time.time() - t_start
    print(f"\nTotal Sweep Time: {total_time:.2f}s across {len(all_summaries):,} strategy runs ({len(all_summaries)/max(total_time,0.001):.0f} strats/sec).")

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
    print("TOP 10 BEST PERFORMING STRATEGIES FROM PARALLEL SWEEP (H1 2026)")
    print("=" * 90)
    top_cols = ["Strategy", "Timeframe", "Fast_EMA", "Slow_EMA", "Total_Return_Pct", "Max_Drawdown_Pct", "Sharpe_Ratio", "Sortino_Ratio", "Composite_Score", "Win_Rate_Pct", "Profit_Factor", "Total_Trades"]
    print(df_master[top_cols].head(10).to_string(index=False))
    print("=" * 90)

if __name__ == "__main__":
    run_master_brute_force_sweep()
