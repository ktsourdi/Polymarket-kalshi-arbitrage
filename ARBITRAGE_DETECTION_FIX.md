# Arbitrage Detection Fix

## Problem
The dashboard was using `detect_arbs()` which requires **exact event matching**. When events had slight wording differences (e.g., "rank" vs "ranked"), opportunities were missed.

## Solution
Changed the dashboard to **always use `detect_arbs_with_matcher()`** which performs fuzzy matching.

## What Changed

### Before:
```python
cross = detect_arbs(kalshi, poly)  # Requires exact match
```

### After:
```python
cross = detect_arbs_with_matcher(
    kalshi,
    poly,
    similarity_threshold=sim_thresh,
    explicit_map=explicit_map_for_detection,
)  # Uses fuzzy matching
```

## How It Works Now

1. **Fuzzy Matching**: Events matched by similarity (threshold: 0.72 default)
2. **Both Directions Checked**:
   - Case A: Kalshi YES + Polymarket NO
   - Case B: Polymarket YES + Kalshi NO
3. **Only Profitable**: Shows opportunities where cost < $1.00

## Example

Sydney Sweeney event:
- Kalshi: YES @ $0.38, NO @ $0.66
- Polymarket: YES @ $0.21, NO @ $0.82

Detected:
- ✅ Polymarket YES + Kalshi NO = $0.87 (13% profit)
- ❌ Kalshi YES + Polymarket NO = $1.20 (filtered out)

## Benefits

1. Finds opportunities with wording differences
2. Checks both directions automatically
3. More opportunities detected
4. Uses auto-generated alias mapping

