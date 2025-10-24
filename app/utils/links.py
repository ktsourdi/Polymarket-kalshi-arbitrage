"""Generate and parse links to market pages on exchanges.

This module provides URL generators for Polymarket and Kalshi market pages,
as well as lightweight URL parsers to extract identifiers from user-supplied
links so we can map them back to quotes in memory.
"""
from urllib.parse import urlparse



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



def parse_market_url(url: str) -> tuple[str, str] | None:
    """Parse a Kalshi or Polymarket market URL into (exchange, market_id).

    This accepts common forms like:
    - https://kalshi.com/markets/TICKER
    - https://polymarket.com/event/<token_id>
    - https://polymarket.com/market/<slug>

    Returns None if the URL cannot be parsed.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return None
    host = (parsed.netloc or "").lower()
    path_parts = [p for p in (parsed.path or "").split("/") if p]

    if "polymarket" in host:
        # Prefer explicit prefixes when present
        if len(path_parts) >= 2 and path_parts[0] in {"event", "market"}:
            return ("polymarket", path_parts[1])
        # Fallback: last segment
        if path_parts:
            return ("polymarket", path_parts[-1])

    if "kalshi" in host:
        if len(path_parts) >= 2 and path_parts[0] in {"markets", "market"}:
            return ("kalshi", path_parts[1])
        if path_parts:
            return ("kalshi", path_parts[-1])

    return None

