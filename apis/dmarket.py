import requests
import logging
import time
from typing import Dict

logger = logging.getLogger(__name__)

BASE_URL = "https://api.dmarket.com/exchange/v1/market/items"
GAME_ID = "a8db"  # CS2
MAX_RETRIES = 3


def get_prices(api_key: str) -> Dict[str, dict]:
    """
    Возвращает {title: {"price": float, "float": float|None}} для всех предметов CS2.
    Использует cursor-пагинацию с retry при таймаутах.
    float берётся у листинга с минимальной ценой.
    """
    if not api_key:
        logger.error("DMARKET_API_KEY не задан")
        return {}

    headers = {"X-Api-Key": api_key}
    prices: Dict[str, float] = {}
    cursor = None
    page = 0

    while True:
        params = {
            "gameId": GAME_ID,
            "currency": "USD",
            "limit": 100,
            "orderBy": "price",
            "orderDir": "asc",
        }
        if cursor:
            params["cursor"] = cursor

        # Retry при временных ошибках/таймаутах
        data = None
        for attempt in range(MAX_RETRIES):
            try:
                r = requests.get(BASE_URL, headers=headers, params=params, timeout=45)
                r.raise_for_status()
                data = r.json()
                break
            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    wait = 2 ** attempt  # 1с, 2с, 4с
                    logger.warning(f"DMarket страница {page}, попытка {attempt + 1} не удалась: {e}. Retry через {wait}с...")
                    time.sleep(wait)
                else:
                    logger.error(f"DMarket страница {page}: все попытки исчерпаны. Загружено {len(prices)} предметов.")
                    return prices

        items = data.get("objects", [])
        if not items:
            break

        for item in items:
            name = item.get("title", "")
            price_raw = item.get("price", {}).get("USD")
            if name and price_raw:
                price = float(price_raw) / 100.0
                float_val = item.get("extra", {}).get("floatValue")
                if name not in prices or price < prices[name]["price"]:
                    prices[name] = {"price": price, "float": float_val}

        cursor = data.get("cursor")
        page += 1

        if page % 20 == 0:
            logger.info(f"DMarket: ~{page * 100} листингов обработано, {len(prices)} уникальных предметов...")

        if not cursor:
            break

        time.sleep(0.15)

    with_float = sum(1 for v in prices.values() if v.get("float") is not None)
    logger.info(f"DMarket: итого {len(prices)} предметов, у {with_float} есть float")
    return prices
