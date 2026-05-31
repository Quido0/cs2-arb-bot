"""
Watchlist — user-defined items to monitor regardless of profit threshold.
Stored in watchlist.json next to the executable.
"""
import json
import os
from typing import List

WATCHLIST_FILE = os.path.join(os.path.dirname(__file__), "watchlist.json")


def load() -> List[str]:
    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [str(x).strip() for x in data if x]
        except Exception:
            pass
    return []


def save(items: List[str]) -> None:
    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)


def check_hits(skinport: dict, dmarket: dict, watchlist: List[str]) -> List[dict]:
    """
    Returns price info for every watchlist item that exists on both platforms,
    regardless of profit percentage.
    """
    hits = []
    for name in watchlist:
        sp = skinport.get(name)
        dm = dmarket.get(name)
        if not sp or not dm:
            continue
        buy  = sp["price"]
        sell = dm["price"]
        sell_after = sell * (1 - 0.025)
        profit     = sell_after - buy
        pct        = (profit / buy) * 100 if buy else 0
        hits.append({
            "name":    name,
            "buy":     buy,
            "sell":    sell,
            "profit":  round(profit, 2),
            "pct":     round(pct, 1),
            "on_sp":   True,
            "on_dm":   True,
        })
    return hits
