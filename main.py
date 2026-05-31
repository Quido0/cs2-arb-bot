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
    logger.info("=== Запуск цикла сканирования ===")

    logger.info("Загружаем цены Skinport...")
    sp_prices = skinport.get_prices(currency="USD")
    if not sp_prices:
        logger.error("Skinport: пустой ответ, пропускаем цикл")
        return

    logger.info("Загружаем цены DMarket...")
    dm_prices = dmarket.get_prices(config.DMARKET_API_KEY)
    if not dm_prices:
        logger.error("DMarket: пустой ответ, пропускаем цикл")
        return

    logger.info(f"Ищем арбитраж (мин. профит {config.MIN_PROFIT_PCT}%)...")
    opportunities = find_opportunities(sp_prices, dm_prices)

    notify_opportunities(opportunities)
    logger.info(f"Цикл завершён. Следующий через {config.POLL_INTERVAL}с")


def main() -> None:
    logger.info("CS2 Arbitrage Bot запущен")
    logger.info(
        f"Настройки: мин. профит={config.MIN_PROFIT_PCT}%, "
        f"диапазон цен=${config.MIN_PRICE_USD}–${config.MAX_PRICE_USD}, "
        f"интервал={config.POLL_INTERVAL}с"
    )

    if not config.DMARKET_API_KEY:
        logger.warning("DMARKET_API_KEY не задан — DMarket будет недоступен")

    while True:
        try:
            run_cycle()
        except KeyboardInterrupt:
            logger.info("Остановлено пользователем")
            break
        except Exception as e:
            logger.exception(f"Неожиданная ошибка: {e}")

        time.sleep(config.POLL_INTERVAL)


if __name__ == "__main__":
    main()
