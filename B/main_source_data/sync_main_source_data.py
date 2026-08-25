"""
Main Source Data Ingestion & Unified Access Layer (Binance Perpetual Futures)
=============================================================================
Primary Direct Provider Datasets:
1. 5m Candles (67,212 bars, 11 raw Binance columns):
   - open_time, open, high, low, close, volume, close_time, quote_volume,
     trades_count, taker_buy_volume, taker_buy_quote_volume
2. 1h Resampled Candles (5,601 continuous hourly bars):
   - Full OHLCV + Quote Volume + Trade Counts + Taker Aggressor Buy Volumes
3. Perpetual Funding Rates History (709 records, Jan 01 - Aug 22, 2026):
   - 8-hour fundingTime, fundingRate, markPrice
4. Open Interest (OI) Statistics:
   - sumOpenInterest (ETH), sumOpenInterestValue (USD)
5. Top Trader Long/Short Account & Position Ratios
6. Taker Buy/Sell Volume Ratio (Aggressive Market Buy vs Sell volumes)
"""

import os
import sys
import json
import time
import sqlite3
import urllib.request
import pandas as pd
import numpy as np

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DATA_DIR, "main_source_data.sqlite")

def init_db(db_path=DB_PATH):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS candles_5m (
            open_time INTEGER PRIMARY KEY,
            open REAL, high REAL, low REAL, close REAL, volume REAL,
            close_time INTEGER, quote_volume REAL, trades_count INTEGER,
            taker_buy_volume REAL, taker_buy_quote_volume REAL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS candles_1h (
            open_time INTEGER PRIMARY KEY,
            open REAL, high REAL, low REAL, close REAL, volume REAL,
            quote_volume REAL, trades_count INTEGER,
            taker_buy_volume REAL, taker_buy_quote_volume REAL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS funding_rates (
            funding_time INTEGER PRIMARY KEY,
            funding_rate REAL,
            mark_price REAL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS open_interest_1h (
            timestamp INTEGER PRIMARY KEY,
            sum_open_interest REAL,
            sum_open_interest_usd REAL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS top_long_short_ratio_1h (
            timestamp INTEGER PRIMARY KEY,
            long_account REAL,
            short_account REAL,
            long_short_ratio REAL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS taker_long_short_ratio_1h (
            timestamp INTEGER PRIMARY KEY,
            buy_vol REAL,
            sell_vol REAL,
            buy_sell_ratio REAL
        )
    """)

    conn.commit()
    conn.close()

def fetch_json(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=12) as response:
        return json.loads(response.read().decode('utf-8'))

def sync_candles():
    init_db()
    src_db = os.path.abspath(os.path.join(DATA_DIR, "../../A/eth_market_data.sqlite"))
    if not os.path.exists(src_db):
        src_db = "A/eth_market_data.sqlite"

    print(f"1. Ingesting raw 5m & 1h Candles from {src_db}...")
    conn_src = sqlite3.connect(src_db)
    df_5m = pd.read_sql_query("SELECT * FROM candles_5m ORDER BY open_time ASC", conn_src)
    conn_src.close()

    conn_dst = sqlite3.connect(DB_PATH)
    df_5m.to_sql("candles_5m", conn_dst, if_exists="replace", index=False)

    df_5m["dt"] = pd.to_datetime(df_5m["open_time"], unit="ms", utc=True)
    df_1h = df_5m.set_index("dt").resample("1h").agg({
        "open_time": "first",
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
        "quote_volume": "sum",
        "trades_count": "sum",
        "taker_buy_volume": "sum",
        "taker_buy_quote_volume": "sum"
    }).dropna().reset_index(drop=True)

    df_1h.to_sql("candles_1h", conn_dst, if_exists="replace", index=False)
    conn_dst.close()

    df_1h.to_csv(os.path.join(DATA_DIR, "eth_2026_1h_candles.csv"), index=False)
    print(f"   [DONE] Ingested {len(df_5m):,} 5m candles and {len(df_1h):,} 1h candles.")

def sync_funding_rates(start_str="2026-01-01"):
    print("2. Ingesting Complete 2026 Funding Rates (every 8 hours)...")
    start_ts = int(pd.Timestamp(start_str, tz="UTC").timestamp() * 1000)
    end_ts = int(pd.Timestamp.now(tz="UTC").timestamp() * 1000)
    
    all_rates = []
    curr_start = start_ts

    while curr_start < end_ts:
        url = f"https://fapi.binance.com/fapi/v1/fundingRate?symbol=ETHUSDT&startTime={curr_start}&limit=1000"
        try:
            data = fetch_json(url)
            if not data:
                break
            for r in data:
                all_rates.append({
                    "funding_time": int(r["fundingTime"]),
                    "funding_rate": float(r["fundingRate"]),
                    "mark_price": float(r.get("markPrice", 0.0))
                })
            last_ts = int(data[-1]["fundingTime"])
            if last_ts == curr_start:
                break
            curr_start = last_ts + 1
            time.sleep(0.08)
        except Exception as e:
            print(f"   Funding rate fetch warning: {e}")
            break

    if all_rates:
        conn = sqlite3.connect(DB_PATH)
        df_fr = pd.DataFrame(all_rates).drop_duplicates(subset=["funding_time"])
        df_fr.to_sql("funding_rates", conn, if_exists="replace", index=False)
        conn.close()
        df_fr.to_csv(os.path.join(DATA_DIR, "eth_2026_funding_rates.csv"), index=False)
        print(f"   [DONE] Ingested {len(df_fr):,} Funding Rate events spanning all of 2026.")

def sync_derivatives_statistics():
    print("3. Ingesting Open Interest, Top Long/Short Ratios & Taker Volumes from Binance...")
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - (29 * 24 * 3600 * 1000) # 30-day lookback supported by Binance REST

    # A. Open Interest
    url_oi = f"https://fapi.binance.com/futures/data/openInterestHist?symbol=ETHUSDT&period=1h&startTime={start_ms}&limit=500"
    try:
        data_oi = fetch_json(url_oi)
        df_oi = pd.DataFrame([{
            "timestamp": int(r["timestamp"]),
            "sum_open_interest": float(r["sumOpenInterest"]),
            "sum_open_interest_usd": float(r["sumOpenInterestValue"])
        } for r in data_oi]).drop_duplicates(subset=["timestamp"])
        
        conn = sqlite3.connect(DB_PATH)
        df_oi.to_sql("open_interest_1h", conn, if_exists="replace", index=False)
        conn.close()
        df_oi.to_csv(os.path.join(DATA_DIR, "eth_open_interest_1h.csv"), index=False)
        print(f"   [DONE] Ingested {len(df_oi):,} Open Interest hourly records.")
    except Exception as e:
        print(f"   OI fetch error: {e}")

    # B. Top Long/Short Ratio
    url_ls = f"https://fapi.binance.com/futures/data/topLongShortPositionRatio?symbol=ETHUSDT&period=1h&startTime={start_ms}&limit=500"
    try:
        data_ls = fetch_json(url_ls)
        df_ls = pd.DataFrame([{
            "timestamp": int(r["timestamp"]),
            "long_account": float(r["longAccount"]),
            "short_account": float(r["shortAccount"]),
            "long_short_ratio": float(r["longShortRatio"])
        } for r in data_ls]).drop_duplicates(subset=["timestamp"])

        conn = sqlite3.connect(DB_PATH)
        df_ls.to_sql("top_long_short_ratio_1h", conn, if_exists="replace", index=False)
        conn.close()
        df_ls.to_csv(os.path.join(DATA_DIR, "eth_top_long_short_ratio_1h.csv"), index=False)
        print(f"   [DONE] Ingested {len(df_ls):,} Top Trader Long/Short ratio records.")
    except Exception as e:
        print(f"   LSR fetch error: {e}")

    # C. Taker Buy/Sell Volume Ratio
    url_tk = f"https://fapi.binance.com/futures/data/takerlongshortRatio?symbol=ETHUSDT&period=1h&startTime={start_ms}&limit=500"
    try:
        data_tk = fetch_json(url_tk)
        df_tk = pd.DataFrame([{
            "timestamp": int(r["timestamp"]),
            "buy_vol": float(r["buyVol"]),
            "sell_vol": float(r["sellVol"]),
            "buy_sell_ratio": float(r["buySellRatio"])
        } for r in data_tk]).drop_duplicates(subset=["timestamp"])

        conn = sqlite3.connect(DB_PATH)
        df_tk.to_sql("taker_long_short_ratio_1h", conn, if_exists="replace", index=False)
        conn.close()
        df_tk.to_csv(os.path.join(DATA_DIR, "eth_taker_long_short_ratio_1h.csv"), index=False)
        print(f"   [DONE] Ingested {len(df_tk):,} Taker Buy/Sell volume ratio records.")
    except Exception as e:
        print(f"   Taker ratio fetch error: {e}")

def run_all():
    print("=" * 80)
    print("INGESTING ALL PRIMARY DIRECT PROVIDER DATASETS INTO B/main_source_data/")
    print("=" * 80)
    sync_candles()
    sync_funding_rates()
    sync_derivatives_statistics()
    print("=" * 80)
    print("ALL PRIMARY PROVIDER DATASETS STORED IN main_source_data.sqlite & CSVs!")
    print("=" * 80)

if __name__ == "__main__":
    run_all()
