import re, json

# 1. DOM ID sync check
with open('app.js', encoding='utf-8') as f: app = f.read()
with open('index.html', encoding='utf-8') as f: html = f.read()

js_ids = set(re.findall(r'getElementById\(["\']([^"\']+)["\']', app))
html_ids = set(re.findall(r'\bid=["\']([^"\']+)["\']', html))
missing_in_html = js_ids - html_ids
print(f"[DOM] JS getElementById calls: {len(js_ids)}")
print(f"[DOM] HTML id attributes: {len(html_ids)}")
if missing_in_html:
    print(f"[DOM BUG] Missing IDs in HTML: {sorted(missing_in_html)}")
else:
    print("[DOM] OK - all IDs present in HTML")

# 2. web_data.json schema
with open('web_data.json', encoding='utf-8') as f: wd = json.load(f)
required_keys = [
    "benchmark","market_capture","heatmap","feature_correlation","risk_studio",
    "waterfall","rolling_alpha","scatter_points","factor_comparison",
    "combined_overlay","base_logics","base_trade_logs","base_equity_curves",
    "pyramid_top","pyramid_by_factor","pyramid_trades","pyramid_series","stats"
]
missing_keys = [k for k in required_keys if k not in wd]
if missing_keys:
    print(f"[JSON BUG] Missing web_data keys: {missing_keys}")
else:
    print("[JSON] OK - all required keys present")

# 3. Check pyramid_top[0] fields needed by champ card
champ = wd['pyramid_top'][0]
needed = ['Strategy_Note','Composite_Score','Total_Return_Pct','Max_Drawdown_Pct','Sharpe','Profit_Factor','Fees_Applied_Pct']
missing_champ = [k for k in needed if k not in champ]
if missing_champ:
    print(f"[CHAMP BUG] Missing champ card fields: {missing_champ}")
else:
    print(f"[CHAMP] OK - champion: {champ.get('Strategy_Note','?')[:60]}, Return={champ.get('Total_Return_Pct')}%")

# 4. Check rolling_alpha for synthetic proxies
ra = wd['rolling_alpha']
print(f"[ALPHA] Rolling alpha points: SAR={len(ra['sar_alpha'])}, PYR={len(ra['pyr_alpha'])}")
if ra['sar_alpha']:
    print(f"[ALPHA] Sample SAR alpha[0]={ra['sar_alpha'][0]}, PYR alpha[0]={ra['pyr_alpha'][0]}")

# 5. Check waterfall fee_drag values
wf = wd['waterfall']
for key, val in wf.items():
    print(f"[WATERFALL] {val['name']}: fee_drag={val['fee_drag']}, net_pnl={val['net_pnl']}, final_eq={val['final_equity']}")

# 6. Check base trade log durations
sample_key = list(wd['base_trade_logs'].keys())[0]
trades = wd['base_trade_logs'][sample_key]
zero_dur = sum(1 for t in trades if t.get('duration', 0) == 0)
print(f"[TRADE LOGS] Key={sample_key}, Trades={len(trades)}, Zero-duration trades={zero_dur}")

# 7. Check scatter_points have all required numeric fields
sp = wd['scatter_points']
req_fields = ['x','y','sharpe','sortino','calmar','winrate','trades','pf','expectancy','pnl_usd','final_equity','hold_hours','exposure','fees','score']
sample_sp = sp[0] if sp else {}
missing_sp = [f for f in req_fields if f not in sample_sp]
if missing_sp:
    print(f"[SCATTER BUG] Missing fields in scatter_points: {missing_sp}")
else:
    print(f"[SCATTER] OK - all {len(req_fields)} fields present. Total points: {len(sp)}")

# 8. Check risk_studio results have needed fields
risk_recs = wd['risk_studio']['results']
risk_sample = risk_recs[0] if risk_recs else {}
risk_needed = ['Total_Return_Pct','Max_Drawdown_Pct','Sharpe','Sortino','Win_Rate_Pct','Profit_Factor','Expectancy_Pct','Final_Equity','Avg_Hold_Hours','Exposure_Pct']
missing_risk = [k for k in risk_needed if k not in risk_sample]
if missing_risk:
    print(f"[RISK BUG] Missing fields in risk_studio results: {missing_risk}")
else:
    print(f"[RISK] OK - all required risk fields present. Total records: {len(risk_recs)}")

# 9. Check hierarchy_explorer structure
hier = wd.get('hierarchy_explorer', [])
print(f"[HIER] hierarchy_explorer count: {len(hier)}")
if hier:
    h0 = hier[0]
    print(f"[HIER] Sample keys: {list(h0.keys())}")
    if 'quarters' in h0:
        q0 = h0['quarters'][0] if h0['quarters'] else {}
        print(f"[HIER] Quarter keys: {list(q0.keys())}")

# 10. Check equity curves populated
eq_curves = wd.get('base_equity_curves', {})
print(f"[EQ_CURVES] Count: {len(eq_curves)}")
if eq_curves:
    sample_ec = list(eq_curves.values())[0]
    print(f"[EQ_CURVES] Sample curve points: {len(sample_ec)}, first={sample_ec[0]}")
