# Timing Feature Implementation

## Overview
Added comprehensive timing functionality to track performance of different operations in the dashboard.

## What Was Added

### 1. New Timing Utility (`app/utils/timing.py`)
- `TimingTracker` class - tracks multiple timing intervals
- `timer()` context manager - time code blocks
- `timed_function()` decorator - automatically time functions
- `format_duration()` helper - human-readable time formatting

### 2. Dashboard Integration
Added timing to these operations:
- ✅ **Fetch Data** - Time to fetch quotes from exchanges
- ✅ **Match Candidates** - Time to build match candidates
- ✅ **Detect Arbs** - Time to detect cross-exchange arbitrage
- ✅ **LLM Validation** - Time for LLM logical validation (if enabled)
- ✅ **Detect Two-Buy** - Time to detect two-buy opportunities

### 3. Display
Timing results are displayed in a new "Performance Timing" section showing:
- `Fetch Data`: X.XXs
- `Match Candidates`: X.XXs
- `Detect Arbs`: X.XXs
- etc.

## Features

### Time Formatting
Times are displayed in appropriate units:
- Microseconds (`μs`) for < 1ms
- Milliseconds (`ms`) for < 1s
- Seconds (`s`) for < 60s
- Minutes (`m XX.Xs`) for >= 60s

### Session Persistence
Timing data persists across dashboard interactions within the same session.

## Usage Example

```python
from app.utils.timing import TimingTracker, timer

tracker = TimingTracker()

# Method 1: Manual start/stop
tracker.start("my_operation")
# ... do work ...
tracker.stop("my_operation")

# Method 2: Context manager
with timer("my_operation", tracker):
    # ... do work ...
    pass

# Get formatted results
summary = tracker.summary()
# Returns: {"my_operation": "1.23s"}
```

## Benefits

1. **Performance Monitoring** - See which operations are slow
2. **Optimization Guidance** - Identify bottlenecks
3. **User Feedback** - Show users how long operations take
4. **Debugging** - Track timing across complex workflows

## Example Dashboard Output

```
#### Performance Timing
┌──────────────┬─────────────┬─────────────┬──────────────┐
│ Fetch Data   │ Match Cands │ Detect Arbs │ LLM Validation│
├──────────────┼─────────────┼─────────────┼──────────────┤
│   2.34s      │   1.45s     │   0.12s     │    3.21s     │
└──────────────┴─────────────┴─────────────┴──────────────┘
```

## Testing

To see the timing feature in action:
1. Run `bash run_ui.sh`
2. Click "Run matching now"
3. Scroll down to see "Performance Timing" section
4. Times update as operations complete


