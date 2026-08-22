import sys
import os
import json
import time
import urllib.request
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

def fetch_eth_2026_klines(symbol="ETHUSDT", interval="1h", start_str="2026-01-01 00:00:00"):
    start_ts = int(pd.Timestamp(start_str, tz="UTC").timestamp() * 1000)
    end_ts = int(pd.Timestamp.now(tz="UTC").timestamp() * 1000)
    
    print(f"Fetching {symbol} ({interval}) data from Binance from {start_str} to now...")
    all_candles = []
    current_start = start_ts
    
    while current_start < end_ts:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&startTime={current_start}&limit=1000"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode('utf-8'))
                if not data:
                    break
                all_candles.extend(data)
                last_time = data[-1][0]
                if len(data) < 1000 or last_time <= current_start:
                    break
                current_start = last_time + 1
                time.sleep(0.05)
        except Exception as e:
            print(f"Error fetching: {e}, retrying...")
            time.sleep(1)
            
    df = pd.DataFrame(all_candles, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_asset_volume", "num_trades",
        "taker_buy_base_volume", "taker_buy_quote_volume", "ignore"
    ])
    
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
    for col in ["open", "high", "low", "close", "volume", "quote_asset_volume"]:
        df[col] = df[col].astype(float)
        
    df = df.drop_duplicates(subset=["open_time"]).sort_values("open_time").reset_index(drop=True)
    csv_file = f"eth_2026_{interval}.csv"
    df.to_csv(csv_file, index=False)
    print(f"Saved {len(df)} candles to {csv_file} (Date range: {df['open_time'].iloc[0]} to {df['open_time'].iloc[-1]})")
    return df

def compute_all_emas(close_arr, min_p=5, max_p=250):
    n = len(close_arr)
    num_periods = max_p - min_p + 1
    ema_matrix = np.empty((num_periods, n), dtype=np.float64)
    
    for idx, p in enumerate(range(min_p, max_p + 1)):
        alpha = 2.0 / (p + 1.0)
        ema = np.empty(n, dtype=np.float64)
        ema[0] = close_arr[0]
        for t in range(1, n):
            ema[t] = alpha * close_arr[t] + (1.0 - alpha) * ema[t-1]
        ema_matrix[idx] = ema
    return ema_matrix

def run_brute_force(df, min_p=5, max_p=250):
    close = df["close"].values
    n = len(close)
    timestamps = df["open_time"].values
    
    # Calculate returns of underlying asset
    asset_ret = np.diff(close) / close[:-1] # length n-1
    bh_total_return = (close[-1] / close[0] - 1.0) * 100.0
    
    # Precompute all EMAs
    t0 = time.time()
    ema_matrix = compute_all_emas(close, min_p, max_p)
    print(f"Precomputed {max_p - min_p + 1} EMAs in {time.time()-t0:.3f}s")
    
    periods = list(range(min_p, max_p + 1))
    period_to_idx = {p: i for i, p in enumerate(periods)}
    
    # Total combinations
    combos = []
    for i in range(len(periods)):
        for j in range(i + 1, len(periods)):
            combos.append((periods[i], periods[j]))
            
    num_combos = len(combos)
    print(f"Running brute-force optimization for {num_combos:,} EMA pairs...")
    
    results = []
    
    # Annualization factor for hourly bars (365 * 24 = 8760 hours/yr)
    bars_per_year = 8760
    duration_years = (n - 1) / bars_per_year
    
    t_start = time.time()
    for count, (p_fast, p_slow) in enumerate(combos):
        idx_fast = period_to_idx[p_fast]
        idx_slow = period_to_idx[p_slow]
        
        fast_ema = ema_matrix[idx_fast]
        slow_ema = ema_matrix[idx_slow]
        
        # Position: 1 if fast > slow, 0 otherwise (Long-Only strategy with Cash exit)
        pos = (fast_ema[:-1] > slow_ema[:-1]).astype(np.float64)
        
        strat_ret = pos * asset_ret
        cum_ret_series = np.cumprod(1.0 + strat_ret)
        total_return_pct = (cum_ret_series[-1] - 1.0) * 100.0
        
        # Max Drawdown
        running_max = np.maximum.accumulate(cum_ret_series)
        drawdowns = (cum_ret_series - running_max) / running_max
        max_drawdown_pct = np.abs(np.min(drawdowns)) * 100.0
        
        # Trade level stats
        pos_diff = np.diff(np.concatenate(([0.0], pos, [0.0])))
        entries = np.where(pos_diff == 1.0)[0]
        exits = np.where(pos_diff == -1.0)[0]
        
        num_trades = len(entries)
        if num_trades > 0:
            trade_pnls = []
            for en, ex in zip(entries, exits):
                p_in = close[en]
                p_out = close[ex] if ex < n else close[-1]
                t_ret = (p_out / p_in - 1.0) * 100.0
                trade_pnls.append(t_ret)
            
            trade_pnls = np.array(trade_pnls)
            wins = trade_pnls[trade_pnls > 0]
            losses = trade_pnls[trade_pnls <= 0]
            win_rate_pct = (len(wins) / num_trades) * 100.0
            
            gross_profit = np.sum(wins) if len(wins) > 0 else 0.0
            gross_loss = np.abs(np.sum(losses)) if len(losses) > 0 else 1e-9
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else 999.0
            avg_trade_pct = np.mean(trade_pnls)
            best_trade_pct = np.max(trade_pnls)
            worst_trade_pct = np.min(trade_pnls)
        else:
            win_rate_pct = 0.0
            profit_factor = 0.0
            avg_trade_pct = 0.0
            best_trade_pct = 0.0
            worst_trade_pct = 0.0
            
        # Annualized metrics
        if duration_years > 0:
            cagr_pct = ((cum_ret_series[-1]) ** (1.0 / duration_years) - 1.0) * 100.0
        else:
            cagr_pct = total_return_pct
            
        # Sharpe Ratio (Hourly Sharpe annualized)
        std_ret = np.std(strat_ret)
        if std_ret > 1e-9:
            sharpe_ratio = (np.mean(strat_ret) / std_ret) * np.sqrt(bars_per_year)
        else:
            sharpe_ratio = 0.0
            
        # Calmar Ratio
        calmar_ratio = (cagr_pct / max_drawdown_pct) if max_drawdown_pct > 0 else 0.0
        
        # Exposure %
        exposure_pct = (np.sum(pos) / len(pos)) * 100.0
        alpha_pct = total_return_pct - bh_total_return
        
        results.append({
            "Fast_EMA": p_fast,
            "Slow_EMA": p_slow,
            "Total_Return_Pct": round(total_return_pct, 2),
            "CAGR_Pct": round(cagr_pct, 2),
            "Alpha_Pct": round(alpha_pct, 2),
            "Max_Drawdown_Pct": round(max_drawdown_pct, 2),
            "Sharpe_Ratio": round(sharpe_ratio, 2),
            "Calmar_Ratio": round(calmar_ratio, 2),
            "Win_Rate_Pct": round(win_rate_pct, 2),
            "Profit_Factor": round(profit_factor, 2),
            "Total_Trades": num_trades,
            "Exposure_Pct": round(exposure_pct, 2),
            "Avg_Trade_Pct": round(avg_trade_pct, 2),
            "Best_Trade_Pct": round(best_trade_pct, 2),
            "Worst_Trade_Pct": round(worst_trade_pct, 2)
        })
        
    print(f"Brute force complete in {time.time() - t_start:.2f}s!")
    res_df = pd.DataFrame(results)
    
    # Save full grid
    full_csv = "all_ema_combinations_results.csv"
    res_df.to_csv(full_csv, index=False)
    print(f"Saved all {len(res_df):,} combination results to {full_csv}")
    
    # Top 50 by Sharpe
    top_sharpe = res_df.sort_values(by=["Sharpe_Ratio", "Total_Return_Pct"], ascending=False).head(50)
    top_sharpe.to_csv("top_50_by_sharpe.csv", index=False)
    
    # Top 50 by Total Return
    top_return = res_df.sort_values(by=["Total_Return_Pct", "Sharpe_Ratio"], ascending=False).head(50)
    top_return.to_csv("top_50_by_return.csv", index=False)
    
    # Worst 20
    worst_df = res_df.sort_values(by="Total_Return_Pct", ascending=True).head(20)
    worst_df.to_csv("worst_20_combinations.csv", index=False)
    
    return res_df, top_return, top_sharpe, worst_df, bh_total_return

def generate_visualizations(res_df, df, top_return):
    print("Generating visualizations...")
    os.makedirs("charts", exist_ok=True)
    
    # 1. 2D Heatmap of Total Return
    pivot_ret = res_df.pivot(index="Fast_EMA", columns="Slow_EMA", values="Total_Return_Pct")
    
    plt.style.use("dark_background")
    fig, ax = plt.subplots(figsize=(12, 9))
    cax = ax.imshow(pivot_ret.values, cmap="viridis", aspect="auto", origin="lower",
                    extent=[res_df["Slow_EMA"].min(), res_df["Slow_EMA"].max(), 
                            res_df["Fast_EMA"].min(), res_df["Fast_EMA"].max()])
    cbar = fig.colorbar(cax, ax=ax)
    cbar.set_label("Total Return (%)", color="white", fontsize=12)
    ax.set_title("ETH 2026 - EMA Cross Brute Force Optimization Heatmap (5-250)", fontsize=14, pad=15, color="white", fontweight="bold")
    ax.set_xlabel("Slow EMA Period", fontsize=12, color="white")
    ax.set_ylabel("Fast EMA Period", fontsize=12, color="white")
    ax.grid(color="gray", linestyle="--", alpha=0.3)
    plt.tight_layout()
    plt.savefig("charts/ema_heatmap_returns.png", dpi=300)
    plt.close()
    
    # 2. Sharpe Ratio Heatmap
    pivot_sharpe = res_df.pivot(index="Fast_EMA", columns="Slow_EMA", values="Sharpe_Ratio")
    fig, ax = plt.subplots(figsize=(12, 9))
    cax = ax.imshow(pivot_sharpe.values, cmap="magma", aspect="auto", origin="lower",
                    extent=[res_df["Slow_EMA"].min(), res_df["Slow_EMA"].max(), 
                            res_df["Fast_EMA"].min(), res_df["Fast_EMA"].max()])
    cbar = fig.colorbar(cax, ax=ax)
    cbar.set_label("Sharpe Ratio (Annualized)", color="white", fontsize=12)
    ax.set_title("ETH 2026 - Sharpe Ratio Heatmap (Fast vs Slow EMA)", fontsize=14, pad=15, color="white", fontweight="bold")
    ax.set_xlabel("Slow EMA Period", fontsize=12, color="white")
    ax.set_ylabel("Fast EMA Period", fontsize=12, color="white")
    ax.grid(color="gray", linestyle="--", alpha=0.3)
    plt.tight_layout()
    plt.savefig("charts/ema_heatmap_sharpe.png", dpi=300)
    plt.close()
    
    # 3. Equity Curve Comparison: Top 3 strategies vs ETH Buy & Hold
    best_combo = top_return.iloc[0]
    best_fast, best_slow = int(best_combo["Fast_EMA"]), int(best_combo["Slow_EMA"])
    
    second_combo = top_return.iloc[1]
    sec_fast, sec_slow = int(second_combo["Fast_EMA"]), int(second_combo["Slow_EMA"])
    
    third_combo = top_return.iloc[2]
    third_fast, third_slow = int(third_combo["Fast_EMA"]), int(third_combo["Slow_EMA"])
    
    close = df["close"].values
    asset_ret = np.diff(close) / close[:-1]
    
    def get_equity(p1, p2):
        alpha1 = 2.0 / (p1 + 1.0)
        alpha2 = 2.0 / (p2 + 1.0)
        ema1 = np.empty(len(close))
        ema2 = np.empty(len(close))
        ema1[0] = close[0]; ema2[0] = close[0]
        for t in range(1, len(close)):
            ema1[t] = alpha1 * close[t] + (1 - alpha1) * ema1[t-1]
            ema2[t] = alpha2 * close[t] + (1 - alpha2) * ema2[t-1]
        pos = (ema1[:-1] > ema2[:-1]).astype(float)
        ret = pos * asset_ret
        return np.cumprod(1.0 + ret) * 100.0
        
    eq_best = get_equity(best_fast, best_slow)
    eq_sec = get_equity(sec_fast, sec_slow)
    eq_third = get_equity(third_fast, third_slow)
    eq_bh = np.cumprod(1.0 + asset_ret) * 100.0
    times = df["open_time"].iloc[1:]
    
    fig, ax = plt.subplots(figsize=(14, 7))
    ax.plot(times, eq_best, label=f"Rank #1: EMA ({best_fast}, {best_slow}) [Return: {best_combo['Total_Return_Pct']:.1f}%]", color="#00ffcc", linewidth=2.0)
    ax.plot(times, eq_sec, label=f"Rank #2: EMA ({sec_fast}, {sec_slow}) [Return: {second_combo['Total_Return_Pct']:.1f}%]", color="#ffcc00", linewidth=1.5)
    ax.plot(times, eq_third, label=f"Rank #3: EMA ({third_fast}, {third_slow}) [Return: {third_combo['Total_Return_Pct']:.1f}%]", color="#ff66cc", linewidth=1.5)
    ax.plot(times, eq_bh, label=f"ETH Benchmark (Buy & Hold) [Return: {(close[-1]/close[0]-1)*100:.1f}%]", color="#888888", linestyle="--", linewidth=1.8)
    
    ax.set_title("ETH 2026: Equity Curve Comparison (Top EMA Strategies vs Buy & Hold)", fontsize=14, color="white", fontweight="bold", pad=15)
    ax.set_ylabel("Portfolio Value (Base = 100)", fontsize=12, color="white")
    ax.legend(loc="upper left", frameon=True, facecolor="#1e1e1e", edgecolor="#444444")
    ax.grid(color="gray", linestyle="--", alpha=0.3)
    plt.tight_layout()
    plt.savefig("charts/top_equity_curves.png", dpi=300)
    plt.close()
    print("Charts generated successfully in ./charts directory!")

def main():
    df = fetch_eth_2026_klines(symbol="ETHUSDT", interval="1h", start_str="2026-01-01 00:00:00")
    res_df, top_return, top_sharpe, worst_df, bh_ret = run_brute_force(df, min_p=5, max_p=250)
    generate_visualizations(res_df, df, top_return)
    print("\n--- SUMMARY OF TOP 10 EMA COMBINATIONS (BY TOTAL RETURN) ---")
    print(top_return.head(10).to_string(index=False))
    print("\n--- SUMMARY OF TOP 10 EMA COMBINATIONS (BY SHARPE RATIO) ---")
    print(top_sharpe.head(10).to_string(index=False))

if __name__ == "__main__":
    main()
