"""
EMA Strategy Signal Generation (Folder B)
=========================================
Generates raw trade direction signals (+1 = Long, -1 = Short, 0 = Flat/Cash):

1. EMA_CROSS_SAR:
   - Fast EMA > Slow EMA -> +1 (Long)
   - Fast EMA < Slow EMA -> -1 (Short)

2. EMA_CROSS_PRICE_CONFIRMED:
   - Long when Fast crosses above Slow AND Close > Fast EMA
   - Short when Fast crosses below Slow AND Close < Fast EMA
   - Exits to 0 (Flat) when opposite cross occurs.

3. SINGLE_EMA_PRICE_SAR:
   - Close > Single EMA -> +1 (Long)
   - Close < Single EMA -> -1 (Short)
"""

import numpy as np

def generate_ema_sar_signals(fast_ema: np.ndarray, slow_ema: np.ndarray) -> np.ndarray:
    """
    Method 1: Stop-and-Reverse (SAR) Bi-directional Crossover.
    Fast > Slow -> +1 (Long), Fast < Slow -> -1 (Short)
    """
    return np.where(fast_ema > slow_ema, 1.0, -1.0)

def generate_ema_cross_price_signals(close: np.ndarray, fast_ema: np.ndarray, slow_ema: np.ndarray) -> np.ndarray:
    """
    Method 2: Cross + Price Confirmation.
    Long = Fast > Slow AND Close > Fast EMA
    Short = Fast < Slow AND Close < Fast EMA
    Flat = In-between transition
    """
    long_cond = (fast_ema > slow_ema) & (close > fast_ema)
    short_cond = (fast_ema < slow_ema) & (close < fast_ema)
    
    signals = np.zeros(len(close), dtype=np.float64)
    signals[long_cond] = 1.0
    signals[short_cond] = -1.0
    return signals

def generate_single_ema_price_signals(close: np.ndarray, single_ema: np.ndarray) -> np.ndarray:
    """
    Single EMA Price Crossover.
    Close > EMA -> +1 (Long), Close < EMA -> -1 (Short)
    """
    return np.where(close > single_ema, 1.0, -1.0)
