# Bug Fix: False Positive Matches Between Different People

## Problem

The matching algorithm was incorrectly pairing different actors together because it was treating common capitalized words like "Google", "Year", "Search", "Actors" as unique entity identifiers.

### Example False Matches

All these different actors were being matched to David Corenswet:
- ❌ Cillian Murphy → David Corenswet (similarity: 0.777)
- ❌ Jacob Elordi → David Corenswet (similarity: 0.768)  
- ❌ Timothée Chalamet → David Corenswet (similarity: 0.748)

### Root Cause

The `extract_entity_tokens()` function was capturing ALL capitalized words as entities:
- "Will Cillian Murphy be the #1 rank on Google's Year in Search 2025 Global - Actors?"
  - Extracted: `{'cillian', 'murphy', 'google', 'year', 'search', 'global', 'actors'}`
- "Will David Corenswet be ranked #1 globally in Google's Year in Search 2025 Actors?"
  - Extracted: `{'david', 'corenswet', 'google', 'year', 'search', 'actors'}`

The intersection `{'google', 'year', 'search', 'actors'}` contained common words, so the entity guard passed even though they're different people!

## Solution

Added common capitalized words to the stop list in `app/utils/text.py`:

```python
_STOP_ENTS = {
    # ... existing stops ...
    # Common capitalized words that shouldn't be treated as unique entities
    "google",
    "year",
    "search",
    "global",
    "actors",
    "people",
    "rank",
    "ranked",
    "globally",
}
```

### Result

Now entity extraction only captures **person names**:
- Cillian Murphy: `{'cillian', 'murphy'}`
- David Corenswet: `{'david', 'corenswet'}`
- Intersection: `set()` (empty - correctly blocks the match!)

## Impact

- ✅ Eliminates false positive matches between different people
- ✅ Improves matching quality by focusing on actual person names
- ✅ Still allows legitimate matches (same person name in both questions)
- ✅ No breaking changes to existing functionality

## Verification

Tested with the three problematic pairs:
1. Cillian Murphy ↔ David Corenswet: **Correctly blocked** (no overlap)
2. Jacob Elordi ↔ David Corenswet: **Correctly blocked** (no overlap)
3. Timothée Chalamet ↔ David Corenswet: **Correctly blocked** (no overlap)

## Next Steps

1. **Restart your dashboard** to see the fix in action
2. The false matches should disappear from your results
3. Consider adding more common capitalized words to the stop list if needed

## Files Changed

- `app/utils/text.py` - Added common capitalized words to stop list

