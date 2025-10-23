# Profit Calculator Feature

## Overview
Added comprehensive profit calculation and stake sizing for arbitrage opportunities.

## What Was Added

### 1. New Calculation Functions (`app/core/arb.py`)

#### `compute_arb_percentage(edge_bps: float) -> float`
Converts edge from basis points to percentage:
- 9910 bps → 99.1%
- 9680 bps → 96.8%

#### `calculate_profit_for_budget(edge_bps, max_notional, budget) -> tuple`
Calculates for a given budget:
- Actual notional used (capped by budget and max_notional)
- Stake on long leg
- Stake on short leg  
- Expected profit

### 2. Enhanced Dashboard Display

Added new columns to arbitrage results:
- **Arb %** - Percentage arbitrage opportunity
- **Budget $1000** - Profit with $1000 budget
- **Stake** - Total amount to stake
- **Strategy** - Clear instructions on where to play
- **Long** - Long leg details (exchange, outcome, price)
- **Short** - Short leg details (exchange, outcome, price)

### 3. Budget Input

Added "Profit Calculator" section in sidebar:
- Configurable budget (default: $1000)
- Adjustable from $10 to $100,000
- Used for all profit calculations

## Example Output

Before:
```
event | long_exch | long_price | short_exch | short_price | edge_bps | max_notional | gross_profit_usd
```

After:
```
event | arb % | budget $1000 | stake | strategy | long | short
```

Example row:
```
Will Florence Pugh... | 99.10% | $9.91 | $10.00 | Buy YES on kalshi @ $0.070
                                                   Buy NO on polymarket @ $0.930 | kalshi YES @0.070 | polymarket NO @0.930
```

## Profit Calculation Formula

For a budget of $1000:
1. **Actual Notional** = min($1000, max_notional_per_leg)
2. **Edge %** = edge_bps / 100
3. **Profit** = actual_notional × (edge_bps / 10000)
4. **Stake Split** = 50/50 on long and short legs

### Example Calculation

Opportunity with:
- Edge: 9910 bps (99.1%)
- Max notional: $500
- Budget: $1000

Result:
- Actual notional: $500 (limited by max_notional)
- Profit: $500 × 0.991 = $4.95
- Stake long: $250
- Stake short: $250

## Benefits

1. **Clear Profit Expectations** - See exactly how much you'll make
2. **Optimal Sizing** - Know how much to stake on each leg
3. **Strategy Clarity** - Clear instructions on where to play
4. **Budget Flexibility** - Adjust budget to see different profit scenarios

## Testing

To see the new profit calculator:
1. Run `bash run_ui.sh`
2. Set your budget in the sidebar
3. Click "Run matching now"
4. Check the "Arbitrage (Cross-Exchange)" tab
5. See profit calculations for each opportunity

