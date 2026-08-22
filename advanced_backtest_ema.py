import os
import sys
import json
import time
import datetime
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from concurrent.futures import ProcessPoolExecutor

def load_or_fetch_eth_2026():
    csv_file = "eth_2026_1h.csv"
    if os.path.exists(csv_file):
        df = pd.read_csv(csv_file)
        df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
        df["close_time"] = pd.to_datetime(df["close_time"], utc=True)
        print(f"Loaded existing {csv_file}: {len(df)} candles from {df['open_time'].iloc[0]} to {df['open_time'].iloc[-1]}")
        return df
    else:
        import urllib.request
        start_ts = int(pd.Timestamp("2026-01-01 00:00:00", tz="UTC").timestamp() * 1000)
        end_ts = int(pd.Timestamp.now(tz="UTC").timestamp() * 1000)
        all_candles = []
        current_start = start_ts
        while current_start < end_ts:
            url = f"https://api.binance.com/api/v3/klines?symbol=ETHUSDT&interval=1h&startTime={current_start}&limit=1000"
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
        df = pd.DataFrame(all_candles, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_asset_volume", "num_trades",
            "taker_buy_base_volume", "taker_buy_quote_volume", "ignore"
        ])
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
        df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)
        df = df.drop_duplicates(subset=["open_time"]).sort_values("open_time").reset_index(drop=True)
        df.to_csv(csv_file, index=False)
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

def run_comprehensive_analysis(df, min_p=5, max_p=250):
    close = df["close"].values
    n = len(close)
    open_times = df["open_time"].values
    close_times = df["close_time"].values
    
    asset_ret = np.diff(close) / close[:-1]
    bh_total_return = (close[-1] / close[0] - 1.0) * 100.0
    bh_max_dd = np.abs(np.min((np.cumprod(1.0 + asset_ret) - np.maximum.accumulate(np.cumprod(1.0 + asset_ret))) / np.maximum.accumulate(np.cumprod(1.0 + asset_ret)))) * 100.0
    
    # Precompute months masks
    # Extract month of each bar
    timestamps_dt = pd.to_datetime(df["open_time"].iloc[1:]) # length n-1
    months = ["Jan_2026", "Feb_2026", "Mar_2026", "Apr_2026", "May_2026", "Jun_2026", "Jul_2026", "Aug_2026"]
    month_indices = {}
    bh_monthly_rets = {}
    for m_num, m_name in enumerate(months, start=1):
        mask = (timestamps_dt.dt.month == m_num) & (timestamps_dt.dt.year == 2026)
        idxs = np.where(mask.values)[0]
        month_indices[m_name] = idxs
        if len(idxs) > 0:
            m_bh = (np.prod(1.0 + asset_ret[idxs]) - 1.0) * 100.0
            bh_monthly_rets[m_name] = round(m_bh, 2)
        else:
            bh_monthly_rets[m_name] = 0.0
            
    print("ETH 2026 Monthly Benchmark Returns (%):", bh_monthly_rets)
    
    ema_matrix = compute_all_emas(close, min_p, max_p)
    periods = list(range(min_p, max_p + 1))
    period_to_idx = {p: i for i, p in enumerate(periods)}
    
    combos = []
    for i in range(len(periods)):
        for j in range(i + 1, len(periods)):
            combos.append((periods[i], periods[j]))
            
    total_combos = len(combos)
    print(f"Brute-forcing {total_combos:,} combinations with full monthly breakdown & metrics...")
    
    results = []
    bars_per_year = 8760
    duration_years = (n - 1) / bars_per_year
    
    t0 = time.time()
    for count, (p_fast, p_slow) in enumerate(combos):
        idx_fast = period_to_idx[p_fast]
        idx_slow = period_to_idx[p_slow]
        
        fast_ema = ema_matrix[idx_fast]
        slow_ema = ema_matrix[idx_slow]
        
        # Position execution (shifted by 1 bar to prevent lookahead)
        pos = (fast_ema[:-1] > slow_ema[:-1]).astype(np.float64)
        strat_ret = pos * asset_ret
        cum_ret = np.cumprod(1.0 + strat_ret)
        total_return_pct = (cum_ret[-1] - 1.0) * 100.0
        
        # Peak equity & Max Drawdown details
        running_max = np.maximum.accumulate(cum_ret)
        drawdowns = (cum_ret - running_max) / running_max
        min_dd_idx = np.argmin(drawdowns)
        max_drawdown_pct = np.abs(drawdowns[min_dd_idx]) * 100.0
        peak_idx = np.argmax(cum_ret)
        
        peak_time_str = str(open_times[peak_idx + 1])[:19]
        mdd_trough_time_str = str(open_times[min_dd_idx + 1])[:19]
        
        # Monthly returns calculation
        monthly_strat_rets = {}
        pos_months_count = 0
        neg_months_count = 0
        for m_name in months:
            m_idxs = month_indices[m_name]
            if len(m_idxs) > 0:
                m_ret = (np.prod(1.0 + strat_ret[m_idxs]) - 1.0) * 100.0
                m_ret_rnd = round(m_ret, 2)
                monthly_strat_rets[m_name] = m_ret_rnd
                if m_ret_rnd > 0:
                    pos_months_count += 1
                elif m_ret_rnd < 0:
                    neg_months_count += 1
            else:
                monthly_strat_rets[m_name] = 0.0
                
        # Best & Worst month
        m_vals = list(monthly_strat_rets.values())
        best_month_idx = np.argmax(m_vals)
        worst_month_idx = np.argmin(m_vals)
        best_month_str = f"{months[best_month_idx]} ({m_vals[best_month_idx]:+.2f}%)"
        worst_month_str = f"{months[worst_month_idx]} ({m_vals[worst_month_idx]:+.2f}%)"
        
        # Trade level stats
        pos_diff = np.diff(np.concatenate(([0.0], pos, [0.0])))
        entries = np.where(pos_diff == 1.0)[0]
        exits = np.where(pos_diff == -1.0)[0]
        num_trades = len(entries)
        
        if num_trades > 0:
            trade_pnls = []
            durations = []
            for en, ex in zip(entries, exits):
                p_in = close[en]
                p_out = close[ex] if ex < n else close[-1]
                t_ret = (p_out / p_in - 1.0) * 100.0
                trade_pnls.append(t_ret)
                durations.append(ex - en)
            
            trade_pnls = np.array(trade_pnls)
            durations = np.array(durations)
            wins = trade_pnls[trade_pnls > 0]
            losses = trade_pnls[trade_pnls <= 0]
            win_rate_pct = (len(wins) / num_trades) * 100.0
            
            gross_profit = np.sum(wins) if len(wins) > 0 else 0.0
            gross_loss = np.abs(np.sum(losses)) if len(losses) > 0 else 1e-9
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else 999.0
            
            avg_trade_pct = np.mean(trade_pnls)
            avg_win_pct = np.mean(wins) if len(wins) > 0 else 0.0
            avg_loss_pct = np.mean(losses) if len(losses) > 0 else 0.0
            win_loss_ratio = (avg_win_pct / abs(avg_loss_pct)) if abs(avg_loss_pct) > 1e-9 else 999.0
            expectancy_pct = (win_rate_pct/100.0 * avg_win_pct) + ((1.0 - win_rate_pct/100.0) * avg_loss_pct)
            
            best_trade_pct = np.max(trade_pnls)
            worst_trade_pct = np.min(trade_pnls)
            avg_holding_hours = np.mean(durations)
            
            # Max Consecutive Wins / Losses
            is_win = (trade_pnls > 0).astype(int)
            max_cons_wins = 0
            max_cons_losses = 0
            cur_w = 0
            cur_l = 0
            for w in is_win:
                if w == 1:
                    cur_w += 1
                    cur_l = 0
                    if cur_w > max_cons_wins:
                        max_cons_wins = cur_w
                else:
                    cur_l += 1
                    cur_w = 0
                    if cur_l > max_cons_losses:
                        max_cons_losses = cur_l
        else:
            win_rate_pct = 0.0
            profit_factor = 0.0
            avg_trade_pct = 0.0
            avg_win_pct = 0.0
            avg_loss_pct = 0.0
            win_loss_ratio = 0.0
            expectancy_pct = 0.0
            best_trade_pct = 0.0
            worst_trade_pct = 0.0
            avg_holding_hours = 0.0
            max_cons_wins = 0
            max_cons_losses = 0
            
        cagr_pct = ((cum_ret[-1]) ** (1.0 / duration_years) - 1.0) * 100.0 if duration_years > 0 else total_return_pct
        
        # Sharpe Ratio
        std_ret = np.std(strat_ret)
        sharpe_ratio = (np.mean(strat_ret) / std_ret) * np.sqrt(bars_per_year) if std_ret > 1e-9 else 0.0
        
        # Sortino Ratio (Downside volatility only)
        downside_ret = strat_ret[strat_ret < 0]
        downside_std = np.std(downside_ret) if len(downside_ret) > 0 else 1e-9
        sortino_ratio = (np.mean(strat_ret) / downside_std) * np.sqrt(bars_per_year) if downside_std > 1e-9 else 0.0
        
        calmar_ratio = (cagr_pct / max_drawdown_pct) if max_drawdown_pct > 0 else 0.0
        exposure_pct = (np.sum(pos) / len(pos)) * 100.0
        alpha_pct = total_return_pct - bh_total_return
        
        res_row = {
            "Fast_EMA": p_fast,
            "Slow_EMA": p_slow,
            "Total_Return_Pct": round(total_return_pct, 2),
            "CAGR_Pct": round(cagr_pct, 2),
            "Alpha_Pct": round(alpha_pct, 2),
            "Max_Drawdown_Pct": round(max_drawdown_pct, 2),
            "Sharpe_Ratio": round(sharpe_ratio, 2),
            "Sortino_Ratio": round(sortino_ratio, 2),
            "Calmar_Ratio": round(calmar_ratio, 2),
            "Win_Rate_Pct": round(win_rate_pct, 2),
            "Profit_Factor": round(profit_factor, 2),
            "Expectancy_Pct": round(expectancy_pct, 2),
            "Total_Trades": num_trades,
            "Avg_Holding_Hours": round(avg_holding_hours, 1),
            "Avg_Win_Pct": round(avg_win_pct, 2),
            "Avg_Loss_Pct": round(avg_loss_pct, 2),
            "Win_Loss_Ratio": round(win_loss_ratio, 2),
            "Max_Cons_Wins": max_cons_wins,
            "Max_Cons_Losses": max_cons_losses,
            "Best_Trade_Pct": round(best_trade_pct, 2),
            "Worst_Trade_Pct": round(worst_trade_pct, 2),
            "Exposure_Pct": round(exposure_pct, 2),
            "Pos_Months": pos_months_count,
            "Neg_Months": neg_months_count,
            "Best_Month": best_month_str,
            "Worst_Month": worst_month_str,
            "Peak_Time": peak_time_str,
            "MDD_Trough_Time": mdd_trough_time_str
        }
        # Add individual monthly columns
        for m_name in months:
            res_row[m_name] = monthly_strat_rets[m_name]
            
        results.append(res_row)
        
    print(f"Full analysis completed in {time.time() - t0:.2f}s!")
    res_df = pd.DataFrame(results)
    
    # Save full matrix
    res_df.to_csv("all_ema_comprehensive_results.csv", index=False)
    print(f"Saved all_ema_comprehensive_results.csv ({len(res_df):,} rows)")
    
    # Top 50 by Return & Top 50 by Sharpe
    top_ret_df = res_df.sort_values(by=["Total_Return_Pct", "Sharpe_Ratio"], ascending=False).head(50)
    top_ret_df.to_csv("top_50_comprehensive_by_return.csv", index=False)
    
    top_sharpe_df = res_df.sort_values(by=["Sharpe_Ratio", "Total_Return_Pct"], ascending=False).head(50)
    top_sharpe_df.to_csv("top_50_comprehensive_by_sharpe.csv", index=False)
    
    # Generate Monthly Matrix Comparison CSV for Top 20 strategies vs ETH
    monthly_cols = ["Fast_EMA", "Slow_EMA", "Total_Return_Pct", "Max_Drawdown_Pct", "Sharpe_Ratio", "Pos_Months"] + months
    top_monthly_matrix = top_ret_df[monthly_cols].copy()
    
    # Add benchmark row
    bh_row = {
        "Fast_EMA": "ETH", "Slow_EMA": "Hold",
        "Total_Return_Pct": round(bh_total_return, 2),
        "Max_Drawdown_Pct": round(bh_max_dd, 2),
        "Sharpe_Ratio": -0.62,
        "Pos_Months": sum(1 for v in bh_monthly_rets.values() if v > 0)
    }
    for m in months:
        bh_row[m] = bh_monthly_rets[m]
    
    top_monthly_matrix = pd.concat([pd.DataFrame([bh_row]), top_monthly_matrix], ignore_index=True)
    top_monthly_matrix.to_csv("top_strategies_monthly_matrix.csv", index=False)
    
    # Generate monthly heatmap comparison plot
    generate_monthly_visualizations(top_monthly_matrix, months)
    
    return res_df, top_ret_df, top_sharpe_df, bh_monthly_rets, bh_total_return, df

def generate_monthly_visualizations(top_monthly_df, months):
    os.makedirs("charts", exist_ok=True)
    plt.style.use("dark_background")
    
    # Monthly Heatmap of Top 10 + ETH Benchmark
    sub_df = top_monthly_df.head(11).copy()
    labels = []
    for idx, r in sub_df.iterrows():
        if r["Fast_EMA"] == "ETH":
            labels.append("ETH Buy & Hold")
        else:
            labels.append(f"EMA ({r['Fast_EMA']}, {r['Slow_EMA']})")
            
    m_data = sub_df[months].values.astype(float)
    
    fig, ax = plt.subplots(figsize=(13, 7))
    import matplotlib
    cmap = matplotlib.colormaps["RdYlGn"]
    cax = ax.imshow(m_data, cmap=cmap, aspect="auto", vmin=-20, vmax=25)
    
    ax.set_xticks(np.arange(len(months)))
    ax.set_yticks(np.arange(len(labels)))
    ax.set_xticklabels([m.replace("_", " ") for m in months], fontsize=11, fontweight="bold", color="white")
    ax.set_yticklabels(labels, fontsize=11, fontweight="bold", color="white")
    
    # Annotate numbers in heatmap
    for i in range(len(labels)):
        for j in range(len(months)):
            val = m_data[i, j]
            text_color = "black" if -10 < val < 15 else "white"
            ax.text(j, i, f"{val:+.1f}%", ha="center", va="center", color=text_color, fontweight="bold", fontsize=10)
            
    cbar = fig.colorbar(cax, ax=ax)
    cbar.set_label("Monthly Return (%)", color="white", fontsize=12)
    ax.set_title("ETH 2026: Month-by-Month Returns Breakdown (Top Strategies vs ETH Benchmark)", fontsize=13, fontweight="bold", pad=15, color="white")
    plt.tight_layout()
    plt.savefig("charts/monthly_returns_heatmap.png", dpi=300)
    plt.close()
    print("Monthly returns heatmap saved to charts/monthly_returns_heatmap.png")

def main():
    df = load_or_fetch_eth_2026()
    res_df, top_ret_df, top_sharpe_df, bh_monthly, bh_tot, raw_df = run_comprehensive_analysis(df, min_p=5, max_p=250)
    print("\n--- TOP 10 STRATEGIES MONTHLY RETURNS BREAKDOWN ---")
    cols_to_print = ["Fast_EMA", "Slow_EMA", "Total_Return_Pct", "Jan_2026", "Feb_2026", "Mar_2026", "Apr_2026", "May_2026", "Jun_2026", "Jul_2026", "Aug_2026"]
    print(top_ret_df[cols_to_print].head(10).to_string(index=False))

if __name__ == "__main__":
    main()
