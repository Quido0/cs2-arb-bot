import os

DMARKET_API_KEY = os.getenv("DMARKET_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Minimum profit after all fees (%)
MIN_PROFIT_PCT = float(os.getenv("MIN_PROFIT_PCT", "15"))

# Minimum buy price — filters out junk items
MIN_PRICE_USD = float(os.getenv("MIN_PRICE_USD", "1.0"))

# Maximum buy price — limits risk per trade
MAX_PRICE_USD = float(os.getenv("MAX_PRICE_USD", "500.0"))

# Scan interval in seconds
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "300"))

# Max Telegram alerts per cycle
MAX_ALERTS = int(os.getenv("MAX_ALERTS", "5"))

# Platform fees
SKINPORT_BUY_FEE = 0.0       # Skinport charges nothing on purchase
DMARKET_SELL_FEE = 0.025     # DMarket charges 2.5% on sale
