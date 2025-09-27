#!/usr/bin/env python3
import os
import asyncio
import logging
from datetime import datetime, date
import pytz
import json
from typing import List

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from telegram import Update
from telegram.constants import ChatType
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

import gspread
from google.oauth2.service_account import Credentials

# --- Config ---
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMINS = [int(x) for x in os.getenv("ADMINS", "").split(",") if x.strip()]
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID", "0")) if os.getenv("GROUP_CHAT_ID") else None
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
GOOGLE_CREDENTIALS = os.getenv("GOOGLE_CREDENTIALS")
TZ = pytz.timezone(os.getenv("TZ", "Europe/Moscow"))

# Время уведомлений из ENV
MORNING_HOUR = int(os.getenv("MORNING_HOUR", "11"))
MORNING_MINUTE = int(os.getenv("MORNING_MINUTE", "0"))
EVENING_HOUR = int(os.getenv("EVENING_HOUR", "18"))
EVENING_MINUTE = int(os.getenv("EVENING_MINUTE", "0"))

if not BOT_TOKEN:
    raise SystemExit("TELEGRAM_BOT_TOKEN is not set in environment")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- Google Sheets helper ---
def open_sheet():
    creds_info = json.loads(GOOGLE_CREDENTIALS)
    creds = Credentials.from_service_account_info(
        creds_info, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
    )
    gc = gspread.Client(auth=creds)
    gc.session = gc.auth.authorize(creds)

    if SPREADSHEET_ID and "https" not in SPREADSHEET_ID:
        sh = gc.open_by_key(SPREADSHEET_ID)
    else:
        sh = gc.open_by_url(SPREADSHEET_ID)

    ws = sh.sheet1
    return ws

def parse_date_from_cell(value: str):
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except Exception:
            continue
    try:
        return datetime.fromisoformat(value.strip()).date()
    except Exception:
        return None

def find_todays_items(ws) -> List[str]:
    today = datetime.now(TZ).date()
    records = ws.get_all_records()
    results = []
    for row in records:
        keys = {k.strip().lower(): k for k in row.keys()}
        d_key = keys.get("d")
        n_key = keys.get("n")
        if not d_key or not n_key:
            continue
        d_val = row.get(d_key)
        n_val = row.get(n_key)
        parsed = None
        if isinstance(d_val, str):
            parsed = parse_date_from_cell(d_val)
        elif isinstance(d_val, (int, float)):
            try:
                parsed = date.fromordinal(date(1900, 1, 1).toordinal() + int(d_val) - 2)
            except Exception:
                parsed = None
        if parsed == today and n_val:
            results.append(str(n_val))
    return results

# --- Bot handlers ---
async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != ChatType.PRIVATE:
        return
    user_id = update.effective_user.id if update.effective_user else None
    if not user_id or user_id not in ADMINS:
        return  # тихо игнорируем
    sched = context.bot_data.get("scheduler_info", {})
    msg = "✅ Бот живой.\n"
    if sched:
        next_runs = sched.get("next_runs", [])
        if next_runs:
            msg += "Следующие запланированные отправки:\n"
            for nr in next_runs:
                msg += f" - {nr}\n"
    await update.message.reply_text(msg)

async def send_morning_message(app, dry=False):
    if not GROUP_CHAT_ID:
        return
    try:
        ws = open_sheet()
        items = find_todays_items(ws)
        if not items:
            return
        text = "☀️ Всем доброго дня!) Записываемся на занятия:\n" + SPREADSHEET_ID
        if dry:
            logger.info("Dry run morning message:\n%s", text)
            return
        await app.bot.send_message(chat_id=GROUP_CHAT_ID, text=text)
    except Exception as e:
        logger.exception("Failed to send morning message: %s", e)

async def send_evening_message(app, dry=False):
    if not GROUP_CHAT_ID:
        return
    try:
        ws = open_sheet()
        items = find_todays_items(ws)
        if not items:
            return
        text = "🌙 Подводим итоги — по " + ", ".join(items) + "р. Приносите наличными до конца недели."
        if dry:
            logger.info("Dry run evening message:\n%s", text)
            return
        await app.bot.send_message(chat_id=GROUP_CHAT_ID, text=text)
    except Exception as e:
        logger.exception("Failed to send evening message: %s", e)

# --- Scheduler jobs ---
def schedule_jobs(scheduler: AsyncIOScheduler, app):
    tz = TZ
    scheduler.add_job(send_morning_message, "cron", hour=MORNING_HOUR, minute=MORNING_MINUTE, timezone=tz, args=[app], id="notify_11")
    scheduler.add_job(send_evening_message, "cron", hour=EVENING_HOUR, minute=EVENING_MINUTE, timezone=tz, args=[app], id="notify_18")

    def restart_now():
        logger.info("Restart at midnight triggered.")
        os._exit(0)

    scheduler.add_job(restart_now, "cron", hour=0, minute=0, timezone=tz, id="restart_midnight")

# --- Refresh jobs from ENV ---
async def refresh_jobs(scheduler, app):
    global MORNING_HOUR, MORNING_MINUTE, EVENING_HOUR, EVENING_MINUTE

    while True:
        await asyncio.sleep(300)  # проверка каждые 5 минут
        new_mh = int(os.getenv("MORNING_HOUR", MORNING_HOUR))
        new_mm = int(os.getenv("MORNING_MINUTE", MORNING_MINUTE))
        new_eh = int(os.getenv("EVENING_HOUR", EVENING_HOUR))
        new_em = int(os.getenv("EVENING_MINUTE", EVENING_MINUTE))

        if (new_mh, new_mm, new_eh, new_em) != (MORNING_HOUR, MORNING_MINUTE, EVENING_HOUR, EVENING_MINUTE):
            logger.info(f"⏰ Изменено время уведомлений: {new_mh}:{new_mm} и {new_eh}:{new_em}")

            MORNING_HOUR, MORNING_MINUTE, EVENING_HOUR, EVENING_MINUTE = new_mh, new_mm, new_eh, new_em

            try:
                scheduler.remove_job("notify_11")
                scheduler.remove_job("notify_18")
            except Exception:
                pass

            schedule_jobs(scheduler, app)

# --- App startup ---
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.bot_data["scheduler_info"] = {"next_runs": []}
    app.add_handler(CommandHandler("ping", ping_command))

    scheduler = AsyncIOScheduler()
    schedule_jobs(scheduler, app)
    scheduler.start()

    next_runs = []
    for job in scheduler.get_jobs():
        if job.next_run_time:
            next_runs.append(job.next_run_time.astimezone(TZ).strftime("%Y-%m-%d %H:%M %Z"))
    app.bot_data["scheduler_info"]["next_runs"] = next_runs

    asyncio.create_task(refresh_jobs(scheduler, app))

    logger.info("Starting bot polling...")
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    try:
        await asyncio.Event().wait()
    finally:
        logger.info("Shutting down...")
        await app.updater.stop_polling()
        await app.stop()
        await app.shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
