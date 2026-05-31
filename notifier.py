import logging
import requests
from typing import List
from arbitrage import Opportunity
import config

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def send_telegram(message: str) -> bool:
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        logger.warning("Telegram not configured — printing to console")
        print(message)
        return False
    try:
        r = requests.post(
            TELEGRAM_API.format(token=config.TELEGRAM_BOT_TOKEN),
            json={
                "chat_id": config.TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
            },
            timeout=10,
        )
        r.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Telegram error: {e}")
        return False


def format_opportunity(opp: Opportunity) -> str:
    liquidity = "🟢 Liquid" if opp.qty >= 20 else "🟡 Medium" if opp.qty >= 5 else "🔴 Low"
    float_line = f"\nFloat:      <code>{opp.float_str}</code>" if opp.float_value else ""
    return (
        f"<b>Arbitrage found</b>\n\n"
        f"<b>{opp.name}</b>\n"
        f"Buy  Skinport:  <b>${opp.buy_price:.2f}</b>\n"
        f"Sell DMarket:   <b>${opp.sell_price:.2f}</b> → ${opp.sell_after_fee:.2f}\n"
        f"Net profit:     <b>${opp.net_profit:.2f} ({opp.profit_pct:.1f}%)</b>\n"
        f"Listings:       {opp.qty} — {liquidity}"
        f"{float_line}"
    )


def notify_opportunities(opportunities: List[Opportunity], max_alerts: int = config.MAX_ALERTS) -> None:
    if not opportunities:
        logger.info("No arbitrage opportunities found")
        return

    logger.info(f"Found {len(opportunities)} opportunities, sending top {min(len(opportunities), max_alerts)}")
    for opp in opportunities[:max_alerts]:
        send_telegram(format_opportunity(opp))
