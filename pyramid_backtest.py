"""
ETH 2026 -- Pyramiding / Reinvestment Layer Brute-Force
=========================================================
On top of the EMA cross signal (best clusters from fee-adjusted results),
we layer a PYRAMIDING engine:

  Once an EMA signal fires (LONG or SHORT):
    - Enter with X% of portfolio on bar 1 of the trade
    - Continue adding X% more at every trigger of Y_FACTOR >= Y_VALUE
      while the original signal is still active ("in series")
    - Close entire position when EMA cross flips (exit signal)

Y_FACTOR options tested:
  1. BARS_ELAPSED   -- Every Y bars since last add
  2. HOURS_ELAPSED  -- Every Y hours since last add
  3. PRICE_FROM_START_PCT  -- Price moved Y% from first entry in series
  4. PRICE_FROM_LAST_PCT   -- Price moved Y% from last reinvest
  5. PROFIT_FROM_START_PCT -- Unrealized profit Y% from first entry
  6. PROFIT_FROM_LAST_PCT  -- Unrealized profit Y% from last reinvest

X values (% of FREE portfolio to deploy per add): 5,10,15,20,25,30,50
Y values (trigger threshold per factor): factor-specific ranges
Initial capital: $10,000

Everything is fee-adjusted (0.10% round-trip per entry/exit).
Results are stored per factor, per param pair, and in a master CSV.
"""

import os, json, time, sqlite3
import numpy as np
import pandas as pd

INITIAL_CAPITAL = 10_000.0
FEE_PCT = 0.001   # 0.10% round-trip per order
MIN_P, MAX_P = 5, 250
MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug"]

# Best EMA pairs from fee-adjusted analysis
BEST_PAIRS = [
    ("EMA_CROSS_SAR",       209, 223),
    ("EMA_CROSS_SAR",       208, 224),
    ("EMA_CROSS_SAR",         5,  15),
    ("EMA_CROSS_LONG_ONLY", 208, 224),
    ("EMA_CROSS_LONG_ONLY",   5,  15),
]

# X values: % of FREE cash to invest on each pyramiding add
X_VALUES = [5, 10, 15, 20, 25, 30, 50, 100]

# Y factors and their test values
Y_FACTORS = {
    "BARS_ELAPSED":           [1, 2, 4, 6, 12, 24, 48, 72, 168],
    "HOURS_ELAPSED":          [1, 2, 4, 6, 12, 24, 48, 72, 168],
    "PRICE_FROM_START_PCT":   [0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 7.0, 10.0],
    "PRICE_FROM_LAST_PCT":    [0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 7.0, 10.0],
    "PROFIT_FROM_START_PCT":  [0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 7.0, 10.0],
    "PROFIT_FROM_LAST_PCT":   [0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 7.0, 10.0],
}


def load_1h():
    conn = sqlite3.connect("eth_market_data.sqlite")
    df = pd.read_sql("SELECT open_time,close FROM candles_5m ORDER BY open_time ASC", conn)
    conn.close()
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df = df.set_index("open_time")["close"].resample("1h").last().dropna().reset_index()
    df.columns = ["open_time", "close"]
    return df


def build_ema(close, p):
    alpha = 2.0 / (p + 1.0)
    ema = close.copy()
    for t in range(1, len(close)):
        ema[t] = alpha * close[t] + (1 - alpha) * ema[t - 1]
    return ema


def get_position_series(close, logic, fast_p, slow_p):
    """Returns array of length n-1: +1 LONG, -1 SHORT, 0 FLAT"""
    ema_fast = build_ema(close, fast_p)
    if slow_p is not None:
        ema_slow = build_ema(close, slow_p)
        sig = ema_fast[:-1] > ema_slow[:-1]
    else:
        sig = close[:-1] > ema_fast[:-1]

    if "LONG_ONLY" in logic:
        return sig.astype(np.float64)
    else:  # SAR
        return np.where(sig, 1.0, -1.0)


def pyramid_backtest(close, open_times, pos_signal,
                     x_pct, y_factor, y_value, logic, fast_p, slow_p):
    """
    Pyramid / Reinvestment simulation.
    pos_signal: +1=LONG, -1=SHORT, 0=FLAT  (length n-1)
    x_pct: percent of free cash to invest on each add (0-100)
    y_factor: string key from Y_FACTORS
    y_value: numeric threshold
    Returns: (summary_dict, trade_log_list, series_log_list)
    """
    n = len(close)
    n_ret = n - 1

    cash = INITIAL_CAPITAL
    position_units = 0.0      # units of ETH held
    position_side = 0         # +1 or -1
    in_trade = False
    series_log = []
    trade_log = []
    portfolio_equity = [INITIAL_CAPITAL]

    # Series tracking
    series_entry_bar = 0
    series_entry_price = 0.0
    last_add_bar = 0
    last_add_price = 0.0
    last_add_unrealized_pct = 0.0
    add_count = 0
    avg_entry_price = 0.0
    total_cost_basis = 0.0

    monthly_equity = {}
    ts = pd.to_datetime(open_times[1:])

    prev_sig = 0.0

    for i in range(n_ret):
        price = close[i]
        next_price = close[i + 1]
        sig = pos_signal[i]
        dt_str = str(open_times[i])[:16]
        hour_of_bar = i  # bar index = hours since start

        # === SIGNAL CHANGED: close existing position ===
        if in_trade and sig != prev_sig:
            # Exit entire position
            exit_price = next_price * (1 - FEE_PCT)  # sell slightly worse
            if position_side == 1:
                proceeds = position_units * exit_price
                realized_pnl = proceeds - total_cost_basis
            else:
                # Short: we shorted at avg_entry, cover at exit
                cover_cost = position_units * exit_price
                realized_pnl = total_cost_basis - cover_cost
                proceeds = total_cost_basis + realized_pnl

            trade_pnl_pct = (realized_pnl / total_cost_basis) * 100 if total_cost_basis > 0 else 0.0
            cash += total_cost_basis + realized_pnl
            direction = "LONG" if position_side == 1 else "SHORT"
            trade_log.append({
                "Logic": logic, "Fast_EMA": fast_p, "Slow_EMA": slow_p,
                "Y_Factor": y_factor, "Y_Value": y_value, "X_Pct": x_pct,
                "Trade_Type": "CLOSE",
                "Direction": direction,
                "Entry_Time": str(open_times[series_entry_bar])[:16],
                "Avg_Entry_Price": round(avg_entry_price, 2),
                "Exit_Time": dt_str,
                "Exit_Price": round(exit_price, 2),
                "Series_Adds": add_count,
                "Realized_PnL_Pct": round(trade_pnl_pct, 2),
                "Realized_PnL_USD": round(realized_pnl, 2),
                "Portfolio_After": round(cash, 2)
            })

            position_units = 0.0
            total_cost_basis = 0.0
            avg_entry_price = 0.0
            in_trade = False
            add_count = 0

        # === ENTER or CONTINUE SERIES ===
        if sig != 0:
            should_add = False

            if not in_trade:
                # Fresh entry
                should_add = True
                series_entry_bar = i
                series_entry_price = next_price * (1 + FEE_PCT)  # buy at slight premium
                last_add_bar = i
                last_add_price = series_entry_price
                last_add_unrealized_pct = 0.0
                add_count = 0
                position_side = int(sig)
            else:
                # Check Y_FACTOR condition for pyramid add
                curr_unrealized = 0.0
                if avg_entry_price > 0:
                    if position_side == 1:
                        curr_unrealized = (price - avg_entry_price) / avg_entry_price * 100
                    else:
                        curr_unrealized = (avg_entry_price - price) / avg_entry_price * 100

                bars_since_add = i - last_add_bar
                price_from_start = abs((price - series_entry_price) / series_entry_price * 100) if position_side == 1 else abs((series_entry_price - price) / series_entry_price * 100)
                price_from_last = abs((price - last_add_price) / last_add_price * 100) if last_add_price > 0 else 0.0
                profit_from_last = curr_unrealized - last_add_unrealized_pct

                if y_factor == "BARS_ELAPSED" and bars_since_add >= y_value:
                    should_add = True
                elif y_factor == "HOURS_ELAPSED" and bars_since_add >= y_value:
                    should_add = True
                elif y_factor == "PRICE_FROM_START_PCT" and price_from_start >= y_value:
                    should_add = True
                elif y_factor == "PRICE_FROM_LAST_PCT" and price_from_last >= y_value:
                    should_add = True
                elif y_factor == "PROFIT_FROM_START_PCT" and curr_unrealized >= y_value:
                    should_add = True
                elif y_factor == "PROFIT_FROM_LAST_PCT" and profit_from_last >= y_value:
                    should_add = True

            if should_add and cash > 1.0:
                invest_usd = cash * (x_pct / 100.0)
                invest_usd = min(invest_usd, cash)
                if invest_usd < 1.0:
                    invest_usd = 0.0

                if invest_usd > 0:
                    entry_price_this = next_price * (1 + FEE_PCT)
                    units_bought = invest_usd / entry_price_this
                    cash -= invest_usd
                    add_count += 1

                    # Update avg entry
                    prev_cost = total_cost_basis
                    total_cost_basis += invest_usd
                    if position_units + units_bought > 0:
                        avg_entry_price = total_cost_basis / (position_units + units_bought)
                    position_units += units_bought

                    in_trade = True
                    last_add_bar = i
                    last_add_price = entry_price_this
                    curr_unr = 0.0
                    if avg_entry_price > 0 and position_side == 1:
                        curr_unr = (price - avg_entry_price) / avg_entry_price * 100
                    elif avg_entry_price > 0 and position_side == -1:
                        curr_unr = (avg_entry_price - price) / avg_entry_price * 100
                    last_add_unrealized_pct = curr_unr

                    series_log.append({
                        "Logic": logic, "Fast_EMA": fast_p, "Slow_EMA": slow_p,
                        "Y_Factor": y_factor, "Y_Value": y_value, "X_Pct": x_pct,
                        "Series_Add_No": add_count,
                        "Bar": i, "Time": dt_str,
                        "Direction": "LONG" if position_side == 1 else "SHORT",
                        "Price": round(entry_price_this, 2),
                        "Invested_USD": round(invest_usd, 2),
                        "Total_Cost_Basis": round(total_cost_basis, 2),
                        "Avg_Entry_Price": round(avg_entry_price, 2),
                        "Units_Held": round(position_units, 6),
                        "Cash_Remaining": round(cash, 2)
                    })

        # Compute mark-to-market equity
        if in_trade and position_units > 0:
            if position_side == 1:
                unr = position_units * next_price - total_cost_basis
            else:
                unr = total_cost_basis - position_units * next_price
            equity = cash + total_cost_basis + unr
        else:
            equity = cash
        portfolio_equity.append(round(equity, 2))
        prev_sig = sig

    # Force close final open position
    if in_trade and position_units > 0:
        exit_price = close[-1] * (1 - FEE_PCT)
        if position_side == 1:
            realized_pnl = position_units * exit_price - total_cost_basis
        else:
            realized_pnl = total_cost_basis - position_units * exit_price
        cash += total_cost_basis + realized_pnl
        trade_pnl_pct = (realized_pnl / total_cost_basis) * 100 if total_cost_basis > 0 else 0.0
        trade_log.append({
            "Logic": logic, "Fast_EMA": fast_p, "Slow_EMA": slow_p,
            "Y_Factor": y_factor, "Y_Value": y_value, "X_Pct": x_pct,
            "Trade_Type": "CLOSE_FINAL",
            "Direction": "LONG" if position_side == 1 else "SHORT",
            "Entry_Time": str(open_times[series_entry_bar])[:16],
            "Avg_Entry_Price": round(avg_entry_price, 2),
            "Exit_Time": str(open_times[-1])[:16],
            "Exit_Price": round(exit_price, 2),
            "Series_Adds": add_count,
            "Realized_PnL_Pct": round(trade_pnl_pct, 2),
            "Realized_PnL_USD": round(realized_pnl, 2),
            "Portfolio_After": round(cash, 2)
        })

    # Compute summary metrics
    eq = np.array(portfolio_equity, dtype=np.float64)
    final_equity = eq[-1]
    total_ret_pct = (final_equity / INITIAL_CAPITAL - 1) * 100
    running_max = np.maximum.accumulate(eq)
    dd = (eq - running_max) / running_max
    max_dd_pct = abs(dd.min()) * 100

    ret_series = np.diff(eq) / eq[:-1]
    std = ret_series.std()
    sharpe = (ret_series.mean() / std) * np.sqrt(8760) if std > 1e-9 else 0.0

    n_trades = len(trade_log)
    pnls = [t["Realized_PnL_Pct"] for t in trade_log]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    wr = (len(wins) / n_trades * 100) if n_trades > 0 else 0.0
    gp = sum(wins); gl = abs(sum(losses)) if losses else 1e-9
    pf = gp / gl if gl > 0 else 999.0
    total_adds = sum(t["Series_Adds"] for t in trade_log)

    # Monthly
    eq_df = pd.DataFrame({"eq": eq, "t": open_times})
    monthly = {}
    for mi, mn in enumerate(MONTHS, 1):
        mask = (pd.to_datetime(eq_df["t"]).dt.month == mi)
        sub = eq[mask.values]
        if len(sub) >= 2:
            monthly[mn] = round((sub[-1]/sub[0]-1)*100, 2)
        else:
            monthly[mn] = 0.0

    summary = {
        "Logic": logic, "Fast_EMA": fast_p, "Slow_EMA": slow_p,
        "Y_Factor": y_factor, "Y_Value": y_value, "X_Pct": x_pct,
        "Initial_Capital": INITIAL_CAPITAL,
        "Final_Equity": round(final_equity, 2),
        "Total_Return_Pct": round(total_ret_pct, 2),
        "Max_Drawdown_Pct": round(max_dd_pct, 2),
        "Sharpe": round(sharpe, 2),
        "Win_Rate_Pct": round(wr, 2),
        "Profit_Factor": round(pf, 2),
        "Total_Trades_Closed": n_trades,
        "Total_Series_Adds": total_adds,
    }
    for mn in MONTHS:
        summary[f"M_{mn}"] = monthly[mn]

    return summary, trade_log, series_log


def run():
    os.makedirs("results/pyramid_trades", exist_ok=True)
    os.makedirs("results/pyramid_series", exist_ok=True)

    df = load_1h()
    close = df["close"].values.astype(np.float64)
    open_times = df["open_time"].values
    n = len(close)
    bh_ret = (close[-1]/close[0]-1)*100

    print(f"ETH 2026 | {n} hourly bars | BH: {bh_ret:+.2f}%")
    print(f"Testing {len(BEST_PAIRS)} EMA pairs x {len(X_VALUES)} X values x {sum(len(v) for v in Y_FACTORS.values())} Y values = "
          f"{len(BEST_PAIRS)*len(X_VALUES)*sum(len(v) for v in Y_FACTORS.values()):,} permutations\n")

    all_summaries = []
    all_trades = []
    all_series = []

    total = 0
    t_start = time.time()
    for logic, fast_p, slow_p in BEST_PAIRS:
        pos_signal = get_position_series(close, logic, fast_p, slow_p)
        for y_factor, y_values in Y_FACTORS.items():
            for y_val in y_values:
                for x_pct in X_VALUES:
                    summary, trades, series = pyramid_backtest(
                        close, open_times, pos_signal,
                        x_pct, y_factor, y_val, logic, fast_p, slow_p
                    )
                    all_summaries.append(summary)
                    all_trades.extend(trades)
                    all_series.extend(series)
                    total += 1

    elapsed = time.time() - t_start
    print(f"Completed {total:,} permutations in {elapsed:.2f}s")

    # Save master summary
    master = pd.DataFrame(all_summaries)
    master.to_csv("results/pyramid_master_summary.csv", index=False)

    # Save trade logs
    pd.DataFrame(all_trades).to_csv("results/pyramid_trades/all_pyramid_trades.csv", index=False)

    # Save series logs
    pd.DataFrame(all_series).to_csv("results/pyramid_series/all_series_adds.csv", index=False)

    # Top 20 by return (overall)
    top = master.sort_values("Total_Return_Pct", ascending=False).head(20)
    top.to_csv("results/pyramid_top20_overall.csv", index=False)

    # Top per Y_Factor
    for yf in Y_FACTORS:
        sub = master[master["Y_Factor"]==yf].sort_values("Total_Return_Pct", ascending=False).head(10)
        sub.to_csv(f"results/pyramid_top10_{yf}.csv", index=False)

    # Print summary
    print("\n=== TOP 10 PYRAMID PERMUTATIONS (Fee-Adjusted, $10k Start) ===")
    print(f"{'Rank':<5}{'Logic':<25}{'EMA':<12}{'Y_Factor':<25}{'Y_Val':<8}{'X%':<6}{'Final $':<12}{'Return%':<10}{'MaxDD%':<9}{'Sharpe':<8}{'Adds'}")
    for rank, (_, r) in enumerate(top.head(10).iterrows(), 1):
        ema_str = f"({r['Fast_EMA']},{r['Slow_EMA']})"
        print(f"{rank:<5}{r['Logic']:<25}{ema_str:<12}{r['Y_Factor']:<25}{r['Y_Value']:<8}{r['X_Pct']:<6}"
              f"${r['Final_Equity']:>10,.2f}   {r['Total_Return_Pct']:>+7.2f}%  {r['Max_Drawdown_Pct']:>6.1f}%  "
              f"{r['Sharpe']:>5.2f}  {r['Total_Series_Adds']}")

    print(f"\n  ETH Buy & Hold (No Pyramid): {bh_ret:+.2f}%")
    print(f"  Initial Capital: ${INITIAL_CAPITAL:,.0f}")
    print(f"\nFiles saved:")
    print("  results/pyramid_master_summary.csv")
    print("  results/pyramid_trades/all_pyramid_trades.csv")
    print("  results/pyramid_series/all_series_adds.csv")
    print("  results/pyramid_top20_overall.csv")

    return master


if __name__ == "__main__":
    run()
