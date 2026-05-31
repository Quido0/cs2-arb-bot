import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import threading
import queue
import time
import logging
import winsound
from datetime import datetime

import settings_manager
import db
import watchlist as wl
import exporter
from apis import skinport, dmarket
from arbitrage import find_opportunities, Opportunity
from notifier import notify_opportunities
from tg_commands import TelegramCommandListener, session as arb_session

# ── Logging bridge: forward logging records into the GUI queue ────────────────

class QueueHandler(logging.Handler):
    def __init__(self, q: queue.Queue):
        super().__init__()
        self.q = q

    def emit(self, record):
        self.q.put(("log", self.format(record)))


# ── Colours and fonts ─────────────────────────────────────────────────────────

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
        self._next_scan_at: float = 0        # timestamp of next scan
        self._sound_enabled: bool = True
        self._watchlist: list = wl.load()

        self._build_ui()
        self._apply_settings_to_ui()
        self._poll_queue()

        # Set up logging → GUI queue bridge
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        handler = QueueHandler(self.q)
        handler.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%H:%M:%S"))
        root_logger.addHandler(handler)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        header = tk.Frame(self, bg=ACCENT, pady=10)
        header.pack(fill="x")
        tk.Label(header, text="CS2 Arbitrage Bot", font=FONT_H,
                 bg=ACCENT, fg=TEXT).pack(side="left", padx=20)
        self.status_lbl = tk.Label(header, text="● Stopped", font=FONT_B,
                                   bg=ACCENT, fg=RED)
        self.status_lbl.pack(side="right", padx=20)
        self.timer_lbl = tk.Label(header, text="", font=FONT,
                                  bg=ACCENT, fg=TEXT_DIM)
        self.timer_lbl.pack(side="right", padx=10)
        self._tick_timer()

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=10, pady=10)

        self._build_left(body)
        self._build_right(body)

    def _build_left(self, parent):
        left = tk.Frame(parent, bg=BG2, bd=0, relief="flat", width=320)
        left.pack(side="left", fill="y", padx=(0, 8))
        left.pack_propagate(False)

        # API Keys
        self._section(left, "API Keys")
        self.dm_key_var   = self._field(left, "DMarket API Key", show="*")
        self.tg_token_var = self._field(left, "Telegram Bot Token", show="*")
        self.tg_chat_var  = self._field(left, "Telegram Chat ID")

        # Parameters
        self._section(left, "Parameters")
        self.min_profit_var = self._field(left, "Min profit (%)")
        self.min_price_var  = self._field(left, "Min price ($)")
        self.max_price_var  = self._field(left, "Max price ($)")
        self.interval_var   = self._field(left, "Interval (sec)")

        # Float filter
        self._section(left, "Float filter (0.00 – 1.00, empty = off)")
        self.min_float_var = self._field(left, "Float from")
        self.max_float_var = self._field(left, "Float to")

        # Auto-save on field change (1 s debounce)
        self._autosave_job = None
        for var in (self.min_profit_var, self.min_price_var,
                    self.max_price_var, self.interval_var,
                    self.min_float_var, self.max_float_var):
            var.trace_add("write", self._schedule_autosave)

        # Buttons
        btn_frame = tk.Frame(left, bg=BG2)
        btn_frame.pack(fill="x", padx=12, pady=12)

        self.start_btn = tk.Button(
            btn_frame, text="▶  Start", font=FONT_B,
            bg=GREEN, fg="#0f172a", activebackground="#22c55e",
            relief="flat", cursor="hand2", pady=6,
            command=self._start,
        )
        self.start_btn.pack(fill="x", pady=(0, 6))

        self.stop_btn = tk.Button(
            btn_frame, text="■  Stop", font=FONT_B,
            bg=RED, fg="#0f172a", activebackground="#ef4444",
            relief="flat", cursor="hand2", pady=6,
            state="disabled", command=self._stop,
        )
        self.stop_btn.pack(fill="x", pady=(0, 6))

        tk.Button(
            btn_frame, text="Save settings", font=FONT,
            bg=ACCENT, fg=TEXT, activebackground="#1e4080",
            relief="flat", cursor="hand2", pady=4,
            command=self._save_settings,
        ).pack(fill="x")

        # Sound toggle
        self._sound_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            left, text="🔔  Sound alert on find", variable=self._sound_var,
            font=FONT, bg=BG2, fg=TEXT_DIM, selectcolor=BG2,
            activebackground=BG2, activeforeground=TEXT,
            command=lambda: setattr(self, "_sound_enabled", self._sound_var.get()),
        ).pack(anchor="w", padx=12, pady=(8, 0))

        self.stats_lbl = tk.Label(left, text="Cycles: 0  |  Found: 0",
                                  font=FONT, bg=BG2, fg=TEXT_DIM)
        self.stats_lbl.pack(pady=(4, 0))
        self._cycles = 0
        self._total_found = 0

    def _build_right(self, parent):
        right = tk.Frame(parent, bg=BG)
        right.pack(side="left", fill="both", expand=True)

        self.notebook = ttk.Notebook(right)
        self.notebook.pack(fill="both", expand=True)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook",     background=BG,    borderwidth=0)
        style.configure("TNotebook.Tab", background=ACCENT, foreground=TEXT,
                        padding=[12, 4], font=FONT_B)
        style.map("TNotebook.Tab",       background=[("selected", BG2)])
        style.configure("Treeview",
                        background=BG2, foreground=TEXT,
                        fieldbackground=BG2, rowheight=24, font=FONT)
        style.configure("Treeview.Heading",
                        background=ACCENT, foreground=TEXT, font=FONT_B)
        style.map("Treeview", background=[("selected", "#0f3460")])

        # ── Tab 1: live opportunities + log ──
        tab1 = tk.Frame(self.notebook, bg=BG)
        self.notebook.add(tab1, text="  Opportunities  ")

        self._section_label(tab1, "Live opportunities")
        cols = ("Item", "Buy $", "Sell $", "Profit $", "Profit %", "Listings", "Float")
        self.tree = ttk.Treeview(tab1, columns=cols, show="headings", height=9)
        widths = (260, 75, 75, 75, 75, 75, 100)
        for col, w in zip(cols, widths):
            self.tree.heading(col, text=col)
            self.tree.column(col, width=w, anchor="center" if col != "Item" else "w")
        self.tree.pack(fill="x", pady=(0, 6))
        self.tree.tag_configure("good", foreground=GREEN)
        self.tree.tag_configure("ok",   foreground=YELLOW)

        self._section_label(tab1, "Log")
        self.log_box = scrolledtext.ScrolledText(
            tab1, font=("Consolas", 9), bg="#0d0d1a", fg=TEXT_DIM,
            insertbackground=TEXT, relief="flat", state="disabled",
        )
        self.log_box.pack(fill="both", expand=True)
        self.log_box.tag_config("info",  foreground=TEXT_DIM)
        self.log_box.tag_config("warn",  foreground=YELLOW)
        self.log_box.tag_config("error", foreground=RED)
        self.log_box.tag_config("ok",    foreground=GREEN)

        # ── Tab 2: SQLite history ──
        tab2 = tk.Frame(self.notebook, bg=BG)
        self.notebook.add(tab2, text="  History  ")
        self._build_history_tab(tab2)

        # ── Tab 3: Watchlist ──
        tab3 = tk.Frame(self.notebook, bg=BG)
        self.notebook.add(tab3, text="  Watchlist  ")
        self._build_watchlist_tab(tab3)

    def _build_history_tab(self, parent):
        self.hist_summary = tk.Label(
            parent, text="Loading...", font=FONT, bg=BG, fg=TEXT_DIM,
            justify="left", anchor="w",
        )
        self.hist_summary.pack(fill="x", pady=(4, 8))

        self._section_label(parent, "Top items all time")
        top_cols = ("Item", "Appearances", "Total profit $", "Avg profit %", "Avg buy $")
        self.top_tree = ttk.Treeview(parent, columns=top_cols, show="headings", height=7)
        top_widths = (300, 90, 110, 100, 90)
        for col, w in zip(top_cols, top_widths):
            self.top_tree.heading(col, text=col)
            self.top_tree.column(col, width=w, anchor="center" if col != "Item" else "w")
        self.top_tree.pack(fill="x", pady=(0, 8))

        self._section_label(parent, "Last 100 records")
        hist_cols = ("Time", "Item", "Buy $", "Profit $", "Profit %", "Float")
        self.hist_tree = ttk.Treeview(parent, columns=hist_cols, show="headings", height=8)
        hist_widths = (130, 260, 75, 75, 75, 100)
        for col, w in zip(hist_cols, hist_widths):
            self.hist_tree.heading(col, text=col)
            self.hist_tree.column(col, width=w, anchor="center" if col != "Item" else "w")
        self.hist_tree.pack(fill="both", expand=True)

        btn_row = tk.Frame(parent, bg=BG)
        btn_row.pack(pady=6)
        tk.Button(
            btn_row, text="↻ Refresh", font=FONT,
            bg=ACCENT, fg=TEXT, relief="flat", cursor="hand2",
            command=self._refresh_history,
        ).pack(side="left", padx=(0, 8))
        tk.Button(
            btn_row, text="⬇ Export CSV", font=FONT,
            bg=GREEN, fg="#0f172a", relief="flat", cursor="hand2",
            command=self._export_csv,
        ).pack(side="left")

        self._refresh_history()

    # ── UI helpers ────────────────────────────────────────────────────────────

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

    # ── Settings ──────────────────────────────────────────────────────────────

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
                "dmarket_api_key":    self.dm_key_var.get().strip(),
                "telegram_bot_token": self.tg_token_var.get().strip(),
                "telegram_chat_id":   self.tg_chat_var.get().strip(),
                "min_profit_pct":     float(self.min_profit_var.get()),
                "min_price_usd":      float(self.min_price_var.get()),
                "max_price_usd":      float(self.max_price_var.get()),
                "poll_interval":      int(self.interval_var.get()),
                "max_alerts":         self.settings.get("max_alerts", 5),
            }
        except ValueError as e:
            messagebox.showerror("Error", f"Invalid value: {e}")
            return None

    def _schedule_autosave(self, *_):
        """Debounced auto-save — waits 1 s after last keystroke."""
        if self._autosave_job:
            self.after_cancel(self._autosave_job)
        self._autosave_job = self.after(1000, self._autosave)

    def _autosave(self):
        """Silent save — skips if a field is still being typed."""
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
            pass  # field not fully typed yet

    def _save_settings(self):
        s = self._collect_settings()
        if s:
            self.settings = s
            settings_manager.save(s)
            self._log("Settings saved", "ok")

    # ── Bot thread ────────────────────────────────────────────────────────────

    def _start(self):
        s = self._collect_settings()
        if not s:
            return
        if not s["dmarket_api_key"]:
            messagebox.showwarning("Warning", "DMarket API Key is not set")
            return
        self.settings = s
        settings_manager.save(s)

        self._running = True
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.status_lbl.config(text="● Running", fg=GREEN)

        # Reset session stats
        arb_session.reset()

        # Start Telegram command listener if credentials are set
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
        self.status_lbl.config(text="● Stopped", fg=RED)

    def _bot_loop(self):
        logger = logging.getLogger("bot")
        s = self.settings

        while self._running:
            logger.info("=== Starting scan cycle ===")

            logger.info("Fetching Skinport prices...")
            sp = skinport.get_prices("USD")
            if not sp:
                logger.error("Skinport: empty response")
                self._sleep_interruptible(60)
                continue

            logger.info("Fetching DMarket prices...")
            dm = dmarket.get_prices(s["dmarket_api_key"])
            if not dm:
                logger.error("DMarket: empty response — check API key")
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

            # Accumulate for /potential command
            arb_session.add(opps)

            # Persist to SQLite
            if opps:
                db.save_opportunities(opps)
                self.q.put(("refresh_history", None))

            if opps:
                import config as cfg
                cfg.TELEGRAM_BOT_TOKEN = s["telegram_bot_token"]
                cfg.TELEGRAM_CHAT_ID   = s["telegram_chat_id"]
                notify_opportunities(opps, max_alerts=s["max_alerts"])
                self.q.put(("sound", None))
            else:
                logger.info("No opportunities found")

            # Check watchlist hits (no profit filter)
            if self._watchlist:
                hits = wl.check_hits(sp, dm, self._watchlist)
                self.q.put(("watchlist_hits", hits))
                for h in hits:
                    if h["profit"] > 0:
                        logger.info(
                            f"[Watchlist] {h['name']} — "
                            f"buy ${h['buy']:.2f} / sell ${h['sell']:.2f} / "
                            f"profit ${h['profit']:.2f} ({h['pct']:.1f}%)"
                        )

            interval = s["poll_interval"]
            self._next_scan_at = time.time() + interval
            logger.info(f"Next scan in {interval}s")
            self._sleep_interruptible(interval)

    def _sleep_interruptible(self, seconds: int):
        for _ in range(seconds):
            if not self._running:
                break
            time.sleep(1)

    # ── Queue pump: bot thread → UI ───────────────────────────────────────────

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
                    self.stats_lbl.config(text=f"Cycles: {cycles}  |  Found: {found}")
                elif kind == "refresh_history":
                    self._refresh_history()
                elif kind == "sound":
                    self._play_alert()
                elif kind == "watchlist_hits":
                    self._wl_refresh_table(data)
        except queue.Empty:
            pass
        self.after(200, self._poll_queue)

    def _log(self, text: str, tag: str = "info"):
        if "ERROR" in text or "error" in text.lower():
            tag = "error"
        elif "WARNING" in text or "warning" in text.lower():
            tag = "warn"
        elif "found" in text.lower() or "loaded" in text.lower() or "saved" in text.lower():
            tag = "ok"

        self.log_box.config(state="normal")
        self.log_box.insert("end", text + "\n", tag)
        self.log_box.see("end")
        self.log_box.config(state="disabled")

    def _update_table(self, opps: list):
        for row in self.tree.get_children():
            self.tree.delete(row)

        for opp in opps[:50]:
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
                    f"Records: {summary['total']}  |  "
                    f"Unique items: {summary['unique_items']}  |  "
                    f"Total potential: ${summary['total_profit']}  |  "
                    f"Avg profit: {summary['avg_pct']}%  |  "
                    f"Best: {summary['best_pct']}%"
                )
            )
        else:
            self.hist_summary.config(text="History is empty — start the bot")

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

    def _build_watchlist_tab(self, parent):
        self._section_label(parent, "Watched items — always alerted regardless of profit %")

        # Input row
        input_row = tk.Frame(parent, bg=BG)
        input_row.pack(fill="x", pady=(0, 8))
        self._wl_entry_var = tk.StringVar()
        tk.Entry(
            input_row, textvariable=self._wl_entry_var,
            font=FONT, bg="#0d0d1a", fg=TEXT, insertbackground=TEXT,
            relief="flat", width=50,
        ).pack(side="left", ipady=4, padx=(0, 8))
        tk.Button(
            input_row, text="+ Add", font=FONT_B,
            bg=GREEN, fg="#0f172a", relief="flat", cursor="hand2",
            command=self._wl_add,
        ).pack(side="left", padx=(0, 4))
        tk.Button(
            input_row, text="✕ Remove selected", font=FONT,
            bg=RED, fg="#0f172a", relief="flat", cursor="hand2",
            command=self._wl_remove,
        ).pack(side="left")

        # Watchlist table (name + last seen prices)
        wl_cols = ("Item", "Skinport $", "DMarket $", "Profit $", "Profit %", "Last seen")
        self.wl_tree = ttk.Treeview(parent, columns=wl_cols, show="headings", height=10)
        wl_widths = (300, 90, 90, 80, 80, 140)
        for col, w in zip(wl_cols, wl_widths):
            self.wl_tree.heading(col, text=col)
            self.wl_tree.column(col, width=w, anchor="center" if col != "Item" else "w")
        self.wl_tree.pack(fill="both", expand=True)
        self.wl_tree.tag_configure("profit", foreground=GREEN)
        self.wl_tree.tag_configure("loss",   foreground=RED)

        self._wl_refresh_table()

    def _wl_add(self):
        name = self._wl_entry_var.get().strip()
        if not name:
            return
        if name not in self._watchlist:
            self._watchlist.append(name)
            wl.save(self._watchlist)
            self._wl_entry_var.set("")
            self._wl_refresh_table()
            self._log(f"Watchlist: added '{name}'", "ok")

    def _wl_remove(self):
        selected = self.wl_tree.selection()
        if not selected:
            return
        for item_id in selected:
            name = self.wl_tree.item(item_id, "values")[0]
            if name in self._watchlist:
                self._watchlist.remove(name)
        wl.save(self._watchlist)
        self._wl_refresh_table()

    def _wl_refresh_table(self, hits: list | None = None):
        for row in self.wl_tree.get_children():
            self.wl_tree.delete(row)
        # Build a lookup from latest hits if provided
        hit_map = {h["name"]: h for h in (hits or [])}
        for name in self._watchlist:
            h = hit_map.get(name)
            if h:
                tag = "profit" if h["profit"] > 0 else "loss"
                self.wl_tree.insert("", "end", values=(
                    name,
                    f"${h['buy']:.2f}",
                    f"${h['sell']:.2f}",
                    f"${h['profit']:.2f}",
                    f"{h['pct']:.1f}%",
                    datetime.now().strftime("%H:%M:%S"),
                ), tags=(tag,))
            else:
                self.wl_tree.insert("", "end", values=(
                    name, "—", "—", "—", "—", "not seen yet"
                ))

    # ── Export CSV ────────────────────────────────────────────────────────────

    def _export_csv(self):
        records = db.get_recent(limit=0)   # 0 = all records
        if not records:
            messagebox.showinfo("Export", "History is empty — nothing to export")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=f"arb_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        )
        if not path:
            return
        exporter.export_csv(records, path)
        self._log(f"Exported {len(records)} records → {path}", "ok")
        messagebox.showinfo("Export", f"Saved {len(records)} records to:\n{path}")

    # ── Countdown timer ───────────────────────────────────────────────────────

    def _tick_timer(self):
        if self._running and self._next_scan_at > 0:
            remaining = max(0, int(self._next_scan_at - time.time()))
            m, s = divmod(remaining, 60)
            self.timer_lbl.config(text=f"Next scan: {m}:{s:02d}")
        else:
            self.timer_lbl.config(text="")
        self.after(1000, self._tick_timer)

    # ── Sound alert ───────────────────────────────────────────────────────────

    def _play_alert(self):
        if self._sound_enabled:
            try:
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            except Exception:
                pass

    # ── Close ─────────────────────────────────────────────────────────────────

    def _on_close(self):
        self._running = False
        self.destroy()


def main():
    app = ArbBot()
    app.mainloop()


if __name__ == "__main__":
    main()
