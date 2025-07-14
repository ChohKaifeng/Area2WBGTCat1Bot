import os, re, asyncio, logging, threading, requests, nest_asyncio

from datetime import datetime, timedelta, timezone as dt_timezone

from flask import Flask
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from pytz import timezone
from functools import lru_cache

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from telegram.error import TimedOut, NetworkError, RetryAfter

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from database import init_db, init_state_db, add_subscriber, remove_subscriber, get_all_subscribers, get_state, set_state

# === Configuration ===
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
WBGT_STATION_ID = "S106"  # Pulau Ubin

# === State Trackers ===
init_db()
init_state_db()
last_zone = get_state("last_zone")
last_cat1_status = get_state("last_cat1_status")
last_cat1_range = get_state("last_cat1_range")

if last_zone is None:
    last_zone = "Green"
    set_state("last_zone", last_zone)

if last_cat1_status is None:
    last_cat1_status = "clear"
    set_state("last_cat1_status", last_cat1_status)

if last_cat1_range is None:
    last_cat1_range = None
    set_state("last_cat1_range", last_cat1_range)

# === Logging ===
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# === WBGT Fetch ===
def calculate_wbgt():
    try:
        # Step 1: Fetch air temperature and RH data
        urls = {
            "air_temperature": "https://api-open.data.gov.sg/v2/real-time/api/air-temperature",
            "relative_humidity": "https://api-open.data.gov.sg/v2/real-time/api/relative-humidity"
        }

        # NEA WBGT station IDs -> Matching NEA Temp/RH station IDs
        station_map = {
            "S124": "S24",   # Changi
            "S126": "S121",  # CCK
            "S130": "S50",   # Clementi
        }
        ubin_station = "S106"        # Pulau Ubin (Temp/RH only)
        fallback_station = "S24"     # Changi

        all_needed_temp_rh_ids = list(station_map.values()) + [ubin_station, fallback_station]
        weather_data = {}

        for key, url in urls.items():
            resp = requests.get(url, timeout=10)
            data = resp.json()

            if data.get("code") != 0:
                logging.warning(f"{key} API error: {data.get('errorMsg')}")
                return None

            reading_map = {entry["stationId"]: entry["value"] for entry in data["data"]["readings"][0]["data"]}
            weather_data[key] = {sid: reading_map.get(sid) for sid in all_needed_temp_rh_ids}
            weather_data["timestamp"] = data["data"]["readings"][0]["timestamp"]

        # Step 2: Fetch NEA WBGT readings for calibration stations
        resp = requests.get("https://api-open.data.gov.sg/v2/real-time/api/weather?api=wbgt", timeout=10)
        wbgt_data = resp.json()
        readings = wbgt_data["data"]["records"][0]["item"]["readings"]

        nea_wbgt = {}
        for r in readings:
            sid = r["station"]["id"]
            if sid in station_map:
                try:
                    nea_wbgt[sid] = float(r["wbgt"])
                except (ValueError, KeyError, TypeError):
                    logging.warning(f"Invalid WBGT value for station {sid}")
        logging.info(f"Fetched NEA WBGT values: {nea_wbgt}")

        # Step 3: Calculate average calibration constant c
        c_values = []
        for wbgt_sid, tr_sid in station_map.items():
            temp = weather_data["air_temperature"].get(tr_sid)
            rh = weather_data["relative_humidity"].get(tr_sid)
            actual = nea_wbgt.get(wbgt_sid)

            logging.info(f"[DEBUG] Calibrating {wbgt_sid} -> Temp: {temp}, RH: {rh}, Actual WBGT: {actual}")

            if temp is not None and rh is not None and actual is not None:
                estimated = 0.7 * temp + 0.2 * rh
                c = actual - estimated
                c_values.append(c)
                logging.info(f"{wbgt_sid} (mapped from {tr_sid}): Temp={temp}, RH={rh}, Estimated={estimated:.2f}, Actual={actual:.2f}, c={c:.3f}")

        if not c_values:
            raise ValueError("No valid calibration data from NEA stations")

        avg_c = sum(c_values) / len(c_values)
        logging.info(f"Average Calibration Constant C: {avg_c:.3f}")

        # Step 4: Compute WBGT for Pulau Ubin (fallback to Changi if either value is missing)
        ubin_temp = weather_data["air_temperature"].get(ubin_station)
        ubin_rh = weather_data["relative_humidity"].get(ubin_station)
        changi_temp = weather_data["air_temperature"].get(fallback_station)
        changi_rh = weather_data["relative_humidity"].get(fallback_station)

        if ubin_temp is not None and ubin_rh is not None:
            temp_used = ubin_temp
            rh_used = ubin_rh
            source = "Pulau Ubin"
        elif changi_temp is not None and changi_rh is not None:
            temp_used = changi_temp
            rh_used = changi_rh
            source = "Changi (Fallback)"
            logging.warning("Pulau Ubin TEMP or RH missing – using Changi data for both")
        else:
            logging.warning("WBGT data unavailable for both Pulau Ubin and Changi.")
            return None

        wbgt = 0.7 * temp_used + 0.2 * rh_used + avg_c
        timestamp = weather_data["timestamp"]
        logging.info(f"{source}: Temp={temp_used}°C, RH={rh_used}%, WBGT≈{wbgt:.1f}, c={avg_c:.3f}")

        return {"timestamp": timestamp, "value": round(wbgt, 1)}

    except Exception as e:
        logging.error(f"Error calculating WBGT: {e}")
        return None

def get_wbgt_zone(wbgt):
    if wbgt <= 30.9:
        return "Green"
    elif 31.0 <= wbgt <= 31.9:
        return "Yellow"
    elif 32.0 <= wbgt <= 32.9:
        return "Red"
    else:
        return "Black"

def get_wbgt_advisory(wbgt):
    zone = get_wbgt_zone(wbgt)
    if "Green" in zone:
        return [
            "Code Green 🟩",
            "45min work : 15min rest",
            "Consume 0.5L/hour of water during activity"
        ]
    elif "Yellow" in zone:
        return [
            "Code Yellow 🟨",
            "30min work : 15min rest",
            "Hydrate 0.5L/hour of water! Monitor body for signs and symptoms of heat-related illness!"
        ]
    elif "Red" in zone:
        return [
            "Code Red 🟥",
            "30min work : 30min rest",
            "Take frequent breaks & Hydrate 0.75L/hour of water! Monitor body for signs and symptoms of heat-related illness!"
        ]
    else:
        return [
            "Code Black ⬛",
            "15min work : 30min rest",
            "Hydrate 0.75L/hour of water! Delay & postpone outdoor activity if possible"
        ]

# === CAT 1 Forecast ===
def fetch_cat1_sector17():
    last_cat1_range = get_state("last_cat1_range")

    try:
        resp = requests.get('https://t.me/s/Lightningrisk', timeout=10)
        soup = BeautifulSoup(resp.text, 'html.parser')
        last_msg = soup.select('.tgme_widget_message_wrap .tgme_widget_message_text')[-1]
        if not last_msg:
            logging.warning("No message found in Lightningrisk channel.")
            return "clear", "✅ Sector 17 is currently clear."

        text = last_msg.get_text().replace("\u200e", "")

        matches = re.findall(r'\((\d{4})-(\d{4})\)\s*([^\n()]+)', text)
        if not matches:
            logging.warning("CAT 1 parsing failed. Message: %s", text)
            return "clear", "✅ Sector 17 is currently clear."

        sgt = timezone("Asia/Singapore")
        sgt_now = datetime.now(sgt)

        for start, end, sector_block in matches:
            sectors = [s.strip().lstrip("0").upper() for s in sector_block.split(',')]
            logging.info(f"[DEBUG] CAT 1 Alert Block: {start}-{end}, Sectors: {sectors}")

            if '17' in sectors:
                try:
                    block_start_naive = datetime.strptime(start, "%H%M").replace(
                        year=sgt_now.year, month=sgt_now.month, day=sgt_now.day)
                    block_end_naive = datetime.strptime(end, "%H%M").replace(
                        year=sgt_now.year, month=sgt_now.month, day=sgt_now.day)

                    if block_end_naive <= block_start_naive:
                        block_end_naive += timedelta(days=1)

                    block_start = sgt.localize(block_start_naive)
                    block_end = sgt.localize(block_end_naive)

                    if block_start <= sgt_now <= block_end:
                        if last_cat1_range and block_start == last_cat1_range[0] and block_end > last_cat1_range[1]:
                            msg = (
                                f"⚠️ *CAT 1 Extended:*\n"
                                f"Sector 17 CAT 1 timing extended till {end}. "
                                f"Stay sheltered until further notice."
                            )
                        else:
                            msg = (
                                f"⚡ *CAT 1 Alert:*\n"
                                f"Sector 17 currently under CAT 1 ({start}–{end}). "
                                f"Head to the nearest shelter!"
                            )
                        set_state("last_cat1_range", (block_start, block_end))
                        set_state("last_cat1_status", "active")
                        return "active", msg

                    elif sgt_now < block_start:
                        if last_cat1_range and block_start <= last_cat1_range[1]:
                            if block_end > last_cat1_range[1]:
                                msg = (
                                    f"⚠️⚡ *CAT 1 Extended:*\n"
                                    f"Sector 17 CAT 1 duration extended till {end}. "
                                    f"Stay sheltered until further notice."
                                )
                                set_state("last_cat1_range", (block_start, block_end))
                                set_state("last_cat1_status", "active")
                                return "active", msg
                            else:
                                continue
                        else:
                            msg = (
                                f"⚠️ *CAT 1 Forecast:*\n"
                                f"Sector 17 expected to enter CAT 1 from {start}–{end}. "
                                f"Prepare to head to shelter."
                            )
                            set_state("last_cat1_range", (block_start, block_end))
                            set_state("last_cat1_status", "active")
                            return "active", msg

                except ValueError:
                    logging.warning(f"Invalid time format in block: {start}-{end}")
                    continue

        set_state("last_cat1_status", "clear")
        return "clear", "✅ Sector 17 is currently clear."

    except Exception as e:
        logging.error(f"Error fetching CAT 1: {e}")
        return "clear", "⚠️ Failed to fetch CAT 1 status."


    # Respect last forecast if still within range
    sgt_now = datetime.now(timezone("Asia/Singapore"))
    if last_cat1_range:
        if sgt_now <= last_cat1_range[1]:
            logging.info("No new forecast, but still within previous CAT 1 range — maintaining forecast status")
            return "active", f"⚠️ CAT 1 Forecast still active (until {last_cat1_range[1].strftime('%H%M')}). Remain alert."

        # Expired — reset
        logging.info("CAT 1 range expired — resetting last_cat1_range")
        last_cat1_range = None
        set_state("last_cat1_status", last_cat1_status)
    return "clear", "✅ Sector 17 is currently clear."

def generate_message(wbgt_data, cat1_status_msg):
    wbgt_time = datetime.strptime(wbgt_data["timestamp"], "%Y-%m-%dT%H:%M:%S%z").astimezone(timezone("Asia/Singapore"))
    wbgt = wbgt_data["value"]
    zone = get_wbgt_zone(wbgt)
    advisory = get_wbgt_advisory(wbgt)  # Now returns a list of 3 strings

    return (
        f"*🌤️ Pulau Ubin WBGT Update*\n"
        f"*Time:* {datetime.now(timezone('Asia/Singapore')).strftime('%d/%m/%Y %H:%M')} Hours\n\n"
        f"*WBGT STATUS (as of {wbgt_time.strftime('%H:%M')} Hours)*\n"
        f"*🌡️ Temperature:* {wbgt:.1f}°C ({advisory[0]})\n"
        f"*🧑‍🔧 Work-Rest Cycle:* {advisory[1]}\n"
        f"*💧 Advisory:* {advisory[2]}\n\n"
        f"*CAT 1 STATUS*\n"
        f"{cat1_status_msg[1]}"
    )

async def safe_send(bot, chat_id, text):
    try:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
    except (TimedOut, NetworkError, RetryAfter) as e:
        logging.warning(f"Retry sending to {chat_id} due to: {e}")
        await asyncio.sleep(5)

        try:
            await bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
        except Exception as ex:
            logging.error(f"Final failure for chat {chat_id}: {ex}")

async def broadcast_message(app, text):
    subscribers = get_all_subscribers()
    if not subscribers:
        logging.info("No subscribers to broadcast to.")
        return

    await asyncio.gather(*[
        safe_send(app.bot, chat_id, text)
        for chat_id in subscribers
    ])

# === Scheduled Tasks ===
async def scheduled_update(app):
    global last_cat1_range

    logging.info("Running scheduled update")

    loop = asyncio.get_event_loop()
    wbgt_task = loop.run_in_executor(None, calculate_wbgt)
    cat1_task = loop.run_in_executor(None, fetch_cat1_sector17)
    wbgt_data, cat1_status = await asyncio.gather(wbgt_task, cat1_task)

    if not wbgt_data:
        return

    msg = generate_message(wbgt_data, cat1_status)
    await broadcast_message(app, msg)

async def check_for_changes(app):
    global last_zone, last_cat1_status, last_cat1_range

    loop = asyncio.get_event_loop()
    wbgt_task = loop.run_in_executor(None, calculate_wbgt)
    cat1_task = loop.run_in_executor(None, fetch_cat1_sector17)
    wbgt_data, cat1_status = await asyncio.gather(wbgt_task, cat1_task)

    if not wbgt_data:
        return

    current_zone = get_wbgt_zone(wbgt_data["value"])
    current_cat1 = cat1_status[0]

    new_cat1_range = last_cat1_range
    if current_cat1 == "active":
        sgt = timezone("Asia/Singapore")
        sgt_now = datetime.now(sgt)
        forecast_match = re.search(r"from (\d{4})–(\d{4})", cat1_status[1])
        active_match = re.search(r"\((\d{4})–(\d{4})\)", cat1_status[1])
        end_match = re.search(r"till (\d{4})", cat1_status[1])

        for match in (forecast_match, active_match, end_match):
            if match:
                start_str, end_str = match.groups() if len(match.groups()) == 2 else (None, match.group(1))
                try:
                    start_dt = datetime.strptime(start_str or sgt_now.strftime("%H%M"), "%H%M").replace(
                        year=sgt_now.year, month=sgt_now.month, day=sgt_now.day)
                    end_dt = datetime.strptime(end_str, "%H%M").replace(
                        year=sgt_now.year, month=sgt_now.month, day=sgt_now.day)
                    if end_dt <= start_dt:
                        end_dt += timedelta(days=1)
                    start_dt = sgt.localize(start_dt)
                    end_dt = sgt.localize(end_dt)
                    new_cat1_range = (start_dt, end_dt)
                except Exception as e:
                    logging.warning(f"Unable to parse extended CAT 1 time: {e}")
                break

    if last_zone is None or last_cat1_status is None:
        last_zone = current_zone
        last_cat1_status = current_cat1
        last_cat1_range = new_cat1_range
        set_state("last_zone", last_zone)
        set_state("last_cat1_status", last_cat1_status)
        set_state("last_cat1_range", last_cat1_range)
        return

    zone_changed = current_zone != last_zone
    cat1_changed = (
        current_cat1 != last_cat1_status or
        (current_cat1 == "active" and last_cat1_range and new_cat1_range and new_cat1_range[1] > last_cat1_range[1])
    )

    if zone_changed or cat1_changed:
        msg_parts = ["*🚨 Immediate Update Detected*"]

        if zone_changed:
            wbgt_time = datetime.strptime(wbgt_data["timestamp"], "%Y-%m-%dT%H:%M:%S%z").astimezone(timezone("Asia/Singapore"))
            wbgt = wbgt_data["value"]
            advisory = get_wbgt_advisory(wbgt)
            msg_parts.append(
                f"*WBGT STATUS (as of {wbgt_time.strftime('%H:%M')} Hours)*\n"
                f"*🌡️ Temperature:* {wbgt:.1f}°C ({advisory[0]})\n"
                f"*🧑‍🔧 Work-Rest Cycle:* {advisory[1]}\n"
                f"*💧 Advisory:* {advisory[2]}\n"
            )

        if cat1_changed:
            msg_parts.append(f"\n*CAT 1 STATUS*\n{cat1_status[1]}")

        msg = "\n".join(msg_parts)
        await broadcast_message(app, msg)

        last_zone = current_zone
        last_cat1_status = current_cat1
        last_cat1_range = new_cat1_range
        set_state("last_zone", last_zone)
        set_state("last_cat1_status", last_cat1_status)
        set_state("last_cat1_range", last_cat1_range)

# === Telegram Commands ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    add_subscriber(chat_id)
    logging.info(f"Subscribed: {chat_id}")
    await update.message.reply_text("✅ Subscribed to Area 2 WBGT and Cat 1 alerts!")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    remove_subscriber(chat_id)
    logging.info(f"Unsubscribed: {chat_id}")
    await update.message.reply_text("🚫 Unsubscribed from alerts.")

async def now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    loop = asyncio.get_event_loop()
    wbgt_task = loop.run_in_executor(None, calculate_wbgt)
    cat1_task = loop.run_in_executor(None, fetch_cat1_sector17)
    wbgt_data, cat1 = await asyncio.gather(wbgt_task, cat1_task)

    if not wbgt_data:
        await update.message.reply_text("⚠️ Could not retrieve WBGT data.")
        return

    msg = generate_message(wbgt_data, cat1)
    await update.message.reply_text(msg, parse_mode="Markdown")

async def first_aid_sop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    image_caption_pairs = [
        (
            os.path.join("img", "UnwellCadetSOPDay.jpg"),
            "🌞 *Unwell Cadet SOP (Day)*\nEnsure cadets rest in the designated First Aid area and are closely monitored during daylight activities."
        ),
        (
            os.path.join("img", "UnwellCadetSOPNight.jpg"),
            "🌙 *Unwell Cadet SOP (Night)*\nCadets should be escorted to a safe, lit area and remain supervised overnight if symptoms persist."
        ),
        (
            os.path.join("img", "UnwellCadetSOPLandEx.jpg"),
            "🧭 *Unwell Cadet SOP (Land Ex)*\nDuring Land Exploration, follow safety protocols immediately and evacuate if symptoms are severe."
        ),
        (
            os.path.join("img", "FARoomCriteria.jpg"),
            "🏥 *First Aid Room Criteria*\nCheck that all requirements for a designated First Aid Room are met and maintained throughout the camp."
        ),
    ]

    for img_path, caption in image_caption_pairs:
        if not os.path.exists(img_path):
            await update.message.reply_text(f"⚠️ Missing image: {os.path.basename(img_path)}")
            continue

        with open(img_path, "rb") as photo:
            await update.message.reply_photo(photo=photo, caption=caption, parse_mode="Markdown")

async def medical_tagging(update: Update, context: ContextTypes.DEFAULT_TYPE):
    img_path = os.path.join("img", "MedicalTagging.jpg")

    if not os.path.exists(img_path):
        await update.message.reply_text("⚠️ Medical Tagging image not found.")
        return

    caption = (
        "*🏷️ Medical Tagging Reference Guide*\n\n"
        "*Colour* | *Medical Condition*\n"
        "🟡 Yellow - Asthma / Respiratory Condition\n"
        "🔴 Red - History of Current Heat Injury\n"
        "🔵 Blue - Allergy\n"
        "⚪ White - Light Duty (No Vigorous Activity)"
    )

    with open(img_path, "rb") as photo:
        await update.message.reply_photo(photo, caption=caption, parse_mode="Markdown")

async def mandown_drill(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caption = (
        "*🚨 Cadets Man-Down Protocol*\n\n"
        "*AVPU Scale:*\n"
        "• *Alert* - Cadet is *not alert* at all\n"
        "• *Verbal* - Cadet is *not able to respond* to questions at all (Time, Place, Person)\n"
        "• *Pain* - Cadet is *not able to respond* to any pain stimuli (e.g., pat on arm)\n"
        "• *Unresponsive* - Cadet is *not responsive* at all\n\n"
        "*🔴 REPORT IMMEDIATELY IF CADETS FAIL ANY OF THE SCALE*"
    )

    await update.message.reply_text(caption, parse_mode="Markdown")

async def heat_injury(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caption = (
        "*🔥 Heat Injury Protocol*\n\n"
        "*Common Signs & Symptoms:*\n"
        "• *Extreme fatigue* - Unable to continue physical activity\n"
        "• *Hot and flushing* (redness) of skin\n"
        "• Severe muscle *cramps*\n"
        "• *Nausea*, vomiting, *headache*, *giddiness*, and/or *fainting spells*\n"
        "• Change in *mental status* - Confusion, disorientation, agitation, seizures, unconscious or comatose\n\n"
        "*First Aid Measures:*\n"
        "1. *Resuscitate* - Perform CPR if no breathing or heartbeat\n"
        "2. *Recognize Symptoms* - Early detection prevents escalation\n"
        "3. *Rest in the Shade* - Remove casualty from activity\n"
        "4. *Reduce Body Temp* - Pour water, fan casualty, apply ice packs (if available)\n"
        "5. *Rehydrate* - If conscious, give fluids. If not, start IV fluids\n"
        "6. *Rush to Medical Facility* if:\n"
        "   • Life/limb-threatening condition\n"
        "   • V, P, or U on *AVPU* scale\n"
        "   • Suspected heat-related injury\n"
        "   • Temp ≥ *38°C* during training"
    )

    await update.message.reply_text(caption, parse_mode="Markdown")

# === Scheduler Setup ===
scheduler = AsyncIOScheduler()
async def post_init(app):
    scheduler.add_job(scheduled_update, args=[app], trigger="cron", minute="*/10")
    scheduler.add_job(check_for_changes, args=[app], trigger="interval", seconds=150)
    scheduler.start()
    logging.info("Scheduler started")

# === Bot Entry ===
def telegram_main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("now", now))
    app.add_handler(CommandHandler("firstaidsop", first_aid_sop))
    app.add_handler(CommandHandler("medicaltagging", medical_tagging))
    app.add_handler(CommandHandler("mandowndrill", mandown_drill))
    app.add_handler(CommandHandler("heatinjury", heat_injury))

    app.run_polling()

# === Flask (for Render uptime) ===
flask_app = Flask(__name__)
@flask_app.route('/')
def index(): return "Bot is alive"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host='0.0.0.0', port=port)

# === Final Startup ===
if __name__ == "__main__":
    nest_asyncio.apply()

    # Start Flask in background
    threading.Thread(target=run_flask, daemon=True).start()

    if os.environ.get("IS_MAIN_PROCESS") == "1":
        # Start Telegram bot and scheduler
        print("The main instance is running")
        telegram_main()
    else:
        print("Skipping polling: Not the main instance")
