"""Generate links to market pages on exchanges.

This module provides URL generators for Polymarket and Kalshi market pages.
"""


def polymarket_market_url(market_id: str) -> str:
    """Generate Polymarket market URL.
    
    Args:
        market_id: Market identifier (token ID or market ID)
        
    Returns:
        URL to Polymarket market page
    """
    # Polymarket URLs typically use the token ID in this format:
    # https://polymarket.com/event/[token_id]
    # Or: https://polymarket.com/market/[slug]
    
    # If it's a full token ID (long hex string), use token format
    if len(market_id) > 10 and all(c in '0123456789abcdefABCDEF' for c in market_id):
        return f"https://polymarket.com/event/{market_id}"
    
    # Otherwise, try market format
    return f"https://polymarket.com/market/{market_id}"


def kalshi_market_url(market_id: str) -> str:
    """Generate Kalshi market URL.
    
    Args:
        market_id: Market identifier (market ID or ticker)
        
    Returns:
        URL to Kalshi market page
    """
    # Kalshi URLs use the ticker in this format:
    # https://kalshi.com/markets/[ticker]
    
    # Clean up any prefixes if present
    clean_id = market_id.replace("kalshi-", "").replace("KALSHI-", "")
    
    return f"https://kalshi.com/markets/{clean_id}"


def create_market_link(text: str, url: str) -> str:
    """Create a markdown link.
    
    Args:
        text: Link text
        url: Link URL
        
    Returns:
        Markdown formatted link string
    """
    return f"[{text}]({url})"


def get_event_link(event: str, exchange: str, market_id: str) -> str:
    """Get formatted link for an event.
    
    Args:
        event: Event description
        exchange: Exchange name (kalshi or polymarket)
        market_id: Market identifier
        
    Returns:
        Markdown formatted link or text if URL unavailable
    """
    if not market_id or market_id == "None":
        return event
    
    if exchange.lower() == "polymarket":
        url = polymarket_market_url(market_id)
    elif exchange.lower() == "kalshi":
        url = kalshi_market_url(market_id)
    else:
        return event
    
    # Truncate long event names for display
    display_text = event if len(event) <= 60 else event[:57] + "..."
    
    return create_market_link(display_text, url)

