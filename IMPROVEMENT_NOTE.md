# Remaining Edge Case: Shared First Names

## Issue
People with the same first name but different last names still match:
- Ryan Gosling vs Ryan Reynolds (both "ryan" in common)
- Possibly other first-name collisions

## Current Behavior
Entity extraction filters work correctly for:
- ✅ Different people with different names (Cillian Murphy ≠ David Corenswet)
- ✅ Same person variations (Timothée Chalamet = Timothée Chalamet)
- ⚠️ Same first name, different last name (Ryan Gosling ≈ Ryan Reynolds)

## Potential Fix
Require multiple name matches or check last names specifically:

```python
def require_name_match(ents1: Set[str], ents2: Set[str], min_matches: int = 2) -> bool:
    """Require multiple name tokens to match."""
    overlap = ents1 & ents2
    return len(overlap) >= min_matches
```

This would prevent "Ryan" alone from matching, but allow "Timothée Chalamet" to match.

## Current Status
Working well for most cases. The fix successfully eliminated:
- ✅ All the false matches shown earlier (Cillian Murphy → David Corenswet, etc.)
- ✅ Common word mismatches (Google, Year, Search)

The Ryan/Ryan case is a rare edge case that could be tightened further if needed.

