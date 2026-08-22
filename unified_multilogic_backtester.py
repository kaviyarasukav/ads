import os
import sys
import json
import time
import sqlite3
import datetime
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

def load_data(db_path="eth_market_data.sqlite"):
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        df_5m = pd.read_sql_query("SELECT open_time, open, high, low, close, volume FROM candles_5m ORDER BY open_time ASC", conn)
        conn.close()
        df_5m["open_time"] = pd.to_datetime(df_5m["open_time"], unit="ms", utc=True)
        # Resample to 1h
        df = df_5m.set_index("open_time").resample("1h").agg({
            "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"
        }).dropna().reset_index()
    else:
        df = pd.read_csv("eth_2026_1h.csv")
        df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
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

def backtest_position_series(pos, close, open_times, logic_name, fast_p, slow_p, months, month_indices, bh_total_return):
    """
    pos: array of length n-1 representing position taken at bar t to hold from t to t+1
    close: price array of length n
    open_times: timestamps array of length n
    """
    n = len(close)
    asset_ret = np.diff(close) / close[:-1] # length n-1
    strat_ret = pos * asset_ret
    cum_ret = np.cumprod(1.0 + strat_ret)
    total_return_pct = (cum_ret[-1] - 1.0) * 100.0
    
    running_max = np.maximum.accumulate(cum_ret)
    drawdowns = (cum_ret - running_max) / running_max
    min_dd_idx = np.argmin(drawdowns)
    max_drawdown_pct = np.abs(drawdowns[min_dd_idx]) * 100.0
    
    # Monthly returns
    monthly_rets = {}
    pos_months = 0
    neg_months = 0
    for m_name in months:
        m_idxs = month_indices[m_name]
        if len(m_idxs) > 0:
            m_ret = (np.prod(1.0 + strat_ret[m_idxs]) - 1.0) * 100.0
            m_ret_rnd = round(m_ret, 2)
            monthly_rets[m_name] = m_ret_rnd
            if m_ret_rnd > 0: pos_months += 1
            elif m_ret_rnd < 0: neg_months += 1
        else:
            monthly_rets[m_name] = 0.0
            
    # Trade logging
    # Identify position changes
    padded_pos = np.concatenate(([0.0], pos, [0.0]))
    pos_changes = np.diff(padded_pos)
    change_indices = np.where(pos_changes != 0)[0]
    
    trades = []
    current_pos = 0.0
    entry_bar = 0
    entry_price = 0.0
    entry_time = None
    cum_equity = 1.0
    
    for i in range(len(pos)):
        new_pos = pos[i]
        if new_pos != current_pos:
            # Close existing position if any
            if current_pos != 0.0:
                exit_bar = i
                exit_price = close[exit_bar]
                exit_time = str(open_times[exit_bar])[:19]
                if current_pos == 1.0: # Long
                    trade_pnl = (exit_price / entry_price - 1.0) * 100.0
                    direction = "LONG"
                else: # Short
                    trade_pnl = (1.0 - exit_price / entry_price) * 100.0
                    direction = "SHORT"
                
                duration_hours = exit_bar - entry_bar
                trades.append({
                    "Strategy_Logic": logic_name,
                    "Fast_EMA": fast_p,
                    "Slow_EMA": slow_p,
                    "Trade_ID": len(trades) + 1,
                    "Direction": direction,
                    "Entry_Time": entry_time,
                    "Entry_Price": round(entry_price, 2),
                    "Exit_Time": exit_time,
                    "Exit_Price": round(exit_price, 2),
                    "Duration_Hours": duration_hours,
                    "Trade_PnL_Pct": round(trade_pnl, 2),
                    "Exit_Reason": f"Signal changed to {new_pos}"
                })
            
            # Open new position if any
            if new_pos != 0.0:
                entry_bar = i
                entry_price = close[entry_bar]
                entry_time = str(open_times[entry_bar])[:19]
            
            current_pos = new_pos
            
    # Close any open trade at last bar
    if current_pos != 0.0:
        exit_bar = n - 1
        exit_price = close[exit_bar]
        exit_time = str(open_times[exit_bar])[:19]
        if current_pos == 1.0:
            trade_pnl = (exit_price / entry_price - 1.0) * 100.0
            direction = "LONG"
        else:
            trade_pnl = (1.0 - exit_price / entry_price) * 100.0
            direction = "SHORT"
        duration_hours = exit_bar - entry_bar
        trades.append({
            "Strategy_Logic": logic_name,
            "Fast_EMA": fast_p,
            "Slow_EMA": slow_p,
            "Trade_ID": len(trades) + 1,
            "Direction": direction,
            "Entry_Time": entry_time,
            "Entry_Price": round(entry_price, 2),
            "Exit_Time": exit_time,
            "Exit_Price": round(exit_price, 2),
            "Duration_Hours": duration_hours,
            "Trade_PnL_Pct": round(trade_pnl, 2),
            "Exit_Reason": "End of Dataset"
        })
        
    num_trades = len(trades)
    if num_trades > 0:
        pnls = np.array([t["Trade_PnL_Pct"] for t in trades])
        wins = pnls[pnls > 0]
        losses = pnls[pnls <= 0]
        win_rate_pct = (len(wins) / num_trades) * 100.0
        gross_profit = np.sum(wins) if len(wins) > 0 else 0.0
        gross_loss = np.abs(np.sum(losses)) if len(losses) > 0 else 1e-9
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 999.0
        avg_trade_pct = np.mean(pnls)
        best_trade_pct = np.max(pnls)
        worst_trade_pct = np.min(pnls)
        avg_holding_hours = np.mean([t["Duration_Hours"] for t in trades])
    else:
        win_rate_pct = 0.0
        profit_factor = 0.0
        avg_trade_pct = 0.0
        best_trade_pct = 0.0
        worst_trade_pct = 0.0
        avg_holding_hours = 0.0
        
    duration_years = (n - 1) / 8760.0
    cagr_pct = ((cum_ret[-1]) ** (1.0 / duration_years) - 1.0) * 100.0 if duration_years > 0 else total_return_pct
    std_ret = np.std(strat_ret)
    sharpe = (np.mean(strat_ret) / std_ret) * np.sqrt(8760.0) if std_ret > 1e-9 else 0.0
    
    downside_ret = strat_ret[strat_ret < 0]
    downside_std = np.std(downside_ret) if len(downside_ret) > 0 else 1e-9
    sortino = (np.mean(strat_ret) / downside_std) * np.sqrt(8760.0) if downside_std > 1e-9 else 0.0
    calmar = (cagr_pct / max_drawdown_pct) if max_drawdown_pct > 0 else 0.0
    alpha_pct = total_return_pct - bh_total_return
    exposure_pct = (np.sum(np.abs(pos)) / len(pos)) * 100.0
    
    summary = {
        "Strategy_Logic": logic_name,
        "Fast_EMA": fast_p,
        "Slow_EMA": slow_p,
        "Total_Return_Pct": round(total_return_pct, 2),
        "CAGR_Pct": round(cagr_pct, 2),
        "Alpha_Pct": round(alpha_pct, 2),
        "Max_Drawdown_Pct": round(max_drawdown_pct, 2),
        "Sharpe_Ratio": round(sharpe, 2),
        "Sortino_Ratio": round(sortino, 2),
        "Calmar_Ratio": round(calmar, 2),
        "Win_Rate_Pct": round(win_rate_pct, 2),
        "Profit_Factor": round(profit_factor, 2),
        "Total_Trades": num_trades,
        "Avg_Holding_Hours": round(avg_holding_hours, 1),
        "Avg_Trade_Pct": round(avg_trade_pct, 2),
        "Best_Trade_Pct": round(best_trade_pct, 2),
        "Worst_Trade_Pct": round(worst_trade_pct, 2),
        "Exposure_Pct": round(exposure_pct, 2),
        "Pos_Months": pos_months,
        "Neg_Months": neg_months
    }
    for m in months:
        summary[m] = monthly_rets[m]
        
    return summary, trades

def run_all_logics():
    os.makedirs("results/trades_detailed_logs", exist_ok=True)
    df = load_data()
    close = df["close"].values
    n = len(close)
    open_times = df["open_time"].values
    
    bh_total_return = (close[-1] / close[0] - 1.0) * 100.0
    print(f"Loaded {n} hourly candles. ETH Benchmark Return: {bh_total_return:.2f}%")
    
    timestamps_dt = pd.to_datetime(df["open_time"].iloc[1:])
    months = ["Jan_2026", "Feb_2026", "Mar_2026", "Apr_2026", "May_2026", "Jun_2026", "Jul_2026", "Aug_2026"]
    month_indices = {}
    for m_num, m_name in enumerate(months, start=1):
        mask = (timestamps_dt.dt.month == m_num) & (timestamps_dt.dt.year == 2026)
        month_indices[m_name] = np.where(mask.values)[0]
        
    min_p, max_p = 5, 250
    ema_matrix = compute_all_emas(close, min_p, max_p)
    periods = list(range(min_p, max_p + 1))
    period_to_idx = {p: i for i, p in enumerate(periods)}
    
    all_summaries = []
    top_trades_collector = []
    
    print("\n--- 1. Testing Logic: PRICE vs EMA (Single EMA Long-Only) ---")
    # Price > EMA -> Long (1), Price < EMA -> Cash (0)
    for p in periods:
        ema = ema_matrix[period_to_idx[p]]
        pos = (close[:-1] > ema[:-1]).astype(np.float64)
        summary, trades = backtest_position_series(pos, close, open_times, "PRICE_VS_EMA_LONG_ONLY", p, "None", months, month_indices, bh_total_return)
        all_summaries.append(summary)
        if p in [10, 20, 50, 100, 200]:
            top_trades_collector.extend(trades)
            
    print("--- 2. Testing Logic: PRICE vs EMA (Single EMA Stop-and-Reverse SAR) ---")
    # Price > EMA -> Long (+1), Price < EMA -> Short (-1)
    for p in periods:
        ema = ema_matrix[period_to_idx[p]]
        pos = np.where(close[:-1] > ema[:-1], 1.0, -1.0)
        summary, trades = backtest_position_series(pos, close, open_times, "PRICE_VS_EMA_SAR_LONG_SHORT", p, "None", months, month_indices, bh_total_return)
        all_summaries.append(summary)
        if p in [10, 20, 50, 100, 200]:
            top_trades_collector.extend(trades)
            
    print("--- 3. Testing Logic: EMA CROSSOVER (Long-Only / Fast vs Slow) ---")
    # Fast > Slow -> Long (+1), Fast < Slow -> Cash (0)
    combos = []
    for i in range(len(periods)):
        for j in range(i + 1, len(periods)):
            combos.append((periods[i], periods[j]))
            
    t0 = time.time()
    for count, (p_fast, p_slow) in enumerate(combos):
        idx_f = period_to_idx[p_fast]
        idx_s = period_to_idx[p_slow]
        pos = (ema_matrix[idx_f][:-1] > ema_matrix[idx_s][:-1]).astype(np.float64)
        summary, trades = backtest_position_series(pos, close, open_times, "EMA_CROSSOVER_LONG_ONLY", p_fast, p_slow, months, month_indices, bh_total_return)
        all_summaries.append(summary)
        if (p_fast, p_slow) in [(5, 15), (208, 224), (50, 200), (12, 26), (9, 21)]:
            top_trades_collector.extend(trades)
            
    print(f"Tested {len(combos):,} Long-Only EMA pairs in {time.time()-t0:.2f}s")
    
    print("--- 4. Testing Logic: EMA CROSSOVER (Stop-and-Reverse SAR / Long-Short) ---")
    # Fast > Slow -> Long (+1), Fast < Slow -> Short (-1)
    t0 = time.time()
    for count, (p_fast, p_slow) in enumerate(combos):
        idx_f = period_to_idx[p_fast]
        idx_s = period_to_idx[p_slow]
        pos = np.where(ema_matrix[idx_f][:-1] > ema_matrix[idx_s][:-1], 1.0, -1.0)
        summary, trades = backtest_position_series(pos, close, open_times, "EMA_CROSSOVER_SAR_LONG_SHORT", p_fast, p_slow, months, month_indices, bh_total_return)
        all_summaries.append(summary)
        if (p_fast, p_slow) in [(5, 15), (208, 224), (50, 200), (12, 26), (9, 21)]:
            top_trades_collector.extend(trades)
            
    print(f"Tested {len(combos):,} SAR EMA pairs in {time.time()-t0:.2f}s")
    
    # Compile Master Summary DataFrame
    master_df = pd.DataFrame(all_summaries)
    master_csv = "results/master_all_logics_summary.csv"
    master_df.to_csv(master_csv, index=False)
    print(f"\nSaved Master Summary with {len(master_df):,} strategies to {master_csv}")
    
    # Save Top 50 by Return for Each Logic Separately
    for logic_name in master_df["Strategy_Logic"].unique():
        sub = master_df[master_df["Strategy_Logic"] == logic_name].sort_values(by="Total_Return_Pct", ascending=False)
        sub_file = f"results/top_50_{logic_name.lower()}.csv"
        sub.head(50).to_csv(sub_file, index=False)
        print(f"Saved: {sub_file} (Best Return: {sub.iloc[0]['Total_Return_Pct']}%)")
        
    # Save Detailed Trade Logs
    trades_df = pd.DataFrame(top_trades_collector)
    trades_file = "results/trades_detailed_logs/representative_strategies_trades.csv"
    trades_df.to_csv(trades_file, index=False)
    print(f"Saved {len(trades_df):,} detailed trades to {trades_file}")
    
    # Store in SQLite database as well
    conn = sqlite3.connect("eth_market_data.sqlite")
    master_df.to_sql("strategy_summary_metrics", conn, if_exists="replace", index=False)
    trades_df.to_sql("detailed_trade_logs", conn, if_exists="replace", index=False)
    conn.close()
    print("Stored all summaries and trade logs into eth_market_data.sqlite!")
    
    return master_df, trades_df

if __name__ == "__main__":
    run_all_logics()
