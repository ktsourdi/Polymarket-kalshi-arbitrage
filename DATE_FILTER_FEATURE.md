# Date Filter Feature

## Overview
Added date filtering to focus on arbitrage opportunities by their resolution date.

## What Was Added

### 1. **Extended MarketQuote Model** (`app/core/models.py`)
Added `end_date` field to store market resolution dates:
```python
@dataclass(frozen=True)
class MarketQuote:
    ...
    end_date: Optional[datetime] = None  # Market resolution date
```

### 2. **Date Extraction** (`app/connectors/polymarket.py`)
Updated to extract end dates from Polymarket API:
- Parses `endDateIso`, `endDate`, `updatedAt`
- Includes date in all MarketQuote objects

### 3. **Date Filtering Utilities** (`app/utils/date_filter.py`)

#### `filter_by_days_until_resolution(quotes, min_days, max_days)`
Filter by days until resolution:
- `min_days`: Minimum days until event resolves
- `max_days`: Maximum days until event resolves

#### `format_resolution_date(quote)`
Human-readable date formatting:
- "Tomorrow"
- "In 5 days"
- "In 2 weeks"
- "In 3 months"

### 4. **Dashboard Integration** (`app/ui/dashboard.py`)
Added "Date Filter" section in sidebar:
- Checkbox to enable/disable filtering
- Min days input (0-365)
- Max days input (0-365)
- Default: 0-90 days

## Usage Examples

### Short-term Opportunities (Next 7 Days)
```python
# Filter for events resolving in the next week
near_term = filter_by_days_until_resolution(quotes, max_days=7)
```

### Medium-term Opportunities (30-90 Days)
```python
# Filter for events resolving in 1-3 months
medium_term = filter_by_days_until_resolution(quotes, min_days=30, max_days=90)
```

### Long-term Opportunities (180+ Days)
```python
# Filter for events resolving in 6+ months
long_term = filter_by_days_until_resolution(quotes, min_days=180)
```

## Dashboard UI

Sidebar now includes:
```
### Date Filter
☐ Filter by resolution date
  Min days until resolution: [0]
  Max days until resolution: [90]
```

## Benefits

1. **Focus on Timeframe** - Find opportunities matching your investment horizon
2. **Quick Turnaround** - Filter for near-term events (next few days)
3. **Long-term Planning** - Find events resolving in specific timeframes
4. **Better Cash Flow** - Understand when positions will settle

## Testing

To use the date filter:
1. Run `bash run_ui.sh`
2. Enable "Filter by resolution date" in sidebar
3. Set min/max days
4. Click "Run matching now"
5. Only see events in your date range

## Technical Notes

- Dates are stored in UTC timezone
- Polymarket dates from `endDateIso` or `endDate` fields
- Kalshi dates still need implementation (API may vary)
- Missing dates are excluded from filtered results


