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
    # Только для личных чатов
    if update.effective_chat.type != ChatType.PRIVATE:
        return

    # Только для админов
    user_id = update.effective_user.id if update.effective_user else None
    if not user_id or user_id not in ADMINS:
        return  # тихо игнорируем

    # Ответ только админу
    sched = context.bot_data.get("scheduler_info", {})
    msg = "✅ Бот живой.\n"
    if sched:
        next_runs = sched.get("next_runs", [])
        if next_runs:
            msg += "Следующие запланированные отправки:\n"
            for nr in next_runs:
                msg += f" - {nr}\n"

    # Проверяем сегодняшние значения n
    try:
        ws = open_sheet()
        items = find_todays_items(ws)
        if items:
            msg += "\nСегодняшние значения n:\n"
            msg += "\n".join(f"- {x}" for x in items)

            # --- Предпросмотр сообщений ---
            morning_text = (
                "☀️ Всем доброго дня!) Записываемся на занятия:\n"
                "https://docs.google.com/spreadsheets/d/1Z39dIQrgdhSoWdD5AE9jIMtfn1ahTxl-femjqxyER0Q/edit#gid=1614712337"
            )
            evening_text = f"Подводим итоги — по {', '.join(items)} р. Приносите наличными до конца недели."

            msg += "\n\n📋 Предпросмотр сообщений на сегодня:\n"
            msg += f"Утро (11:00):\n{morning_text}\n\n"
            msg += f"Вечер (18:00):\n{evening_text}"
        else:
            msg += "\nСегодня занятий нет."
    except Exception as e:
        msg += f"\n⚠️ Ошибка при проверке таблицы: {e}"

    await update.message.reply_text(msg)

async def send_group_notification(app, mode="morning", dry=False):
    if not GROUP_CHAT_ID:
        logger.warning("GROUP_CHAT_ID not set; skipping notification")
        return
    try:
        ws = open_sheet()
        items = find_todays_items(ws)
        if not items:
            logger.info("No items for today; nothing to send.")
            return

        if mode == "morning":
            text = (
                "☀️ Всем доброго дня!) Записываемся на занятия:\n"
                "https://docs.google.com/spreadsheets/d/1Z39dIQrgdhSoWdD5AE9jIMtfn1ahTxl-femjqxyER0Q/edit#gid=1614712337"
            )
        elif mode == "evening":
            text = f"Подводим итоги — по {', '.join(items)} р. Приносите наличными до конца недели."
        else:
            return

        if dry:
            logger.info("Dry run message:\n%s", text)
            return
        await app.bot.send_message(chat_id=GROUP_CHAT_ID, text=text)
        logger.info("Sent notification (%s) to %s", mode, GROUP_CHAT_ID)
    except Exception as e:
        logger.exception("Failed to send notification: %s", e)

# --- Scheduler jobs ---
def schedule_jobs(scheduler: AsyncIOScheduler, app):
    tz = TZ

    scheduler.add_job(send_group_notification, "cron", hour=11, minute=0, timezone=tz, args=[app, "morning"], id="notify_11")
    scheduler.add_job(send_group_notification, "cron", hour=18, minute=0, timezone=tz, args=[app, "evening"], id="notify_18")

    def restart_now():
        logger.info("Restart at midnight triggered.")
        os._exit(0)

    scheduler.add_job(restart_now, "cron", hour=0, minute=0, timezone=tz, id="restart_midnight")

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
