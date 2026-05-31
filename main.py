import logging
import time
import sys
from apis import skinport, dmarket
from arbitrage import find_opportunities
from notifier import notify_opportunities
import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("arb_bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("main")


def run_cycle() -> None:
    logger.info("=== Starting scan cycle ===")

    logger.info("Fetching Skinport prices...")
    sp_prices = skinport.get_prices(currency="USD")
    if not sp_prices:
        logger.error("Skinport: empty response, skipping cycle")
        return

    logger.info("Fetching DMarket prices...")
    dm_prices = dmarket.get_prices(config.DMARKET_API_KEY)
    if not dm_prices:
        logger.error("DMarket: empty response, check API key")
        return

    logger.info(f"Scanning for arbitrage (min profit {config.MIN_PROFIT_PCT}%)...")
    opportunities = find_opportunities(sp_prices, dm_prices)

    notify_opportunities(opportunities)
    logger.info(f"Cycle complete. Next scan in {config.POLL_INTERVAL}s")


def main() -> None:
    logger.info("CS2 Arbitrage Bot started")
    logger.info(
        f"Settings: min_profit={config.MIN_PROFIT_PCT}%, "
        f"price_range=${config.MIN_PRICE_USD}–${config.MAX_PRICE_USD}, "
        f"interval={config.POLL_INTERVAL}s"
    )

    if not config.DMARKET_API_KEY:
        logger.warning("DMARKET_API_KEY not set — DMarket will be unavailable")

    while True:
        try:
            run_cycle()
        except KeyboardInterrupt:
            logger.info("Stopped by user")
            break
        except Exception as e:
            logger.exception(f"Unexpected error: {e}")

        time.sleep(config.POLL_INTERVAL)


if __name__ == "__main__":
    main()
