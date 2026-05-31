import os

DMARKET_API_KEY = os.getenv("DMARKET_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Минимальный профит после всех комиссий (%)
MIN_PROFIT_PCT = float(os.getenv("MIN_PROFIT_PCT", "15"))

# Минимальная цена покупки — фильтруем мусор
MIN_PRICE_USD = float(os.getenv("MIN_PRICE_USD", "1.0"))

# Максимальная цена — ограничиваем риск
MAX_PRICE_USD = float(os.getenv("MAX_PRICE_USD", "500.0"))

# Интервал обновления цен (секунды)
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "300"))

# Топ-N алертов за цикл
MAX_ALERTS = int(os.getenv("MAX_ALERTS", "5"))

# Комиссии площадок
SKINPORT_BUY_FEE = 0.0       # Skinport не берёт при покупке
DMARKET_SELL_FEE = 0.025     # DMarket берёт 2.5% при продаже
