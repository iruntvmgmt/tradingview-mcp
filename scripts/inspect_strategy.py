#!/usr/bin/env python3
"""Strategy Inspection Script — Curve Fitting vs Legitimate Edge Analysis.

Connects to TradingView Desktop via CDP, reads the active Pine Script
and Strategy Tester results, then analyzes for curve fitting red flags.

Usage:
    PYTHONPATH=. .venv/bin/python scripts/inspect_strategy.py
"""

import asyncio
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.services.cdp_connection import CDPConnection

# ── Output paths ────────────────────────────────────────────────
LOG_DIR = Path(__file__).resolve().parent.parent / "docs" / "qa"
LOG_FILE = LOG_DIR / "strategy-inspection-log.md"


# ═════════════════════════════════════════════════════════════════
# CDP JS evaluation helper
# ═════════════════════════════════════════════════════════════════

class StrategyInspector:
    def __init__(self, cdp: CDPConnection, log_file: Path):
        self._cdp = cdp
        self._log_file = log_file
        self._findings = {
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "symbol": None,
            "timeframe": None,
            "script_name": None,
            "pine_source": None,
            "pine_source_lines": 0,
            "strategy_tester_summary": {},
            "trade_list": [],
            "trade_count": 0,
            "dom_snapshot": {},
            "curve_fitting_analysis": {
                "verdict": "UNKNOWN",
                "risk_flags": [],
                "positive_indicators": [],
                "confidence": 0.0,
            },
            "issues": [],
        }

    async def run(self):
        """Run the full inspection protocol."""
        print("=" * 70)
        print("STRATEGY INSPECTION — Curve Fitting vs Legitimate Edge")
        print("=" * 70)

        await self._cdp.connect()
        print("\n✅ Connected to TradingView Desktop")

        # Step 1: Get session context
        await self._get_chart_context()

        # Step 2: Read Pine Script source
        await self._read_pine_script()

        # Step 3: Read Strategy Tester
        await self._read_strategy_tester()

        # Step 4: Analyze for curve fitting
        self._analyze_curve_fitting()

        # Step 5: Write log
        self._write_log()

        await self._cdp.disconnect()
        print("\n✅ Disconnected. Log written to:", self._log_file)

    # ── Step 1: Chart Context ────────────────────────────────────

    async def _get_chart_context(self):
        """Read symbol, timeframe, and indicator names."""
        print("\n── Step 1: Chart Context ──")

        # Symbol from the header
        js = """
        (() => {
            // Try the symbol header element
            const els = document.querySelectorAll('[data-symbol-full], [data-symbol-short], .symbol-edit');
            if (els.length) {
                return { key: 'symbol_header', value: els[0].textContent?.trim() || els[0].getAttribute('data-symbol-full') || '' };
            }
            // Try the title bar
            const titleEls = document.querySelectorAll('.title-HK6YOOhY, .chart-title, .pane-legend-title');
            for (const el of titleEls) {
                const txt = el.textContent?.trim();
                if (txt && txt.length < 30) return { key: 'title', value: txt };
            }
            // Try URL
            return { key: 'url', value: window.location.href };
        })()
        """
        r = await self._cdp.execute_js(js)
        ctx = r.get("result", {}).get("value", {})
        self._findings["symbol"] = ctx.get("value", "UNKNOWN")
        print(f"  Symbol: {self._findings['symbol']}")

        # Timeframe from the toolbar
        js2 = """
        (() => {
            // Try to find the interval button
            const btns = document.querySelectorAll('[data-interval], .value-DWZXOdoK, .item-DWZXOdoK, .interval-HK6YOOhY');
            for (const b of btns) {
                const txt = b.textContent?.trim();
                const data = b.getAttribute('data-interval');
                if (txt && txt.length < 10 && (txt.match(/^\\d/) || data)) {
                    return data || txt;
                }
            }
            // Try active interval in toolbar
            const active = document.querySelectorAll('.active-DWZXOdoK, .isActive-DWZXOdoK, [aria-pressed="true"]');
            for (const a of active) {
                const txt = a.textContent?.trim();
                if (txt && txt.length < 10 && txt.match(/^[\\dDHWM]+/)) return txt;
            }
            return null;
        })()
        """
        r2 = await self._cdp.execute_js(js2)
        tf = r2.get("result", {}).get("value", None)
        self._findings["timeframe"] = tf
        print(f"  Timeframe: {self._findings['timeframe']}")

        # Indicator list from the chart pane legend
        js3 = """
        (() => {
            const legends = document.querySelectorAll('.pane-legend-line, .pane-legend-title, .legend-KLHKbDEI, .sourcesWrapper-HK6YOOhY, .indicator-HK6YOOhY, .study-HK6YOOhY');
            const names = [];
            for (const el of legends) {
                const txt = el.textContent?.trim();
                if (txt && txt.length > 1 && txt.length < 100 && !txt.match(/^\\d+$/) && !txt.includes('UTC')) {
                    names.push(txt);
                }
            }
            // Also try to get from the indicator list at the bottom
            const bottomIndicators = document.querySelectorAll('.indicatorContainer-HK6YOOhY .title-HK6YOOhY, .pane-legend-item .title-HK6YOOhY');
            for (const el of bottomIndicators) {
                const txt = el.textContent?.trim();
                if (txt && txt.length > 1 && !names.includes(txt)) names.push(txt);
            }
            return [...new Set(names)].slice(0, 20);
        })()
        """
        r3 = await self._cdp.execute_js(js3)
        indicators = r3.get("result", {}).get("value", [])
        print(f"  Indicators on chart: {indicators}")

        self._findings["indicators_on_chart"] = indicators

    # ── Step 2: Read Pine Script ─────────────────────────────────

    async def _read_pine_script(self):
        """Read source from the Pine Editor panel."""
        print("\n── Step 2: Pine Script Source ──")

        # First, find if Pine Editor is open
        js_detect = """
        (() => {
            // Check multiple possible editor containers
            const containers = [
                '#pine-editor-dialog',
                '.pine-editor-dialog',
                '[data-role="pine-editor"]',
                '.editorContainer-HK6YOOhY',
                '.monaco-editor',
                '.code-editor',
                '.pine-editor-container',
            ];
            for (const sel of containers) {
                const el = document.querySelector(sel);
                if (el) return { container: sel, visible: el.offsetParent !== null };
            }
            return { container: null, visible: false };
        })()
        """
        r = await self._cdp.execute_js(js_detect)
        ed = r.get("result", {}).get("value", {})
        if not ed.get("container"):
            print("  ⚠️  Pine Editor not found in DOM")
            self._findings["issues"].append("Pine Editor not found in DOM — is it open?")
            return

        print(f"  Editor container: {ed['container']} (visible: {ed['visible']})")

        # Read source via Monaco editor API
        js_read = """
        (() => {
            // Try Monaco editor instances
            if (typeof monaco !== 'undefined' && monaco.editor) {
                const models = monaco.editor.getModels();
                if (models.length) {
                    const src = models[0].getValue();
                    if (src && src.length > 50) {
                        return { method: 'monaco', source: src, lines: models[0].getLineCount() };
                    }
                }
            }
            // Try view-lines
            const viewLines = document.querySelectorAll('.view-line');
            if (viewLines.length > 0) {
                return { method: 'view-lines', source: Array.from(viewLines).map(l => l.textContent).join('\\n'), lines: viewLines.length };
            }
            // Try textarea fallback
            const textarea = document.querySelector('textarea.pine-editor, textarea[aria-label="Pine Script"]');
            if (textarea && textarea.value) {
                return { method: 'textarea', source: textarea.value, lines: textarea.value.split('\\n').length };
            }
            // Try code element
            const codeEl = document.querySelector('code.pine-source, pre.pine-source');
            if (codeEl) {
                return { method: 'code-element', source: codeEl.textContent, lines: codeEl.textContent.split('\\n').length };
            }
            return { method: 'none', source: null, lines: 0 };
        })()
        """
        r2 = await self._cdp.execute_js(js_read)
        src_data = r2.get("result", {}).get("value", {})
        method = src_data.get("method", "none")
        print(f"  Read method: {method}")

        if src_data.get("source"):
            source = src_data["source"]
            self._findings["pine_source"] = source
            self._findings["pine_source_lines"] = src_data.get("lines", len(source.split("\n")))
            print(f"  Source lines: {self._findings['pine_source_lines']}")
            # Print first 20 lines as a preview
            preview = source[:1000]
            print(f"  Source preview:\n{preview[:800]}...")
        else:
            print("  ⚠️  Could not read Pine Script source")
            self._findings["issues"].append("Could not read Pine Script source via any method")

        # Try to get script name
        js_name = """
        (() => {
            const titleEl = document.querySelector('.title-HK6YOOhY span, .script-title, .pine-editor-title, [data-name]');
            if (titleEl) return titleEl.textContent?.trim() || titleEl.getAttribute('data-name');
            // Try the tab header
            const tab = document.querySelector('.tab-HK6YOOhY.active, .tab-HK6YOOhY[aria-selected="true"]');
            if (tab) return tab.textContent?.trim();
            return null;
        })()
        """
        r3 = await self._cdp.execute_js(js_name)
        name = r3.get("result", {}).get("value")
        self._findings["script_name"] = name
        print(f"  Script name: {name}")

    # ── Step 3: Strategy Tester ──────────────────────────────────

    async def _read_strategy_tester(self):
        """Read Strategy Tester panel results."""
        print("\n── Step 3: Strategy Tester ──")

        # Check if Strategy Tester tab is visible
        js_detect = """
        (() => {
            const labels = [
                '.strategy-tester',
                '.backtesting-report',
                '[data-name="strategy-tester"]',
                '.report-tab',
                '.bottom-window .tab-bar',
            ];
            for (const sel of labels) {
                const el = document.querySelector(sel);
                if (el && el.offsetParent !== null) {
                    return { container: sel, visible: true };
                }
            }
            return { container: null, visible: false };
        })()
        """
        r = await self._cdp.execute_js(js_detect)
        st = r.get("result", {}).get("value", {})
        print(f"  Strategy Tester visible: {st.get('visible')}")

        if not st.get("visible"):
            print("  ⚠️  Strategy Tester not visible — trying to click tab...")
            self._findings["issues"].append("Strategy Tester not visible — may need to open bottom panel")

        # Read summary statistics
        js_summary = """
        (() => {
            const result = {};
            // Strategy Tester summary rows — common class patterns
            const selectors = [
                '.summary-KLHKbDEI tr, .summary-KLHKbDEI .row',
                '.report-data .summaryTable tr',
                '.backtesting-content tr',
                '.strategy-report tr',
                'table.report-table tr',
            ];
            for (const sel of selectors) {
                const rows = document.querySelectorAll(sel);
                if (rows.length > 3) {
                    for (const row of rows) {
                        const cells = row.querySelectorAll('td, th');
                        if (cells.length >= 2) {
                            const key = cells[0].textContent?.trim();
                            const val = cells[1]?.textContent?.trim();
                            if (key && val && key.length < 50) {
                                result[key] = val;
                            }
                        }
                    }
                    if (Object.keys(result).length > 3) break;
                }
            }
            // Fallback: try to grab all text from the backtest panel
            if (Object.keys(result).length < 3) {
                const panels = document.querySelectorAll('.backtesting-content, .strategy-tester, .report-content, .bottom-window');
                for (const p of panels) {
                    const text = p.textContent?.trim();
                    if (text && text.length > 50) {
                        result['_raw_text'] = text.substring(0, 3000);
                    }
                }
            }
            return result;
        })()
        """
        r2 = await self._cdp.execute_js(js_summary)
        summary = r2.get("result", {}).get("value", {})
        self._findings["strategy_tester_summary"] = summary
        print(f"  Summary keys: {list(summary.keys()) if summary else 'NONE'}")

        if summary:
            for k, v in summary.items():
                if k != "_raw_text":
                    print(f"    {k}: {v}")
            if "_raw_text" in summary:
                print(f"    Raw text (first 500 chars): {summary['_raw_text'][:500]}")

        # Read trade list
        js_trades = """
        (() => {
            const tables = document.querySelectorAll('.trades-table, .list-table, table.table-KLHKbDEI, .data-table tr');
            const trades = [];
            // Try to find the trades table
            for (const table of tables) {
                const rows = table.querySelectorAll('tr');
                if (rows.length > 2) {
                    for (const row of rows) {
                        const cells = row.querySelectorAll('td');
                        if (cells.length >= 4) {
                            const trade = {};
                            const headers = ['trade_no', 'type', 'entry', 'exit', 'pnl', 'date', 'size'];
                            cells.forEach((c, i) => {
                                const txt = c.textContent?.trim();
                                if (txt && i < headers.length) trade[headers[i]] = txt;
                            });
                            if (Object.keys(trade).length >= 3) trades.push(trade);
                        }
                    }
                    if (trades.length > 0) break;
                }
            }
            return { count: trades.length, trades: trades.slice(0, 50) };
        })()
        """
        r3 = await self._cdp.execute_js(js_trades)
        trade_data = r3.get("result", {}).get("value", {})
        self._findings["trade_list"] = trade_data.get("trades", [])
        self._findings["trade_count"] = trade_data.get("count", 0)
        print(f"  Trades found: {self._findings['trade_count']}")

        if self._findings["trade_list"]:
            print(f"  First 3 trades:")
            for t in self._findings["trade_list"][:3]:
                print(f"    {t}")

    # ── Step 4: Curve Fitting Analysis ───────────────────────────

    def _analyze_curve_fitting(self):
        """Analyze the strategy for curve-fitting red flags vs legitimate edge."""
        print("\n── Step 4: Curve Fitting Analysis ──")

        flags = []
        positives = []
        source = self._findings.get("pine_source", "")
        summary = self._findings.get("strategy_tester_summary", {})
        trades = self._findings.get("trade_list", [])
        trade_count = self._findings.get("trade_count", 0)

        # ── Source code analysis ──
        if source:
            # Flag 1: Excessive parameters
            param_count = len(re.findall(r'\binput\.\w+\(', source))
            if param_count > 15:
                flags.append(f"🔴 HIGH: {param_count} input parameters — high degrees of freedom, easy to curve-fit")
            elif param_count > 8:
                flags.append(f"🟡 MEDIUM: {param_count} input parameters — moderate risk of over-optimization")
            else:
                positives.append(f"🟢 LOW: Only {param_count} input parameters — fewer degrees of freedom")

            # Flag 2: Multiple nested indicators
            indicator_count = len(re.findall(r'\b(ta\.\w+|request\.\w+)\s*\(', source))
            if indicator_count > 8:
                flags.append(f"🔴 HIGH: {indicator_count} indicator/function calls — indicator soup risk")
            elif indicator_count > 5:
                flags.append(f"🟡 MEDIUM: {indicator_count} indicator calls — moderately complex")
            else:
                positives.append(f"🟢 LOW: {indicator_count} indicator calls — reasonable complexity")

            # Flag 3: Conditional logic depth
            if_depth = max(len(re.findall(r'\bif\b', source)), 0)
            else_depth = max(len(re.findall(r'\belse\b', source)), 0)
            ternary_count = len(re.findall(r'\?\s*.*\s*:', source))
            condition_depth = if_depth + else_depth + ternary_count
            if condition_depth > 20:
                flags.append(f"🔴 HIGH: {condition_depth} conditional branches — potential path-dependency overfitting")
            elif condition_depth > 10:
                flags.append(f"🟡 MEDIUM: {condition_depth} conditional branches — moderate complexity")
            else:
                positives.append(f"🟢 LOW: {condition_depth} conditional branches — straightforward logic")

            # Flag 4: Lookahead / repaint risk
            lookahead_patterns = [
                (r'security\s*\(\s*.*?,\s*["\']D["\']', 'Higher-timeframe security() call may introduce lookahead'),
                (r'request\.security\s*\(', 'request.security() with HTF — verify repaint behavior'),
                (r'barstate\.isrealtime', 'barstate.isrealtime — confirms repaint awareness (positive)'),
                (r'barstate\.isconfirmed', 'barstate.isconfirmed — good practice, avoids repaint'),
            ]
            for pattern, msg in lookahead_patterns:
                if re.search(pattern, source, re.IGNORECASE):
                    if 'good' in msg or 'positive' in msg:
                        positives.append(f"🟢 {msg}")
                    else:
                        flags.append(f"🟡 {msg}")

            # Flag 5: Stop-loss / take-profit usage
            has_sl = bool(re.search(r'\bstop\b.*loss|sl\s*=|strategy\.exit.*loss', source, re.IGNORECASE))
            has_tp = bool(re.search(r'\btake\b.*profit|tp\s*=|strategy\.exit.*profit', source, re.IGNORECASE))
            if has_sl and has_tp:
                positives.append("🟢 Has both SL and TP — risk management present")
            elif has_sl or has_tp:
                positives.append("🟢 Has partial risk management (SL or TP)")
            else:
                flags.append("🟡 No explicit SL/TP found — uncontrolled risk")

            # Flag 6: Martingale / grid / averaging
            martingale_patterns = [
                (r'strategy\.order\s*\(.*strategy\.position_size', 'Potential position sizing logic'),
                (r'pyramid|averaging_down|grid', 'Potential martingale/grid strategy'),
            ]
            for pattern, msg in martingale_patterns:
                if re.search(pattern, source, re.IGNORECASE):
                    flags.append(f"🔴 {msg} — high curve-fit risk profile")

            # Flag 7: Source length
            lines = self._findings.get("pine_source_lines", 0)
            if lines > 500:
                flags.append(f"🟡 {lines} lines of code — very complex, hard to validate out-of-sample")
            elif lines > 200:
                pass  # moderate
            else:
                positives.append(f"🟢 Only {lines} lines — reasonably concise")

            # Flag 8: Date filtering
            date_filter = bool(re.search(r'time\s*>=\s*timestamp|time\s*<=\s*timestamp|from\s*=\s*timestamp', source))
            in_sample = bool(re.search(r'In\s*Sample|Training|from_year|to_year', source, re.IGNORECASE))
            if date_filter and in_sample:
                positives.append("🟢 Has explicit in-sample/out-of-sample date filtering — good practice")
            elif date_filter:
                positives.append("🟢 Has date filtering (possible train/test split)")
            else:
                flags.append("🟡 No date filtering — strategy tested on entire dataset, no OOS validation visible")

        # ── Strategy Tester analysis ──
        if summary:
            raw_text = summary.get("_raw_text", "")
            all_text = " ".join(f"{k}: {v}" for k, v in summary.items() if k != "_raw_text") + " " + raw_text

            # Try to extract win rate
            win_rate_match = re.search(r'(?:Win\s*Rate|Percent\s*Profitable|%?\s*Profitable)[:\s]*([\d.]+)\s*%?', all_text, re.IGNORECASE)
            if win_rate_match:
                wr = float(win_rate_match.group(1))
                if wr > 80:
                    flags.append(f"🔴 Win rate {wr}% — suspiciously high, likely overfit")
                elif wr > 65:
                    flags.append(f"🟡 Win rate {wr}% — above average; verify out-of-sample")
                elif wr > 40:
                    positives.append(f"🟢 Win rate {wr}% — realistic range")
                else:
                    flags.append(f"🔴 Win rate {wr}% — very low; may rely on large winners")

            # Try to extract profit factor
            pf_match = re.search(r'(?:Profit\s*Factor)[:\s]*([\d.]+)', all_text, re.IGNORECASE)
            if pf_match:
                pf = float(pf_match.group(1))
                if pf > 5:
                    flags.append(f"🔴 Profit Factor {pf} — extraordinarily high, strong overfit signal")
                elif pf > 3:
                    flags.append(f"🟡 Profit Factor {pf} — very high, verify robustness")
                elif pf > 1.3:
                    positives.append(f"🟢 Profit Factor {pf} — reasonable")
                else:
                    flags.append(f"🟡 Profit Factor {pf} — marginal edge")

            # Try to extract Sharpe / Sortino
            sharpe_match = re.search(r'(?:Sharpe|Sortino)\s*(?:Ratio)?[:\s]*([\d.-]+)', all_text, re.IGNORECASE)
            if sharpe_match:
                sharpe = float(sharpe_match.group(1))
                if sharpe > 3:
                    flags.append(f"🔴 Sharpe {sharpe} — unrealistically high (market avg ~0.5-1.5)")
                elif sharpe > 1.5:
                    flags.append(f"🟡 Sharpe {sharpe} — above average, needs OOS verification")
                else:
                    positives.append(f"🟢 Sharpe {sharpe} — realistic")

            # Number of trades
            if trade_count > 0:
                if trade_count < 30:
                    flags.append(f"🔴 Only {trade_count} trades — insufficient sample size, statistically meaningless")
                elif trade_count < 100:
                    flags.append(f"🟡 {trade_count} trades — small sample, be cautious")
                else:
                    positives.append(f"🟢 {trade_count} trades — adequate sample size")

        # ── Determine verdict ──
        red_count = sum(1 for f in flags if f.startswith("🔴"))
        yellow_count = sum(1 for f in flags if f.startswith("🟡"))
        green_count = len(positives)

        if red_count >= 3:
            verdict = "LIKELY CURVE-FITTED"
            confidence = min(90, red_count * 25)
        elif red_count >= 1:
            verdict = "SUSPICIOUS — NEEDS OOS VALIDATION"
            confidence = 60
        elif yellow_count >= 3:
            verdict = "MODERATE CONCERN — VERIFY ROBUSTNESS"
            confidence = 50
        elif yellow_count >= 1:
            verdict = "POTENTIALLY LEGITIMATE — FURTHER TESTING ADVISED"
            confidence = 35
        else:
            verdict = "LIKELY LEGITIMATE EDGE"
            confidence = 20

        analysis = {
            "verdict": verdict,
            "risk_flags": flags,
            "positive_indicators": positives,
            "confidence": confidence,
            "red_count": red_count,
            "yellow_count": yellow_count,
            "green_count": green_count,
        }
        self._findings["curve_fitting_analysis"] = analysis

        print(f"\n  VERDICT: {verdict} (confidence: {confidence}%)")
        print(f"  Red flags: {red_count}, Yellow: {yellow_count}, Green: {green_count}")
        print("\n  Risk Flags:")
        for f in flags:
            print(f"    {f}")
        print("\n  Positive Indicators:")
        for p in positives:
            print(f"    {p}")

    # ── Step 5: Write Log ────────────────────────────────────────

    def _write_log(self):
        """Write findings to a markdown log file."""
        f = self._findings
        a = f["curve_fitting_analysis"]
        summary = f.get("strategy_tester_summary", {})

        md = f"""# Strategy Inspection Log

**Generated:** {f['timestamp']}
**Symbol:** {f.get('symbol', 'UNKNOWN')}
**Timeframe:** {f.get('timeframe', 'UNKNOWN')}
**Script:** {f.get('script_name', 'UNKNOWN')}

---

## ⚖️ Curve Fitting Verdict

| Metric | Value |
|--------|-------|
| **Verdict** | **{a['verdict']}** |
| Confidence | {a['confidence']}% |
| 🔴 Red Flags | {a['red_count']} |
| 🟡 Yellow Warnings | {a['yellow_count']} |
| 🟢 Positive Indicators | {a['green_count']} |

---

## 🔴 Risk Flags

"""
        for flag in a["risk_flags"]:
            md += f"- {flag}\n"

        md += "\n## 🟢 Positive Indicators\n\n"
        for pos in a["positive_indicators"]:
            md += f"- {pos}\n"

        md += f"""
---

## 📊 Strategy Tester Summary

"""
        if summary:
            for k, v in summary.items():
                if k != "_raw_text":
                    md += f"| **{k}** | {v} |\n"
            if "_raw_text" in summary:
                md += f"\n<details>\n<summary>Raw Panel Text</summary>\n\n```\n{summary['_raw_text'][:2000]}\n```\n</details>\n"
        else:
            md += "_No Strategy Tester data captured._\n"

        md += f"""
---

## 📝 Pine Script Source

**Lines:** {f.get('pine_source_lines', 0)}
**Trade Count:** {f.get('trade_count', 0)}

<details>
<summary>Click to expand source (first 200 lines)</summary>

```pine
{f.get('pine_source', 'N/A')[:5000]}
```
</details>

---

## 🔧 Issues Encountered

"""
        if f["issues"]:
            for issue in f["issues"]:
                md += f"- ⚠️ {issue}\n"
        else:
            md += "_No issues encountered._\n"

        md += f"""
---

## 📋 Analysis Methodology

1. **Source code analysis**: Parameter count, indicator complexity, conditional depth, lookahead/repaint patterns, risk management
2. **Strategy Tester metrics**: Win rate, profit factor, Sharpe ratio, trade count
3. **Red flags for curve fitting**:
   - >15 input parameters (high degrees of freedom)
   - >8 indicators (indicator soup)
   - Win rate >80% or profit factor >5
   - <30 trades (statistically insignificant)
   - No date filtering (no OOS validation)
   - Martingale/grid patterns

---

*Generated by Strategy Inspector v1.0 — QA Mode*
"""

        LOG_DIR.mkdir(parents=True, exist_ok=True)
        self._log_file.write_text(md)
        print(f"\n✅ Log written to {self._log_file}")


# ═════════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════════

async def main():
    cdp = CDPConnection(debug_port=8315)
    inspector = StrategyInspector(cdp, LOG_FILE)
    await inspector.run()


if __name__ == "__main__":
    asyncio.run(main())
