from dataclasses import dataclass, field
from typing import Dict, List, Optional
import config

MIN_LIQUIDITY = 5   # minimum listings on Skinport to consider an item liquid

# CS2 float boundaries per wear category
FLOAT_RANGES = {
    "Factory New":    (0.00, 0.07),
    "Minimal Wear":   (0.07, 0.15),
    "Field-Tested":   (0.15, 0.38),
    "Well-Worn":      (0.38, 0.45),
    "Battle-Scarred": (0.45, 1.00),
}


def float_wear(f: float) -> str:
    for wear, (lo, hi) in FLOAT_RANGES.items():
        if lo <= f < hi:
            return wear
    return "Unknown"


@dataclass
class Opportunity:
    name: str
    buy_price: float              # purchase price on Skinport
    sell_price: float             # sell price on DMarket (before fee)
    sell_after_fee: float         # amount received after DMarket fee
    net_profit: float             # net profit in USD
    profit_pct: float             # profit in %
    qty: int                      # number of listings on Skinport (liquidity)
    float_value: Optional[float] = field(default=None)  # float of the DMarket listing

    @property
    def wear(self) -> str:
        if self.float_value is None:
            return "—"
        return float_wear(self.float_value)

    @property
    def float_str(self) -> str:
        if self.float_value is None:
            return "—"
        return f"{self.float_value:.4f} ({self.wear})"

    def __str__(self) -> str:
        return (
            f"{self.name}\n"
            f"  Buy  Skinport: ${self.buy_price:.2f} (listings: {self.qty})\n"
            f"  Sell DMarket:  ${self.sell_price:.2f} → ${self.sell_after_fee:.2f} after fee\n"
            f"  Profit:        ${self.net_profit:.2f} ({self.profit_pct:.1f}%)\n"
            f"  Float:         {self.float_str}"
        )


def find_opportunities(
    skinport: Dict[str, dict],
    dmarket: Dict[str, dict],
    min_profit_pct: float = config.MIN_PROFIT_PCT,
    min_price: float = config.MIN_PRICE_USD,
    max_price: float = config.MAX_PRICE_USD,
    min_liquidity: int = MIN_LIQUIDITY,
    max_float: Optional[float] = None,
    min_float: Optional[float] = None,
) -> List[Opportunity]:
    results: List[Opportunity] = []

    for name, sp_data in skinport.items():
        sp_price = sp_data["price"]
        qty = sp_data["qty"]

        if name not in dmarket:
            continue
        if not (min_price <= sp_price <= max_price):
            continue
        if qty < min_liquidity:
            continue

        dm_data = dmarket[name]
        dm_price = dm_data["price"]
        float_val = dm_data.get("float")

        # Float filter (only applied when set)
        if float_val is not None:
            if max_float is not None and float_val > max_float:
                continue
            if min_float is not None and float_val < min_float:
                continue

        sell_after_fee = dm_price * (1 - config.DMARKET_SELL_FEE)
        net_profit = sell_after_fee - sp_price
        profit_pct = (net_profit / sp_price) * 100

        if profit_pct >= min_profit_pct:
            results.append(Opportunity(
                name=name,
                buy_price=sp_price,
                sell_price=dm_price,
                sell_after_fee=sell_after_fee,
                net_profit=net_profit,
                profit_pct=profit_pct,
                qty=qty,
                float_value=float_val,
            ))

    results.sort(key=lambda o: o.profit_pct, reverse=True)
    return results
