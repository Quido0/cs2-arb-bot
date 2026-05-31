# CS2 Arbitrage Bot

A CS2 skin arbitrage bot that monitors price gaps between **Skinport** and **DMarket**, sends Telegram alerts, and stores history in SQLite.

![demo](assets/demo.gif)

---

## How it works

CS2 skins trade on dozens of platforms simultaneously. The price of the same item can differ by 10–30%. Every N minutes the bot:

1. Fetches all prices from **Skinport** (public API, ~24 000 items)
2. Fetches all prices from **DMarket** (cursor pagination, ~10 000 listings)
3. Finds price gaps after fees (DMarket charges 2.5% on sale)
4. Filters out illiquid items (fewer than 5 listings on Skinport)
5. Sends top alerts to Telegram and saves everything to the database

**Real math**: buy on Skinport for $10 → sell on DMarket for $13 → after 2.5% fee receive $12.67 → net profit $2.67 (26.7%)

---

## Features

- **tkinter GUI** — runs locally, no server required
- **Telegram alerts** — instant notifications when arbitrage is found
- **Float filter** — filter by item wear value (0.00–1.00)
- **Liquidity filter** — only items with 5+ listings on Skinport
- **SQLite history** — all found opportunities are saved, top items stats
- **Watchlist** — monitor specific items regardless of profit threshold
- **CSV export** — one click exports full history to a spreadsheet
- **Countdown timer** — shows time until the next scan
- **Sound alert** — plays a sound when an opportunity is found
- **/potential command** — send `/potential` to your bot, get session profit summary
- **Auto-save settings** — all parameters saved automatically as you type

---

## Installation

```bash
git clone https://github.com/Quido0/cs2-arb-bot
cd cs2-arb-bot
pip install -r requirements.txt
```

---

## Running

```bash
# Option 1 — double click
start.bat

# Option 2 — command line (GUI)
python gui.py

# Option 3 — headless (server, settings via .env)
python main.py
```

---

## Setup

### DMarket API Key
1. Go to [dmarket.com](https://dmarket.com) → profile → **Settings → API**
2. Copy the **Public Key**
3. Paste it into the "DMarket API Key" field in the GUI

### Telegram alerts
1. Find [@BotFather](https://t.me/BotFather) on Telegram → `/newbot` → get a token
2. Send `/start` to your new bot
3. Paste the token and your Chat ID into the GUI

To find your Chat ID: message [@userinfobot](https://t.me/userinfobot)

---

## Float filter

Leave both fields empty to disable (scans all wear categories).

| Goal | Float from | Float to |
|---|---|---|
| Factory New only | 0.00 | 0.07 |
| Minimal Wear | 0.07 | 0.15 |
| Low float Field-Tested | 0.15 | 0.20 |

---

## Telegram commands

| Command | Description |
|---|---|
| `/potential` | Total potential profit for the current session |
| `/start` | List available commands |

---

## Project structure

```
cs2-arb-bot/
├── gui.py              — GUI app (main entry point)
├── main.py             — headless mode
├── arbitrage.py        — arbitrage logic + float filter
├── db.py               — SQLite history
├── notifier.py         — Telegram alerts
├── tg_commands.py      — /potential command handler
├── watchlist.py        — watchlist storage and checks
├── exporter.py         — CSV export
├── settings_manager.py — settings persistence
├── config.py           — env-variable config
├── build.py            — build to .exe
├── start.bat           — one-click launcher
├── apis/
│   ├── skinport.py     — Skinport API (public, with cache)
│   └── dmarket.py      — DMarket API (cursor pagination, retry)
└── requirements.txt
```

---

## Platform fees

| Platform | Buy fee | Sell fee |
|---|---|---|
| Skinport | 0% | 12% |
| DMarket | ~0% | 2.5% |
| Steam Market | 0% | 15% (Steam wallet only) |

**Skinport → DMarket** is the cleanest pair for real cash withdrawal. Steam Market does not allow direct cash withdrawal.

---

## Build to .exe

```bash
python build.py
# → dist/CS2ArbBot.exe
```

Single file, no Python installation required on the target machine.

---

## Realistic expectations

With **$50–100** capital and careful item selection — **$30–80/month** net. The main risk is buying an illiquid item that sits unsold for weeks. The bot filters by listing count, but the final buy decision is yours.

---

## License

MIT
