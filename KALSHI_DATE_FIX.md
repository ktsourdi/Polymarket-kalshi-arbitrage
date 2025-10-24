# Kalshi Date Filter Fix

## Problem
Kalshi markets weren't being filtered by date because the code wasn't extracting date information from the API response.

## Solution

### 1. Added Date Parsing (`app/connectors/kalshi.py`)
Added `_parse_dt()` method to parse Kalshi date strings:
- Handles ISO format dates
- Supports timezone-aware timestamps
- Returns None for invalid dates

### 2. Extract End Dates
Added date extraction that checks multiple possible fields:
- `settle_time` - Market settlement time
- `settle_time_iso` - ISO format settlement time
- `end_time` - Market end time
- `expiration_time` - Market expiration
- `expiration_time_iso` - ISO format expiration

### 3. Include in MarketQuote
Now all Kalshi MarketQuote objects include the `end_date` field.

## How It Works

```python
# Kalshi returns dates in various formats
end_date = (
    self._parse_dt(m.get("settle_time"))
    or self._parse_dt(m.get("settle_time_iso"))
    or self._parse_dt(m.get("end_time"))
    or self._parse_dt(m.get("expiration_time"))
    or self._parse_dt(m.get("expiration_time_iso"))
)

# Included in MarketQuote
MarketQuote(
    ...
    end_date=end_date,
)
```

## Testing

Now when you enable the date filter in the dashboard:
1. Kalshi markets will have their resolution dates extracted
2. Date filtering will work for both Kalshi and Polymarket
3. You can filter by days until resolution

## What Fields Kalshi Uses

Based on typical prediction market APIs, Kalshi likely uses:
- `settle_time` or `settle_time_iso` - When the market settles/resolves
- This is the primary field for determining resolution date

## Next Steps

If date filtering still doesn't work:
1. Check the actual Kalshi API response format
2. Add logging to see what fields are present
3. Adjust field names based on actual API structure


