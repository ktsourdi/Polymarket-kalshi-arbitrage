"""Slippage protection utilities for order book depth.

This module provides functions to estimate slippage based on order book depth
and cap trade sizes to prevent significant price impact.
"""

from typing import List, Optional, Tuple

from app.core.models import MarketQuote, OrderLevel


def estimate_fill_price(levels: List[OrderLevel], target_size: float) -> Tuple[float, float]:
    """Estimate average fill price for a given order size based on order book depth.
    
    Args:
        levels: List of order book levels (sorted by price)
        target_size: Target order size
        
    Returns:
        Tuple of (average_price, total_cost)
        
    Example:
        levels = [
            OrderLevel(price=0.22, size=100),  # 100 shares @ $0.22
            OrderLevel(price=0.23, size=200),  # 200 shares @ $0.23
            OrderLevel(price=0.24, size=500),  # 500 shares @ $0.24
        ]
        # For 250 shares:
        # - 100 @ $0.22 = $22
        # - 150 @ $0.23 = $34.50
        # - Total = $56.50 / 250 = $0.226 avg
    """
    if not levels or target_size <= 0:
        return 0.0, 0.0
    
    filled = 0.0
    total_cost = 0.0
    
    for level in levels:
        if filled >= target_size:
            break
        
        remaining = target_size - filled
        take_from_level = min(remaining, level.size)
        
        filled += take_from_level
        total_cost += take_from_level * level.price
    
    if filled == 0:
        return 0.0, 0.0
    
    avg_price = total_cost / filled
    return avg_price, total_cost


def calculate_max_size_for_price_impact(levels: List[OrderLevel], max_price_impact: float = 0.01) -> float:
    """Calculate maximum order size that keeps price impact below threshold.
    
    Args:
        levels: List of order book levels
        max_price_impact: Maximum acceptable price impact (default: 1%)
        
    Returns:
        Maximum safe order size
        
    Example:
        If best price is $0.22 and max impact is 1%:
        - Can take orders up to price of $0.2222
        - Calculates how many shares available at or below that price
    """
    if not levels:
        return 0.0
    
    best_price = levels[0].price
    max_price = best_price * (1 + max_price_impact)
    
    total_size = 0.0
    for level in levels:
        if level.price > max_price:
            break
        total_size += level.size
    
    return total_size


def get_safe_order_size(quote: MarketQuote, max_price_impact: float = 0.01) -> float:
    """Get safe order size for a quote given its order book depth.
    
    Args:
        quote: Market quote with order depth
        max_price_impact: Maximum acceptable price impact
        
    Returns:
        Safe order size that won't move price significantly
    """
    if quote.order_depth is None or not quote.order_depth:
        # Fallback to quoted size if no depth data
        return quote.size
    
    return calculate_max_size_for_price_impact(quote.order_depth, max_price_impact)


def estimate_execution_cost(quote: MarketQuote, order_size: float) -> Tuple[float, float]:
    """Estimate the actual execution cost for an order size.
    
    Args:
        quote: Market quote with order depth
        order_size: Desired order size
        
    Returns:
        Tuple of (average_price, slippage_bps)
        where slippage_bps is the price impact in basis points
    """
    if quote.order_depth is None or not quote.order_depth:
        # No depth data - assume quoted price
        return quote.price, 0.0
    
    avg_price, total_cost = estimate_fill_price(quote.order_depth, order_size)
    
    if avg_price == 0 or quote.price == 0:
        return avg_price, 0.0
    
    slippage_bps = ((avg_price - quote.price) / quote.price) * 10000.0
    return avg_price, slippage_bps


def cap_order_by_liquidity(
    long_quote: MarketQuote,
    short_quote: MarketQuote,
    desired_notional: float,
    max_price_impact: float = 0.01,
) -> Tuple[float, float, float]:
    """Cap order size based on available liquidity on both legs.
    
    Args:
        long_quote: Long leg quote
        short_quote: Short leg quote
        desired_notional: Desired total notional
        max_price_impact: Maximum acceptable price impact
        
    Returns:
        Tuple of (long_size, short_size, actual_notional)
    """
    # Calculate safe sizes for each leg
    long_safe_size = get_safe_order_size(long_quote, max_price_impact)
    short_safe_size = get_safe_order_size(short_quote, max_price_impact)
    
    # Calculate max notional for each leg
    long_max_notional = long_safe_size * long_quote.price
    short_max_notional = short_safe_size * (1 - short_quote.price)
    
    # Cap by liquidity
    actual_notional = min(desired_notional, long_max_notional, short_max_notional)
    
    # Calculate sizes
    long_size = actual_notional / long_quote.price if long_quote.price > 0 else 0
    short_size = actual_notional / (1 - short_quote.price) if short_quote.price < 1 else 0
    
    return long_size, short_size, actual_notional

