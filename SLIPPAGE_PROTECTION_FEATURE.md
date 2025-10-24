# Slippage Protection Feature

## Overview
Added protection against order book depth issues that could eliminate arbitrage opportunities when placing large orders.

## Problem
When you see an arbitrage opportunity at specific prices (e.g., YES @ $0.22), placing a large order will:
1. **Fill at multiple price levels** - Buy some at $0.22, some at $0.23, some at $0.24
2. **Move average fill price higher** - Your actual average might be $0.235
3. **Eliminate the edge** - What looked like 13% arbitrage might become 0% or negative

## Solution

### 1. **Enhanced Data Model** (`app/core/models.py`)
Added `OrderLevel` class to represent order book depth:
```python
@dataclass(frozen=True)
class OrderLevel:
    price: float
    size: float
```

Added `order_depth` field to `MarketQuote`:
```python
order_depth: Optional[List[OrderLevel]] = None  # Order book depth levels
```

### 2. **Slippage Protection Module** (`app/utils/slippage_protection.py`)

Functions added:
- `estimate_fill_price()` - Calculate average fill price for an order size
- `calculate_max_size_for_price_impact()` - Max size with limited price impact
- `get_safe_order_size()` - Safe order size based on order book depth
- `estimate_execution_cost()` - Estimate slippage in basis points
- `cap_order_by_liquidity()` - Cap both legs based on liquidity

### 3. **Enhanced Arbitrage Detection** (`app/core/arb.py`)
Now accounts for slippage:
1. **Cap order size** by available liquidity
2. **Estimate actual fill prices** with slippage
3. **Recalculate edge** using real execution prices
4. **Only show opportunities** that remain profitable after slippage

### 4. **Dashboard Integration**
Added "Slippage Protection" section:
- **Cap orders by liquidity depth** (checkbox, default: enabled)
- **Max price impact (%)** (default: 1.0%)

## How It Works

### Example Scenario

Order book for YES contracts:
- 100 shares @ $0.22
- 200 shares @ $0.23
- 500 shares @ $0.24

**Without protection:**
- See price: $0.22
- Place order: 500 shares
- Actual fill: 100@$0.22 + 200@$0.23 + 200@$0.24
- Average price: $0.234
- Slippage: +6.4%

**With protection (1% max impact):**
- See price: $0.22
- Max safe size: ~300 shares (stays below $0.222)
- Only take orders up to that point
- Average price: ~$0.222
- Slippage: +0.9%

## Formula

```python
# Estimate fill price
fill_price = weighted_average(price_levels × sizes / total_size)

# Calculate slippage
slippage_bps = ((fill_price - best_price) / best_price) × 10000

# Cap by price impact
max_price = best_price × (1 + max_price_impact)
max_size = sum(sizes for levels where price <= max_price)
```

## Benefits

1. **Realistic Profit Estimates** - Accounts for actual execution prices
2. **Prevents Over-Sizing** - Won't suggest orders too large for the book
3. **Protects Edge** - Shows only opportunities that survive slippage
4. **Customizable** - Adjust max price impact based on your strategy

## Current Limitations

⚠️ **We don't currently fetch full order book depth from APIs**

The implementation is ready, but we need to:
1. Fetch order book data from Kalshi API
2. Fetch order book data from Polymarket API
3. Parse and store in `order_depth` field

Currently, it falls back to using the quoted `size` field as a conservative estimate.

## Testing

Once order book data is available:
1. Run `bash run_ui.sh`
2. Enable "Cap orders by liquidity depth"
3. Set "Max price impact" (e.g., 1.0%)
4. Only profitable opportunities will show
5. Profit calculations account for slippage

## Next Steps

To fully implement:
1. Add order book fetching to Kalshi connector
2. Add order book fetching to Polymarket connector
3. Store depth data in `order_depth` field
4. Display depth info in dashboard


