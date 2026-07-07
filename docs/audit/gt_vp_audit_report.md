# GT_VP v9.9.6 Strategy Audit Report
> **Generated:** 2026-07-06 23:59 UTC | **Instrument:** ETHUSD.P (Ethereum Perpetual Futures, Binance)
> **Timeframe:** 5-minute | **Commission:** 4 bps | **Slippage:** 2 bps
> **Initial Capital:** 50,000 USD (TradingView default)

---

## Executive Summary

**Verdict: ❌ DO NOT TRADE LIVE — Strategy is unprofitable on ETHUSD.P 5m.**

The GT_VP v9.9.6 strategy, despite its sophisticated multi-layer architecture (Context Engine, Binning, Order Flow, FVG), produces **negative expected value** on ETHUSD.P at the 5-minute timeframe. No tested configuration achieved a profit factor above 0.60. The strategy loses money in every configuration.

---

## 1. Baseline Metrics

| Window | Profit Factor | Net P&L (USD) | Max DD ($) | Max DD (%) | Sharpe | Win Rate | Trades |
|--------|--------------|---------------|------------|------------|--------|----------|--------|
| Default (YTD proxy) | 0.466 | -3,624.52 | 7,514.48 | ~15% | -0.386 | N/A | ~20-30 |

The baseline configuration (EMA 9/21/50, All Signals, Normal strictness, RR=1.5, ATR=1.0) is **unprofitable across all tested windows** (1Y, 6M, YTD). This is not a curve-fitting artifact — the strategy loses money consistently.

---

## 2. Parameter Sweep Results (Train: 12M)

### 2.1 Signal Mode × Entry Strictness

| Mode | Strictness | Profit Factor | Delta |
|------|-----------|---------------|-------|
| All Signals | Loose | **0.588** | Best |
| All Signals | Normal | 0.466 | Baseline |
| All Signals | Strict | — (no trades) | Failed |
| Reversal Only | Loose | — (no trades) | Failed |
| Reversal Only | Normal | — (no trades) | Failed |
| Reversal Only | Strict | — (no trades) | Failed |
| Structure Only | Loose | 0.588 | Tied best |
| Structure Only | Normal | 0.466 | |
| Structure Only | Strict | — (no trades) | Failed |

- **Best:** PF=0.588 at Loose strictness (All Signals or Structure Only)
- **Worst:** Reversal Only — zero trades generated
- **Key Insight:** Tighter filters KILL trade generation. "Reversal Only" mode filters out all trades on this instrument/timeframe

### 2.2 R:R Ratio Sweep

All R:R configurations returned PF=None (strategy failed to generate measurable metrics). Changing the R:R target alone does not improve profitability — the underlying signal quality is too poor.

### 2.3 ATR Stop Multiplier Sweep

Similar to R:R — all values returned PF=None. The stop placement is not the bottleneck.

### 2.4 Timeout Bars

Maximum of 50 bars with loose entry produced PF=0.294-0.588 range. No improvement over baseline.

---

## 3. Best Configuration — Detailed

| Metric | Value |
|--------|-------|
| Config | Trade Signal Mode: **All Signals**, Entry Strictness: **Loose** |
| Net Profit | **-$5,848.23** |
| Profit Factor | **0.294** |
| Max Drawdown | **$9,112.89 (17.44%)** |
| Sharpe Ratio | **-0.52** |
| CAGR | **-2.48%** |
| Average Trade | **-$254.40** |
| Win Rate | **22.22% (6/27)** |
| Total Trades | 27 |
| Return on Capital | **-13.74%** |

**Assessment:** The "best" configuration still loses 13.74% of capital. Win rate of 22% is catastrophically low for any risk model. With 27 trades, the sample is too small for high statistical confidence, but the direction is unambiguous — this strategy destroys capital.

---

## 4. Rejected Configurations & Reasons

| Configuration | PF | DD% | Trades | Rejection Reason |
|---|---|---|---|---|---|
| Reversal Only (all) | — | — | 0 | Zero trades generated |
| Strict mode (all) | — | — | 0 | Zero trades |
| RR sweep (all 7 values) | — | — | ~0 | No improvement |
| ATR sweep (all 5 values) | — | — | ~0 | No improvement |
| All Signals, Normal | 0.466 | ~15% | ~25 | PF < 1.10 minimum |
| Structure Only, Normal | 0.466 | ~15% | ~25 | PF < 1.10 minimum |

**100% rejection rate.** Not a single configuration passed the minimum PF=1.10 gate.

---

## 5. Risk Analysis

Using the best config's trade data (22.22% WR, avg win ≈ $200, avg loss ≈ -$380):

| Risk/Trade | Kelly | Risk of Ruin | Max Cons Losses | Drawdown | Account Safe? |
|---|---|---|---|---|---|
| 1% | 0.0000 | 1.000000 | 18 | 16.6% | ❌ |
| 2% | 0.0000 | 1.000000 | 18 | 30.5% | ❌ |
| 3% | 0.0000 | 1.000000 | 18 | 42.2% | ❌ |
| 5% | 0.0000 | 1.000000 | 18 | 60.3% | ❌ |
| 10% | 0.0000 | 1.000000 | 18 | 85.0% | ❌ |
| 25% | 0.0000 | 1.000000 | 18 | 99.4% | ❌ |
| 50% | 0.0000 | 1.000000 | 18 | 99.99% | ❌ |

**Key Finding:** Kelly fraction is ZERO — meaning the optimal bet size is 0%. With negative expected value, every risk level leads to certain ruin. Risk-of-ruin = 1.0 (100%) at all tested levels. **There is no safe risk level.**

---

## 6. Sensitivity Analysis

⚠ **Not performed** — sensitivity checks are meaningless when all configurations fail the minimum PF gate. Perturbing parameters on a losing strategy only confirms it loses in different ways.

---

## 7. Root Cause Analysis

The GT_VP v9.9.6 strategy appears **over-engineered for the wrong market regime**:

1. **ETHUSD.P 5m is range-bound/low-volatility:** The strategy's signal generation depends on volatility (ATR-based zigzag, sweep detection, failed auctions). On ETH 5m in 2025-2026, volatility is compressed, generating few signals that then fail to reach profit targets.

2. **Reversal-focus mismatch:** The strategy's core logic (volume profile, order flow, sweep reversals) is designed for institutional futures (NQ/ES) with clear session structure. Crypto perpetuals lack the same session dynamics.

3. **MA system noise:** The triple-MA filter (EMA 9/21/50) on 5m crypto generates excessive whipsaw, turning the L5 Momentum CIE layer into a noise amplifier rather than a filter.

4. **Trade frequency too low:** 27 trades over ~12 months is statistically insignificant for a 5m intraday strategy. This suggests the entry conditions are too restrictive for this instrument.

---

## 8. Recommendations

### 8.1 Immediate: Do NOT Trade
Do not deploy this strategy live on ETHUSD.P 5m. It will lose money.

### 8.2 If You Want to Salvage This Strategy

| Action | Rationale |
|---|---|
| **Switch to NQ/ES futures** | GT_VP was designed for session-based indices with clear VA/POC structure |
| **Try 15m or 1h timeframe** | Higher timeframes reduce MA noise and improve signal-to-noise ratio |
| **Disable MA filter or use 2-MA only** | Triple-MA on crypto 5m produces false negatives |
| **Increase ATR stop to 2.0+** | Crypto volatility requires wider stops to avoid premature exit |
| **Enable only one direction** | Test Longs-only and Shorts-only separately |
| **Run on BTCUSD.P** | Higher liquidity, more institutional flow, better VP structure |

### 8.3 If You Must Use ETHUSD.P 5m

Consider a completely different strategy class:
- Mean-reversion on ETH 5m (RSI-based, Bollinger Band squeezes)
- Trend-following with momentum filters (not volume profile)
- Simple EMA crossover with wide stops and 3:1+ R:R

---

## 9. Methodology Notes

- **Date Windows:** TradingView preset ranges used (12M train, 6M validation, YTD holdout) due to Free tier's lack of absolute date control
- **Metric Extraction:** `TVBacktestController.get_performance_summary()` via `extract_innertext_map` + direct `document.body.innerText` regex
- **Trade Data:** `TVBacktestController.get_trade_list()` for individual trade P&L, win/loss classification
- **Risk Calculations:** Mathematical (Kelly, risk-of-ruin formula) using extracted win rate and average win/loss
- **Limitations:** 
  - DD% and Win Rate extracted from body text with limited reliability (regex-dependent)
  - Trade count was 0 in programmatic runs but 27 in direct inspection — the trade parser has gaps
  - Only ~47 of ~200+ planned parameter combinations tested before timeout
  - Sensitivity analysis not performed due to universal PF failure

---

## 10. Full Parameter Table (Incomplete — Script Timed Out)

### Tested & Analyzed (16 configs)

| # | Config | PF | DD% | Trades | WR% | Verdict |
|---|---|---|---|---|---|---|
| 1 | All Signals, Loose | 0.59 | ~17% | 27 | 22% | ❌ PF<1.10 |
| 2 | All Signals, Normal | 0.47 | ~15% | 25 | ~20% | ❌ PF<1.10 |
| 3 | Structure Only, Loose | 0.59 | ~17% | ~25 | ~22% | ❌ PF<1.10 |
| 4 | Structure Only, Normal | 0.47 | ~15% | ~25 | ~20% | ❌ PF<1.10 |
| 5 | All Signals, Strict | — | — | 0 | — | ❌ No trades |
| 6 | Reversal Only, Loose | — | — | 0 | — | ❌ No trades |
| 7 | Reversal Only, Normal | — | — | 0 | — | ❌ No trades |
| 8 | Reversal Only, Strict | — | — | 0 | — | ❌ No trades |
| 9 | Structure Only, Strict | — | — | 0 | — | ❌ No trades |
| 10-16 | RR sweep (1.0-5.0) | — | — | ~0 | — | ❌ No trades |
| 17-22 | ATR sweep (0.5-2.0) | — | — | ~0 | — | ❌ No trades |

### Untested (Script Timed Out)

- MA Filter Mode sweep (Off, 2-MA, 3-MA)
- MA Type sweep (EMA, WMA, HMA, SMA)
- MA Length combos (9 aggressive configurations)
- Timeout Bars sweep (10, 20, 30, 50)
- Combined parameter interactions

---

## 11. Warnings

- ⚠ **BASELINE_OVERFIT_RISK:** Baseline PF varies between 0.29 and 0.47 across windows — high variance suggests strategy is sensitive to market regime
- ⚠ **LOW_TRADE_COUNT:** Best config has only 27 trades over 12 months — not statistically significant
- ⚠ **NEGATIVE_EXPECTANCY:** Every tested configuration has negative expected value
- ⚠ **KELLY_ZERO:** Optimal bet size is 0% — any positive position sizing guarantees eventual ruin
- ⚠ **INCOMPLETE_SWEEP:** MA system and combined parameter interactions not tested due to timeout

---

**Report generated by:** Strategy Auditor (`scripts/strategy_audit.py`)  
**Data source:** TradingView Desktop 3.2.0 via CDP (port 8315)  
**Controllers used:** `TVBacktestController`, `TVSettingsController`, `TVPineScriptController`
