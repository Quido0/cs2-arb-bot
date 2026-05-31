"""
Слушает команды от пользователя в Telegram (long polling).
Поддерживает /potential — статистика потенциального профита за сессию.
"""
import requests
import logging
import time
import threading
from datetime import datetime
from typing import List
from arbitrage import Opportunity

logger = logging.getLogger(__name__)

# ── Хранилище сессии ──────────────────────────────────────────────────────────

class SessionStats:
    def __init__(self):
        self._lock = threading.Lock()
        self.started_at: datetime = datetime.now()
        self.all_opps: List[Opportunity] = []   # все найденные возможности
        self.cycles: int = 0

    def add(self, opps: List[Opportunity]):
        with self._lock:
            self.all_opps.extend(opps)
            self.cycles += 1

    def reset(self):
        with self._lock:
            self.all_opps.clear()
            self.cycles = 0
            self.started_at = datetime.now()

    def snapshot(self):
        with self._lock:
            return list(self.all_opps), self.cycles, self.started_at


# Глобальный объект — используется из gui.py и этого модуля
session = SessionStats()


# ── Telegram polling ──────────────────────────────────────────────────────────

class TelegramCommandListener:
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = str(chat_id)
        self.api = f"https://api.telegram.org/bot{token}"
        self._offset = 0
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        logger.info("Telegram команды: слушаем /potential")

    def stop(self):
        self._running = False

    def _poll_loop(self):
        fail_count = 0
        while self._running:
            try:
                updates = self._get_updates()
                for upd in updates:
                    self._handle(upd)
                fail_count = 0          # сброс при успехе
                time.sleep(2)
            except Exception as e:
                fail_count += 1
                # Логируем только первую ошибку подряд, потом молчим
                if fail_count == 1:
                    logger.warning(f"Telegram недоступен, жду восстановления... ({e})")
                # Экспоненциальная пауза: 5с → 10с → 20с → макс 60с
                wait = min(5 * (2 ** (fail_count - 1)), 60)
                time.sleep(wait)

    def _get_updates(self) -> list:
        r = requests.get(
            f"{self.api}/getUpdates",
            params={"offset": self._offset, "timeout": 10},
            timeout=15,
        )
        data = r.json()
        updates = data.get("result", [])
        if updates:
            self._offset = updates[-1]["update_id"] + 1
        return updates

    def _handle(self, upd: dict):
        msg = upd.get("message", {})
        text = msg.get("text", "").strip().lower()
        from_id = str(msg.get("chat", {}).get("id", ""))

        # Отвечаем только своему chat_id
        if from_id != self.chat_id:
            return

        if text == "/potential":
            self._send(self._build_potential_report())
        elif text == "/start":
            self._send(
                "CS2 Arb Bot активен.\n\n"
                "/potential — потенциальный профит за сессию"
            )

    def _build_potential_report(self) -> str:
        opps, cycles, started_at = session.snapshot()

        if not opps:
            elapsed = _fmt_elapsed(started_at)
            return (
                f"За текущую сессию ({elapsed}) "
                f"возможностей пока не найдено.\n"
                f"Циклов сканирования: {cycles}"
            )

        total_invested = sum(o.buy_price for o in opps)
        total_profit   = sum(o.net_profit for o in opps)
        avg_pct        = sum(o.profit_pct for o in opps) / len(opps)
        best           = max(opps, key=lambda o: o.profit_pct)
        elapsed        = _fmt_elapsed(started_at)

        # Топ-5 по профиту
        top5 = sorted(opps, key=lambda o: o.net_profit, reverse=True)[:5]
        top5_lines = "\n".join(
            f"  • {o.name[:35]}: +${o.net_profit:.2f} ({o.profit_pct:.1f}%)"
            for o in top5
        )

        return (
            f"<b>Потенциал сессии</b>\n"
            f"Время: {elapsed} | Циклов: {cycles}\n\n"
            f"Возможностей найдено: <b>{len(opps)}</b>\n"
            f"Суммарно инвестиций: <b>${total_invested:.2f}</b>\n"
            f"Суммарный профит:    <b>${total_profit:.2f}</b>\n"
            f"Средний профит:      <b>{avg_pct:.1f}%</b>\n\n"
            f"Лучшая сделка: <b>{best.name[:40]}</b>\n"
            f"  +${best.net_profit:.2f} ({best.profit_pct:.1f}%)\n\n"
            f"Топ-5 по сумме профита:\n{top5_lines}"
        )

    def _send(self, text: str):
        try:
            requests.post(
                f"{self.api}/sendMessage",
                json={"chat_id": self.chat_id, "text": text, "parse_mode": "HTML"},
                timeout=10,
            )
        except Exception as e:
            logger.error(f"Telegram отправка ошибка: {e}")


def _fmt_elapsed(since: datetime) -> str:
    delta = datetime.now() - since
    h, rem = divmod(int(delta.total_seconds()), 3600)
    m, s   = divmod(rem, 60)
    if h:
        return f"{h}ч {m}м"
    if m:
        return f"{m}м {s}с"
    return f"{s}с"
