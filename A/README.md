# ETH 2026 Quantitative EMA & Pyramiding Systematic Trading Intelligence

A high-performance algorithmic backtesting engine, multi-factor quantitative optimizer, and interactive HTML5/Canvas visualization terminal evaluating **68,202 parameter permutations** across 5,601 1-hour ETH/USDT bars in 2026.

---

## 🌟 Key Architecture & Capabilities

1. **Deterministic Vectorized Simulation Engine (`unified_trade_engine.py`)**:
   - Zero-lookahead trade execution on bar $t+1$ open.
   - Compounding portfolio equity continuity with $0.10\%$ fee friction.
   - Dynamic pyramiding series reinvestment with exact blended cost-basis tracking ($\sum \text{Cash} / \sum \text{Units}$).
   - Complete Stop Loss, Take Profit, Trailing SL, and Trailing TP simulation across conservative vs immediate re-entry modes.

2. **Interactive HTML5 Quantitative Terminal (`index.html`, `app.js`, `index.css`)**:
   - **Step 1: Macro Parameter Universe & Heatmaps**: 2D parameter heatmaps and risk-reward profiles.
   - **Step 2A: 4D Multi-Feature Interactive Studio**: Custom X, Y, Z, and Color dimensions with live Pareto Frontier.
   - **Step 2B: Feature-vs-Feature Comparative Studio**: Empirical correlation matrix and density histograms.
   - **Step 2C: Hierarchical Multi-Level Data Drill-Down Explorer**: 5-tier exploration (Yearly $\rightarrow$ Quarterly $\rightarrow$ Monthly $\rightarrow$ Trade Series $\rightarrow$ Micro-Tranches).
   - **Step 3A: Base Single-Entry Matrix**: Filter across 60,762 combinations with multi-slider bounds.
   - **Step 3B: Pyramiding Reinvestment Matrix**: Filter across 7,000 multi-factor compounding combinations.
   - **Step 3C: Risk Management Studio**: 440 Stop Loss, Take Profit, and Trailing Stops combinations.
   - **Step 4: Market % Movement vs Realized Gain % Studio**: Timeline scrubber comparing market move vs strategy gain.
   - **Step 5: Master Synthesis Report**: PnL attribution waterfall and rolling alpha streams.

3. **Master Verification Test Suite (`tests/`, `run_all_tests.py`)**:
   - 18 automated unit, integration, and blackbox tests validating mathematical accuracy, UI DOM synchronization, and boundary conditions.

---

## 🚀 Getting Started

### 1. Run Automated Test Suite
```powershell
python run_all_tests.py
```

### 2. Launch Local Dashboard Terminal
```powershell
python -m http.server 3000
```
Open [http://localhost:3000](http://localhost:3000) or [http://localhost:3000/explorer.html](http://localhost:3000/explorer.html) in any browser.

---

## 📊 Core Performance Benchmark Summary

| Strategy Configuration | Total Return (%) | Net Profit ($) | Max Drawdown (%) | Sharpe Ratio | Sortino | Calmar | Win Rate (%) |
|---|---|---|---|---|---|---|---|
| **ETH Spot Benchmark (Buy & Hold)** | **-18.68%** | -$1,868.00 | 55.0% | -0.15 | -0.18 | -0.34 | N/A |
| **Top Base EMA (209, 223) SAR** | **+102.39%** | +$10,239.00 | 23.8% | 2.17 | 2.34 | 4.30 | 43.8% |
| **Crown Champion: Pyramid SAR (207, 224 | X=10%, Y=1h)** | **+70.60%** | +$7,060.00 | **16.4%** | **2.08** | **2.45** | **4.30** | **46.7%** |
| **Base EMA (208, 224) Long Only** | **+37.02%** | +$3,702.00 | 17.0% | 1.48 | 1.62 | 2.18 | 44.4% |
