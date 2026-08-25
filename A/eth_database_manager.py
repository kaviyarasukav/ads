import os
import sys
import json
import time
import sqlite3
import urllib.request
import numpy as np
import pandas as pd

DB_PATH = "eth_market_data.sqlite"

def init_db(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS candles_5m (
            open_time INTEGER PRIMARY KEY,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume REAL,
            close_time INTEGER,
            quote_volume REAL,
            trades_count INTEGER,
            taker_buy_volume REAL,
            taker_buy_quote_volume REAL
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_candles_5m_open_time ON candles_5m(open_time);")
    conn.commit()
    conn.close()

def sync_eth_5m_data(symbol="ETHUSDT", start_str="2026-01-01 00:00:00", db_path=DB_PATH):
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    cur.execute("SELECT MAX(open_time) FROM candles_5m")
    max_ts = cur.fetchone()[0]
    
    if max_ts is not None:
        start_ts = max_ts + 1
        print(f"Resuming sync from last recorded timestamp: {pd.to_datetime(start_ts, unit='ms', utc=True)}")
    else:
        start_ts = int(pd.Timestamp(start_str, tz="UTC").timestamp() * 1000)
        print(f"Starting fresh sync from {start_str}...")
        
    end_ts = int(pd.Timestamp.now(tz="UTC").timestamp() * 1000)
    current_start = start_ts
    total_new = 0
    
    while current_start < end_ts:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=5m&startTime={current_start}&limit=1000"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode('utf-8'))
                if not data:
                    break
                
                rows_to_insert = [
                    (
                        int(d[0]), float(d[1]), float(d[2]), float(d[3]), float(d[4]),
                        float(d[5]), int(d[6]), float(d[7]), int(d[8]), float(d[9]), float(d[10])
                    )
                    for d in data
                ]
                
                cur.executemany("""
                    INSERT OR REPLACE INTO candles_5m 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, rows_to_insert)
                conn.commit()
                
                total_new += len(rows_to_insert)
                last_time = data[-1][0]
                if len(data) < 1000 or last_time <= current_start:
                    break
                current_start = last_time + 1
                time.sleep(0.04)
        except Exception as e:
            print(f"Sync error: {e}, retrying...")
            time.sleep(1)
            
    cur.execute("SELECT COUNT(*), MIN(open_time), MAX(open_time) FROM candles_5m")
    count, min_t, max_t = cur.fetchone()
    conn.close()
    
    print(f"Database synced successfully! Total 5m candles: {count:,}")
    print(f"Time span: {pd.to_datetime(min_t, unit='ms', utc=True)} to {pd.to_datetime(max_t, unit='ms', utc=True)}")
    return count

def get_resampled_dataframe(timeframe="1h", db_path=DB_PATH):
    """
    Supported timeframes:
      '5m'  - Native
      '15m' - 15 minutes
      '30m' - 30 minutes
      '1h'  - 1 hour
      '2h'  - 2 hours
      '4h'  - 4 hours
      '1D'  - 1 day
    """
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query("SELECT open_time, open, high, low, close, volume, taker_buy_volume FROM candles_5m ORDER BY open_time ASC", conn)
    conn.close()
    
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    
    if timeframe.lower() in ["5m", "5min"]:
        return df
        
    freq_map = {
        "15m": "15min", "30m": "30min",
        "1h": "1h", "2h": "2h", "3h": "3h", "4h": "4h", "6h": "6h", "8h": "8h", "12h": "12h",
        "1d": "1D", "1w": "1W"
    }
    target_freq = freq_map.get(timeframe.lower(), timeframe)
    
    df = df.set_index("open_time")
    resampled = df.resample(target_freq).agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
        "taker_buy_volume": "sum"
    }).dropna().reset_index()
    
    return resampled

if __name__ == "__main__":
    sync_eth_5m_data(symbol="ETHUSDT", start_str="2026-01-01 00:00:00")
    print("\n--- Testing Resampling Engine ---")
    for tf in ["15m", "30m", "1h", "2h", "4h", "1D"]:
        t0 = time.time()
        res_df = get_resampled_dataframe(tf)
        print(f"Timeframe: {tf:<4} | Rows: {len(res_df):<6} | First: {res_df['open_time'].iloc[0]} | Last: {res_df['open_time'].iloc[-1]} | Time: {(time.time()-t0)*1000:.1f}ms")
