"""
Quantitative Visual Report & Chart Generator (Folder B)
========================================================
Generates publication-quality dark-themed financial charts:
1. Top Equity Curves vs ETH Benchmark
2. Multi-Timeframe Risk-Return & Sharpe Scatter
3. Brute-Force 2D Heatmap Matrix
4. Monthly Performance Return Matrix
5. Underwater Drawdown Profiles
"""

import os
import sys
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from main_source_data.data_loader import load_candle_data
from indicators.ema import calculate_ema
from strategies.strategy_ema import generate_ema_sar_signals, generate_single_ema_price_signals
from execution.futures_engine import simulate_futures_trading_full

RESULTS_DIR = os.path.join(BASE_DIR, "results")
CHARTS_DIR = os.path.join(BASE_DIR, "charts")
os.makedirs(CHARTS_DIR, exist_ok=True)

# Set Dark Institutional Theme
plt.style.use("dark_background")
matplotlib.rcParams['font.sans-serif'] = 'DejaVu Sans'
matplotlib.rcParams['axes.edgecolor'] = '#30363d'
matplotlib.rcParams['axes.linewidth'] = 0.8
matplotlib.rcParams['grid.color'] = '#21262d'
matplotlib.rcParams['grid.linestyle'] = '--'
matplotlib.rcParams['grid.alpha'] = 0.6

def generate_all_visuals():
    print("=" * 80)
    print("GENERATING QUANTITATIVE VISUAL ASSETS & CHARTS (FOLDER B)")
    print("=" * 80)

    # 1. Load Data
    df_1h = load_candle_data("1h")
    df_30m = load_candle_data("30m")
    df_5m = load_candle_data("5m")

    # --- CHART 1: Top Equity Curves vs Benchmark ---
    print("[1/5] Generating Top Equity Curves Chart...")
    fig, ax = plt.subplots(figsize=(14, 7), dpi=300)

    # ETH Benchmark curve
    eth_close_1h = df_1h["close"].values
    eth_eq_norm = (eth_close_1h / eth_close_1h[0]) * 10000.0
    dates_1h = pd.to_datetime(df_1h["datetime"])

    ax.plot(dates_1h, eth_eq_norm, label="ETH Spot Benchmark (-47.10%)", color="#ff4d4d", linewidth=2.2, linestyle="--", alpha=0.9)

    # Strategy 1: EMA_SAR_209_223_1h
    f_ema = calculate_ema(eth_close_1h, 209)
    s_ema = calculate_ema(eth_close_1h, 223)
    sig_1h = generate_ema_sar_signals(f_ema, s_ema)
    _, _, eq_1h = simulate_futures_trading_full(
        df_1h["open"].values, eth_close_1h, df_1h["datetime"].values, sig_1h,
        timeframe="1h", strategy_name="EMA_SAR_209_223_1h", fast_p=209, slow_p=223
    )
    ax.plot(dates_1h, eq_1h, label="1. EMA_SAR_209_223_1h (+50.01% | Sharpe 1.95)", color="#00ffcc", linewidth=2.5)

    # Strategy 2: SINGLE_EMA_82_1h
    ema82 = calculate_ema(eth_close_1h, 82)
    sig_82 = generate_single_ema_price_signals(eth_close_1h, ema82)
    _, _, eq_82 = simulate_futures_trading_full(
        df_1h["open"].values, eth_close_1h, df_1h["datetime"].values, sig_82,
        timeframe="1h", strategy_name="SINGLE_EMA_82_1h", fast_p=82, slow_p=None
    )
    ax.plot(dates_1h, eq_82, label="2. SINGLE_EMA_82_1h (+30.60% | Sharpe 1.25)", color="#a371f7", linewidth=2.0)

    # Strategy 3: EMA_SAR_20_30_30m
    dates_30m = pd.to_datetime(df_30m["datetime"])
    eth_close_30m = df_30m["close"].values
    f_30m = calculate_ema(eth_close_30m, 20)
    s_30m = calculate_ema(eth_close_30m, 30)
    sig_30m = generate_ema_sar_signals(f_30m, s_30m)
    _, _, eq_30m = simulate_futures_trading_full(
        df_30m["open"].values, eth_close_30m, df_30m["datetime"].values, sig_30m,
        timeframe="30m", strategy_name="EMA_SAR_20_30_30m", fast_p=20, slow_p=30
    )
    ax.plot(dates_30m, eq_30m, label="3. EMA_SAR_20_30_30m (+55.59% | Sharpe 1.81)", color="#ffc107", linewidth=2.0)

    # Strategy 4: EMA_SAR_70_190_5m
    dates_5m = pd.to_datetime(df_5m["datetime"])
    eth_close_5m = df_5m["close"].values
    f_5m = calculate_ema(eth_close_5m, 70)
    s_5m = calculate_ema(eth_close_5m, 190)
    sig_5m = generate_ema_sar_signals(f_5m, s_5m)
    _, _, eq_5m = simulate_futures_trading_full(
        df_5m["open"].values, eth_close_5m, df_5m["datetime"].values, sig_5m,
        timeframe="5m", strategy_name="EMA_SAR_70_190_5m", fast_p=70, slow_p=190
    )
    ax.plot(dates_5m, eq_5m, label="4. EMA_SAR_70_190_5m (+56.75% | Sharpe 1.82)", color="#38ef7d", linewidth=2.0)

    ax.axhline(10000, color="#8b949e", linestyle=":", alpha=0.5, label="Initial Capital ($10,000)")
    ax.set_title("ETH/USDT Perpetual Futures: High-Alpha Quant Strategies vs Benchmark (H1 2026)", fontsize=15, fontweight="bold", pad=15, color="#f0f6fc")
    ax.set_ylabel("Portfolio Value ($ USD)", fontsize=12, color="#c9d1d9")
    ax.set_xlabel("Time (H1 2026: Jan - Jun)", fontsize=12, color="#c9d1d9")
    ax.grid(True)
    ax.legend(loc="upper left", frameon=True, facecolor="#161b22", edgecolor="#30363d", fontsize=10)
    plt.tight_layout()
    chart1_path = os.path.join(CHARTS_DIR, "top_equity_curves.png")
    plt.savefig(chart1_path, dpi=300)
    plt.close()
    print(f" Saved: {chart1_path}")

    # --- CHART 2: Timeframe Risk-Return & Sharpe Scatter ---
    print("[2/5] Generating Timeframe Risk-Return Scatter...")
    superset_path = os.path.join(RESULTS_DIR, "master_ema_brute_force_superset.csv")
    if os.path.exists(superset_path):
        df_sup = pd.read_csv(superset_path)
        fig, ax = plt.subplots(figsize=(12, 7), dpi=300)

        tf_colors = {"1h": "#00ffcc", "30m": "#ffc107", "5m": "#38ef7d"}
        
        for tf, color in tf_colors.items():
            sub = df_sup[df_sup["Timeframe"] == tf]
            scatter = ax.scatter(
                sub["Max_Drawdown_Pct"], sub["Total_Return_Pct"],
                c=color, label=f"Timeframe: {tf.upper()} ({len(sub):,} setups)",
                alpha=0.6, s=sub["Sharpe_Ratio"].clip(lower=0.1) * 35, edgecolors="none"
            )

        ax.axhline(0, color="#8b949e", linestyle=":", alpha=0.5)
        ax.set_title("Multi-Timeframe Parameter Space: Total Return % vs Max Drawdown %", fontsize=14, fontweight="bold", pad=15, color="#f0f6fc")
        ax.set_xlabel("Max Drawdown (%)", fontsize=12, color="#c9d1d9")
        ax.set_ylabel("Total Return (%)", fontsize=12, color="#c9d1d9")
        ax.grid(True)
        ax.legend(loc="upper right", frameon=True, facecolor="#161b22", edgecolor="#30363d", fontsize=11)
        plt.tight_layout()
        chart2_path = os.path.join(CHARTS_DIR, "timeframe_risk_return.png")
        plt.savefig(chart2_path, dpi=300)
        plt.close()
        print(f" Saved: {chart2_path}")

    # --- CHART 3: Brute Force EMA Parameter Heatmap (5M) ---
    print("[3/5] Generating Brute-Force 2D Heatmap Matrix...")
    if os.path.exists(superset_path):
        sub_5m = df_sup[df_sup["Timeframe"] == "5m"]
        pivot_5m = sub_5m.pivot(index="Fast_EMA", columns="Slow_EMA", values="Total_Return_Pct")
        
        fig, ax = plt.subplots(figsize=(13, 9), dpi=300)
        sns.heatmap(pivot_5m, cmap="magma", cbar_kws={'label': 'Total Net Return (%)'}, ax=ax, linewidths=0.05, linecolor="#161b22")
        ax.set_title("5-Minute Resolution: Brute-Force EMA Period Sweep Return Heatmap (5 to 200)", fontsize=14, fontweight="bold", pad=15, color="#f0f6fc")
        ax.set_xlabel("Slow EMA Period", fontsize=12, color="#c9d1d9")
        ax.set_ylabel("Fast EMA Period", fontsize=12, color="#c9d1d9")
        plt.tight_layout()
        chart3_path = os.path.join(CHARTS_DIR, "ema_heatmap_grid.png")
        plt.savefig(chart3_path, dpi=300)
        plt.close()
        print(f" Saved: {chart3_path}")

    # --- CHART 4: Monthly Performance Return Matrix ---
    print("[4/5] Generating Monthly Performance Return Matrix...")
    leaderboard_path = os.path.join(RESULTS_DIR, "multi_timeframe_ema_leaderboard.csv")
    if os.path.exists(leaderboard_path):
        df_lt = pd.read_csv(leaderboard_path).head(8)
        month_cols = ["M_Jan", "M_Feb", "M_Mar", "M_Apr", "M_May", "M_Jun"]
        m_matrix = df_lt.set_index("Strategy")[month_cols]
        m_matrix.columns = ["Jan 2026", "Feb 2026", "Mar 2026", "Apr 2026", "May 2026", "Jun 2026"]

        fig, ax = plt.subplots(figsize=(12, 6), dpi=300)
        sns.heatmap(m_matrix, annot=True, fmt="+.2f", cmap="coolwarm_r", center=0.0, cbar_kws={'label': 'Monthly Return (%)'}, ax=ax, linewidths=0.5, linecolor="#161b22")
        ax.set_title("Monthly Return Heatmap Matrix for Top 8 Quant Strategies (H1 2026)", fontsize=14, fontweight="bold", pad=15, color="#f0f6fc")
        ax.set_xlabel("Month", fontsize=12, color="#c9d1d9")
        ax.set_ylabel("Strategy", fontsize=12, color="#c9d1d9")
        plt.tight_layout()
        chart4_path = os.path.join(CHARTS_DIR, "monthly_performance_matrix.png")
        plt.savefig(chart4_path, dpi=300)
        plt.close()
        print(f" Saved: {chart4_path}")

    # --- CHART 5: Underwater Drawdown Profiles ---
    print("[5/5] Generating Underwater Drawdown Profiles...")
    fig, ax = plt.subplots(figsize=(14, 5), dpi=300)

    # Compute Underwater Curves
    def get_underwater(eq_series):
        peaks = np.maximum.accumulate(eq_series)
        return -((peaks - eq_series) / np.where(peaks == 0, 1e-9, peaks)) * 100.0

    dd_1h = get_underwater(eq_1h)
    dd_30m = get_underwater(eq_30m)
    dd_5m = get_underwater(eq_5m)

    ax.fill_between(dates_1h, dd_1h, 0, color="#00ffcc", alpha=0.3, label="EMA_SAR_209_223_1h (Max DD: -22.26%)")
    ax.plot(dates_1h, dd_1h, color="#00ffcc", linewidth=1.2)

    ax.plot(dates_30m, dd_30m, color="#ffc107", alpha=0.7, linewidth=1.0, label="EMA_SAR_20_30_30m (Max DD: -19.83%)")
    ax.plot(dates_5m, dd_5m, color="#38ef7d", alpha=0.7, linewidth=1.0, label="EMA_SAR_70_190_5m (Max DD: -20.99%)")

    ax.set_title("Underwater Drawdown Profile (% from Peak) - H1 2026", fontsize=14, fontweight="bold", pad=15, color="#f0f6fc")
    ax.set_ylabel("Drawdown (%)", fontsize=12, color="#c9d1d9")
    ax.set_xlabel("Date", fontsize=12, color="#c9d1d9")
    ax.set_ylim(-35, 2)
    ax.grid(True)
    ax.legend(loc="lower left", frameon=True, facecolor="#161b22", edgecolor="#30363d", fontsize=10)
    plt.tight_layout()
    chart5_path = os.path.join(CHARTS_DIR, "drawdown_underwater_curves.png")
    plt.savefig(chart5_path, dpi=300)
    plt.close()
    print(f" Saved: {chart5_path}")

    print("\nAll visual charts generated successfully in B/charts/!")

if __name__ == "__main__":
    generate_all_visuals()
