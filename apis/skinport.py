import requests
import logging
import time
from typing import Dict

logger = logging.getLogger(__name__)

BASE_URL = "https://api.skinport.com/v1/items"

_last_prices: Dict[str, float] = {}   # кэш последнего успешного ответа
_blocked_until: float = 0             # timestamp до которого не делаем запросы


def get_prices(currency: str = "USD") -> Dict[str, dict]:
    """
    Возвращает {market_hash_name: {"price": float, "qty": int}} для всех предметов CS2.
    При 429 не ждёт — сразу возвращает кэш, помечает время разблокировки.
    """
    global _last_prices, _blocked_until

    # Ещё в cooldown — отдаём кэш без запроса
    remaining = _blocked_until - time.time()
    if remaining > 0:
        mins = int(remaining // 60)
        secs = int(remaining % 60)
        label = f"{mins}м {secs}с" if mins else f"{secs}с"
        logger.info(f"Skinport: cooldown ещё {label}, используем кэш ({len(_last_prices)} предметов)")
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
            # Ограничиваем — не ждём больше 10 минут
            cooldown = min(retry_after, 600)
            _blocked_until = time.time() + cooldown
            mins = cooldown // 60
            logger.warning(
                f"Skinport: rate limit (сервер просит {retry_after}с, "
                f"ждём {mins}м). Используем кэш ({len(_last_prices)} предметов)."
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
        logger.info(f"Skinport: загружено {len(prices)} предметов")
        return prices

    except Exception as e:
        logger.error(f"Skinport API ошибка: {e}")
        if _last_prices:
            logger.info(f"Skinport: используем кэш ({len(_last_prices)} предметов)")
        return _last_prices
