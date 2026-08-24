"""
ETH 2026 — Pyramid / Reinvestment Brute-Force (CORRECTED v2.1)
==============================================================
FIXES from v1:
  - X% is now taken from INITIAL CAPITAL (fixed dollar per add)
    e.g. X=10% on $10k -> each add = $1,000 regardless of remaining cash
    Max adds per series = floor(100/X) before cash runs out
  - Tests top 20 EMA pairs from master_fee_adjusted.csv (not just 5)
  - Relative data stored: return vs BH, return vs base EMA strategy
  - Per-trade and per-series logs labelled with all params
  - Fee: 0.10% per order (each add = 1 order, 1 exit = 1 order)

FIXES in v2.1 (this file):
  - BUG 3: SHORT PnL formula corrected: proceeds = cost_basis + pnl_usd.
  - BUG 4: PROFIT_FROM_LAST_PCT now uses price_vs_last (same as PRICE_FROM_LAST_PCT)
           instead of stale last_add_unr_pct which tracked portfolio-level unrealized.
  - BUG 5: Monthly returns chained via prev_equity (not s[0] = first bar of month).
  - IMP 4: Calmar, Sortino, Expectancy added to row output.
  - IMP 7: Mark-to-market equity uses close[i] (current bar) not close[i+1] (lookahead).
==========================================================
FIXES from v1:
  - X% is now taken from INITIAL CAPITAL (fixed dollar per add)
    e.g. X=10% on $10k -> each add = $1,000 regardless of remaining cash
    Max adds per series = floor(100/X) before cash runs out
  - Tests top 20 EMA pairs from master_fee_adjusted.csv (not just 5)
  - Relative data stored: return vs BH, return vs base EMA strategy
  - Per-trade and per-series logs labelled with all params
  - Fee: 0.10% per order (each add = 1 order, 1 exit = 1 order)

Y_FACTOR options:
  BARS_ELAPSED          -- every N bars since last add
  HOURS_ELAPSED         -- every N hours since last add (= bars on 1h data)
  PRICE_FROM_START_PCT  -- price moved N% from first entry of series
  PRICE_FROM_LAST_PCT   -- price moved N% from last add price
  PROFIT_FROM_START_PCT -- unrealized profit >= N% from series open
  PROFIT_FROM_LAST_PCT  -- unrealized profit grew N% since last add

X values  : 5, 10, 15, 20, 25, 30, 50 (% of $10k = $500/$1k/$1.5k/$2k/$2.5k/$3k/$5k per add)
Y values  : factor-specific ranges
"""

import os, time, sqlite3
import numpy as np
import pandas as pd

INITIAL_CAPITAL = 10_000.0
FEE_RT = 0.001          # 0.10% per order
BH_RETURN = -18.68      # ETH 2026 buy & hold

X_VALUES = [5, 10, 15, 20, 25, 30, 50]   # % of initial capital per add

Y_FACTORS = {
    "BARS_ELAPSED":           [1, 2, 4, 6, 12, 24, 48, 72, 168],
    "HOURS_ELAPSED":          [1, 2, 4, 6, 12, 24, 48, 72, 168],
    "PRICE_FROM_START_PCT":   [0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 7.0, 10.0],
    "PRICE_FROM_LAST_PCT":    [0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 7.0, 10.0],
    "PROFIT_FROM_START_PCT":  [0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 7.0, 10.0],
    "PROFIT_FROM_LAST_PCT":   [0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 7.0, 10.0],
}

MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug"]


# ─── DATA LOADING ────────────────────────────────────────────────────────────

def load_1h():
    conn = sqlite3.connect("eth_market_data.sqlite")
    df = pd.read_sql("SELECT open_time,close FROM candles_5m ORDER BY open_time ASC", conn)
    conn.close()
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df = df.set_index("open_time")["close"].resample("1h").last().dropna().reset_index()
    df.columns = ["open_time", "close"]
    return df


def build_ema(close, p):
    a = 2.0 / (p + 1.0)
    e = close.copy()
    for t in range(1, len(close)):
        e[t] = a * close[t] + (1 - a) * e[t - 1]
    return e


def get_signal(close, logic, fast_p, slow_p):
    """Returns position array length n-1: +1=LONG, -1=SHORT, 0=FLAT"""
    ef = build_ema(close, int(fast_p))
    if slow_p is not None and not (isinstance(slow_p, float) and np.isnan(slow_p)):
        es = build_ema(close, int(slow_p))
        cross = ef[:-1] > es[:-1]
    else:
        cross = close[:-1] > ef[:-1]

    if "LONG_ONLY" in logic:
        return cross.astype(np.float64)
    else:
        return np.where(cross, 1.0, -1.0)


def base_return(close, pos_signal):
    """Fee-adjusted base return without pyramiding (single entry per signal block)"""
    prev = np.concatenate([[0.0], pos_signal[:-1]])
    changes = (pos_signal != prev).astype(np.float64)
    ret = np.diff(close) / close[:-1]
    strat_ret = ret * pos_signal - changes * FEE_RT
    cum = np.prod(1 + strat_ret)
    return round((cum - 1) * 100, 2)


# ─── PYRAMID ENGINE ──────────────────────────────────────────────────────────

def pyramid_sim(close, open_times, pos_signal, x_pct, y_factor, y_value,
                logic, fast_p, slow_p, base_ret):
    """
    Run one pyramid simulation. Returns (summary_row, trade_log, series_log).
    X is % of INITIAL CAPITAL per add (fixed dollar).
    """
    add_budget = INITIAL_CAPITAL * (x_pct / 100.0)   # Fixed $ per add
    max_adds = int(np.floor(100.0 / x_pct))           # Max adds before cash exhausted

    cash = INITIAL_CAPITAL
    position_units = 0.0
    position_side = 0            # +1 LONG, -1 SHORT
    in_trade = False

    total_cost_basis = 0.0
    avg_entry_price = 0.0
    add_count = 0
    series_entry_bar = 0
    series_entry_price = 0.0
    last_add_bar = 0
    last_add_price = 0.0
    last_add_unr_pct = 0.0

    equity_curve = [INITIAL_CAPITAL]
    trade_log = []
    series_log = []
    prev_sig = 0.0

    n_ret = len(pos_signal)

    for i in range(n_ret):
        price = close[i]
        next_bar_price = close[i + 1]
        sig = pos_signal[i]
        dt = str(open_times[i])[:16]

        # ── SIGNAL FLIP → close position ────────────────────────────
        if in_trade and sig != prev_sig:
            exit_px = next_bar_price * (1.0 - FEE_RT)   # sell/cover at slight cost
            if position_side == 1:
                proceeds = position_units * exit_px
                pnl_usd = proceeds - total_cost_basis
            else:  # SHORT — BUG 3 FIX: correct formula
                pnl_usd = (avg_entry_price - exit_px) * position_units
                proceeds = total_cost_basis + pnl_usd

            pnl_pct = (pnl_usd / total_cost_basis) * 100 if total_cost_basis > 0 else 0.0
            cash += proceeds

            trade_log.append({
                "Strategy": f"{logic}|EMA({fast_p},{slow_p})",
                "Logic": logic, "Fast_EMA": fast_p, "Slow_EMA": slow_p,
                "Y_Factor": y_factor, "Y_Value": y_value, "X_Pct": x_pct,
                "Note": f"[{logic}] EMA({fast_p},{slow_p}) | Y_Factor={y_factor} Y_Val={y_value} X%={x_pct}",
                "Direction": "LONG" if position_side == 1 else "SHORT",
                "Series_Entry_Time": str(open_times[series_entry_bar])[:16],
                "Series_Entry_Price": round(series_entry_price, 2),
                "Avg_Entry_Price": round(avg_entry_price, 2),
                "Exit_Time": dt,
                "Exit_Price": round(exit_px, 2),
                "Total_Adds_In_Series": add_count,
                "Total_Invested_USD": round(total_cost_basis, 2),
                "Realized_PnL_USD": round(pnl_usd, 2),
                "Realized_PnL_Pct": round(pnl_pct, 2),
                "Portfolio_After_USD": round(cash, 2)
            })

            position_units = 0.0; total_cost_basis = 0.0
            avg_entry_price = 0.0; add_count = 0; in_trade = False

        # ── OPEN or ADD in series ────────────────────────────────────
        if sig != 0:
            do_add = False

            if not in_trade:
                do_add = True
                position_side = int(sig)
                series_entry_bar = i
                series_entry_price = next_bar_price * (1.0 + FEE_RT)
                last_add_bar = i
                last_add_price = series_entry_price
                last_add_unr_pct = 0.0
            elif add_count < max_adds:
                # Check Y trigger
                bars_since = i - last_add_bar

                if position_side == 1:
                    curr_unr = (price - avg_entry_price) / avg_entry_price * 100 if avg_entry_price > 0 else 0.0
                    price_vs_start = (price - series_entry_price) / series_entry_price * 100
                    price_vs_last = (price - last_add_price) / last_add_price * 100
                else:
                    curr_unr = (avg_entry_price - price) / avg_entry_price * 100 if avg_entry_price > 0 else 0.0
                    price_vs_start = (series_entry_price - price) / series_entry_price * 100
                    price_vs_last = (last_add_price - price) / last_add_price * 100

                if y_factor == "BARS_ELAPSED" and bars_since >= y_value:
                    do_add = True
                elif y_factor == "HOURS_ELAPSED" and bars_since >= y_value:
                    do_add = True
                elif y_factor == "PRICE_FROM_START_PCT" and price_vs_start >= y_value:
                    do_add = True
                elif y_factor == "PRICE_FROM_LAST_PCT" and price_vs_last >= y_value:
                    do_add = True
                elif y_factor == "PROFIT_FROM_START_PCT" and curr_unr >= y_value:
                    do_add = True
                # BUG 4 FIX: use price_vs_last (movement from last add price) not stale unr snapshot
                elif y_factor == "PROFIT_FROM_LAST_PCT" and price_vs_last >= y_value:
                    do_add = True

            if do_add and cash >= add_budget:
                entry_px = next_bar_price * (1.0 + FEE_RT)
                units = add_budget / entry_px
                cash -= add_budget
                position_units += units
                total_cost_basis += add_budget
                avg_entry_price = total_cost_basis / position_units
                add_count += 1
                in_trade = True
                last_add_bar = i
                last_add_price = entry_px

                if position_side == 1:
                    curr_unr = (price - avg_entry_price) / avg_entry_price * 100 if avg_entry_price > 0 else 0.0
                else:
                    curr_unr = (avg_entry_price - price) / avg_entry_price * 100 if avg_entry_price > 0 else 0.0

                series_log.append({
                    "Strategy": f"{logic}|EMA({fast_p},{slow_p})",
                    "Note": f"[{logic}] EMA({fast_p},{slow_p}) | Y_Factor={y_factor} Y_Val={y_value} X%={x_pct}",
                    "Y_Factor": y_factor, "Y_Value": y_value, "X_Pct": x_pct,
                    "Series_Add_No": add_count,
                    "Bar_Index": i, "Time": dt,
                    "Direction": "LONG" if position_side == 1 else "SHORT",
                    "Entry_Price": round(entry_px, 2),
                    "Fixed_Add_USD": round(add_budget, 2),
                    "Total_Cost_Basis": round(total_cost_basis, 2),
                    "Avg_Entry_Price": round(avg_entry_price, 2),
                    "Units_Total": round(position_units, 6),
                    "Cash_Remaining": round(cash, 2),
                    "Unrealized_Pct": round(curr_unr, 2)
                })

        # ── Mark-to-market equity ────────────────────────────────────
        # IMP 7 FIX: use close[i] (current bar) not close[i+1] (1-bar lookahead)
        if in_trade and position_units > 0:
            if position_side == 1:
                unr = position_units * price - total_cost_basis
            else:
                unr = total_cost_basis - position_units * price
            eq = cash + total_cost_basis + unr
        else:
            eq = cash
        equity_curve.append(round(eq, 2))
        prev_sig = sig

    # Force-close final open position
    if in_trade and position_units > 0:
        exit_px = close[-1] * (1.0 - FEE_RT)
        if position_side == 1:
            pnl_usd = position_units * exit_px - total_cost_basis
        else:
            pnl_usd = total_cost_basis - position_units * exit_px
        cash += total_cost_basis + pnl_usd
        pnl_pct = (pnl_usd / total_cost_basis) * 100 if total_cost_basis > 0 else 0.0
        trade_log.append({
            "Strategy": f"{logic}|EMA({fast_p},{slow_p})",
            "Logic": logic, "Fast_EMA": fast_p, "Slow_EMA": slow_p,
            "Y_Factor": y_factor, "Y_Value": y_value, "X_Pct": x_pct,
            "Note": f"[{logic}] EMA({fast_p},{slow_p}) | Y_Factor={y_factor} Y_Val={y_value} X%={x_pct}",
            "Direction": "LONG" if position_side == 1 else "SHORT",
            "Series_Entry_Time": str(open_times[series_entry_bar])[:16],
            "Series_Entry_Price": round(series_entry_price, 2),
            "Avg_Entry_Price": round(avg_entry_price, 2),
            "Exit_Time": str(open_times[-1])[:16],
            "Exit_Price": round(exit_px, 2),
            "Total_Adds_In_Series": add_count,
            "Total_Invested_USD": round(total_cost_basis, 2),
            "Realized_PnL_USD": round(pnl_usd, 2),
            "Realized_PnL_Pct": round(pnl_pct, 2),
            "Portfolio_After_USD": round(cash, 2)
        })

    # ── Summary metrics ──────────────────────────────────────────────
    eq = np.array(equity_curve, dtype=np.float64)
    final_eq = eq[-1]
    total_ret = (final_eq / INITIAL_CAPITAL - 1) * 100
    running_max = np.maximum.accumulate(eq)
    dd = (eq - running_max) / np.where(running_max == 0, 1e-9, running_max)
    max_dd = abs(dd.min()) * 100
    r = np.diff(eq) / np.where(eq[:-1] == 0, 1e-9, eq[:-1])
    std = r.std()
    sharpe = (r.mean() / std) * np.sqrt(8760) if std > 1e-9 else 0.0

    # IMP 4: Sortino (downside-only std)
    down = r[r < 0]
    down_std = down.std() if len(down) > 1 else 1e-9
    sortino = (r.mean() / down_std) * np.sqrt(8760) if down_std > 1e-9 else 0.0

    # IMP 4: Calmar (annualised return / max drawdown)
    dataset_years = len(eq) / 8760.0
    ann_ret = ((final_eq / INITIAL_CAPITAL) ** (1.0 / max(dataset_years, 0.001)) - 1.0) * 100.0
    calmar = ann_ret / max_dd if max_dd > 1e-9 else 0.0

    n_closed = len(trade_log)
    pnls = [t["Realized_PnL_Pct"] for t in trade_log]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    wr = (len(wins) / n_closed * 100) if n_closed > 0 else 0.0
    gp = sum(wins); gl = abs(sum(losses)) if losses else 1e-9
    pf = gp / gl if gl > 1e-9 else 999.0
    total_adds = sum(t["Total_Adds_In_Series"] for t in trade_log)
    avg_adds = round(total_adds / n_closed, 1) if n_closed > 0 else 0.0

    # IMP 4: Expectancy per trade
    avg_win_p = float(np.mean(wins)) if wins else 0.0
    avg_loss_p = abs(float(np.mean(losses))) if losses else 0.0
    wr_f = wr / 100.0
    expectancy_pct = wr_f * avg_win_p - (1.0 - wr_f) * avg_loss_p

    # BUG 5 FIX: chain monthly returns via prev_equity, not s[0] = first bar of month
    monthly = {}
    prev_eq_m = INITIAL_CAPITAL
    df_eq = pd.DataFrame({"eq": eq, "t": open_times})
    dt_series = pd.to_datetime(df_eq["t"])
    for mi, mn in enumerate(MONTHS, 1):
        mask = (dt_series.dt.month == mi).values
        s = eq[mask]
        if len(s) >= 1:
            m_ret = (s[-1] / prev_eq_m - 1) * 100
            monthly[mn] = round(float(m_ret), 2)
            prev_eq_m = float(s[-1])
        else:
            monthly[mn] = 0.0

    row = {
        # --- Strategy identity ---
        "Strategy_Note": f"[{logic}] EMA({fast_p},{slow_p}) | Y={y_factor}({y_value}) X={x_pct}%",
        "Logic": logic, "Fast_EMA": fast_p, "Slow_EMA": slow_p,
        "Y_Factor": y_factor, "Y_Value": y_value, "X_Pct": x_pct,
        "Fixed_Add_USD": round(add_budget, 2),
        "Max_Possible_Adds": max_adds,
        # --- Portfolio metrics ---
        "Initial_Capital": INITIAL_CAPITAL,
        "Final_Equity": round(final_eq, 2),
        "Total_Return_Pct": round(total_ret, 2),
        "Net_PnL_USD": round(final_eq - INITIAL_CAPITAL, 2),
        "Max_Drawdown_Pct": round(max_dd, 2),
        "Sharpe": round(sharpe, 2),
        "Sortino": round(sortino, 2),          # IMP 4
        "Calmar": round(calmar, 2),            # IMP 4
        "Win_Rate_Pct": round(wr, 2),
        "Profit_Factor": round(min(pf, 999.0), 2),
        "Expectancy_Pct": round(expectancy_pct, 2),  # IMP 4
        # --- Trade stats ---
        "Total_Closed_Trades": n_closed,
        "Total_Series_Adds": total_adds,
        "Avg_Adds_Per_Trade": avg_adds,
        # --- Relative comparison ---
        "Base_Return_Pct": base_ret,
        "Alpha_vs_Base_Pct": round(total_ret - base_ret, 2),
        "Alpha_vs_BH_Pct": round(total_ret - BH_RETURN, 2),
        "Pyramid_Added_Pct": round(total_ret - base_ret, 2),
    }
    for mn in MONTHS:
        row[f"M_{mn}"] = monthly[mn]

    return row, trade_log, series_log


# ─── MAIN ────────────────────────────────────────────────────────────────────

def run():
    os.makedirs("results/pyramid_trades", exist_ok=True)
    os.makedirs("results/pyramid_series", exist_ok=True)

    # Load hourly price data
    df = load_1h()
    close = df["close"].values.astype(np.float64)
    open_times = df["open_time"].values
    n = len(close)
    print(f"Loaded {n} hourly bars | ETH ${close[0]:.2f} -> ${close[-1]:.2f} | BH: {BH_RETURN:+.2f}%")

    # Load top 20 EMA pairs from fee-adjusted master
    master_src = pd.read_csv("results/master_fee_adjusted.csv")
    top_pairs_df = master_src.sort_values("Total_Ret_Pct", ascending=False).head(20)[
        ["Logic","Fast_EMA","Slow_EMA","Total_Ret_Pct"]].drop_duplicates()
    pairs = list(top_pairs_df.itertuples(index=False, name=None))
    print(f"Testing top {len(pairs)} EMA pairs x {len(X_VALUES)} X% x {sum(len(v) for v in Y_FACTORS.values())} Y vals")

    total_perms = len(pairs) * len(X_VALUES) * sum(len(v) for v in Y_FACTORS.values())
    print(f"Total permutations: {total_perms:,}\n")

    all_rows, all_trades, all_series = [], [], []
    t0 = time.time()

    for logic, fast_p, slow_p, base_ret_from_master in pairs:
        pos_signal = get_signal(close, logic, fast_p, slow_p)

        for y_factor, y_values in Y_FACTORS.items():
            for y_val in y_values:
                for x_pct in X_VALUES:
                    row, trades, series = pyramid_sim(
                        close, open_times, pos_signal,
                        x_pct, y_factor, y_val,
                        logic, fast_p, slow_p, base_ret_from_master
                    )
                    all_rows.append(row)
                    all_trades.extend(trades)
                    all_series.extend(series)

    elapsed = time.time() - t0
    print(f"Completed {len(all_rows):,} permutations in {elapsed:.1f}s")

    # ── Save all outputs ──────────────────────────────────────────────
    master = pd.DataFrame(all_rows)
    master.to_csv("results/pyramid_v2_master.csv", index=False)

    trades_df = pd.DataFrame(all_trades)
    trades_df.to_csv("results/pyramid_trades/pyramid_v2_all_trades.csv", index=False)

    series_df = pd.DataFrame(all_series)
    series_df.to_csv("results/pyramid_series/pyramid_v2_all_series.csv", index=False)

    # Top 20 overall
    top20 = master.sort_values("Total_Return_Pct", ascending=False).head(20)
    top20.to_csv("results/pyramid_v2_top20.csv", index=False)

    # Best per Y_Factor
    for yf in Y_FACTORS:
        sub = master[master["Y_Factor"]==yf].sort_values("Total_Return_Pct", ascending=False).head(10)
        sub.to_csv(f"results/pyramid_v2_top10_{yf}.csv", index=False)

    # Best per EMA pair (relative lift)
    best_per_pair = master.sort_values("Total_Return_Pct", ascending=False).groupby(
        ["Logic","Fast_EMA","Slow_EMA"]).first().reset_index()
    best_per_pair.to_csv("results/pyramid_v2_best_per_pair.csv", index=False)

    # ── Print summary ─────────────────────────────────────────────────
    print("\n=== TOP 10 PYRAMID PERMUTATIONS (Fixed X$ per add, Fee-Adj) ===")
    print(f"{'#':<3} {'Logic':<22} {'EMA':<12} {'Y_Factor':<24} {'Y_Val':<7} {'X%':<5} {'$/add':<7} {'MaxAdds':<8} {'Return%':<10} {'Alpha>Base':<11} {'MDD%':<8} {'Sharpe':<8} {'Adds'}")
    top10 = master.sort_values("Total_Return_Pct", ascending=False).head(10)
    for rank, (_, r) in enumerate(top10.iterrows(), 1):
        ema = f"({r['Fast_EMA']},{r['Slow_EMA']})"
        print(f"{rank:<3} {r['Logic']:<22} {ema:<12} {r['Y_Factor']:<24} {r['Y_Value']:<7} "
              f"{r['X_Pct']:<5} ${r['Fixed_Add_USD']:<6,.0f} {r['Max_Possible_Adds']:<8} "
              f"{r['Total_Return_Pct']:>+7.2f}%  {r['Alpha_vs_Base_Pct']:>+6.2f}%     "
              f"{r['Max_Drawdown_Pct']:>5.1f}%  {r['Sharpe']:>5.2f}  {r['Total_Series_Adds']}")

    print(f"\n  ETH Buy & Hold: {BH_RETURN:+.2f}% | Initial: ${INITIAL_CAPITAL:,.0f}")

    # Effect of X_Pct
    print("\n=== EFFECT OF X% (avg / max return across all pairs & factors) ===")
    grp = master.groupby("X_Pct")["Total_Return_Pct"].agg(["mean","max","min"])
    grp.columns = ["Avg_Ret%","Max_Ret%","Min_Ret%"]
    grp["Fixed_$/add"] = [f"${INITIAL_CAPITAL*x/100:,.0f}" for x in grp.index]
    grp["Max_Possible_Adds"] = [int(100/x) for x in grp.index]
    print(grp.to_string())

    # Best per Y_Factor
    print("\n=== BEST PER Y_FACTOR ===")
    for yf in Y_FACTORS:
        best = master[master["Y_Factor"]==yf].sort_values("Total_Return_Pct", ascending=False).iloc[0]
        print(f"  {yf:<28} X={best['X_Pct']}% (${best['Fixed_Add_USD']:,.0f}/add) Y={best['Y_Value']:5} "
              f"-> Ret={best['Total_Return_Pct']:+.2f}% | Alpha_vs_Base={best['Alpha_vs_Base_Pct']:+.2f}% "
              f"| MDD={best['Max_Drawdown_Pct']:.1f}% | Adds={best['Total_Series_Adds']}")

    print("\nFiles:")
    print("  results/pyramid_v2_master.csv")
    print("  results/pyramid_trades/pyramid_v2_all_trades.csv")
    print("  results/pyramid_series/pyramid_v2_all_series.csv")
    print("  results/pyramid_v2_top20.csv")


if __name__ == "__main__":
    run()
