# Liquidity Filter Feature

## Overview
Added filtering to exclude markets without sufficient orders on both sides (YES and NO).

## Problem
Some markets have incomplete order books:
- ❌ Only YES orders (no NO orders)
- ❌ Only NO orders (no YES orders)  
- ❌ No orders at all
- ❌ Zero prices or zero size

These markets can't be arbitraged because you can't execute both legs of the trade.

## Solution

### 1. **Liquidity Filter Module** (`app/utils/liquidity_filter.py`)

Functions added:
- `has_both_outcomes()` - Check if event has both YES and NO quotes
- `has_valid_prices()` - Check if both outcomes have non-zero prices
- `has_minimum_liquidity()` - Check if both outcomes meet size threshold
- `filter_by_liquidity()` - Filter quotes to only liquid markets
- `get_liquidity_summary()` - Get statistics about market liquidity

### 2. **Dashboard Integration**

Added "Liquidity Filter" section in sidebar:
- **Filter markets without orders** (checkbox, default: enabled)
- **Require both YES and NO orders** (checkbox, default: enabled)
- **Min price** (default: 0.0 = any non-zero price)
- **Min size** (default: 0.0 = any non-zero size)

### 3. **Automatic Filtering**

Markets are filtered before detection:
- Removes events without both YES and NO quotes
- Removes events with zero prices
- Removes events with insufficient size (if min_size > 0)

## Filtering Logic

For each event, it checks:
1. ✅ Has both YES and NO quotes
2. ✅ Both have valid prices (> 0)
3. ✅ Both meet minimum size requirement (if set)

If all checks pass, the event is included. Otherwise, excluded.

## Example

**Market A** (Emma Stone):
- YES: $0.95 (good)
- NO: No orders available
- ❌ **Filtered out** - Missing NO orders

**Market B** (Jenna Ortega):
- YES: $0.95, size=100
- NO: $0.05, size=50
- ✅ **Included** - Has both sides

## Benefits

1. **Excludes Illiquid Markets** - No more impossible-to-trade opportunities
2. **Realistic Opportunities** - Only shows markets you can actually arbitrage
3. **Better Accuracy** - Profit calculations reflect reality
4. **Customizable** - Adjust filters based on your needs

## Testing

To use the liquidity filter:
1. Run `bash run_ui.sh`
2. Enable "Filter markets without orders" in sidebar
3. Configure:
   - Require both YES and NO orders: ✅
   - Min price: 0.0 (any price > 0)
   - Min size: 0.0 (any size > 0)
4. Click "Run matching now"
5. Only markets with orders on both sides will appear

## Technical Details

- Filters quotes before arbitrage detection
- Works on both Kalshi and Polymarket
- Applies same filters to both exchanges
- Compatible with date filtering

