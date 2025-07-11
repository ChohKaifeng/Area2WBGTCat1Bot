# 🌀 Area 2 WBGT & CAT 1 Bot

_A Telegram bot to monitor Wet Bulb Globe Temperature (WBGT) and CAT 1 lightning alerts for NPCC Area 2's Adventure Training Camp (ATC)._

## 📌 Overview

This passion project was built for NPCC Group Instructors (GIs) to **enhance cadet safety and instructor awareness** during outdoor field activities like ATC. It fetches real-time weather data from NEA, estimates WBGT at **Pulau Ubin**, and broadcasts heat stress advisories. It also scrapes lightning alert data (CAT 1) from the **@ArmyCAT1** Telegram channel for **Sector 17 (Ubin)**.

## ✅ Features

- 🌡️ **WBGT Estimation** at Pulau Ubin (`S106`) using live air temperature and RH data.
- 🧠 **Dynamic Calibration** against official NEA WBGT stations: Changi, Clementi, and Choa Chu Kang.
- ⚠️ **Fallback Mechanism**: If Ubin's data is unavailable, the bot uses Changi’s temp & RH.
- ⚡ **CAT 1 Detection** for Sector 17 by scraping the latest lightning forecast blocks.
- 🔄 **Instant Change Detection** every 2 minutes:
  - Detects changes in WBGT zone (Green/Yellow/Red/Black).
  - Detects CAT 1 status changes or extensions.
  - Sends an *Immediate Alert* message if either changes.
- 📢 **Scheduled Updates** every 10 minutes with current WBGT and CAT 1 status.
- 📬 **Command Interface**:
  - `/start` – Subscribe to automatic updates
  - `/stop` – Unsubscribe from updates
  - `/now` – Fetch the latest WBGT and CAT 1 status on demand

## 💬 Message Logic

- **Scheduled Alerts (every 10 mins)** show *both* WBGT and CAT 1 status.
- **Immediate Alerts (on change)** will:
  - Show **only WBGT** if CAT 1 remains unchanged.
  - Show **only CAT 1** if WBGT remains unchanged.
  - Show **both** if both change.
- **CAT 1 Extensions** are explicitly flagged as extended blocks.
- **Initial startup** does not trigger broadcasts to avoid false alerts.

## 🖥️ Deployment Stack

- Python 3.10+
- [`python-telegram-bot`](https://github.com/python-telegram-bot/python-telegram-bot) v20+
- `Flask` for uptime ping (Render hosting)
- `APScheduler` for timed job execution
- `SQLite` for persistent subscription database
- `requests` & `BeautifulSoup` for API & Telegram scraping
- Deployed on Render (free tier) with `gunicorn`

## ⚙️ Key Files

| File              | Description                                         |
|-------------------|-----------------------------------------------------|
| `Area2WBGTCat1Bot.py` | Main bot logic (WBGT + CAT 1 alerts + scheduler)  |
| `database.py`         | SQLite-based Telegram chat ID subscriber storage |

## 🧠 WBGT Formula

```python
wbgt = 0.7 * temperature + 0.2 * relative_humidity + dynamic_c
```

Where `dynamic_c` is *dynamically* calibrated using **Changi** (`S124`), **Clementi** (`S130`), and **Choa Chu Kang** (`S126`) [NEA WBGT](https://data.gov.sg/collections/1459/view) data.

If Pulau Ubin’s RH or Temp is missing, fallback uses Changi for both values.

## 🤝 Acknowledgements

- **NEA Data APIs** (Air Temp, RH, WBGT) via [data.gov.sg/collections/1459](https://data.gov.sg/collections/1459/view)  
- **Lightning Risk Update** ([`@ArmyCAT1`](https://t.me/ArmyCAT1))  
- Insights from:  
  - [Harvesting Data for Lightning Alerts – Edward Yeung](https://edward-yeung.medium.com/harvesting-data-for-lightning-alerts-913f6de0e3eb)  
  - [Wet Bulb Globe Temperature (WBGT) – @weeleongenator](https://medium.com/@weeleongenator/wet-bulb-globe-temperature-wbgt-6c6b2a2585a6)
