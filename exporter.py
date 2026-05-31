"""
Export arbitrage history to CSV.
"""
import csv
import os
from datetime import datetime
from typing import List, Dict, Any


def export_csv(records: List[Dict[str, Any]], path: str | None = None) -> str:
    """
    Write records to a CSV file.
    Returns the path of the created file.
    """
    if path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(os.path.dirname(__file__), f"arb_history_{ts}.csv")

    fieldnames = ["time", "item", "buy_price", "sell_price",
                  "net_profit", "profit_pct", "listings", "float"]

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in records:
            writer.writerow({
                "time":       r.get("ts", ""),
                "item":       r.get("name", ""),
                "buy_price":  r.get("buy_price", ""),
                "sell_price": r.get("sell_price", ""),
                "net_profit": r.get("net_profit", ""),
                "profit_pct": r.get("profit_pct", ""),
                "listings":   r.get("qty", ""),
                "float":      r.get("float_value", ""),
            })
    return path
