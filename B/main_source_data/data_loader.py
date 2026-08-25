"""
Multi-Timeframe Data Access Layer (Folder B)
===========================================
Provides clean loading for 5m, 30m, and 1h timeframes across H1 2026 (Jan 01 - Jun 30, 2026):
- 5m:  52,128 continuous bars
- 30m: 8,688 continuous bars (resampled from 5m)
- 1h:  4,344 continuous bars (resampled from 5m)
"""

import os
import sqlite3
import pandas as pd
import numpy as np

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DATA_DIR, "main_source_data.sqlite")

def get_connection(db_path=DB_PATH):
    return sqlite3.connect(db_path)

def load_candle_data(timeframe: str = "5m") -> pd.DataFrame:
    """
    Loads OHLCV candle data for the specified timeframe across H1 2026.
    timeframe: '5m', '30m', or '1h'
    """
    conn = get_connection()
    df_5m = pd.read_sql_query("SELECT * FROM candles_5m_h1_half_year ORDER BY open_time ASC", conn)
    conn.close()
    
    df_5m["datetime"] = pd.to_datetime(df_5m["open_time"], unit="ms", utc=True)
    
    if timeframe.lower() == "5m":
        return df_5m

    # Resample rules
    freq_map = {"30m": "30min", "1h": "1h"}
    rule = freq_map.get(timeframe.lower(), "1h")

    df_resampled = df_5m.set_index("datetime").resample(rule).agg({
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
    }).dropna().reset_index()

    return df_resampled

# Convenience aliases
def load_5m_data(): return load_candle_data("5m")
def load_30m_data(): return load_candle_data("30m")
def load_1h_data(): return load_candle_data("1h")

if __name__ == "__main__":
    for tf in ["5m", "30m", "1h"]:
        df = load_candle_data(tf)
        print(f"Timeframe: {tf:<4} | Bars: {len(df):>6,} | Start: {df['datetime'].min()} | End: {df['datetime'].max()}")
