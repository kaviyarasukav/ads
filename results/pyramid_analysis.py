import pandas as pd

df = pd.read_csv("pyramid_master_summary.csv")
real = df[df["X_Pct"] < 100]

print("=== Best result per Y_Factor ===")
for yf in real["Y_Factor"].unique():
    sub = real[real["Y_Factor"]==yf].sort_values("Total_Return_Pct", ascending=False).iloc[0]
    print(f"  {yf:<28} X={sub['X_Pct']}%  Y={sub['Y_Value']}  Final=${sub['Final_Equity']:,.2f}  Ret={sub['Total_Return_Pct']:+.2f}%  MDD={sub['Max_Drawdown_Pct']:.1f}%  Adds={sub['Total_Series_Adds']}")

print()
print("=== Effect of X% on Avg Return (all factors) ===")
grp = real.groupby("X_Pct")["Total_Return_Pct"].agg(["mean","max","min"])
print(grp.to_string())

print()
best = real.sort_values("Total_Return_Pct", ascending=False).iloc[0]
months = ["M_Jan","M_Feb","M_Mar","M_Apr","M_May","M_Jun","M_Jul","M_Aug"]
print(f"Best Pyramid: {best['Logic']} EMA({best['Fast_EMA']},{best['Slow_EMA']}) Y_Factor={best['Y_Factor']} Y={best['Y_Value']} X={best['X_Pct']}%")
print(f"Final: ${best['Final_Equity']:,.2f}  Return: {best['Total_Return_Pct']:+.2f}%  Adds: {best['Total_Series_Adds']}")
for m in months:
    print(f"  {m}: {best[m]:+.2f}%")

print()
# Worst performing X_Factor
print("=== Worst result per Y_Factor ===")
for yf in real["Y_Factor"].unique():
    sub = real[real["Y_Factor"]==yf].sort_values("Total_Return_Pct", ascending=True).iloc[0]
    print(f"  {yf:<28} X={sub['X_Pct']}%  Y={sub['Y_Value']}  Ret={sub['Total_Return_Pct']:+.2f}%  MDD={sub['Max_Drawdown_Pct']:.1f}%  Adds={sub['Total_Series_Adds']}")
