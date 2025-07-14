# 🌀 Area 2 WBGT & CAT 1 Bot

_A real-time Telegram bot to monitor Wet Bulb Globe Temperature (WBGT) and CAT 1 lightning alerts for NPCC Area 2 at Pulau Ubin._

## 📌 Overview

This passion project was built for NPCC Group Instructors (GIs) to **enhance cadet safety and instructor awareness** during outdoor field activities like ATC. It fetches real-time weather data from NEA, calculates WBGT at **Pulau Ubin**, and broadcasts heat stress advisories. It also scrapes lightning alert data (CAT 1) from the **@ArmyCAT1** Telegram channel for **Sector 17 (Ubin)**.

## ✅ Features

- 🌡️ **WBGT Estimation** at Pulau Ubin (`S106`) using real-time air temperature and relative humidity data.
- 🧠 **Dynamic Calibration** against official NEA WBGT stations: **Changi (S124)**, **Clementi (S130)**, and **Choa Chu Kang (S126)** for accurate zone estimation.
- ⚠️ **Fallback Mechanism**: Automatically uses Changi's data if Pulau Ubin readings are unavailable.
- ⚡ **CAT 1 Detection** for **Sector 17** by scraping the latest lightning forecast updates from [@ArmyCAT1](https://t.me/Lightningrisk).
- 🔄 **Instant Change Detection** (every 2 minutes):
  - Detects WBGT zone changes (🟩 Green, 🟨 Yellow, 🟥 Red, ⬛ Black)
  - Detects CAT 1 status changes, activations, or extensions
  - Sends an *🚨 Immediate Update* if either status changes
- 📢 **Scheduled Updates** (every 10 minutes): Always posts the current WBGT zone and CAT 1 status.
- 🩺 **First Aid SOPs**: Provides visual and text-based First Aid procedures for common ATC emergencies.
- 🏷️ **Medical Tagging Guide**: Shows tagging criteria and colour codes for cadets with medical conditions.
- 🚨 **Man-Down Protocol**: Shares AVPU scale and response steps if a cadet becomes unresponsive.
- 🔥 **Heat Injury Management**: Highlights symptoms and immediate actions for suspected heat exhaustion/stroke.

### 📬 Telegram Commands

| Command   | Description                                      |
|-----------|--------------------------------------------------|
| `/start`  | Subscribe to automatic updates                   |
| `/stop`   | Unsubscribe from updates                         |
| `/now`    | Get the current WBGT and CAT 1 status instantly  |
| `/firstaidsop`   | View First Aid SOP images                    |
| `/medicaltagging`| Medical tagging reference                    |
| `/mandowndrill`  | Man-down protocol & AVPU scale               |
| `/heatinjury`    | Signs & First Aid for Heat Injury            |

## 💬 Message Logic

- **Scheduled Alerts (every 10 mins)** show *both* WBGT and CAT 1 status.
- **Immediate Alerts (on change)** will:
  - Show **only WBGT** if CAT 1 remains unchanged.
  - Show **only CAT 1** if WBGT remains unchanged.
  - Show **both** if both change.
- **CAT 1 Extensions** are explicitly flagged as extended blocks.
- Messages include:
  - WBGT Zone (🟩🟨🟥⬛)
  - Work-rest cycle advice
  - Hydration recommendation
  - Sector 17 CAT 1 status
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


## 📊 WBGT Formula Breakdown

```python
wbgt = 0.7 * temperature + 0.2 * relative_humidity + avg_calibration_offset
```

- `temperature`: from NEA real-time data (`S106` Pulau Ubin)
- `relative_humidity`: from same station
- `avg_calibration_offset`: derived from:
  - Actual NEA WBGT readings at S124, S126, S130
  - Calculated offset = actual – estimated value

If Pulau Ubin’s RH or Temp is missing, fallback uses Changi for both values.

## 🔐 Safety Logic

- If both temperature and RH from Ubin are **unavailable**, fallback to Changi
- If NEA WBGT stations return invalid readings, calculation is skipped
- CAT 1 range automatically resets after expiry
- Safe send with retry on Telegram API errors

## 🤝 Acknowledgements

- **NEA Data APIs** (Air Temp, RH, WBGT) via [data.gov.sg/collections/1459](https://data.gov.sg/collections/1459/view)  
- **Lightning Risk Update** ([`@ArmyCAT1`](https://t.me/ArmyCAT1))  
- Insights from:  
  - [Harvesting Data for Lightning Alerts – Edward Yeung](https://edward-yeung.medium.com/harvesting-data-for-lightning-alerts-913f6de0e3eb)  
  - [Wet Bulb Globe Temperature (WBGT) – @weeleongenator](https://medium.com/@weeleongenator/wet-bulb-globe-temperature-wbgt-6c6b2a2585a6)


## 👨‍💻 Maintainer

Created and maintained by **Choh Kaifeng**  
To contribute or report issues, feel free to fork or raise a pull request.
