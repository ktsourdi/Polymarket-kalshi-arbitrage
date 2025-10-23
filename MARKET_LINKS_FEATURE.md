# Market Links Feature

## Overview
Added clickable links to market pages on Polymarket and Kalshi for easy navigation to trading opportunities.

## What Was Added

### 1. Link Generator Module (`app/utils/links.py`)

#### `polymarket_market_url(market_id: str) -> str`
Generates Polymarket market URLs:
- Format: `https://polymarket.com/event/{token_id}`
- Example: `https://polymarket.com/event/0x1234...`

#### `kalshi_market_url(market_id: str) -> str`
Generates Kalshi market URLs:
- Format: `https://kalshi.com/markets/{ticker}`
- Example: `https://kalshi.com/markets/USA-2024`

#### `get_event_link(event, exchange, market_id) -> str`
Creates formatted markdown links for events.

### 2. Dashboard Integration

Added two new columns to arbitrage results:
- **View Long** - Clickable link to long leg market
- **View Short** - Clickable link to short leg market

### 3. Link Display

Links are displayed as:
- ✅ Clickable "🔗 Open" buttons in the dataframe
- ✅ Direct URLs in a separate column
- ✅ Embedded in strategy text

## Example Output

### Before:
```
event | arb % | profit | stake | strategy
```

### After:
```
event | arb % | profit | stake | strategy | view long | view short
```

With clickable links in the last two columns.

## URL Formats

### Polymarket
- Full token ID: `https://polymarket.com/event/0x1234567890abcdef`
- Market ID: `https://polymarket.com/market/market-id`

### Kalshi
- Ticker: `https://kalshi.com/markets/USA-2024`
- Market ID: `https://kalshi.com/markets/market-id`

## Benefits

1. **Quick Navigation** - Click to go directly to trading pages
2. **Easy Verification** - Check market details and prices
3. **Faster Execution** - No manual searching for markets
4. **Better UX** - Clear links with icons

## Testing

To see the links:
1. Run `bash run_ui.sh`
2. Click "Run matching now"
3. Check the "Arbitrage (Cross-Exchange)" tab
4. Click the "🔗 Open" links in the "view long" and "view short" columns
5. Should open the market pages in new tabs

## Technical Details

- Links are generated from `market_id` field in `MarketQuote`
- Polymarket uses token IDs or market IDs
- Kalshi uses tickers or market IDs
- Streamlit LinkColumn displays links as clickable buttons

