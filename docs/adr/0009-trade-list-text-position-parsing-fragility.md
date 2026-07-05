# ADR-0009: backtest_trade_list parses flattened innerText by line position, not stable selectors — silent-corruption risk on TradingView updates

**Status:** accepted
**Date:** 2026-07-05
**Author(s):** Sage (ai-team-dev)

## Context

`DomBacktestBackend.get_trade_list()` (implemented 2026-07-05, documented in
`docs/handoff/2026-07-05-pine-errors-and-trade-list.md`) reads individual
trade records from the Strategy Tester's "List of trades" tab. The trade
data is rendered as a flat block of text in `document.body.innerText` — the
DOM has no per-field selectors, no `data-name`/`data-qa-id` attributes, no
stable CSS class names, and no `<table>`/`<tr>`/`<td>` structure for these
records.

Every other verified capability in this project parses structured data using
stable semantic selectors:

| Capability | Selector pattern |
|---|---|
| `settings_list_fields`, `settings_read`, `settings_write` | `div[data-name="indicator-properties-dialog"]`, `button[role="combobox"]`, `input[data-qa-id="…"]` |
| `pine_compile_errors_read` | `.selectable-v4HmQr2o.error-v4HmQr2o`, `.time-v4HmQr2o` |
| `indicator_apply` | `div[data-name="indicator-properties-dialog"]`, `button[title="Add to chart"]` |

The trade-list backend is the **sole exception**: it extracts fields by
consuming lines from `innerText` in a fixed positional order, assuming a
specific line layout:

```
N<direction>
<tab><tab>Exit<tab>Entry<tab>
<exit_date><tab><entry_date><tab>
<exit_price> USD <entry_price> USD <tab>
<size> <value>KUSD <tab>
<pnl> USD <tab>
<return_pct>%
```

The parser walks line-by-line, pattern-matching each expected field value
(`^(\d+)(long|short)$` for trade headers, `^[\d,]+\.\d{2}$` for prices,
`^\d+$` for sizes, `^[+\u2212-]?[\d,]+$` for PnL) and consuming surrounding
label/unit text (e.g. "USD", "KUSD", "Exit", "Entry") as noise to skip.

## Risk: silent corruption, not loud failure

A selector-based parser that encounters a DOM change will simply fail to
match — the result is empty (no trades found) or an exception. That is a
**loud failure**: the caller immediately knows something is wrong.

A text-position parser that encounters a TradingView wording or line-order
change will likely **still return a result** — the number pattern `\d+`
matching trade headers, the price pattern `[\d,]+\.\d{2}`, and the direction
words `long|short` are unlikely to disappear entirely from the UI. If lines
are reordered (e.g. Entry before Exit), or a new field is inserted (e.g.
"Commission" between size and PnL), or unit text changes (e.g. "USD" →
"USDT"), the parser will silently assign values to the wrong dictionary keys
while still returning a list of "valid" trade records.

**This is worse than failing loud**: nothing signals the corruption. A
downstream agent making strategy decisions based on silently-swapped
entry/exit prices or PnL values would have no indication the data is wrong.

## Decision

Accept the current implementation — it is the only known working approach
given the DOM structure. The Strategy Tester's trade list is not built with
interactive widgets or HTML tables; it is a rendered text block with no
parseable structure beyond the visual line layout.

Flag this as a **standing manual spot-check item**. The `recon` module's
`verified` flag only confirms that selectors resolve, not that a
text-position parse is still mapping fields correctly. After any
TradingView Desktop update, the spot-check procedure below must be re-run
**before** trusting new `backtest_trade_list` output, even if recon still
reports `verified: true`.

## Spot-check procedure

1. Open TradingView Desktop with the CDP debug port active
   (`ws://127.0.0.1:8315`).
2. Apply the MA Cross Strategy (any symbol, e.g. BINANCE:ETHUSD.P, 1h
   timeframe) with default parameters (Fast MA = 9, Slow MA = 21).
3. Open the Strategy Tester panel, select the "List of trades" tab.
4. Call `backtest_trade_list` and confirm it returns 11 trades.
5. Spot-check trade #1: direction = "long", entry price ≈ 29,198.75,
   exit price ≈ 29,180.00, net PnL ≈ −375.
6. Change the strategy parameter (Fast MA 9 → 7), re-run, and confirm
   the trade count and values differ from step 4 (regression test — if
   values are identical, the parser is likely swallowing real data).
7. If any field is missing, zero, or obviously wrong relative to the
   Strategy Tester UI, the parser line layout has broken and must be
   updated to match the new `innerText` structure.

## Consequences

- **What this makes easier:** Trade-pnl calculations, win-rate analysis,
  and per-trade parameter sensitivity are now available — capabilities
  that were previously impossible without manual CSV export.
- **What this makes harder:** The `backtest_trade_list` tool cannot run
  unattended across TV Desktop version upgrades. Unlike selector-based
  tools where recon's automated `verified` check is sufficient, this
  tool requires a human (or agent with a live TV session) to re-run the
  spot-check procedure above after every TradingView Desktop update.
- **When to revisit:** If a future TradingView Desktop version adds
  semantic attributes (`data-name`, `data-qa-id`, `data-field`) or an
  HTML `<table>` structure to the trade list DOM, this ADR should be
  superseded by a new ADR documenting the stable-selector approach, and
  the `backtest_trade_list` entry in `recon_findings.json` should be
  updated with those selectors.

## Evidence

The trade-list innerText layout was confirmed against TradingView Desktop
3.2.0 on 2026-07-05 with the MA Cross Strategy on BINANCE:ETHUSD.P, 1h.
The spot-check procedure above documents the known-good baseline for that
version.
