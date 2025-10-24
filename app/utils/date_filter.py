"""Date filtering utilities for market quotes.

This module provides functions to filter market quotes by their resolution dates.
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from app.core.models import MarketQuote


def filter_by_days_until_resolution(
    quotes: List[MarketQuote],
    min_days: Optional[int] = None,
    max_days: Optional[int] = None,
) -> List[MarketQuote]:
    """Filter quotes by days until resolution.
    
    Args:
        quotes: List of market quotes to filter
        min_days: Minimum days until resolution (None = no minimum)
        max_days: Maximum days until resolution (None = no maximum)
        
    Returns:
        Filtered list of quotes
        
    Example:
        # Get events resolving in next 7 days
        near_term = filter_by_days_until_resolution(quotes, max_days=7)
        
        # Get events resolving in 30-90 days
        medium_term = filter_by_days_until_resolution(quotes, min_days=30, max_days=90)
    """
    if not quotes:
        return quotes
    
    now = datetime.now(timezone.utc)
    filtered = []
    
    for quote in quotes:
        if quote.end_date is None:
            # If no date, include it (or skip based on your preference)
            continue
        
        days_until = (quote.end_date - now).days
        
        # Check bounds
        if min_days is not None and days_until < min_days:
            continue
        if max_days is not None and days_until > max_days:
            continue
        
        filtered.append(quote)
    
    return filtered


def filter_by_date_range(
    quotes: List[MarketQuote],
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> List[MarketQuote]:
    """Filter quotes by absolute date range.
    
    Args:
        quotes: List of market quotes to filter
        start_date: Earliest resolution date (None = no minimum)
        end_date: Latest resolution date (None = no maximum)
        
    Returns:
        Filtered list of quotes
    """
    if not quotes:
        return quotes
    
    filtered = []
    
    for quote in quotes:
        if quote.end_date is None:
            continue
        
        if start_date and quote.end_date < start_date:
            continue
        if end_date and quote.end_date > end_date:
            continue
        
        filtered.append(quote)
    
    return filtered


def get_days_until_resolution(quote: MarketQuote) -> Optional[int]:
    """Get days until resolution for a quote.
    
    Args:
        quote: Market quote
        
    Returns:
        Days until resolution, or None if no date
    """
    if quote.end_date is None:
        return None
    
    now = datetime.now(timezone.utc)
    return (quote.end_date - now).days


def format_resolution_date(quote: MarketQuote) -> str:
    """Format resolution date for display.
    
    Args:
        quote: Market quote
        
    Returns:
        Formatted date string or "No date"
    """
    if quote.end_date is None:
        return "No date"
    
    now = datetime.now(timezone.utc)
    days = (quote.end_date - now).days
    
    if days < 0:
        return f"Expired ({abs(days)} days ago)"
    elif days == 0:
        return "Today"
    elif days == 1:
        return "Tomorrow"
    elif days < 7:
        return f"In {days} days"
    elif days < 30:
        weeks = days // 7
        return f"In {weeks} week{'s' if weeks > 1 else ''}"
    elif days < 365:
        months = days // 30
        return f"In {months} month{'s' if months > 1 else ''}"
    else:
        years = days // 365
        return f"In {years} year{'s' if years > 1 else ''}"


