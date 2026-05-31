import json
import os

SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "settings.json")

DEFAULTS = {
    "dmarket_api_key": "",
    "telegram_bot_token": "",
    "telegram_chat_id": "",
    "min_profit_pct": 15.0,
    "min_price_usd": 1.0,
    "max_price_usd": 500.0,
    "poll_interval": 300,
    "max_alerts": 5,
    "min_float": "",
    "max_float": "",
}


def load() -> dict:
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {**DEFAULTS, **data}
        except Exception:
            pass
    return dict(DEFAULTS)


def save(settings: dict) -> None:
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
