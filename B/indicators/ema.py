"""
Pure Mathematical EMA Calculator (Folder B)
===========================================
High-performance Exponential Moving Average calculation using SciPy digital IIR filter (lfilter)
with vectorized NumPy fallback.
"""

import numpy as np

try:
    from scipy.signal import lfilter as _scipy_lfilter
    _SCIPY_OK = True
except ImportError:
    _SCIPY_OK = False

def calculate_ema(close: np.ndarray, period: int) -> np.ndarray:
    """
    Computes a single EMA series over a 1D NumPy array of close prices.
    Formula: alpha = 2 / (period + 1), EMA_t = alpha * Close_t + (1 - alpha) * EMA_{t-1}
    """
    n = len(close)
    if n == 0:
        return np.array([], dtype=np.float64)
    if period <= 1:
        return close.copy().astype(np.float64)

    alpha = 2.0 / (period + 1.0)
    
    if _SCIPY_OK:
        b = [alpha]
        a = [1.0, alpha - 1.0]
        out, _ = _scipy_lfilter(b, a, close, zi=np.array([close[0]]) * (1.0 - alpha))
        out[0] = close[0]
        return out
    else:
        ema = np.empty(n, dtype=np.float64)
        ema[0] = close[0]
        for t in range(1, n):
            ema[t] = alpha * close[t] + (1.0 - alpha) * ema[t - 1]
        return ema

def build_ema_matrix(close: np.ndarray, min_p: int = 5, max_p: int = 250):
    """
    Pre-computes all EMA periods from min_p to max_p in a single 2D matrix.
    Returns: (ema_matrix, period_to_idx_dict)
    """
    n = len(close)
    num_periods = max_p - min_p + 1
    ema_matrix = np.empty((num_periods, n), dtype=np.float64)
    
    for idx, p in enumerate(range(min_p, max_p + 1)):
        ema_matrix[idx] = calculate_ema(close, p)
        
    period_to_idx = {p: i for i, p in enumerate(range(min_p, max_p + 1))}
    return ema_matrix, period_to_idx

if __name__ == "__main__":
    test_close = np.array([100.0, 102.0, 101.0, 105.0, 107.0, 106.0, 110.0])
    ema_9 = calculate_ema(test_close, 9)
    print("Test EMA-9:", np.round(ema_9, 2))
