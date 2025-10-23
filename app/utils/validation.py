"""Input validation utilities for market data and orders.

This module provides validation functions to ensure data integrity
before processing or executing trades. This prevents errors and potential
financial losses from invalid data.
"""

from typing import Any


class ValidationError(ValueError):
    """Raised when input validation fails."""
    pass


def validate_price(price: Any, label: str = "price") -> float:
    """Validate and normalize a price value.
    
    Args:
        price: The price value to validate
        label: Label for error messages
        
    Returns:
        Normalized float price value
        
    Raises:
        ValidationError: If price is invalid
    """
    if not isinstance(price, (int, float)):
        raise ValidationError(f"{label} must be numeric, got {type(price).__name__}")
    
    price = float(price)
    
    if not 0 <= price <= 1:
        raise ValidationError(f"{label} must be between 0 and 1, got {price}")
    
    return price


def validate_size(size: Any, label: str = "size") -> float:
    """Validate and normalize a size/quantity value.
    
    Args:
        size: The size value to validate
        label: Label for error messages
        
    Returns:
        Normalized float size value
        
    Raises:
        ValidationError: If size is invalid
    """
    if not isinstance(size, (int, float)):
        raise ValidationError(f"{label} must be numeric, got {type(size).__name__}")
    
    size = float(size)
    
    if size < 0:
        raise ValidationError(f"{label} must be non-negative, got {size}")
    
    return size


def validate_market_id(market_id: Any, label: str = "market_id") -> str:
    """Validate a market identifier.
    
    Args:
        market_id: The market ID to validate
        label: Label for error messages
        
    Returns:
        Normalized string market ID
        
    Raises:
        ValidationError: If market_id is invalid
    """
    if not isinstance(market_id, str):
        market_id = str(market_id)
    
    market_id = market_id.strip()
    
    if not market_id:
        raise ValidationError(f"{label} cannot be empty")
    
    return market_id


def validate_event_name(event: Any, label: str = "event") -> str:
    """Validate an event/market name.
    
    Args:
        event: The event name to validate
        label: Label for error messages
        
    Returns:
        Normalized string event name
        
    Raises:
        ValidationError: If event is invalid
    """
    if not isinstance(event, str):
        event = str(event)
    
    event = event.strip()
    
    if not event:
        raise ValidationError(f"{label} cannot be empty")
    
    if len(event) > 500:
        raise ValidationError(f"{label} is too long (max 500 characters)")
    
    return event


def validate_outcome(outcome: Any, label: str = "outcome") -> str:
    """Validate an outcome value (YES/NO).
    
    Args:
        outcome: The outcome to validate
        label: Label for error messages
        
    Returns:
        Normalized uppercase outcome string
        
    Raises:
        ValidationError: If outcome is invalid
    """
    if not isinstance(outcome, str):
        outcome = str(outcome)
    
    outcome = outcome.strip().upper()
    
    if outcome not in ("YES", "NO"):
        raise ValidationError(f"{label} must be 'YES' or 'NO', got '{outcome}'")
    
    return outcome


def clip_price(price: float, min_val: float = 0.01, max_val: float = 0.99) -> float:
    """Clip a price value to a safe range.
    
    Args:
        price: The price to clip
        min_val: Minimum allowed value
        max_val: Maximum allowed value
        
    Returns:
        Clipped price value
    """
    return max(min_val, min(max_val, float(price)))

