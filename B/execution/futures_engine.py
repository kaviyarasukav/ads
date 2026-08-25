"""
Comprehensive High-Performance Perpetual Futures Execution & Analytical Engine (Folder B)
=========================================================================================
Vectorized, zero-copy, highly optimized quantitative engine (40+ metrics):
1. Returns & PnL: Initial Capital, Final Equity, Net PnL, Total Return %, CAGR %, Alpha vs ETH
2. Risk & Drawdown: Max Drawdown % & $, Avg Drawdown %, Max Drawdown Duration (Bars & Hours),
   Peak Time, Trough Time, Recovery Factor
3. Risk-Adjusted: Sharpe Ratio, Sortino Ratio, Calmar Ratio, Omega Ratio, Composite Score (0-100)
4. Trade Quality & Distribution: Total Trades, Win Rate %, Loss Rate %, Profit Factor, Expectancy % & $,
   Avg Win %, Avg Loss %, Payoff Ratio (Win/Loss), Max Consecutive Wins, Max Consecutive Losses,
   Best Trade %, Worst Trade %
5. Directional Breakdown: Long Trades Count, Long Win Rate %, Long Net PnL,
   Short Trades Count, Short Win Rate %, Short Net PnL
6. Operational & Exposure: Market Exposure %, Total Fees $, Fee Drag %, Avg Hold Hours & Bars
7. Monthly Breakdown: Positive Months (x/6), Negative Months, Best Month, Worst Month,
   M_Jan, M_Feb, M_Mar, M_Apr, M_May, M_Jun
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Any

FEE_RT = 0.001          # 0.10% round-trip fee
INITIAL_CAPITAL = 10_000.0
ETH_H1_BENCHMARK = -47.10  # H1 2026 ETH spot move

TIMEFRAME_ANNUAL_BARS = {"5m": 105120.0, "30m": 17520.0, "1h": 8760.0}
TIMEFRAME_BAR_HOURS = {"5m": 5.0 / 60.0, "30m": 0.5, "1h": 1.0}

_MONTH_CACHE: Dict[int, List[Tuple[str, int]]] = {}

def _get_month_info(timestamps: np.ndarray) -> List[Tuple[str, int]]:
    key = id(timestamps)
    if key not in _MONTH_CACHE:
        dt = pd.to_datetime(timestamps)
        months = dt.month.values
        month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]
        ends = []
        for m_idx, m_name in enumerate(month_names, 1):
            matching = np.where(months == m_idx)[0]
            if len(matching) > 0:
                ends.append((m_name, int(matching[-1])))
            else:
                ends.append((m_name, -1))
        _MONTH_CACHE[key] = ends
    return _MONTH_CACHE[key]

def _calculate_sortino(bar_returns: np.ndarray, annualization: float) -> float:
    if len(bar_returns) < 2:
        return 0.0
    downside = bar_returns[bar_returns < 0]
    if len(downside) == 0:
        return float(np.mean(bar_returns) / 1e-9 * np.sqrt(annualization))
    ds = float(np.std(downside))
    return 0.0 if ds < 1e-9 else float(np.mean(bar_returns) / ds * np.sqrt(annualization))

def _calculate_omega(bar_returns: np.ndarray) -> float:
    pos = bar_returns[bar_returns > 0]
    neg = np.abs(bar_returns[bar_returns < 0])
    sum_neg = np.sum(neg)
    return float(np.sum(pos) / sum_neg) if sum_neg > 1e-9 else 99.0

def simulate_futures_trading_full(
    open_prices: np.ndarray,
    close_prices: np.ndarray,
    timestamps: np.ndarray,
    signals: np.ndarray,
    timeframe: str = "5m",
    strategy_name: str = "EMA_Futures_Strategy",
    fast_p: int = 20,
    slow_p: int = 200,
    method: str = "Method 1: SAR",
    initial_capital: float = INITIAL_CAPITAL,
    fee_rt: float = FEE_RT,
    warmup_bars: int = 50,
    record_details: bool = True
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], np.ndarray]:
    """
    Ultra-optimized multi-feature quantitative simulation on 5m, 30m, or 1h candles.
    """
    n = len(close_prices)
    tf_key = timeframe.lower()
    annual_bars = TIMEFRAME_ANNUAL_BARS.get(tf_key, 105120.0)
    bar_hour_mult = TIMEFRAME_BAR_HOURS.get(tf_key, 5.0 / 60.0)

    # 1-bar execution delay: signal evaluated on bar t-1 -> filled on bar t open
    target_pos_arr = np.zeros(n, dtype=np.float64)
    target_pos_arr[1:] = signals[:-1]
    
    if 0 < warmup_bars < n:
        target_pos_arr[:warmup_bars] = 0.0

    cash = initial_capital
    portfolio_equity = initial_capital
    units = 0.0
    cost_basis = 0.0
    current_direction = 0.0
    
    entry_bar = 0
    entry_price = 0.0
    bars_in_market = 0

    raw_trades: List[Dict[str, Any]] = []
    eq_arr = np.empty(n, dtype=np.float64)
    eq_arr[0] = initial_capital
    
    peak_equity = initial_capital
    peak_idx = 0
    mdd_trough_idx = 0
    max_drawdown_pct = 0.0
    max_drawdown_usd = 0.0

    fee_per_side = fee_rt / 2.0  # 0.05% per order

    for i in range(1, n):
        target_pos = target_pos_arr[i]
        curr_open = open_prices[i]
        curr_close = close_prices[i]

        # 1. Close Position / Signal Direction Flip
        if target_pos != current_direction and current_direction != 0.0:
            if current_direction == 1.0: # Long
                exit_price = curr_open * (1.0 - fee_per_side)
                proceeds = units * exit_price
                realized_pnl_usd = proceeds - cost_basis
            else: # Short
                exit_price = curr_open * (1.0 + fee_per_side)
                realized_pnl_usd = cost_basis - (units * exit_price)
                proceeds = cost_basis + realized_pnl_usd

            cash += proceeds
            portfolio_equity = cash
            realized_pnl_pct = (realized_pnl_usd / cost_basis) * 100.0 if cost_basis > 0 else 0.0
            hold_bars = i - entry_bar

            raw_trades.append({
                "trade_id": len(raw_trades) + 1,
                "strategy": strategy_name,
                "timeframe": timeframe,
                "fast_ema": fast_p,
                "slow_ema": slow_p,
                "direction": "LONG" if current_direction == 1.0 else "SHORT",
                "entry_bar": entry_bar,
                "exit_bar": i,
                "entry_price": round(float(entry_price), 2),
                "exit_price": round(float(exit_price), 2),
                "duration_bars": hold_bars,
                "duration_hours": round(hold_bars * bar_hour_mult, 2),
                "invested_usd": round(float(cost_basis), 2),
                "realized_pnl_usd": round(float(realized_pnl_usd), 2),
                "realized_pnl_pct": round(float(realized_pnl_pct), 2),
                "portfolio_after": round(float(portfolio_equity), 2),
                "exit_reason": "Signal Direction Flip"
            })

            units = 0.0
            cost_basis = 0.0
            current_direction = 0.0

        # 2. Open Position
        if target_pos != 0.0 and current_direction == 0.0 and cash > 10.0:
            current_direction = target_pos
            entry_bar = i
            
            if current_direction == 1.0:
                entry_price = curr_open * (1.0 + fee_per_side)
            else:
                entry_price = curr_open * (1.0 - fee_per_side)

            allocated_usd = cash
            units = allocated_usd / entry_price
            cost_basis = allocated_usd
            cash -= allocated_usd

        # 3. Mark-to-Market Valuation
        if current_direction != 0.0:
            bars_in_market += 1
            if current_direction == 1.0:
                pos_val = units * curr_close * (1.0 - fee_per_side)
            else:
                pos_val = cost_basis + (cost_basis - units * curr_close * (1.0 + fee_per_side))
            current_portfolio_equity = cash + pos_val
        else:
            current_portfolio_equity = cash

        if current_portfolio_equity > peak_equity:
            peak_equity = current_portfolio_equity
            peak_idx = i

        dd_usd = peak_equity - current_portfolio_equity
        dd_pct = (dd_usd / peak_equity) * 100.0 if peak_equity > 0 else 0.0

        if dd_pct > max_drawdown_pct:
            max_drawdown_pct = dd_pct
            max_drawdown_usd = dd_usd
            mdd_trough_idx = i

        eq_arr[i] = current_portfolio_equity

    # 4. Final Settlement on Last Candle
    if current_direction != 0.0:
        if current_direction == 1.0:
            exit_price = close_prices[-1] * (1.0 - fee_per_side)
            proceeds = units * exit_price
            realized_pnl_usd = proceeds - cost_basis
        else:
            exit_price = close_prices[-1] * (1.0 + fee_per_side)
            realized_pnl_usd = cost_basis - (units * exit_price)
            proceeds = cost_basis + realized_pnl_usd

        cash += proceeds
        portfolio_equity = cash
        realized_pnl_pct = (realized_pnl_usd / cost_basis) * 100.0 if cost_basis > 0 else 0.0
        hold_bars = n - 1 - entry_bar

        raw_trades.append({
            "trade_id": len(raw_trades) + 1,
            "strategy": strategy_name,
            "timeframe": timeframe,
            "fast_ema": fast_p,
            "slow_ema": slow_p,
            "direction": "LONG" if current_direction == 1.0 else "SHORT",
            "entry_bar": entry_bar,
            "exit_bar": n - 1,
            "entry_price": round(float(entry_price), 2),
            "exit_price": round(float(exit_price), 2),
            "duration_bars": hold_bars,
            "duration_hours": round(hold_bars * bar_hour_mult, 2),
            "invested_usd": round(float(cost_basis), 2),
            "realized_pnl_usd": round(float(realized_pnl_usd), 2),
            "realized_pnl_pct": round(float(realized_pnl_pct), 2),
            "portfolio_after": round(float(portfolio_equity), 2),
            "exit_reason": "End of 6-Month Period Settlement"
        })
        eq_arr[-1] = portfolio_equity

    # 5. Format trade details (only if record_details is True)
    closed_trades: List[Dict[str, Any]] = []
    if record_details and len(raw_trades) > 0:
        for t in raw_trades:
            e_bar = t["entry_bar"]
            x_bar = t["exit_bar"]
            closed_trades.append({
                "trade_id": t["trade_id"],
                "strategy": t["strategy"],
                "timeframe": t["timeframe"],
                "fast_ema": t["fast_ema"],
                "slow_ema": t["slow_ema"],
                "direction": t["direction"],
                "entry_time": str(timestamps[e_bar])[:16],
                "entry_price": t["entry_price"],
                "exit_time": str(timestamps[x_bar])[:16],
                "exit_price": t["exit_price"],
                "duration_bars": t["duration_bars"],
                "duration_hours": t["duration_hours"],
                "invested_usd": t["invested_usd"],
                "realized_pnl_usd": t["realized_pnl_usd"],
                "realized_pnl_pct": t["realized_pnl_pct"],
                "portfolio_after": t["portfolio_after"],
                "exit_reason": t["exit_reason"]
            })

    # 6. Complete 40-Feature Metrics Suite Computation
    total_return_pct = ((portfolio_equity - initial_capital) / initial_capital) * 100.0
    net_pnl_usd = portfolio_equity - initial_capital
    alpha_vs_eth = total_return_pct - ETH_H1_BENCHMARK

    bar_returns = np.diff(eq_arr) / np.where(eq_arr[:-1] == 0, 1e-9, eq_arr[:-1])
    
    ann_factor = np.sqrt(annual_bars)
    sharpe = float(np.mean(bar_returns) / (np.std(bar_returns) + 1e-9) * ann_factor) if len(bar_returns) > 0 else 0.0
    sortino = _calculate_sortino(bar_returns, annualization=annual_bars)
    omega = _calculate_omega(bar_returns)

    dataset_years = (n - 1) / annual_bars
    cagr_pct = ((portfolio_equity / initial_capital) ** (1.0 / max(dataset_years, 0.001)) - 1.0) * 100.0
    calmar = cagr_pct / max_drawdown_pct if max_drawdown_pct > 1e-9 else 0.0
    recovery_factor = (net_pnl_usd / max_drawdown_usd) if max_drawdown_usd > 1e-9 else 99.0

    # Drawdown Series & Underwater Time
    peaks = np.maximum.accumulate(eq_arr)
    drawdowns_series = (peaks - eq_arr) / np.where(peaks == 0, 1e-9, peaks) * 100.0
    avg_drawdown_pct = float(np.mean(drawdowns_series))
    
    # Longest drawdown duration
    underwater = drawdowns_series > 0.01
    dd_durations = []
    curr_dd_len = 0
    for is_under in underwater:
        if is_under:
            curr_dd_len += 1
        else:
            if curr_dd_len > 0:
                dd_durations.append(curr_dd_len)
                curr_dd_len = 0
    if curr_dd_len > 0:
        dd_durations.append(curr_dd_len)

    max_dd_duration_bars = max(dd_durations) if dd_durations else 0
    max_dd_duration_hours = max_dd_duration_bars * bar_hour_mult

    # 7. Trade-Level Analytics
    if len(raw_trades) > 0:
        pnls_usd = np.array([t["realized_pnl_usd"] for t in raw_trades])
        pnls_pct = np.array([t["realized_pnl_pct"] for t in raw_trades])
        hold_hours_arr = np.array([t["duration_hours"] for t in raw_trades])
        directions = [t["direction"] for t in raw_trades]

        total_trades = len(raw_trades)
        wins = pnls_usd[pnls_usd > 0]
        losses = pnls_usd[pnls_usd <= 0]
        win_count = len(wins)
        loss_count = len(losses)
        win_rate_pct = (win_count / total_trades) * 100.0
        loss_rate_pct = 100.0 - win_rate_pct

        gross_profit = float(np.sum(wins)) if win_count > 0 else 0.0
        gross_loss = float(abs(np.sum(losses))) if loss_count > 0 else 0.0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 999.0

        expectancy_pct = float(np.mean(pnls_pct))
        expectancy_usd = float(np.mean(pnls_usd))
        avg_win_p = float(np.mean(pnls_pct[pnls_pct > 0])) if win_count > 0 else 0.0
        avg_loss_p = float(abs(np.mean(pnls_pct[pnls_pct <= 0]))) if loss_count > 0 else 0.0
        payoff_ratio = (avg_win_p / avg_loss_p) if avg_loss_p > 0 else 99.0

        avg_hold_hours = float(np.mean(hold_hours_arr))
        best_trade_pct = float(np.max(pnls_pct))
        worst_trade_pct = float(np.min(pnls_pct))

        # Long vs Short Breakdown
        long_indices = [idx for idx, d in enumerate(directions) if d == "LONG"]
        short_indices = [idx for idx, d in enumerate(directions) if d == "SHORT"]

        long_trades_count = len(long_indices)
        if long_trades_count > 0:
            long_pnls = pnls_usd[long_indices]
            long_win_rate = (len(long_pnls[long_pnls > 0]) / long_trades_count) * 100.0
            long_net_pnl_usd = float(np.sum(long_pnls))
        else:
            long_win_rate = 0.0
            long_net_pnl_usd = 0.0

        short_trades_count = len(short_indices)
        if short_trades_count > 0:
            short_pnls = pnls_usd[short_indices]
            short_win_rate = (len(short_pnls[short_pnls > 0]) / short_trades_count) * 100.0
            short_net_pnl_usd = float(np.sum(short_pnls))
        else:
            short_win_rate = 0.0
            short_net_pnl_usd = 0.0

        # Consecutive streaks
        cw, cl, max_cons_wins, max_cons_loss = 0, 0, 0, 0
        for pnl in pnls_usd:
            if pnl > 0:
                cw += 1; cl = 0
                if cw > max_cons_wins: max_cons_wins = cw
            else:
                cl += 1; cw = 0
                if cl > max_cons_loss: max_cons_loss = cl
    else:
        total_trades = 0
        win_rate_pct, loss_rate_pct = 0.0, 0.0
        profit_factor, payoff_ratio = 1.0, 1.0
        expectancy_pct, expectancy_usd = 0.0, 0.0
        avg_win_p, avg_loss_p = 0.0, 0.0
        avg_hold_hours = 0.0
        best_trade_pct, worst_trade_pct = 0.0, 0.0
        max_cons_wins, max_cons_loss = 0, 0
        long_trades_count, long_win_rate, long_net_pnl_usd = 0, 0.0, 0.0
        short_trades_count, short_win_rate, short_net_pnl_usd = 0, 0.0, 0.0

    exposure_pct = (bars_in_market / max(n - 1, 1)) * 100.0
    total_fees_usd = total_trades * (initial_capital * fee_rt)
    fee_drag_pct = total_trades * fee_rt * 100.0

    # 8. Fast Monthly Returns Breakdown
    month_info = _get_month_info(timestamps)
    m_returns = {}
    prev_m_eq = initial_capital
    for m_name, end_idx in month_info:
        if end_idx >= 0:
            m_end = eq_arr[end_idx]
            m_ret = ((m_end - prev_m_eq) / prev_m_eq) * 100.0
            m_returns[f"M_{m_name}"] = round(float(m_ret), 2)
            prev_m_eq = m_end
        else:
            m_returns[f"M_{m_name}"] = 0.0

    pos_months = sum(1 for v in m_returns.values() if v > 0)
    neg_months = 6 - pos_months
    
    m_sorted = sorted(m_returns.items(), key=lambda x: x[1], reverse=True)
    best_month = f"{m_sorted[0][0][2:]} ({m_sorted[0][1]:+.2f}%)" if m_sorted else "N/A"
    worst_month = f"{m_sorted[-1][0][2:]} ({m_sorted[-1][1]:+.2f}%)" if m_sorted else "N/A"

    # Composite Institutional Score (0 to 100 scale)
    sh_score = min(30.0, max(0.0, sharpe * 15.0))
    calmar_score = min(25.0, max(0.0, calmar * 8.0))
    pf_score = min(20.0, max(0.0, (profit_factor - 1.0) * 15.0))
    dd_score = min(15.0, max(0.0, (50.0 - max_drawdown_pct) * 0.3))
    pos_score = (pos_months / 6.0) * 10.0
    composite_score = round(float(sh_score + calmar_score + pf_score + dd_score + pos_score), 1)

    peak_time = str(timestamps[peak_idx])[:16]
    mdd_trough_time = str(timestamps[mdd_trough_idx])[:16]

    summary = {
        # 1. Identifiers & Sizing
        "Strategy": strategy_name,
        "Timeframe": timeframe,
        "Fast_EMA": fast_p,
        "Slow_EMA": slow_p,
        "Method": method,
        "Initial_Capital": initial_capital,
        "Final_Equity": round(float(portfolio_equity), 2),
        "Net_PnL_USD": round(float(net_pnl_usd), 2),
        "Total_Return_Pct": round(float(total_return_pct), 2),
        "CAGR_Pct": round(float(cagr_pct), 2),
        "Alpha_vs_ETH_Pct": round(float(alpha_vs_eth), 2),
        
        # 2. Risk & Volatility
        "Max_Drawdown_Pct": round(float(max_drawdown_pct), 2),
        "Max_Drawdown_USD": round(float(max_drawdown_usd), 2),
        "Avg_Drawdown_Pct": round(float(avg_drawdown_pct), 2),
        "Peak_Equity_Time": peak_time,
        "MDD_Trough_Time": mdd_trough_time,
        "Max_DD_Duration_Hours": round(float(max_dd_duration_hours), 1),
        "Recovery_Factor": round(float(min(recovery_factor, 99.0)), 2),
        "Sharpe_Ratio": round(float(sharpe), 2),
        "Sortino_Ratio": round(float(sortino), 2),
        "Calmar_Ratio": round(float(calmar), 2),
        "Omega_Ratio": round(float(min(omega, 99.0)), 2),
        "Composite_Score": composite_score,

        # 3. Trade Metrics & Distribution
        "Total_Trades": total_trades,
        "Win_Rate_Pct": round(float(win_rate_pct), 1),
        "Loss_Rate_Pct": round(float(loss_rate_pct), 1),
        "Profit_Factor": round(float(min(profit_factor, 999.0)), 2),
        "Expectancy_Pct": round(float(expectancy_pct), 2),
        "Expectancy_USD": round(float(expectancy_usd), 2),
        "Avg_Win_Pct": round(float(avg_win_p), 2),
        "Avg_Loss_Pct": round(float(avg_loss_p), 2),
        "Payoff_Ratio": round(float(min(payoff_ratio, 99.0)), 2),
        "Max_Cons_Wins": max_cons_wins,
        "Max_Cons_Losses": max_cons_loss,
        "Best_Trade_Pct": round(float(best_trade_pct), 2),
        "Worst_Trade_Pct": round(float(worst_trade_pct), 2),
        "Avg_Holding_Hours": round(float(avg_hold_hours), 1),

        # 4. Long vs Short Breakdown
        "Long_Trades_Count": long_trades_count,
        "Long_Win_Rate_Pct": round(float(long_win_rate), 1),
        "Long_Net_PnL_USD": round(float(long_net_pnl_usd), 2),
        "Short_Trades_Count": short_trades_count,
        "Short_Win_Rate_Pct": round(float(short_win_rate), 1),
        "Short_Net_PnL_USD": round(float(short_net_pnl_usd), 2),

        # 5. Friction & Exposure
        "Exposure_Pct": round(float(exposure_pct), 1),
        "Total_Fees_USD": round(float(total_fees_usd), 2),
        "Fee_Drag_Pct": round(float(fee_drag_pct), 2),

        # 6. Monthly Consistency (H1 2026)
        "Pos_Months": pos_months,
        "Neg_Months": neg_months,
        "Best_Month": best_month,
        "Worst_Month": worst_month,
        **m_returns
    }

    return summary, closed_trades, eq_arr

# Alias for backward compatibility
simulate_futures_trading = simulate_futures_trading_full
