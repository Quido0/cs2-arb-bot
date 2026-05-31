import requests
import logging
import time
from typing import Dict

logger = logging.getLogger(__name__)

BASE_URL = "https://api.skinport.com/v1/items"

_last_prices: Dict[str, dict] = {}   # cache of last successful response
_blocked_until: float = 0            # timestamp until which requests are suppressed


def get_prices(currency: str = "USD") -> Dict[str, dict]:
    """
    Returns {market_hash_name: {"price": float, "qty": int}} for all CS2 items.
    On 429 returns cache immediately without blocking the scan loop.
    """
    global _last_prices, _blocked_until

    # Still in cooldown — return cache without making a request
    remaining = _blocked_until - time.time()
    if remaining > 0:
        mins = int(remaining // 60)
        secs = int(remaining % 60)
        label = f"{mins}m {secs}s" if mins else f"{secs}s"
        logger.info(f"Skinport: cooldown {label} remaining, using cache ({len(_last_prices)} items)")
        return _last_prices

    try:
        r = requests.get(
            BASE_URL,
            params={"app_id": 730, "currency": currency},
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "application/json",
                "Accept-Encoding": "br",
            },
            timeout=30,
        )

        if r.status_code == 429:
            retry_after = int(r.headers.get("Retry-After", 300))
            cooldown = min(retry_after, 600)   # cap at 10 minutes
            _blocked_until = time.time() + cooldown
            logger.warning(
                f"Skinport: rate limited (server asked {retry_after}s, "
                f"waiting {cooldown // 60}m). Using cache ({len(_last_prices)} items)."
            )
            return _last_prices

        r.raise_for_status()
        items = r.json()
        prices = {}
        for item in items:
            name = item.get("market_hash_name")
            min_price = item.get("min_price")
            quantity = item.get("quantity", 0)
            if name and min_price and quantity > 0:
                prices[name] = {"price": min_price / 100.0, "qty": quantity}

        _last_prices = prices
        logger.info(f"Skinport: loaded {len(prices)} items")
        return prices

    except Exception as e:
        logger.error(f"Skinport API error: {e}")
        if _last_prices:
            logger.info(f"Skinport: using cache ({len(_last_prices)} items)")
        return _last_prices
