"""Liquidity filtering utilities for market quotes.

This module provides functions to filter out markets with insufficient liquidity
or incomplete order books (e.g., only YES orders, only NO orders, or no orders).
"""

from typing import List, Optional

from app.core.models import MarketQuote


def has_both_outcomes(quotes: List[MarketQuote], event: str) -> bool:
    """Check if an event has both YES and NO quotes.
    
    Args:
        quotes: List of market quotes
        event: Event name to check
        
    Returns:
        True if both YES and NO quotes exist for the event
    """
    events = {q.event for q in quotes if q.event == event}
    if not events:
        return False
    
    outcomes = {q.outcome for q in quotes if q.event == event}
    return "YES" in outcomes and "NO" in outcomes


def has_valid_prices(quotes: List[MarketQuote], event: str) -> bool:
    """Check if an event has valid (non-zero) prices for both outcomes.
    
    Args:
        quotes: List of market quotes
        event: Event name to check
        
    Returns:
        True if both YES and NO have valid prices (> 0)
    """
    yes_quotes = [q for q in quotes if q.event == event and q.outcome == "YES"]
    no_quotes = [q for q in quotes if q.event == event and q.outcome == "NO"]
    
    if not yes_quotes or not no_quotes:
        return False
    
    yes_has_price = any(q.price > 0 for q in yes_quotes)
    no_has_price = any(q.price > 0 for q in no_quotes)
    
    return yes_has_price and no_has_price


def has_minimum_liquidity(quotes: List[MarketQuote], event: str, min_size: float = 1.0) -> bool:
    """Check if an event has minimum liquidity on both sides.
    
    Args:
        quotes: List of market quotes
        event: Event name to check
        min_size: Minimum size required for each outcome
        
    Returns:
        True if both YES and NO have sufficient size
    """
    yes_quotes = [q for q in quotes if q.event == event and q.outcome == "YES"]
    no_quotes = [q for q in quotes if q.event == event and q.outcome == "NO"]
    
    if not yes_quotes or not no_quotes:
        return False
    
    yes_has_liquidity = any(q.size >= min_size for q in yes_quotes)
    no_has_liquidity = any(q.size >= min_size for q in no_quotes)
    
    return yes_has_liquidity and no_has_liquidity


def filter_by_liquidity(quotes: List[MarketQuote], require_both_outcomes: bool = True, min_price: float = 0.0, min_size: float = 0.0) -> List[MarketQuote]:
    """Filter quotes to only include markets with sufficient liquidity.
    
    Args:
        quotes: List of market quotes to filter
        require_both_outcomes: Require both YES and NO quotes
        min_price: Minimum price threshold (0 = any non-zero price)
        min_size: Minimum size threshold (0 = any non-zero size)
        
    Returns:
        Filtered list of quotes
        
    Example:
        # Only keep markets with both outcomes and valid prices
        liquid_quotes = filter_by_liquidity(quotes, require_both_outcomes=True, min_price=0.0)
        
        # Require minimum size as well
        liquid_quotes = filter_by_liquidity(quotes, min_size=100.0)
    """
    if not quotes:
        return quotes
    
    # Group by event
    events = set(q.event for q in quotes)
    
    # Filter events that meet criteria
    valid_events = set()
    for event in events:
        if require_both_outcomes and not has_both_outcomes(quotes, event):
            continue
        
        if min_price == 0.0:
            if not has_valid_prices(quotes, event):
                continue
        else:
            # Check specific price threshold
            yes_quotes = [q for q in quotes if q.event == event and q.outcome == "YES"]
            no_quotes = [q for q in quotes if q.event == event and q.outcome == "NO"]
            if not yes_quotes or not no_quotes:
                continue
            if not all(q.price >= min_price for q in yes_quotes + no_quotes):
                continue
        
        if min_size > 0.0 and not has_minimum_liquidity(quotes, event, min_size):
            continue
        
        valid_events.add(event)
    
    # Return quotes for valid events only
    return [q for q in quotes if q.event in valid_events]


def get_liquidity_summary(quotes: List[MarketQuote]) -> dict:
    """Get summary statistics about market liquidity.
    
    Args:
        quotes: List of market quotes
        
    Returns:
        Dictionary with liquidity statistics
    """
    events = set(q.event for q in quotes)
    
    both_outcomes = sum(1 for event in events if has_both_outcomes(quotes, event))
    with_prices = sum(1 for event in events if has_valid_prices(quotes, event))
    
    # Count quotes by outcome
    yes_count = sum(1 for q in quotes if q.outcome == "YES" and q.price > 0)
    no_count = sum(1 for q in quotes if q.outcome == "NO" and q.price > 0)
    
    return {
        "total_events": len(events),
        "events_with_both_outcomes": both_outcomes,
        "events_with_valid_prices": with_prices,
        "yes_quotes_with_price": yes_count,
        "no_quotes_with_price": no_count,
        "total_quotes": len(quotes),
    }

