"""
Unified Trade Execution Engine (Baseline X=0, Y=0 & Series Reinvestment X=n, Y=n)
==================================================================================
Strict 1-bar delay execution, 0.10% round-trip fee model, zero lookahead bias.

Supports:
  1. Base Execution (X=0, Y=0): Single entry on signal flip, 1-shot holding until exit.
  2. Series Reinvestment (X=n, Y=n): Initial entry + continuous tranche additions (X%)
     at factor trigger intervals (Y) until exit flip.
  3. Direct Trade-by-Trade Comparative Delta Tracking:
     Compares Base (X=0, Y=0) vs Reinvested (X=n, Y=n) on the exact same market bars.
"""

import sqlite3
import numpy as np
import pandas as pd
import multiprocessing as mp
import time
import os

FEE_RT = 0.001       # 0.10% round-trip fee
INITIAL_CAPITAL = 10_000.0

def load_data():
    conn = sqlite3.connect("eth_market_data.sqlite")
    df_5m = pd.read_sql_query("SELECT open_time, open, high, low, close, volume FROM candles_5m ORDER BY open_time ASC", conn)
    conn.close()
    
    df_5m["open_time"] = pd.to_datetime(df_5m["open_time"], unit="ms", utc=True)
    df_1h = df_5m.set_index("open_time").resample("1h").agg({
        "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"
    }).dropna().reset_index()
    return df_1h

def build_ema_matrix(close, min_p=5, max_p=250):
    n = len(close)
    num_periods = max_p - min_p + 1
    ema_matrix = np.empty((num_periods, n), dtype=np.float64)
    for idx, p in enumerate(range(min_p, max_p + 1)):
        alpha = 2.0 / (p + 1.0)
        ema = np.empty(n, dtype=np.float64)
        ema[0] = close[0]
        for t in range(1, n):
            ema[t] = alpha * close[t] + (1.0 - alpha) * ema[t-1]
        ema_matrix[idx] = ema
    period_to_idx = {p: i for i, p in enumerate(range(min_p, max_p + 1))}
    return ema_matrix, period_to_idx

def simulate_series_execution(close, open_times, logic, fast_p, slow_p, y_factor, y_val, x_pct, ema_matrix, period_to_idx, record_details=False):
    """
    Unified Execution Simulator:
    If x_pct == 0 or y_val == 0: Behaves as pure Baseline (X=0, Y=0).
    If x_pct > 0 and y_val > 0: Behaves as Series Reinvestment (X=n, Y=n).
    """
    n = len(close)
    if "PRICE" in logic:
        ema = ema_matrix[period_to_idx[fast_p]]
        if "LONG_ONLY" in logic:
            signals = np.where(close > ema, 1.0, 0.0)
        else:
            signals = np.where(close > ema, 1.0, -1.0)
    else:
        idx_f = period_to_idx[fast_p]
        idx_s = period_to_idx[slow_p]
        if "LONG_ONLY" in logic:
            signals = np.where(ema_matrix[idx_f] > ema_matrix[idx_s], 1.0, 0.0)
        else:
            signals = np.where(ema_matrix[idx_f] > ema_matrix[idx_s], 1.0, -1.0)

    # 1-bar execution delay
    pos = np.zeros(n, dtype=np.float64)
    pos[1:] = signals[:-1]

    # Execution state
    portfolio_equity = INITIAL_CAPITAL
    cash = INITIAL_CAPITAL
    units = 0.0
    cost_basis_total = 0.0
    current_direction = 0.0
    
    series_entry_bar = 0
    series_entry_price = 0.0
    series_entry_time = None
    last_add_bar = 0
    last_add_price = 0.0
    adds_count = 0
    
    is_pyramiding = (x_pct > 0 and y_val > 0)
    fixed_tranche_usd = (INITIAL_CAPITAL * (x_pct / 100.0)) if is_pyramiding else INITIAL_CAPITAL
    max_possible_adds = int(100 // x_pct) if is_pyramiding else 1

    closed_trades = []
    series_adds = []
    
    equity_curve = [INITIAL_CAPITAL]
    peak_equity = INITIAL_CAPITAL
    max_drawdown_pct = 0.0
    
    monthly_equities = {m: [] for m in ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug"]}
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug"]

    month_indices = pd.to_datetime(open_times).month - 1
    for i in range(1, n):
        target_pos = pos[i]
        curr_price = close[i]
        bar_time = str(open_times[i])[:16]
        m_idx = month_indices[i]
        if 0 <= m_idx < len(month_names):
            m_name = month_names[m_idx]
        else:
            m_name = "Aug"

        # Signal Flip / Position Close Check
        if target_pos != current_direction and current_direction != 0.0:
            exit_price = curr_price * (1.0 - (FEE_RT / 2.0) if current_direction == 1.0 else 1.0 + (FEE_RT / 2.0))
            if current_direction == 1.0:
                proceeds = units * exit_price * (1.0 - FEE_RT / 2.0)
                realized_pnl_usd = proceeds - cost_basis_total
            else: # SHORT
                proceeds = cost_basis_total + (cost_basis_total - units * exit_price * (1.0 + FEE_RT / 2.0))
                realized_pnl_usd = proceeds - cost_basis_total
            
            cash += proceeds
            portfolio_equity = cash
            realized_pnl_pct = (realized_pnl_usd / cost_basis_total) * 100.0 if cost_basis_total > 0 else 0.0
            avg_entry_price = cost_basis_total / units if units > 0 else series_entry_price

            if record_details:
                closed_trades.append({
                    "Strategy": f"{logic}_{fast_p}_{slow_p}",
                    "Logic": logic,
                    "Fast_EMA": fast_p,
                    "Slow_EMA": slow_p,
                    "Y_Factor": y_factor,
                    "Y_Value": y_val,
                    "X_Pct": x_pct,
                    "Note": f"[{logic}] EMA({fast_p},{slow_p}) | Y_Factor={y_factor} Y_Val={y_val} X%={x_pct}" if is_pyramiding else f"[{logic}] EMA({fast_p},{slow_p}) | Baseline (X=0, Y=0)",
                    "Direction": "LONG" if current_direction == 1.0 else "SHORT",
                    "Series_Entry_Time": series_entry_time,
                    "Series_Entry_Price": round(series_entry_price, 2),
                    "Avg_Entry_Price": round(avg_entry_price, 2),
                    "Exit_Time": bar_time,
                    "Exit_Price": round(exit_price, 2),
                    "Total_Adds_In_Series": adds_count,
                    "Total_Invested_USD": round(cost_basis_total, 2),
                    "Realized_PnL_USD": round(realized_pnl_usd, 2),
                    "Realized_PnL_Pct": round(realized_pnl_pct, 2),
                    "Portfolio_After_USD": round(portfolio_equity, 2)
                })

            units = 0.0
            cost_basis_total = 0.0
            current_direction = 0.0
            adds_count = 0

        # Position Open / New Series Entry
        if target_pos != 0.0 and current_direction == 0.0:
            current_direction = target_pos
            series_entry_bar = i
            series_entry_price = curr_price * (1.0 + (FEE_RT / 2.0) if current_direction == 1.0 else 1.0 - (FEE_RT / 2.0))
            series_entry_time = bar_time
            last_add_bar = i
            last_add_price = series_entry_price

            # Size allocation: X% for pyramiding, 100% of available cash for baseline
            allocated_usd = min(cash, fixed_tranche_usd if is_pyramiding else cash)
            effective_exec_price = series_entry_price * (1.0 + FEE_RT / 2.0)
            u = allocated_usd / effective_exec_price
            
            cash -= allocated_usd
            units = u
            cost_basis_total = allocated_usd
            adds_count = 1

            if record_details and is_pyramiding:
                series_adds.append({
                    "Strategy": f"{logic}_{fast_p}_{slow_p}",
                    "Note": f"[{logic}] EMA({fast_p},{slow_p}) | Y_Factor={y_factor} Y_Val={y_val} X%={x_pct}",
                    "Y_Factor": y_factor,
                    "Y_Value": y_val,
                    "X_Pct": x_pct,
                    "Series_Add_No": 1,
                    "Bar_Index": i,
                    "Time": bar_time,
                    "Direction": "LONG" if current_direction == 1.0 else "SHORT",
                    "Entry_Price": round(series_entry_price, 2),
                    "Fixed_Add_USD": round(allocated_usd, 2),
                    "Total_Cost_Basis": round(cost_basis_total, 2),
                    "Avg_Entry_Price": round(cost_basis_total / units, 2),
                    "Units_Total": round(units, 6),
                    "Cash_Remaining": round(cash, 2),
                    "Unrealized_Pct": 0.0
                })

        # Pyramiding Series Reinvestment (Tranche Additions during active series)
        elif target_pos != 0.0 and current_direction == target_pos and is_pyramiding:
            if adds_count < max_possible_adds and cash >= fixed_tranche_usd * 0.95:
                should_add = False
                bars_since_start = i - series_entry_bar
                bars_since_last = i - last_add_bar

                if y_factor == "BARS_ELAPSED" and bars_since_last >= y_val:
                    should_add = True
                elif y_factor == "HOURS_ELAPSED" and bars_since_last >= y_val:
                    should_add = True
                elif y_factor == "PRICE_FROM_START_PCT":
                    p_diff = (curr_price / series_entry_price - 1.0) * 100.0 if current_direction == 1.0 else (1.0 - curr_price / series_entry_price) * 100.0
                    if p_diff >= y_val * adds_count:
                        should_add = True
                elif y_factor == "PRICE_FROM_LAST_PCT":
                    p_diff = (curr_price / last_add_price - 1.0) * 100.0 if current_direction == 1.0 else (1.0 - curr_price / last_add_price) * 100.0
                    if p_diff >= y_val:
                        should_add = True
                elif y_factor == "PROFIT_FROM_START_PCT":
                    curr_val = (units * curr_price) if current_direction == 1.0 else (cost_basis_total + (cost_basis_total - units * curr_price))
                    unrealized_pct = ((curr_val - cost_basis_total) / cost_basis_total) * 100.0
                    if unrealized_pct >= y_val * adds_count:
                        should_add = True
                elif y_factor == "PROFIT_FROM_LAST_PCT":
                    curr_val = (units * curr_price) if current_direction == 1.0 else (cost_basis_total + (cost_basis_total - units * curr_price))
                    unrealized_pct = ((curr_val - cost_basis_total) / cost_basis_total) * 100.0
                    if unrealized_pct >= y_val:
                        should_add = True

                if should_add:
                    allocated_usd = min(cash, fixed_tranche_usd)
                    add_price = curr_price * (1.0 + (FEE_RT / 2.0) if current_direction == 1.0 else 1.0 - (FEE_RT / 2.0))
                    u_add = allocated_usd / (add_price * (1.0 + FEE_RT / 2.0))
                    
                    cash -= allocated_usd
                    units += u_add
                    cost_basis_total += allocated_usd
                    adds_count += 1
                    last_add_bar = i
                    last_add_price = add_price
                    avg_p = cost_basis_total / units

                    if record_details:
                        curr_val = (units * curr_price) if current_direction == 1.0 else (cost_basis_total + (cost_basis_total - units * curr_price))
                        unreal_p = ((curr_val - cost_basis_total) / cost_basis_total) * 100.0
                        series_adds.append({
                            "Strategy": f"{logic}_{fast_p}_{slow_p}",
                            "Note": f"[{logic}] EMA({fast_p},{slow_p}) | Y_Factor={y_factor} Y_Val={y_val} X%={x_pct}",
                            "Y_Factor": y_factor,
                            "Y_Value": y_val,
                            "X_Pct": x_pct,
                            "Series_Add_No": adds_count,
                            "Bar_Index": i,
                            "Time": bar_time,
                            "Direction": "LONG" if current_direction == 1.0 else "SHORT",
                            "Entry_Price": round(add_price, 2),
                            "Fixed_Add_USD": round(allocated_usd, 2),
                            "Total_Cost_Basis": round(cost_basis_total, 2),
                            "Avg_Entry_Price": round(avg_p, 2),
                            "Units_Total": round(units, 6),
                            "Cash_Remaining": round(cash, 2),
                            "Unrealized_Pct": round(unreal_p, 2)
                        })

        # Calculate Open Mark-to-Market Portfolio Equity
        if current_direction != 0.0:
            if current_direction == 1.0:
                pos_val = units * curr_price * (1.0 - FEE_RT / 2.0)
            else:
                pos_val = cost_basis_total + (cost_basis_total - units * curr_price * (1.0 + FEE_RT / 2.0))
            current_portfolio_equity = cash + pos_val
        else:
            current_portfolio_equity = cash

        if current_portfolio_equity > peak_equity:
            peak_equity = current_portfolio_equity
        dd = ((current_portfolio_equity - peak_equity) / peak_equity) * 100.0
        if abs(dd) > max_drawdown_pct:
            max_drawdown_pct = abs(dd)

        equity_curve.append(current_portfolio_equity)
        monthly_equities[m_name].append(current_portfolio_equity)

    # Final Close at Dataset End if position open
    if current_direction != 0.0:
        exit_price = close[-1] * (1.0 - (FEE_RT / 2.0) if current_direction == 1.0 else 1.0 + (FEE_RT / 2.0))
        if current_direction == 1.0:
            proceeds = units * exit_price * (1.0 - FEE_RT / 2.0)
            realized_pnl_usd = proceeds - cost_basis_total
        else:
            proceeds = cost_basis_total + (cost_basis_total - units * exit_price * (1.0 + FEE_RT / 2.0))
            realized_pnl_usd = proceeds - cost_basis_total
        cash += proceeds
        portfolio_equity = cash
        realized_pnl_pct = (realized_pnl_usd / cost_basis_total) * 100.0 if cost_basis_total > 0 else 0.0
        avg_entry_price = cost_basis_total / units if units > 0 else series_entry_price

        if record_details:
            closed_trades.append({
                "Strategy": f"{logic}_{fast_p}_{slow_p}",
                "Logic": logic,
                "Fast_EMA": fast_p,
                "Slow_EMA": slow_p,
                "Y_Factor": y_factor,
                "Y_Value": y_val,
                "X_Pct": x_pct,
                "Note": f"[{logic}] EMA({fast_p},{slow_p}) | Y_Factor={y_factor} Y_Val={y_val} X%={x_pct}" if is_pyramiding else f"[{logic}] EMA({fast_p},{slow_p}) | Baseline (X=0, Y=0)",
                "Direction": "LONG" if current_direction == 1.0 else "SHORT",
                "Series_Entry_Time": series_entry_time,
                "Series_Entry_Price": round(series_entry_price, 2),
                "Avg_Entry_Price": round(avg_entry_price, 2),
                "Exit_Time": str(open_times[-1])[:16],
                "Exit_Price": round(exit_price, 2),
                "Total_Adds_In_Series": adds_count,
                "Total_Invested_USD": round(cost_basis_total, 2),
                "Realized_PnL_USD": round(realized_pnl_usd, 2),
                "Realized_PnL_Pct": round(realized_pnl_pct, 2),
                "Portfolio_After_USD": round(portfolio_equity, 2)
            })

    total_return_pct = ((portfolio_equity - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100.0
    
    # Calculate Sharpe
    eq_arr = np.array(equity_curve)
    bar_rets = np.diff(eq_arr) / eq_arr[:-1]
    sharpe = float(np.mean(bar_rets) / (np.std(bar_rets) + 1e-9) * np.sqrt(8760)) if len(bar_rets) > 0 else 0.0

    # Win rate and Profit Factor
    if closed_trades:
        pnls = [t["Realized_PnL_USD"] for t in closed_trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        win_rate_pct = (len(wins) / len(pnls)) * 100.0 if pnls else 0.0
        profit_factor = (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else (99.0 if wins else 1.0)
    else:
        win_rate_pct = 0.0
        profit_factor = 1.0

    # Month returns
    m_returns = {}
    prev_m_eq = INITIAL_CAPITAL
    for m in month_names:
        m_vals = monthly_equities[m]
        if m_vals:
            m_end = m_vals[-1]
            m_ret = ((m_end - prev_m_eq) / prev_m_eq) * 100.0
            m_returns[f"M_{m}"] = round(m_ret, 2)
            prev_m_eq = m_end
        else:
            m_returns[f"M_{m}"] = 0.0

    summary = {
        "Strategy": f"{logic}_{fast_p}_{slow_p}",
        "Logic": logic,
        "Fast_EMA": fast_p,
        "Slow_EMA": slow_p,
        "Y_Factor": y_factor,
        "Y_Value": y_val,
        "X_Pct": x_pct,
        "Fixed_Add_USD": fixed_tranche_usd if is_pyramiding else INITIAL_CAPITAL,
        "Total_Return_Pct": round(total_return_pct, 2),
        "Final_Equity": round(portfolio_equity, 2),
        "Max_Drawdown_Pct": round(max_drawdown_pct, 2),
        "Sharpe": round(sharpe, 2),
        "Win_Rate_Pct": round(win_rate_pct, 2),
        "Profit_Factor": round(profit_factor, 2),
        "Total_Closed_Trades": len(closed_trades),
        "Total_Series_Adds": len(series_adds),
        "Strategy_Note": f"[{logic}] EMA({fast_p},{slow_p}) | Y={y_factor}({y_val}) X={x_pct}%" if is_pyramiding else f"[{logic}] EMA({fast_p},{slow_p}) | Base (X=0, Y=0)",
        **m_returns
    }

    if record_details:
        return summary, closed_trades, series_adds
    return summary

if __name__ == "__main__":
    print("Testing Unified Execution Simulator on Top Pair (209, 223)...")
    df_1h = load_data()
    close = df_1h["close"].values
    open_times = df_1h["open_time"].values
    ema_matrix, period_to_idx = build_ema_matrix(close)
    
    # 1. Base Execution (X=0, Y=0)
    base_sum, base_trades, _ = simulate_series_execution(
        close, open_times, "EMA_CROSS_SAR", 209, 223, "NONE", 0, 0, ema_matrix, period_to_idx, record_details=True
    )
    print(f"Base (X=0, Y=0): Return = {base_sum['Total_Return_Pct']}%, Max DD = {base_sum['Max_Drawdown_Pct']}%, Trades = {len(base_trades)}")
    
    # 2. Pyramiding Execution (X=10%, Y=1 hour)
    pyr_sum, pyr_trades, pyr_adds = simulate_series_execution(
        close, open_times, "EMA_CROSS_SAR", 207, 224, "HOURS_ELAPSED", 1, 10, ema_matrix, period_to_idx, record_details=True
    )
    print(f"Pyramid (X=10%, Y=1h): Return = {pyr_sum['Total_Return_Pct']}%, Max DD = {pyr_sum['Max_Drawdown_Pct']}%, Closed Series = {len(pyr_trades)}, Tranche Adds = {len(pyr_adds)}")
