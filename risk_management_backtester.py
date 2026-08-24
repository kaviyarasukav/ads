"""
ETH 2026 Comprehensive Risk Management Backtester (Dual Re-Entry Modes)
======================================================================
FIXES in this version:
  - BUG 8: pnl_log (lightweight float list) always recorded regardless of record_trades.
           Fixes: all Fixed SL/TP $ sweeps previously showed 0 trades / 0% win rate / PF=1.0.

IMPROVEMENTS:
  - IMP 5: Net_PnL_USD, Avg_Hold_Hours, Exposure_Pct added to every summary dict.
  - IMP 5: Sortino ratio computed and returned.
  - Zero-division guards on max_drawdown and profit_factor.
"""

import os
import json
import time
import numpy as np
import pandas as pd
from unified_trade_engine import load_data, build_ema_matrix

FEE_RT = 0.001
INITIAL_CAPITAL = 10_000.0

def run_risk_trade_simulation(
    open_p, high_p, low_p, close_p, open_times,
    logic, fast_p, slow_p,
    sl_type, sl_val,
    tp_type, tp_val,
    tsl_type, tsl_val,
    ttp_act, ttp_call,
    re_entry_mode, # "RE_ENTER_IMMEDIATE" or "WAIT_NEXT_FLIP"
    ema_matrix, period_to_idx,
    record_trades=False
):
    n = len(close_p)
    fast_idx = period_to_idx[fast_p]
    fast_series = ema_matrix[fast_idx]

    if slow_p is not None and slow_p > 0:
        slow_idx = period_to_idx[slow_p]
        slow_series = ema_matrix[slow_idx]
    else:
        slow_series = None

    # Determine direction signals
    direction_signal = np.zeros(n, dtype=int)
    if logic == "EMA_CROSS_SAR":
        direction_signal = np.where(fast_series > slow_series, 1, -1)
    elif logic == "EMA_CROSS_LONG_ONLY":
        direction_signal = np.where(fast_series > slow_series, 1, 0)
    elif logic == "PRICE_EMA_SAR":
        direction_signal = np.where(close_p > fast_series, 1, -1)
    elif logic == "PRICE_EMA_LONG_ONLY":
        direction_signal = np.where(close_p > fast_series, 1, 0)

    portfolio = INITIAL_CAPITAL
    equity_curve = [portfolio]
    closed_trades = []
    pnl_log = []          # BUG 8 FIX: always record pnl floats, regardless of record_trades
    bars_in_market = 0    # IMP 5: track for Exposure_Pct
    
    in_pos = False
    pos_dir = 0
    pos_entry_price = 0.0
    pos_entry_time = None
    pos_entry_bar = 0
    peak_price = 0.0
    trough_price = 0.0
    ttp_active = False
    last_exit_sig = 0 # tracks signal when trade exited early

    for i in range(1, n):
        curr_sig = direction_signal[i - 1] # 1-bar lagged signal
        prev_bar_sig = direction_signal[i - 2] if i >= 2 else curr_sig

        # Check active position management
        if in_pos:
            exit_triggered = False
            exit_price = 0.0
            exit_reason = ""

            if pos_dir == 1: # LONG
                if high_p[i] > peak_price:
                    peak_price = high_p[i]
                
                # 1. Trailing Stop Loss
                if not exit_triggered and tsl_val > 0:
                    tsl_floor = peak_price * (1.0 - tsl_val / 100.0) if tsl_type == "PCT" else (peak_price - tsl_val)
                    if low_p[i] <= tsl_floor:
                        exit_triggered = True
                        exit_price = min(open_p[i], tsl_floor)
                        exit_reason = f"Trailing SL ({tsl_val}{'%' if tsl_type=='PCT' else '$'})"

                # 2. Fixed Stop Loss
                if not exit_triggered and sl_val > 0:
                    sl_floor = pos_entry_price * (1.0 - sl_val / 100.0) if sl_type == "PCT" else (pos_entry_price - sl_val)
                    if low_p[i] <= sl_floor:
                        exit_triggered = True
                        exit_price = min(open_p[i], sl_floor)
                        exit_reason = f"Fixed SL ({sl_val}{'%' if sl_type=='PCT' else '$'})"

                # 3. Trailing Take Profit
                if not exit_triggered and ttp_act > 0:
                    if high_p[i] >= pos_entry_price * (1.0 + ttp_act / 100.0):
                        ttp_active = True
                    if ttp_active:
                        ttp_floor = peak_price * (1.0 - ttp_call / 100.0)
                        if low_p[i] <= ttp_floor:
                            exit_triggered = True
                            exit_price = min(open_p[i], ttp_floor)
                            exit_reason = f"Trailing TP (Act {ttp_act}%, Call {ttp_call}%)"

                # 4. Fixed Take Profit
                if not exit_triggered and tp_val > 0:
                    tp_ceil = pos_entry_price * (1.0 + tp_val / 100.0) if tp_type == "PCT" else (pos_entry_price + tp_val)
                    if high_p[i] >= tp_ceil:
                        exit_triggered = True
                        exit_price = max(open_p[i], tp_ceil)
                        exit_reason = f"Fixed TP ({tp_val}{'%' if tp_type=='PCT' else '$'})"

                # 5. Signal Reversal Exit
                if not exit_triggered and curr_sig != 1:
                    exit_triggered = True
                    exit_price = open_p[i]
                    exit_reason = "Signal Flip"

            elif pos_dir == -1: # SHORT
                if low_p[i] < trough_price:
                    trough_price = low_p[i]

                # 1. Trailing Stop Loss
                if not exit_triggered and tsl_val > 0:
                    tsl_ceil = trough_price * (1.0 + tsl_val / 100.0) if tsl_type == "PCT" else (trough_price + tsl_val)
                    if high_p[i] >= tsl_ceil:
                        exit_triggered = True
                        exit_price = max(open_p[i], tsl_ceil)
                        exit_reason = f"Trailing SL ({tsl_val}{'%' if tsl_type=='PCT' else '$'})"

                # 2. Fixed Stop Loss
                if not exit_triggered and sl_val > 0:
                    sl_ceil = pos_entry_price * (1.0 + sl_val / 100.0) if sl_type == "PCT" else (pos_entry_price + sl_val)
                    if high_p[i] >= sl_ceil:
                        exit_triggered = True
                        exit_price = max(open_p[i], sl_ceil)
                        exit_reason = f"Fixed SL ({sl_val}{'%' if sl_type=='PCT' else '$'})"

                # 3. Trailing Take Profit
                if not exit_triggered and ttp_act > 0:
                    if low_p[i] <= pos_entry_price * (1.0 - ttp_act / 100.0):
                        ttp_active = True
                    if ttp_active:
                        ttp_ceil = trough_price * (1.0 + ttp_call / 100.0)
                        if high_p[i] >= ttp_ceil:
                            exit_triggered = True
                            exit_price = max(open_p[i], ttp_ceil)
                            exit_reason = f"Trailing TP (Act {ttp_act}%, Call {ttp_call}%)"

                # 4. Fixed Take Profit
                if not exit_triggered and tp_val > 0:
                    tp_floor = pos_entry_price * (1.0 - tp_val / 100.0) if tp_type == "PCT" else (pos_entry_price - tp_val)
                    if low_p[i] <= tp_floor:
                        exit_triggered = True
                        exit_price = min(open_p[i], tp_floor)
                        exit_reason = f"Fixed TP ({tp_val}{'%' if tp_type=='PCT' else '$'})"

                # 5. Signal Reversal Exit
                if not exit_triggered and curr_sig != -1:
                    exit_triggered = True
                    exit_price = open_p[i]
                    exit_reason = "Signal Flip"

            if exit_triggered:
                raw_ret = (exit_price / pos_entry_price - 1.0) if pos_dir == 1 else (1.0 - exit_price / pos_entry_price)
                fee_deduct = FEE_RT * 2.0
                net_ret = raw_ret - fee_deduct
                pnl_usd = portfolio * net_ret
                portfolio += pnl_usd
                hold_bars = i - pos_entry_bar

                pnl_log.append((net_ret * 100.0, pnl_usd, hold_bars))  # BUG 8 FIX

                if record_trades:
                    closed_trades.append({
                        "trade_no": len(closed_trades) + 1,
                        "direction": "LONG" if pos_dir == 1 else "SHORT",
                        "entry_time": str(pos_entry_time),
                        "entry_price": round(float(pos_entry_price), 2),
                        "exit_time": str(open_times[i]),
                        "exit_price": round(float(exit_price), 2),
                        "duration_hours": hold_bars,
                        "realized_pnl_pct": round(float(net_ret * 100.0), 2),
                        "realized_pnl_usd": round(float(pnl_usd), 2),
                        "portfolio_after": round(float(portfolio), 2),
                        "exit_reason": exit_reason
                    })

                in_pos = False
                pos_dir = 0
                ttp_active = False
                last_exit_sig = curr_sig

        # Entry logic
        if not in_pos and curr_sig != 0:
            allow_entry = False
            if re_entry_mode == "RE_ENTER_IMMEDIATE":
                allow_entry = True
            elif re_entry_mode == "WAIT_NEXT_FLIP":
                # Only allow entry if signal has just flipped away from last_exit_sig
                if last_exit_sig == 0 or curr_sig != last_exit_sig:
                    allow_entry = True

            if allow_entry:
                in_pos = True
                pos_dir = curr_sig
                pos_entry_price = open_p[i]
                pos_entry_time = open_times[i]
                pos_entry_bar = i
                peak_price = pos_entry_price
                trough_price = pos_entry_price
                ttp_active = False
                last_exit_sig = 0

        if in_pos:
            bars_in_market += 1  # IMP 5: count bars spent in market

        equity_curve.append(portfolio)

    # Force close at end
    if in_pos:
        exit_price = close_p[-1]
        raw_ret = (exit_price / pos_entry_price - 1.0) if pos_dir == 1 else (1.0 - exit_price / pos_entry_price)
        fee_deduct = FEE_RT * 2.0
        net_ret = raw_ret - fee_deduct
        pnl_usd = portfolio * net_ret
        portfolio += pnl_usd
        pnl_log.append((net_ret * 100.0, pnl_usd, int(n - 1 - pos_entry_bar)))  # BUG 8 FIX
        if record_trades:
            closed_trades.append({
                "trade_no": len(closed_trades) + 1,
                "direction": "LONG" if pos_dir == 1 else "SHORT",
                "entry_time": str(pos_entry_time),
                "entry_price": round(float(pos_entry_price), 2),
                "exit_time": str(open_times[-1]),
                "exit_price": round(float(exit_price), 2),
                "duration_hours": int(n - 1 - pos_entry_bar),
                "realized_pnl_pct": round(float(net_ret * 100.0), 2),
                "realized_pnl_usd": round(float(pnl_usd), 2),
                "portfolio_after": round(float(portfolio), 2),
                "exit_reason": "End of Backtest Period"
            })
        equity_curve[-1] = portfolio

    # Metrics computation
    total_ret = ((portfolio - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100.0
    eq_arr = np.array(equity_curve)
    peaks = np.maximum.accumulate(eq_arr)
    drawdowns = (peaks - eq_arr) / np.where(peaks == 0, 1e-9, peaks) * 100.0
    max_dd = float(np.max(drawdowns))

    returns_arr = np.diff(eq_arr) / np.where(eq_arr[:-1] == 0, 1e-9, eq_arr[:-1])
    sharpe = float(np.mean(returns_arr) / (np.std(returns_arr) + 1e-9) * np.sqrt(8760)) if len(returns_arr) > 1 else 0.0
    down_r = returns_arr[returns_arr < 0]
    down_std = float(down_r.std()) if len(down_r) > 1 else 1e-9
    sortino = float(np.mean(returns_arr) / down_std * np.sqrt(8760)) if down_std > 1e-9 else 0.0

    # BUG 8 FIX: use pnl_log (always recorded) for trade metrics
    total_trades = len(pnl_log)
    trade_pcts = [p[0] for p in pnl_log]
    trade_usds = [p[1] for p in pnl_log]
    hold_bars_list = [p[2] for p in pnl_log]
    win_trades = [p for p in trade_pcts if p > 0]
    loss_trades = [p for p in trade_pcts if p <= 0]
    win_rate = (len(win_trades) / total_trades * 100.0) if total_trades > 0 else 0.0

    gross_gains = sum(p for p in trade_usds if p > 0)
    gross_losses = abs(sum(p for p in trade_usds if p <= 0))
    profit_factor = float(gross_gains / gross_losses) if gross_losses > 1e-9 else 999.0

    avg_hold_hours = float(np.mean(hold_bars_list)) if hold_bars_list else 0.0  # IMP 5
    exposure_pct = (bars_in_market / max(n - 1, 1)) * 100.0                     # IMP 5
    net_pnl_usd = portfolio - INITIAL_CAPITAL                                   # IMP 5

    summary = {
        "Logic": logic,
        "Fast_EMA": fast_p,
        "Slow_EMA": slow_p,
        "SL_Type": sl_type, "SL_Val": sl_val,
        "TP_Type": tp_type, "TP_Val": tp_val,
        "TSL_Type": tsl_type, "TSL_Val": tsl_val,
        "TTP_Act": ttp_act, "TTP_Call": ttp_call,
        "Re_Entry_Mode": re_entry_mode,
        "Total_Return_Pct": round(total_ret, 2),
        "Net_PnL_USD": round(net_pnl_usd, 2),          # IMP 5
        "Max_Drawdown_Pct": round(max_dd, 2),
        "Sharpe": round(sharpe, 2),
        "Sortino": round(sortino, 2),                   # IMP 5
        "Calmar": round(total_ret / (max_dd or 1), 2),
        "Win_Rate_Pct": round(win_rate, 1),
        "Profit_Factor": round(min(profit_factor, 999.0), 2),
        "Total_Trades": total_trades,
        "Avg_Hold_Hours": round(avg_hold_hours, 1),     # IMP 5
        "Exposure_Pct": round(exposure_pct, 1),         # IMP 5
        "Final_Equity": round(portfolio, 2)
    }

    return summary, closed_trades


def run_full_risk_sweep():
    print("=" * 80)
    print("STARTING DUAL-MODE TP/SL/TSL/TTP RISK MANAGEMENT GRID SWEEP")
    print("=" * 80)
    start_time = time.time()

    df_1h = load_data()
    open_p = df_1h["open"].values
    high_p = df_1h["high"].values
    low_p = df_1h["low"].values
    close_p = df_1h["close"].values
    open_times = df_1h["open_time"].values

    ema_matrix, period_to_idx = build_ema_matrix(close_p)

    candidate_strats = [
        ("EMA_CROSS_SAR", 209, 223, "Top Base SAR"),
        ("EMA_CROSS_SAR", 207, 224, "Pyramid Base SAR"),
        ("EMA_CROSS_LONG_ONLY", 208, 224, "Top Base Long Only"),
        ("PRICE_EMA_SAR", 82, None, "Top Single EMA SAR")
    ]

    sl_pct_values = [0, 1.0, 2.0, 3.0, 5.0, 7.5, 10.0, 15.0, 20.0]
    sl_price_values = [0, 25, 50, 100, 200, 500]

    tp_pct_values = [0, 2.0, 4.0, 6.0, 10.0, 15.0, 20.0, 30.0, 50.0, 100.0]
    tp_price_values = [0, 50, 100, 200, 500, 1000]

    tsl_pct_values = [0, 1.0, 2.0, 3.0, 5.0, 7.5, 10.0, 15.0]
    tsl_price_values = [0, 25, 50, 100, 200, 500]

    ttp_pairs = [(0, 0), (5.0, 1.0), (5.0, 2.0), (10.0, 2.0), (10.0, 3.0), (15.0, 3.0), (20.0, 5.0), (30.0, 5.0)]

    all_risk_results = []
    sample_risk_trades = {}

    for mode in ["WAIT_NEXT_FLIP", "RE_ENTER_IMMEDIATE"]:
        print(f"\nProcessing Re-Entry Mode: {mode}...")
        for logic, f_p, s_p, strat_label in candidate_strats:
            # 1. Baseline
            summary, trades = run_risk_trade_simulation(
                open_p, high_p, low_p, close_p, open_times, logic, f_p, s_p,
                "PCT", 0, "PCT", 0, "PCT", 0, 0, 0, mode, ema_matrix, period_to_idx, record_trades=True
            )
            summary["Risk_Archetype"] = "NO_SL_NO_TP"
            summary["Strategy_Label"] = strat_label
            summary["Risk_Note"] = f"{strat_label} | Raw Signal Flip [{mode}]"
            all_risk_results.append(summary)
            sample_risk_trades[summary["Risk_Note"]] = trades

            # 2. Fixed SL %
            for sl_p in sl_pct_values[1:]:
                summary, trades = run_risk_trade_simulation(
                    open_p, high_p, low_p, close_p, open_times, logic, f_p, s_p,
                    "PCT", sl_p, "PCT", 0, "PCT", 0, 0, 0, mode, ema_matrix, period_to_idx, record_trades=True
                )
                summary["Risk_Archetype"] = "FIXED_SL_ONLY"
                summary["Strategy_Label"] = strat_label
                summary["Risk_Note"] = f"{strat_label} | Fixed SL {sl_p}% [{mode}]"
                all_risk_results.append(summary)
                if sl_p in [3.0, 5.0, 10.0]:
                    sample_risk_trades[summary["Risk_Note"]] = trades

            # 3. Fixed SL $
            for sl_usd in sl_price_values[1:]:
                summary, _ = run_risk_trade_simulation(
                    open_p, high_p, low_p, close_p, open_times, logic, f_p, s_p,
                    "PRICE", sl_usd, "PCT", 0, "PCT", 0, 0, 0, mode, ema_matrix, period_to_idx, record_trades=False
                )
                summary["Risk_Archetype"] = "FIXED_SL_ONLY"
                summary["Strategy_Label"] = strat_label
                summary["Risk_Note"] = f"{strat_label} | Fixed SL ${sl_usd} [{mode}]"
                all_risk_results.append(summary)

            # 4. Fixed TP %
            for tp_p in tp_pct_values[1:]:
                summary, trades = run_risk_trade_simulation(
                    open_p, high_p, low_p, close_p, open_times, logic, f_p, s_p,
                    "PCT", 0, "PCT", tp_p, "PCT", 0, 0, 0, mode, ema_matrix, period_to_idx, record_trades=True
                )
                summary["Risk_Archetype"] = "FIXED_TP_ONLY"
                summary["Strategy_Label"] = strat_label
                summary["Risk_Note"] = f"{strat_label} | Fixed TP {tp_p}% [{mode}]"
                all_risk_results.append(summary)
                if tp_p in [6.0, 15.0, 30.0]:
                    sample_risk_trades[summary["Risk_Note"]] = trades

            # 5. Fixed TP $
            for tp_usd in tp_price_values[1:]:
                summary, _ = run_risk_trade_simulation(
                    open_p, high_p, low_p, close_p, open_times, logic, f_p, s_p,
                    "PCT", 0, "PRICE", tp_usd, "PCT", 0, 0, 0, mode, ema_matrix, period_to_idx, record_trades=False
                )
                summary["Risk_Archetype"] = "FIXED_TP_ONLY"
                summary["Strategy_Label"] = strat_label
                summary["Risk_Note"] = f"{strat_label} | Fixed TP ${tp_usd} [{mode}]"
                all_risk_results.append(summary)

            # 6. Trailing SL %
            for tsl_p in tsl_pct_values[1:]:
                summary, trades = run_risk_trade_simulation(
                    open_p, high_p, low_p, close_p, open_times, logic, f_p, s_p,
                    "PCT", 0, "PCT", 0, "PCT", tsl_p, 0, 0, mode, ema_matrix, period_to_idx, record_trades=True
                )
                summary["Risk_Archetype"] = "TRAILING_SL_ONLY"
                summary["Strategy_Label"] = strat_label
                summary["Risk_Note"] = f"{strat_label} | Trailing SL {tsl_p}% [{mode}]"
                all_risk_results.append(summary)
                if tsl_p in [2.0, 5.0, 7.5]:
                    sample_risk_trades[summary["Risk_Note"]] = trades

            # 7. Trailing TP
            for act_p, call_p in ttp_pairs[1:]:
                summary, trades = run_risk_trade_simulation(
                    open_p, high_p, low_p, close_p, open_times, logic, f_p, s_p,
                    "PCT", 0, "PCT", 0, "PCT", 0, act_p, call_p, mode, ema_matrix, period_to_idx, record_trades=True
                )
                summary["Risk_Archetype"] = "TRAILING_TP_ONLY"
                summary["Strategy_Label"] = strat_label
                summary["Risk_Note"] = f"{strat_label} | Trailing TP (Act {act_p}%, Call {call_p}%) [{mode}]"
                all_risk_results.append(summary)
                if (act_p, call_p) in [(10.0, 2.0), (15.0, 3.0)]:
                    sample_risk_trades[summary["Risk_Note"]] = trades

            # 8. Combined Hybrids
            for sl_p in [3.0, 5.0, 10.0]:
                for tp_p in [10.0, 20.0, 30.0]:
                    summary, trades = run_risk_trade_simulation(
                        open_p, high_p, low_p, close_p, open_times, logic, f_p, s_p,
                        "PCT", sl_p, "PCT", tp_p, "PCT", 0, 0, 0, mode, ema_matrix, period_to_idx, record_trades=True
                    )
                    summary["Risk_Archetype"] = "FIXED_SL_AND_TP"
                    summary["Strategy_Label"] = strat_label
                    summary["Risk_Note"] = f"{strat_label} | Fixed SL {sl_p}% + TP {tp_p}% [{mode}]"
                    all_risk_results.append(summary)

            for tsl_p in [3.0, 5.0]:
                for tp_p in [15.0, 30.0]:
                    summary, trades = run_risk_trade_simulation(
                        open_p, high_p, low_p, close_p, open_times, logic, f_p, s_p,
                        "PCT", 0, "PCT", tp_p, "PCT", tsl_p, 0, 0, mode, ema_matrix, period_to_idx, record_trades=True
                    )
                    summary["Risk_Archetype"] = "TRAILING_SL_AND_FIXED_TP"
                    summary["Strategy_Label"] = strat_label
                    summary["Risk_Note"] = f"{strat_label} | TSL {tsl_p}% + Fixed TP {tp_p}% [{mode}]"
                    all_risk_results.append(summary)

    os.makedirs("results", exist_ok=True)
    risk_df = pd.DataFrame(all_risk_results)
    risk_df.to_csv("results/risk_management_sweep_results.csv", index=False)

    with open("results/risk_management_trades.json", "w") as f:
        json.dump(sample_risk_trades, f)

    elapsed = time.time() - start_time
    print(f"\nSUCCESS: Evaluated {len(risk_df)} complete risk management combinations in {elapsed:.2f}s!")
    print(f"Results saved to results/risk_management_sweep_results.csv")

if __name__ == "__main__":
    run_full_risk_sweep()
