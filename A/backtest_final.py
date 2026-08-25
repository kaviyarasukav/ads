"""
ETH 2026 Brute-Force EMA Backtester — Fixed & Production-Grade
Fixes applied:
  1. Realistic fees: 0.10% round-trip per trade (both entry and exit)
  2. True 1-bar execution delay (zero lookahead)
  3. Separate trade logs per strategy/logic
  4. Monthly PnL breakdown
  5. All 4 logics: EMA-X LO, EMA-X SAR, Price-EMA LO, Price-EMA SAR
"""
import os, json, time, sqlite3
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

FEE_RT = 0.001  # 0.10% round-trip (0.05% entry + 0.05% exit)
MIN_P, MAX_P = 5, 250
MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug"]

def load_1h():
    conn = sqlite3.connect("eth_market_data.sqlite")
    df = pd.read_sql("SELECT open_time,open,high,low,close,volume FROM candles_5m ORDER BY open_time ASC", conn)
    conn.close()
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df = df.set_index("open_time").resample("1h").agg(
        {"open":"first","high":"max","low":"min","close":"last","volume":"sum"}
    ).dropna().reset_index()
    return df

def build_ema_matrix(close):
    n = len(close)
    ps = range(MIN_P, MAX_P+1)
    M = np.empty((len(ps), n), dtype=np.float64)
    for i, p in enumerate(ps):
        a = 2.0/(p+1.0)
        e = close.copy()
        for t in range(1, n):
            e[t] = a*close[t] + (1-a)*e[t-1]
        M[i] = e
    return M

def pct_ret(strat_ret, fees_per_trade, pos):
    """Deduct fee when position changes. pos and strat_ret are both length n-1."""
    prev_pos = np.concatenate([[0.0], pos[:-1]])  # previous position, same length as pos
    changes = (pos != prev_pos).astype(np.float64)
    adj_ret = strat_ret - changes * fees_per_trade
    return adj_ret

def calc_metrics(adj_ret, pos, close, open_times, months_mask, bh_ret, fast_p, slow_p, logic):
    n_ret = len(adj_ret)
    cum = np.cumprod(1.0 + adj_ret)
    total_ret = (cum[-1]-1.0)*100.0
    running_max = np.maximum.accumulate(cum)
    dd = (cum-running_max)/running_max
    mdd = abs(dd.min())*100.0
    dur_yr = n_ret/8760.0
    cagr = ((cum[-1])**(1/dur_yr)-1)*100 if dur_yr > 0 else total_ret
    std = adj_ret.std()
    sharpe = (adj_ret.mean()/std)*np.sqrt(8760) if std>1e-9 else 0.0
    dstd = adj_ret[adj_ret<0].std() if (adj_ret<0).any() else 1e-9
    sortino = (adj_ret.mean()/dstd)*np.sqrt(8760) if dstd>1e-9 else 0.0
    calmar = (cagr/mdd) if mdd>0 else 0.0
    exposure = (np.abs(pos).sum()/len(pos))*100.0
    alpha = total_ret - bh_ret

    # Trade stats
    padded = np.concatenate([[0.0], pos, [0.0]])
    diffs = np.diff(padded)
    entries = np.where(diffs > 0)[0]
    exits_l = np.where(diffs < 0)[0]
    shorts_e = np.where(diffs < 0)[0]  # short entry
    shorts_x = np.where(diffs > 0)[0]  # short exit

    trades, wins, losses = [], [], []
    cur = 0.0; eb=0; ep=0.0; et=""
    for i in range(len(pos)):
        np_ = pos[i]
        if np_ != cur:
            if cur != 0.0:
                xp = close[i]; xt = str(open_times[i])[:16]
                pnl = ((xp/ep-1)*100 if cur>0 else (ep/xp-1)*100) - FEE_RT*100
                d = "LONG" if cur>0 else "SHORT"
                trades.append({"direction":d,"entry_time":et,"entry_price":round(ep,2),
                               "exit_time":xt,"exit_price":round(xp,2),
                               "duration":i-eb,"pnl":round(pnl,2),"reason":"Signal flip"})
                (wins if pnl>0 else losses).append(pnl)
            if np_ != 0.0:
                ep=close[i]; eb=i; et=str(open_times[i])[:16]
            cur=np_
    if cur!=0.0:
        xp=close[-1]; xt=str(open_times[-1])[:16]
        pnl=((xp/ep-1)*100 if cur>0 else (ep/xp-1)*100) - FEE_RT*100
        d="LONG" if cur>0 else "SHORT"
        trades.append({"direction":d,"entry_time":et,"entry_price":round(ep,2),
                       "exit_time":xt,"exit_price":round(xp,2),
                       "duration":len(pos)-eb,"pnl":round(pnl,2),"reason":"Dataset end"})
        (wins if pnl>0 else losses).append(pnl)

    nt=len(trades)
    wr=(len(wins)/nt)*100 if nt>0 else 0.0
    gp=sum(wins) if wins else 0.0
    gl=abs(sum(losses)) if losses else 1e-9
    pf=gp/gl if gl>0 else 999.0
    avg_hold=np.mean([t["duration"] for t in trades]) if trades else 0.0
    exp_pct=(wr/100*np.mean(wins) if wins else 0)+(((100-wr)/100)*np.mean(losses) if losses else 0)

    monthly = {}
    for m_name, mask in months_mask.items():
        if mask.any():
            monthly[m_name] = round((np.prod(1+adj_ret[mask])-1)*100, 2)
        else:
            monthly[m_name] = 0.0

    row = {
        "Logic":logic, "Fast_EMA":fast_p, "Slow_EMA":slow_p if slow_p is not None else "N/A",
        "Total_Ret_Pct":round(total_ret,2), "CAGR_Pct":round(cagr,2), "Alpha_Pct":round(alpha,2),
        "Max_DD_Pct":round(mdd,2), "Sharpe":round(sharpe,2), "Sortino":round(sortino,2),
        "Calmar":round(calmar,2), "Win_Rate_Pct":round(wr,2), "Profit_Factor":round(pf,2),
        "Expectancy_Pct":round(exp_pct,2), "Total_Trades":nt, "Avg_Hold_Hours":round(avg_hold,1),
        "Exposure_Pct":round(exposure,2), "Fees_Applied_Pct":round(nt*FEE_RT*100,2),
        "Pos_Months":sum(1 for v in monthly.values() if v>0),
    }
    row.update({f"M_{k}":v for k,v in monthly.items()})
    return row, trades

def run():
    os.makedirs("results/trades", exist_ok=True)
    os.makedirs("charts", exist_ok=True)

    df = load_1h()
    close = df["close"].values
    ot = df["open_time"].values
    n = len(close)
    print(f"Loaded {n} hourly bars | ETH Start: ${close[0]:.2f} | End: ${close[-1]:.2f}")

    bh_ret = (close[-1]/close[0]-1)*100.0
    asset_ret = np.diff(close)/close[:-1]
    n_ret = len(asset_ret)

    # Month masks (on ret array which is length n-1)
    ts = pd.to_datetime(df["open_time"].iloc[1:])
    months_mask = {}
    for mi, mn in enumerate(MONTHS, 1):
        months_mask[mn] = (ts.dt.month==mi).values

    print("Building EMA matrix...")
    t0=time.time()
    M = build_ema_matrix(close)
    pi = {p:i for i,p in enumerate(range(MIN_P,MAX_P+1))}
    print(f"EMA matrix ready in {time.time()-t0:.2f}s")

    periods = list(range(MIN_P, MAX_P+1))
    combos = [(p1,p2) for i,p1 in enumerate(periods) for p2 in periods[i+1:]]
    print(f"Testing {len(combos):,} EMA pairs x 2 logics + {len(periods)} singles x 2 logics = ~{len(combos)*2+len(periods)*2:,} total strategies\n")

    all_rows = []
    all_trades = {}

    # --- Single EMA (Price vs EMA) ---
    print("=== Logic 1: Price vs Single EMA (Long-Only) ===")
    for p in periods:
        ema = M[pi[p]]
        pos = (close[:-1] > ema[:-1]).astype(np.float64)
        adj = pct_ret(asset_ret * pos, FEE_RT/2, pos)  # half round-trip per side
        row, trades = calc_metrics(adj, pos, close, ot, months_mask, bh_ret, p, None, "PRICE_EMA_LONG_ONLY")
        all_rows.append(row)
        key=f"PRICE_EMA_LONG_ONLY_{p}_None"
        if p in [10,20,50,82,100,200]: all_trades[key]=trades

    print("=== Logic 2: Price vs Single EMA (Stop-and-Reverse) ===")
    for p in periods:
        ema = M[pi[p]]
        pos = np.where(close[:-1] > ema[:-1], 1.0, -1.0)
        adj = pct_ret(asset_ret * pos, FEE_RT/2, pos)
        row, trades = calc_metrics(adj, pos, close, ot, months_mask, bh_ret, p, None, "PRICE_EMA_SAR")
        all_rows.append(row)
        key=f"PRICE_EMA_SAR_{p}_None"
        if p in [10,20,50,82,100,200]: all_trades[key]=trades

    print("=== Logic 3 & 4: EMA Crossover (Long-Only & SAR) ===")
    t0=time.time()
    for idx,(pf,ps) in enumerate(combos):
        ef = M[pi[pf]]; es = M[pi[ps]]
        sig = (ef[:-1] > es[:-1])

        pos_lo = sig.astype(np.float64)
        adj_lo = pct_ret(asset_ret * pos_lo, FEE_RT/2, pos_lo)
        row_lo, trades_lo = calc_metrics(adj_lo, pos_lo, close, ot, months_mask, bh_ret, pf, ps, "EMA_CROSS_LONG_ONLY")
        all_rows.append(row_lo)

        pos_sar = np.where(sig, 1.0, -1.0)
        adj_sar = pct_ret(asset_ret * pos_sar, FEE_RT/2, pos_sar)
        row_sar, trades_sar = calc_metrics(adj_sar, pos_sar, close, ot, months_mask, bh_ret, pf, ps, "EMA_CROSS_SAR")
        all_rows.append(row_sar)

        if (pf,ps) in [(5,15),(208,224),(50,200),(9,21),(12,26)]:
            all_trades[f"EMA_CROSS_LONG_ONLY_{pf}_{ps}"] = trades_lo
            all_trades[f"EMA_CROSS_SAR_{pf}_{ps}"] = trades_sar

    print(f"Crossover brute-force done in {time.time()-t0:.2f}s")

    # Save master CSV
    master = pd.DataFrame(all_rows)
    master.to_csv("results/master_fee_adjusted.csv", index=False)

    # Save top 50 leaderboards per logic
    for logic in master["Logic"].unique():
        sub = master[master["Logic"]==logic].sort_values("Total_Ret_Pct", ascending=False).head(50)
        sub.to_csv(f"results/top50_{logic}.csv", index=False)

    # Save trade logs
    for key, trades in all_trades.items():
        pd.DataFrame(trades).to_csv(f"results/trades/{key}.csv", index=False)

    print(f"\nSaved {len(master):,} strategy rows")
    print("=== TOP RESULT SUMMARY (Fee-Adjusted) ===")
    for logic in master["Logic"].unique():
        sub = master[master["Logic"]==logic].sort_values("Total_Ret_Pct", ascending=False).iloc[0]
        print(f"  [{logic}] Best: EMA({sub['Fast_EMA']},{sub['Slow_EMA']}) -> "
              f"Ret={sub['Total_Ret_Pct']:+.2f}% | MDD={sub['Max_DD_Pct']:.1f}% | "
              f"Sharpe={sub['Sharpe']:.2f} | Trades={sub['Total_Trades']} | "
              f"FeesDrag={sub['Fees_Applied_Pct']:.1f}%")

    print(f"\n  ETH B&H Benchmark: {bh_ret:+.2f}%")

    # Heatmap for crossover long-only
    _plot_heatmap(master[master["Logic"]=="EMA_CROSS_LONG_ONLY"], "EMA_CROSS_LONG_ONLY")
    _plot_heatmap(master[master["Logic"]=="EMA_CROSS_SAR"], "EMA_CROSS_SAR")

    # Export data.js for frontend
    _export_web(master, all_trades, close)

def _plot_heatmap(sub, name):
    from matplotlib import colors
    sub = sub.copy()
    sub["Slow_EMA"] = sub["Slow_EMA"].replace("N/A", np.nan).astype(float)
    sub["Fast_EMA"] = sub["Fast_EMA"].astype(int)
    pivot = sub.pivot(index="Fast_EMA", columns="Slow_EMA", values="Total_Ret_Pct")
    fig, ax = plt.subplots(figsize=(12,9))
    plt.style.use("dark_background")
    im = ax.imshow(pivot.values, cmap="viridis", aspect="auto", origin="lower",
                   extent=[pivot.columns.min(), pivot.columns.max(),
                           pivot.index.min(), pivot.index.max()])
    fig.colorbar(im, ax=ax, label="Fee-Adj Return (%)")
    ax.set_title(f"{name} — Fee-Adjusted Total Return Heatmap (ETH 2026)", fontweight="bold", pad=12)
    ax.set_xlabel("Slow EMA Period"); ax.set_ylabel("Fast EMA Period")
    plt.tight_layout()
    plt.savefig(f"charts/{name}_heatmap.png", dpi=200)
    plt.close()
    print(f"Saved charts/{name}_heatmap.png")

def _export_web(master, all_trades, close):
    logics = {}
    for logic in master["Logic"].unique():
        sub = master[master["Logic"]==logic].sort_values("Total_Ret_Pct", ascending=False).head(100)
        logics[logic] = json.loads(sub.to_json(orient="records"))

    trade_export = {}
    for k, v in all_trades.items():
        trade_export[k] = v

    bh = round(float((close[-1]/close[0]-1)*100), 2)
    payload = {
        "benchmark": {"return": bh, "start": round(float(close[0]),2), "end": round(float(close[-1]),2)},
        "logics": logics,
        "trade_logs": trade_export,
        "stats": {
            "total": len(master),
            "fee_pct": FEE_RT*100,
            "best_sar": float(master[master["Logic"]=="EMA_CROSS_SAR"]["Total_Ret_Pct"].max()),
            "best_lo": float(master[master["Logic"]=="EMA_CROSS_LONG_ONLY"]["Total_Ret_Pct"].max()),
        }
    }
    with open("data.js", "w") as f:
        f.write("window.WEB_DATA = " + json.dumps(payload) + ";\n")
    with open("web_data.json", "w") as f:
        json.dump(payload, f)
    print("Exported data.js and web_data.json")

if __name__ == "__main__":
    run()
