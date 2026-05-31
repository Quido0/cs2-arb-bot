import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import queue
import time
import logging
from datetime import datetime

import settings_manager
import db
from apis import skinport, dmarket
from arbitrage import find_opportunities, Opportunity
from notifier import notify_opportunities
from tg_commands import TelegramCommandListener, session as arb_session

# ── Logging bridge: перенаправляем logging в GUI-очередь ──────────────────────

class QueueHandler(logging.Handler):
    def __init__(self, q: queue.Queue):
        super().__init__()
        self.q = q

    def emit(self, record):
        self.q.put(("log", self.format(record)))


# ── Цвета и шрифты ────────────────────────────────────────────────────────────

BG       = "#1a1a2e"
BG2      = "#16213e"
ACCENT   = "#0f3460"
GREEN    = "#4ade80"
RED      = "#f87171"
YELLOW   = "#fbbf24"
TEXT     = "#e2e8f0"
TEXT_DIM = "#94a3b8"
FONT     = ("Consolas", 10)
FONT_B   = ("Consolas", 10, "bold")
FONT_H   = ("Consolas", 13, "bold")


class ArbBot(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("CS2 Arbitrage Bot")
        self.geometry("1000x700")
        self.minsize(800, 560)
        self.configure(bg=BG)

        self.settings = settings_manager.load()
        self.q: queue.Queue = queue.Queue()
        self._running = False
        self._thread: threading.Thread | None = None
        self._tg_listener: TelegramCommandListener | None = None

        self._build_ui()
        self._apply_settings_to_ui()
        self._poll_queue()

        # Настраиваем logging
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        handler = QueueHandler(self.q)
        handler.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%H:%M:%S"))
        root_logger.addHandler(handler)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Заголовок
        header = tk.Frame(self, bg=ACCENT, pady=10)
        header.pack(fill="x")
        tk.Label(header, text="CS2 Arbitrage Bot", font=FONT_H,
                 bg=ACCENT, fg=TEXT).pack(side="left", padx=20)
        self.status_lbl = tk.Label(header, text="● Остановлен", font=FONT_B,
                                   bg=ACCENT, fg=RED)
        self.status_lbl.pack(side="right", padx=20)

        # Основная область: левая панель + правая панель
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=10, pady=10)

        self._build_left(body)
        self._build_right(body)

    def _build_left(self, parent):
        left = tk.Frame(parent, bg=BG2, bd=0, relief="flat", width=320)
        left.pack(side="left", fill="y", padx=(0, 8))
        left.pack_propagate(False)

        # API ключи
        self._section(left, "API Ключи")
        self.dm_key_var = self._field(left, "DMarket API Key", show="*")
        self.tg_token_var = self._field(left, "Telegram Bot Token", show="*")
        self.tg_chat_var = self._field(left, "Telegram Chat ID")

        # Параметры
        self._section(left, "Параметры")
        self.min_profit_var = self._field(left, "Мин. профит (%)")
        self.min_price_var  = self._field(left, "Мин. цена ($)")
        self.max_price_var  = self._field(left, "Макс. цена ($)")
        self.interval_var   = self._field(left, "Интервал (сек)")

        # Float-фильтр
        self._section(left, "Float-фильтр (0.00 – 1.00, пусто = выкл)")
        self.min_float_var = self._field(left, "Float от")
        self.max_float_var = self._field(left, "Float до")

        # Автосохранение при изменении параметров (дебаунс 1 сек)
        self._autosave_job = None
        for var in (self.min_profit_var, self.min_price_var,
                    self.max_price_var, self.interval_var,
                    self.min_float_var, self.max_float_var):
            var.trace_add("write", self._schedule_autosave)

        # Кнопки
        btn_frame = tk.Frame(left, bg=BG2)
        btn_frame.pack(fill="x", padx=12, pady=12)

        self.start_btn = tk.Button(
            btn_frame, text="▶  Запустить", font=FONT_B,
            bg=GREEN, fg="#0f172a", activebackground="#22c55e",
            relief="flat", cursor="hand2", pady=6,
            command=self._start,
        )
        self.start_btn.pack(fill="x", pady=(0, 6))

        self.stop_btn = tk.Button(
            btn_frame, text="■  Остановить", font=FONT_B,
            bg=RED, fg="#0f172a", activebackground="#ef4444",
            relief="flat", cursor="hand2", pady=6,
            state="disabled", command=self._stop,
        )
        self.stop_btn.pack(fill="x", pady=(0, 6))

        tk.Button(
            btn_frame, text="Сохранить настройки", font=FONT,
            bg=ACCENT, fg=TEXT, activebackground="#1e4080",
            relief="flat", cursor="hand2", pady=4,
            command=self._save_settings,
        ).pack(fill="x")

        # Счётчик
        self.stats_lbl = tk.Label(left, text="Циклов: 0  |  Найдено: 0",
                                  font=FONT, bg=BG2, fg=TEXT_DIM)
        self.stats_lbl.pack(pady=(4, 0))
        self._cycles = 0
        self._total_found = 0

    def _build_right(self, parent):
        right = tk.Frame(parent, bg=BG)
        right.pack(side="left", fill="both", expand=True)

        # Вкладки
        self.notebook = ttk.Notebook(right)
        self.notebook.pack(fill="both", expand=True)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook",        background=BG,    borderwidth=0)
        style.configure("TNotebook.Tab",    background=ACCENT, foreground=TEXT,
                        padding=[12, 4],   font=FONT_B)
        style.map("TNotebook.Tab",          background=[("selected", BG2)])
        style.configure("Treeview",
                        background=BG2, foreground=TEXT,
                        fieldbackground=BG2, rowheight=24, font=FONT)
        style.configure("Treeview.Heading",
                        background=ACCENT, foreground=TEXT, font=FONT_B)
        style.map("Treeview", background=[("selected", "#0f3460")])

        # ── Вкладка 1: текущие возможности + лог ──
        tab1 = tk.Frame(self.notebook, bg=BG)
        self.notebook.add(tab1, text="  Возможности  ")

        self._section_label(tab1, "Найденные возможности")
        cols = ("Предмет", "Купить $", "Продать $", "Профит $", "Профит %", "Листингов", "Float")
        self.tree = ttk.Treeview(tab1, columns=cols, show="headings", height=9)
        widths = (260, 75, 75, 75, 75, 75, 100)
        for col, w in zip(cols, widths):
            self.tree.heading(col, text=col)
            self.tree.column(col, width=w, anchor="center" if col != "Предмет" else "w")
        self.tree.pack(fill="x", pady=(0, 6))
        self.tree.tag_configure("good", foreground=GREEN)
        self.tree.tag_configure("ok",   foreground=YELLOW)

        self._section_label(tab1, "Лог")
        self.log_box = scrolledtext.ScrolledText(
            tab1, font=("Consolas", 9), bg="#0d0d1a", fg=TEXT_DIM,
            insertbackground=TEXT, relief="flat", state="disabled",
        )
        self.log_box.pack(fill="both", expand=True)
        self.log_box.tag_config("info",  foreground=TEXT_DIM)
        self.log_box.tag_config("warn",  foreground=YELLOW)
        self.log_box.tag_config("error", foreground=RED)
        self.log_box.tag_config("ok",    foreground=GREEN)

        # ── Вкладка 2: история из БД ──
        tab2 = tk.Frame(self.notebook, bg=BG)
        self.notebook.add(tab2, text="  История  ")
        self._build_history_tab(tab2)

    def _build_history_tab(self, parent):
        # Статистика
        self.hist_summary = tk.Label(
            parent, text="Загрузка...", font=FONT, bg=BG, fg=TEXT_DIM,
            justify="left", anchor="w",
        )
        self.hist_summary.pack(fill="x", pady=(4, 8))

        # Топ предметов
        self._section_label(parent, "Топ предметов за всё время")
        top_cols = ("Предмет", "Появлений", "Сумм. профит $", "Ср. профит %", "Ср. цена $")
        self.top_tree = ttk.Treeview(parent, columns=top_cols, show="headings", height=7)
        top_widths = (300, 90, 110, 100, 90)
        for col, w in zip(top_cols, top_widths):
            self.top_tree.heading(col, text=col)
            self.top_tree.column(col, width=w, anchor="center" if col != "Предмет" else "w")
        self.top_tree.pack(fill="x", pady=(0, 8))

        # Последние записи
        self._section_label(parent, "Последние 100 записей")
        hist_cols = ("Время", "Предмет", "Купить $", "Профит $", "Профит %", "Float")
        self.hist_tree = ttk.Treeview(parent, columns=hist_cols, show="headings", height=8)
        hist_widths = (130, 260, 75, 75, 75, 100)
        for col, w in zip(hist_cols, hist_widths):
            self.hist_tree.heading(col, text=col)
            self.hist_tree.column(col, width=w, anchor="center" if col != "Предмет" else "w")
        self.hist_tree.pack(fill="both", expand=True)

        tk.Button(
            parent, text="↻ Обновить историю", font=FONT,
            bg=ACCENT, fg=TEXT, relief="flat", cursor="hand2",
            command=self._refresh_history,
        ).pack(pady=6)

        self._refresh_history()

    # ── Хелперы UI ────────────────────────────────────────────────────────────

    def _section(self, parent, text):
        tk.Label(parent, text=text, font=FONT_B, bg=BG2,
                 fg=YELLOW).pack(anchor="w", padx=12, pady=(12, 2))

    def _section_label(self, parent, text):
        tk.Label(parent, text=text, font=FONT_B, bg=BG,
                 fg=YELLOW).pack(anchor="w", pady=(0, 4))

    def _field(self, parent, label: str, show: str = "") -> tk.StringVar:
        tk.Label(parent, text=label, font=FONT, bg=BG2,
                 fg=TEXT_DIM).pack(anchor="w", padx=12)
        var = tk.StringVar()
        e = tk.Entry(parent, textvariable=var, font=FONT,
                     bg="#0d0d1a", fg=TEXT, insertbackground=TEXT,
                     relief="flat", show=show)
        e.pack(fill="x", padx=12, pady=(0, 6), ipady=4)
        return var

    # ── Настройки ─────────────────────────────────────────────────────────────

    def _apply_settings_to_ui(self):
        s = self.settings
        self.dm_key_var.set(s["dmarket_api_key"])
        self.tg_token_var.set(s["telegram_bot_token"])
        self.tg_chat_var.set(s["telegram_chat_id"])
        self.min_profit_var.set(str(s["min_profit_pct"]))
        self.min_price_var.set(str(s["min_price_usd"]))
        self.max_price_var.set(str(s["max_price_usd"]))
        self.interval_var.set(str(s["poll_interval"]))
        self.min_float_var.set(str(s.get("min_float", "")))
        self.max_float_var.set(str(s.get("max_float", "")))

    def _collect_settings(self) -> dict | None:
        try:
            return {
                "dmarket_api_key":   self.dm_key_var.get().strip(),
                "telegram_bot_token": self.tg_token_var.get().strip(),
                "telegram_chat_id":  self.tg_chat_var.get().strip(),
                "min_profit_pct":    float(self.min_profit_var.get()),
                "min_price_usd":     float(self.min_price_var.get()),
                "max_price_usd":     float(self.max_price_var.get()),
                "poll_interval":     int(self.interval_var.get()),
                "max_alerts":        self.settings.get("max_alerts", 5),
            }
        except ValueError as e:
            messagebox.showerror("Ошибка", f"Неверное значение: {e}")
            return None

    def _schedule_autosave(self, *_):
        """Откладывает сохранение на 1 сек — если снова пишут, сбрасывает таймер."""
        if self._autosave_job:
            self.after_cancel(self._autosave_job)
        self._autosave_job = self.after(1000, self._autosave)

    def _autosave(self):
        """Тихое сохранение без сообщения об ошибке если поле не заполнено до конца."""
        try:
            min_f = self.min_float_var.get().strip()
            max_f = self.max_float_var.get().strip()
            s = {
                "dmarket_api_key":    self.dm_key_var.get().strip(),
                "telegram_bot_token": self.tg_token_var.get().strip(),
                "telegram_chat_id":   self.tg_chat_var.get().strip(),
                "min_profit_pct":     float(self.min_profit_var.get()),
                "min_price_usd":      float(self.min_price_var.get()),
                "max_price_usd":      float(self.max_price_var.get()),
                "poll_interval":      int(self.interval_var.get()),
                "max_alerts":         self.settings.get("max_alerts", 5),
                "min_float":          float(min_f) if min_f else "",
                "max_float":          float(max_f) if max_f else "",
            }
            self.settings = s
            settings_manager.save(s)
        except ValueError:
            pass  # поле ещё не дописано — просто ждём

    def _save_settings(self):
        s = self._collect_settings()
        if s:
            self.settings = s
            settings_manager.save(s)
            self._log("Настройки сохранены", "ok")

    # ── Бот-поток ─────────────────────────────────────────────────────────────

    def _start(self):
        s = self._collect_settings()
        if not s:
            return
        if not s["dmarket_api_key"]:
            messagebox.showwarning("Предупреждение", "DMarket API Key не заполнен")
            return
        self.settings = s
        settings_manager.save(s)

        self._running = True
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.status_lbl.config(text="● Работает", fg=GREEN)

        # Сбрасываем статистику сессии
        arb_session.reset()

        # Запускаем слушатель Telegram-команд если токен задан
        self._tg_listener = None
        if s["telegram_bot_token"] and s["telegram_chat_id"]:
            self._tg_listener = TelegramCommandListener(
                s["telegram_bot_token"], s["telegram_chat_id"]
            )
            self._tg_listener.start()

        self._thread = threading.Thread(target=self._bot_loop, daemon=True)
        self._thread.start()

    def _stop(self):
        self._running = False
        if self._tg_listener:
            self._tg_listener.stop()
            self._tg_listener = None
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.status_lbl.config(text="● Остановлен", fg=RED)

    def _bot_loop(self):
        logger = logging.getLogger("bot")
        s = self.settings

        while self._running:
            logger.info("=== Запуск сканирования ===")

            logger.info("Загружаем Skinport...")
            sp = skinport.get_prices("USD")
            if not sp:
                logger.error("Skinport: пустой ответ")
                self._sleep_interruptible(60)
                continue

            logger.info("Загружаем DMarket...")
            dm = dmarket.get_prices(s["dmarket_api_key"])
            if not dm:
                logger.error("DMarket: пустой ответ — проверь API Key")
                self._sleep_interruptible(60)
                continue

            min_f = s.get("min_float")
            max_f = s.get("max_float")
            opps = find_opportunities(
                sp, dm,
                min_profit_pct=s["min_profit_pct"],
                min_price=s["min_price_usd"],
                max_price=s["max_price_usd"],
                min_float=float(min_f) if min_f else None,
                max_float=float(max_f) if max_f else None,
            )

            self._cycles += 1
            self._total_found += len(opps)
            self.q.put(("opportunities", opps))
            self.q.put(("stats", (self._cycles, self._total_found)))

            # Накапливаем в статистику сессии для /potential
            arb_session.add(opps)

            # Сохраняем в SQLite
            if opps:
                db.save_opportunities(opps)
                self.q.put(("refresh_history", None))

            if opps:
                # Telegram-алерты с настройками из UI
                import config as cfg
                cfg.TELEGRAM_BOT_TOKEN = s["telegram_bot_token"]
                cfg.TELEGRAM_CHAT_ID   = s["telegram_chat_id"]
                notify_opportunities(opps, max_alerts=s["max_alerts"])
            else:
                logger.info("Возможностей не найдено")

            logger.info(f"Следующий цикл через {s['poll_interval']}с")
            self._sleep_interruptible(s["poll_interval"])

    def _sleep_interruptible(self, seconds: int):
        for _ in range(seconds):
            if not self._running:
                break
            time.sleep(1)

    # ── Очередь сообщений из потока → UI ──────────────────────────────────────

    def _poll_queue(self):
        try:
            while True:
                kind, data = self.q.get_nowait()
                if kind == "log":
                    self._log(data)
                elif kind == "opportunities":
                    self._update_table(data)
                elif kind == "stats":
                    cycles, found = data
                    self.stats_lbl.config(text=f"Циклов: {cycles}  |  Найдено всего: {found}")
                elif kind == "refresh_history":
                    self._refresh_history()
        except queue.Empty:
            pass
        self.after(200, self._poll_queue)

    def _log(self, text: str, tag: str = "info"):
        if "ERROR" in text or "ошибка" in text.lower():
            tag = "error"
        elif "WARNING" in text or "предупреждение" in text.lower():
            tag = "warn"
        elif "найден" in text.lower() or "OK" in text or "сохранен" in text.lower():
            tag = "ok"

        self.log_box.config(state="normal")
        self.log_box.insert("end", text + "\n", tag)
        self.log_box.see("end")
        self.log_box.config(state="disabled")

    def _update_table(self, opps: list):
        # Очищаем
        for row in self.tree.get_children():
            self.tree.delete(row)

        for opp in opps[:50]:  # показываем топ-50 в таблице
            tag = "good" if opp.profit_pct >= 25 else "ok"
            self.tree.insert("", "end", values=(
                opp.name,
                f"${opp.buy_price:.2f}",
                f"${opp.sell_price:.2f}",
                f"${opp.net_profit:.2f}",
                f"{opp.profit_pct:.1f}%",
                opp.qty,
                opp.float_str,
            ), tags=(tag,))

    def _refresh_history(self):
        summary = db.get_summary()
        if summary.get("total"):
            self.hist_summary.config(
                text=(
                    f"Всего записей: {summary['total']}  |  "
                    f"Уникальных предметов: {summary['unique_items']}  |  "
                    f"Суммарный потенциал: ${summary['total_profit']}  |  "
                    f"Средний профит: {summary['avg_pct']}%  |  "
                    f"Лучший: {summary['best_pct']}%"
                )
            )
        else:
            self.hist_summary.config(text="История пуста — запусти бота")

        # Топ предметов
        for row in self.top_tree.get_children():
            self.top_tree.delete(row)
        for item in db.get_top_items(10):
            self.top_tree.insert("", "end", values=(
                item["name"],
                item["appearances"],
                f"${item['total_profit']}",
                f"{item['avg_pct']}%",
                f"${item['avg_buy']}",
            ))

        # Последние записи
        for row in self.hist_tree.get_children():
            self.hist_tree.delete(row)
        for rec in db.get_recent(100):
            fv = f"{rec['float_value']:.4f}" if rec.get("float_value") else "—"
            self.hist_tree.insert("", "end", values=(
                rec["ts"],
                rec["name"],
                f"${rec['buy_price']:.2f}",
                f"${rec['net_profit']:.2f}",
                f"{rec['profit_pct']:.1f}%",
                fv,
            ))

    # ── Закрытие ──────────────────────────────────────────────────────────────

    def _on_close(self):
        self._running = False
        self.destroy()


def main():
    app = ArbBot()
    app.mainloop()


if __name__ == "__main__":
    main()
