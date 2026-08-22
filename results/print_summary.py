import pandas as pd
df = pd.read_csv("master_fee_adjusted.csv")
print("ETH 2026 Fee-Adjusted Backtest — Final Results")
print("="*70)
for logic in df["Logic"].unique():
    sub = df[df["Logic"]==logic].sort_values("Total_Ret_Pct", ascending=False).iloc[0]
    fast = sub["Fast_EMA"]
    slow = sub["Slow_EMA"]
    print(f"\n[{logic}]")
    print(f"  Best Params : EMA ({fast}, {slow})")
    print(f"  Return      : {sub['Total_Ret_Pct']:+.2f}%")
    print(f"  Fee Drag    : {sub['Fees_Applied_Pct']:.1f}%")
    print(f"  Net Return  : {sub['Total_Ret_Pct'] - sub['Fees_Applied_Pct']:+.2f}% (est.)")
    print(f"  Max DD      : {sub['Max_DD_Pct']:.1f}%")
    print(f"  Sharpe      : {sub['Sharpe']:.2f}")
    print(f"  Win Rate    : {sub['Win_Rate_Pct']:.1f}%")
    print(f"  Trades      : {sub['Total_Trades']}")
print("\n  ETH Buy & Hold: -18.68%")
